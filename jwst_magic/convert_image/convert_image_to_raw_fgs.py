"""Convert NIRCam or FGS images to raw FGS frame.

This tool takes input NIRCam or FGS images, re-bins to FGS plate scale
if necessary, applies the DQ array if necessary, rotates the image
according to the SIAF coordinate transformations, and re-normalizes to
the desired FGS countrate/magnitude. The development of this code used
mock-up NIRCam files from Ball Aerospace's ITM tool, simulating Global
Alignment using the short wavelength channel.

Authors
-------
    - Keira Brooks
    - Lauren Chambers
    - Shannon Osborne


Use
---
    This module can be executed in a Python shell as such:
    ::
        from jwst_magic.convert_image import convert_image_to_raw_fgs
        convert_image_to_raw_fgs.convert_im(input_im, guider, root):

    Required arguments:
        ``input_image`` - filepath for the input (NIRCam or FGS) image
        ``guider`` - number for guider 1 or guider 2
        ``root`` - will be used to create the output directory, ./out/{root}
    Optional arguments:
        ``nircam`` - denotes if the input_image is an FGS or NIRCam
            image. If True, the image will be converted to FGS format.
        ``nircam_det`` - used to specify the detector of a provided
            NIRCam image. If left blank, the detector will be extracted
            from the header of the NIRCam FITS file.
        ``normalize`` - denotes if the image will be normalized.
        ``norm_value`` and ``norm_unit`` - If the image will be
            normalized, specifies the value to normalize to and the
            units of that value (either FGS Magnitude or FGS countrate).
        ``out_dir`` - where output files will be saved. If not provided,
            the image(s) will be saved within the repository at
            jwst_magic/
        ``coarse_pointing`` - denotes if the image will have a Gaussian
            filter applied to simulate the effects of jitter when the
            observatory is in coarse pointing rather than fine guide.
        ``jitter_rate_arcsec`` - the rate of the spacecraft jitter, in
            arcseconds, that will be used to apply the Gaussian filter
            if coarse_pointing is True.
        ``logger_passed`` - denotes if a logger object has already been
            generated.

References
----------
    See JWST-STScI-001550 (Rev A), "Description and Use of the JWST
    Science Instrument Aperture File," on SOCCER for definition of
    coordinate transformations between NIRCam and FGS frames, and
    between DMS/Science frames and raw frames.

Notes
-----
    NIRCam short wave field-of-view: 1.09' x 1.09'
    NIRCam short wave pixel scale: 0.032"/pixel

    FGS field-of-view: 2.4' x 2.4'
    FGS pixel scale: 0.070"/pixel
"""

# Standard Library Imports
import copy
import datetime
import itertools
import logging
import os
import yaml

# Third Party Imports
from astropy.io import ascii as asc
from astropy.io import fits
from astropy.nddata import Cutout2D
from astropy.stats import sigma_clip
from jwst.resample import ResampleStep
from jwst.datamodels import ImageModel
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import numpy as np
import pysiaf
from scipy import signal
from scipy import ndimage
from scipy.ndimage import gaussian_filter
from scipy.signal import medfilt2d

# Local Imports
from jwst_magic.convert_image import renormalize
from jwst_magic.utils import utils, coordinate_transforms

# Paths
__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
PACKAGE_PATH = os.path.split(__location__)[0]
OUT_PATH = os.path.split(PACKAGE_PATH)[0]  # Location of out/ and logs/ directory
DATA_PATH = os.path.join(PACKAGE_PATH, 'data')
BAD_PIXEL_MAP_YAML = os.path.join(PACKAGE_PATH, 'data', 'bad_pixel_mask.yaml')

# Constants
NIRCAM_SW_SCALE = 0.0311  # NIRCam SW pixel scale (arcsec/pixel)
NIRCAM_LW_SCALE = 0.063  # NIRCam LW pixel scale (arcsec/pixel)
FGS1_SCALE = 0.06929  # FGS 1 pixel scale (arcsec/pixel)
FGS2_SCALE = 0.06891  # FGS 2 pixel scale (arcsec/pixel)
FGS_PIXELS = 2048  # FGS image size in pixels
FGS1_PLATE_SIZE = FGS1_SCALE * FGS_PIXELS / 60  # FGS 1 image size in arcminutes
FGS2_PLATE_SIZE = FGS2_SCALE * FGS_PIXELS / 60  # FGS 2 image size in arcminutes

# Start logger
LOGGER = logging.getLogger(__name__)

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# SUPPORTING FUNCTIONS
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


def apply_coarse_pointing_filter(data, jitter_rate_arcsec, pixel_scale):
    """Apply a Gaussian filter to simulate coarse pointing

    Parameters
    ----------
    data : 2-D numpy array
        Image data
    jitter_rate_arcsec : float
        The rate of jitter of the telescope (arcsec/sec)
    pixel_scale : float
        The pixel scale of the detector (arcsec/pixel)

    Returns
    -------
    data_gauss : 2-D numpy array
        Image data with coarse pointing filter applied
    """
    t_fullframe_read = 10.7  # sec
    jitter_rate = jitter_rate_arcsec / pixel_scale  # pixel/sec
    sigma = jitter_rate * t_fullframe_read / 3  # pixel

    data_gauss = gaussian_filter(data, sigma)

    return data_gauss


def bad_pixel_correction(data, nircam, detector, dq_array=None):
    """Finds bad pixels using bad pixel map, and replace them
    with the median of the surrounding pixels

    Parameters
    ----------
    data : 2-D numpy array
        Image data
    nircam : bool
        True if image is from NIRCam, False if from FGS
    detector : str
        Name of detector
    dq_array : 2-D numpy array, optional
        The DQ extension from the input image, convert to 1s and 0s

    Returns
    -------
    data : 2-D numpy array
        Image data with pixel correction applied
    """
    # Pull bad pixel map
    if dq_array is not None:
        bad_pix_data = dq_array
    else:
        with open(BAD_PIXEL_MAP_YAML) as f:
            bad_pixel_map_yaml = yaml.safe_load(f.read())

        instr = 'NIRCAM' if nircam else 'FGS'
        bad_pixel_mask_file = os.path.join(DATA_PATH, bad_pixel_map_yaml[instr.upper()][detector.upper()])
        with fits.open(bad_pixel_mask_file) as bad_pix_hdu:
            bad_pix_data = bad_pix_hdu[0].data

    # Now, use data
    m, n = data.shape
    new_data = copy.deepcopy(data)
    for i, j in itertools.product(range(m), range(n)):
        # If the bad pixel is flagged, need to replace it
        if bad_pix_data[i, j] == 1:
            # For each surrounding pixel
            vals = []
            for k, h in itertools.product([i + 1, i, i - 1], [j + 1, j, j - 1]):
                # Does the surrounding pixel exist on the array - if not, ignore it
                if k < 0 or k >= m:
                    pass
                elif h < 0 or h >= n:
                    pass
                # Is the surrounding pixel also bad - ignore it
                elif bad_pix_data[k, h] == 1:
                    pass
                # If it passes those tests, include it
                else:
                    vals.append(new_data[k, h])

            if len(vals) == 0:
                # If pix is surrounded by all bad pixels, set it's value to 0
                new_data[i, j] = 0
            else:
                # Take the median value
                new_data[i, j] = np.median(vals)

    return new_data


def transform_nircam_image(image, to_fgs_detector, from_nircam_detector, header,
                           nircam_coord_frame='sci'):
    """Given NIRCam image and detector, rotate and flip to put in
    correct orientation for FGS 1 or 2.

    Parameters
    ----------
    image : 2-D numpy array
        NIRCam image to be rotated into correct FGS frame
    to_fgs_detector : int
        Guider 1 or 2
    header : astropy.io.fits.Header object
        The header of the input NIRCam image
    from_nircam_detector : str
        The NIRCam detector with which the image was taken.
        Expects: A1, A2, A3, A4, A5, B1, B2, B3, B4, or B5
    nircam_coord_frame : str, optional
        The coordinate frame that the input image is in.
        Expects: 'sci' for the science/DMS frame, or 'raw' or 'det' for
        the raw detector frame

    Returns
    --------
    nircam_scale : float
        Detector pixel scale depending on if the input image is from a
        long- or shortwave detector
    image : 2-D numpy array
        The transformed NIRCam image
    """
    # If the NIRCam detector isn't specified, get it from the header
    if from_nircam_detector in [None, "-Parse from Header-"]:
        # The Detector keyword returns 'NRCA*' or 'NRCB*', so to simplify matters
        # just pull out the 4th & 5th character in the string
        from_nircam_detector = header['DETECTOR'][3:].strip()
    LOGGER.info("Image Conversion: Transforming from NIRCAM Detector = {}".format(from_nircam_detector))

    # Determine whether the NIRCam image is short- or long-wave to determine
    # the pixel scale
    nircam_scale = NIRCAM_LW_SCALE if '5' in from_nircam_detector else NIRCAM_SW_SCALE

    # Perform the transformation
    if nircam_coord_frame == 'sci':
        LOGGER.info("Image Conversion: Input NIRCam image in SCI coordinate frame.")
        image = coordinate_transforms.transform_sci_to_fgs_raw(image, to_fgs_detector)

    elif nircam_coord_frame == 'raw' or nircam_coord_frame == 'det':
        LOGGER.info("Image Conversion: Input NIRCam image in RAW/DET coordinate frame.")
        image = coordinate_transforms.transform_nircam_raw_to_fgs_raw(image, from_nircam_detector, to_fgs_detector)

    else:
        raise ValueError('Unrecognized coordinate frame name.')

    return nircam_scale, image


def pad_data(data, padding, fgs_pix):
    """Pad re-binned NIRCam data with mean of data; effectively placing
    NIRCam data onto an appropriately-sized FGS array with the
    appropriate pixel scale.

    Parameters
    ----------
    data : 2-D numpy array
        Image data
    padding : int
        Width of padded area around data
    fgs_pix : int
        Number of pixels along one side of an FGS image (probably 2048)

    Returns
    -------
    padded_data
        Image data padded to match FGS pixel scale

    Raises
    ------
    ValueError
        If the output FGS image is not going to be 2048x2048 (i.e. if
        the padding width does not match the size of the input image
        data)
    """
    # Determine the size of the data array
    size = np.shape(data)[0]

    # Create an array of size (binned data + 2*padding), filled with the mean data value
    padded_size = size + 2 * padding
    if padded_size != fgs_pix - 8:
        # If just a +1 error from odd size of image
        if padded_size == 2039:
            padded_size = 2040
        # If something else is going on....
        else:
            raise ValueError('Padded image not of proper size (should be 2040): {}'.format(padded_size))
    padded_data = np.zeros((padded_size, padded_size))

    # Replace center of array with real data
    padded_data[padding:padding + size, padding:padding + size] = data

    # Correct any negative pixels
    padded_data = utils.correct_image(padded_data)

    return padded_data


def resize_nircam_image(data, nircam_scale, fgs_pix, guider):
    """Resize a NIRCam image to the expected FGS size and pixel scale

    Parameters
    ----------
    data : 2-D numpy array
        Image data
    nircam_scale : float
        Pixel scale of NIRCam detector
    fgs_pix : int
        Number of pixels along one side of an FGS image (probably 2048)
    guider : int
        Guider number, 1 or 2

    Returns
    -------
    fgs_data
        Re-binned and padded image data
    """
    fgs_plate_size = globals()['FGS{}_PLATE_SIZE'.format(guider)]
    cropped = data[4:-4, 4:-4]  # crop 4pixel zero-padding
    binned_pix = int(round((data.shape[0] * nircam_scale * fgs_pix) / (fgs_plate_size * 60)))
    data_resized = utils.resize_array(cropped, binned_pix, binned_pix)

    padding = int((cropped.shape[0] - binned_pix) / 2)
    data_pad = pad_data(data_resized, padding, fgs_pix)
    fgs_data = np.pad(data_pad, 4, 'constant')  # Add back reference pixels

    return fgs_data


def normalize_data(data, fgs_countrate):
    """Re-normalize data to the desired FGS countrate without
    masking out any of the background. See JWSTFGS-160 for the
    reasoning behind this.

    Parameters
    ----------
    data : 2-D numpy array
        Image data
    fgs_countrate : float
        The FGS countrate value to normalize to

    Returns
    -------
    data_norm
        Normalized image data

    """

    data_norm = np.copy(data.astype(np.float64))
    data_norm *= (fgs_countrate / data_norm.sum())

    return data_norm


def remove_pedestal(data, nircam, itm):
    """Subtract the vertical (for NIRCam) or horizontal (for FGS)
     pedestals/amps from a raw frame. The pedestal is calculated
     as the median of the amps if the image is ITM and the median
     of the reference pixels if it is not.

    Parameters
    ----------
    data : 2-D numpy array
        Image data
    nircam : bool
        True if the data is NIRCam SCI frame data. False if
        the data is FGS SCI frame data.
    itm : bool
        True if the data is an ITM image (which won't have
        accurate reference pixels)

    Returns
    -------
    noped_data : 2-D numpy array
        Image data with pedestals subtracted
    """
    size = np.shape(data)[0]
    ped_size = size // 4
    pedestals = []

    if itm is True:  # Use the median of the amps and subtract it from the whole amp
        noped_data = np.zeros(np.shape(data))
        for i in range(4):
            ped_start = i * ped_size
            ped_stop = (i + 1) * ped_size

            # Subtract median from each pedestal strip
            if nircam:
                ped_strip = data[:, ped_start:ped_stop]
                pedestal = np.median(ped_strip)
                pedestals.append(pedestal)
                noped_data[:, ped_start:ped_stop] = data[:, ped_start:ped_stop] - pedestal
            else:
                ped_strip = data[ped_start:ped_stop, :]
                pedestal = np.median(ped_strip)
                pedestals.append(pedestal)
                noped_data[ped_start:ped_stop, :] = data[ped_start:ped_stop, :] - pedestal

    # For CV3/Other hardware data (that includes reference pixels)
    else:  # Use the median of the refpix and subtract it only from the non-refpix on the amp
        noped_data = copy.deepcopy(data)  # retain the refpix - will overwrite everything else
        for i in range(4):
            ped_start = i * ped_size
            ped_stop = (i + 1) * ped_size

            # Get pedestal start/stop points excluding the reference pixels
            if i == 0:
                start = ped_start + 4  # for left rows of refpix
                stop = ped_stop
            elif i == 3:
                start = ped_start
                stop = ped_stop - 4  # for right rows of refpix
            else:
                start = ped_start
                stop = ped_stop

            # Pull each pedestral strip (FGS vs NIRCam pedestal runs different ways)
            # Subtract median of 4px refpix from each pedestal strip (not including the reference pixels)
            if nircam:
                pedestal = np.median([data[0:4, start:stop], data[-4:, start:stop]])
                pedestals.append(pedestal)
                noped_data[4:-4, start:stop] = data[4:-4, start:stop] - pedestal
            else:
                pedestal = np.median([data[start:stop, 0:4], data[start:stop, -4:]])
                pedestals.append(pedestal)
                noped_data[start:stop, 4:-4] = data[start:stop, 4:-4] - pedestal

    LOGGER.info("Image Conversion: " +
                "Removed pedestal values from image: {} ".
                format(', '.join(['{:.2f}'.format(p) for p in pedestals])))

    return noped_data


def choose_threshold(smoothed_data, gauss_sigma):
    """Prompt the user to choose which method to use to select the
    threshold

    Parameters
    ----------
    smoothed_data : 2-D numpy array
        Image data that has been smoothed with a Gaussian filter
    gauss_sigma : float
        The sigma of the Gaussian smoothing filter

    Returns
    -------
    num_psfs : int
        The number of PSFs found in the smoothed data
    coords : list
        List of tuples of x and y coordinates of all identified PSFs
    threshold : float
        The threshold used with photutils.find_peaks

    Raises
    ------
    ValueError
        User did not accept either of the threshold options.
    """
    # Perform statistics
    mean = np.mean(smoothed_data)
    std = np.std(smoothed_data)

    # Run find_peaks with two different threshold options
    thresholds = [3 * std, mean]

    sources_std = utils.find_peaks(smoothed_data, box_size=gauss_sigma, threshold=thresholds[0])
    sources_mean = utils.find_peaks(smoothed_data, box_size=gauss_sigma, threshold=thresholds[1])

    # Show plots of each for user to choose between
    plt.ion()
    smoothed_data[smoothed_data == 0] = 0.1  # Allow LogNorm plotting
    fig, [ax1, ax2] = plt.subplots(1, 2, figsize=(16, 8))
    fig.subplots_adjust(top=.95, left=.05, bottom=.05)

    ax1.imshow(smoothed_data, cmap='bone', interpolation='nearest',
               clim=(0.1, 100), norm=LogNorm())
    ax1.scatter(sources_std['x_peak'], sources_std['y_peak'], c='r', marker='+')
    ax1.set_title('Threshold = 3 sigma ({} sources found)'.format(len(sources_std)))

    ax2.imshow(smoothed_data, cmap='bone', interpolation='nearest',
               clim=(0.1, 100), norm=LogNorm())
    ax2.scatter(sources_mean['x_peak'], sources_mean['y_peak'], c='r', marker='+')
    ax2.set_title('fThreshold = Mean ({} sources found)'.format(len(sources_mean)))

    plt.get_current_fig_manager().window.raise_()
    plt.show()

    # Prompt user to choose
    choice = input('''
                   Examine the two options presented. To use the stars \
                   selected with a 3 standard deviation threshold, \
                   type "S". To use the stars selected with a mean \
                   threshold, type "M". To use neither and cancel the \
                   program, press enter.

                   Choice: ''')

    plt.close()

    if choice == 'S':
        num_psfs = len(sources_std)
        coords = [(x, y) for [x, y] in sources_std['x_peak', 'y_peak']]
        return num_psfs, coords, thresholds[0]
    if choice == 'M':
        num_psfs = len(sources_mean)
        coords = [(x, y) for [x, y] in sources_mean['x_peak', 'y_peak']]
        return num_psfs, coords, thresholds[1]
    else:
        LOGGER.error('Image Conversion: User rejection of identified PSFs.')
        raise ValueError('User rejection of identified PSFs.')


def count_psfs(smoothed_data, gauss_sigma, npeaks=np.inf, detection_threshold='standard-deviation', choose=False):
    """Use utils.find_peaks, which is a wrapper around photutils.find_peaks, to count how many PSFS
    are present in the data.

    Parameters
    ----------
    smoothed_data : 2-D numpy array
        Image data that has been smoothed with a Gaussian filter
    gauss_sigma : float
        The sigma of the Gaussian smoothing filter
    npeaks : int or np.inf
        Number of peaks to choose with photutils.find_peaks
    detection_threshold: str, optional
        Options are "standard-deviation" to set threshold=median + (3 * std) or
        "pixel-wise" to use photutils' detect_threshold() function (used only
        for normal operations)
    choose : bool, optional
        Prompt the user to choose which method to use to select the
        threshold

    Returns
    -------
    num_psfs : int
        The number of PSFs found in the smoothed data
    coords : list
        List of tuples of x and y coordinates of all identified PSFs
    threshold : float
        The threshold used with photutils.find_peaks
    """

    if choose:
        num_psfs, coords, threshold = choose_threshold(smoothed_data, gauss_sigma)

    else:
        # Find PSFs
        sources, threshold = utils.find_peaks(smoothed_data, box_size=gauss_sigma, npeaks=npeaks,
                                              threshold=detection_threshold, return_threshold=True)
        num_psfs = len(sources)
        if num_psfs == 0:
            raise ValueError("You have no sources in your data.")
        coords = sources['x_peak', 'y_peak']
        coords = [(x, y) for [x, y] in coords]

        if isinstance(threshold, np.ndarray):
            print_threshold = f'a pixel-wise array with mean={np.mean(threshold)}'
        else:
            print_threshold = threshold

        LOGGER.info('Image Conversion: {} PSFs detected in Gaussian-smoothed data '
                    '(threshold = {}; sigma = {})'.format(num_psfs, print_threshold, gauss_sigma))

    return num_psfs, coords, threshold


def create_all_found_psfs_file(data, guider, root, out_dir, smoothing='default',
                               detection_threshold='standard-deviation', save=True, num_peaks=None):
    """Take input column information and save out the all_found_psfs_file

    Parameters
    ----------
    data : 2-D numpy array
        Image data
    guider : int
        Guider number (1 or 2)
    root : str
        Name used to create the output directory, {out_dir}/out/{root}
    out_dir : str
        Where output files will be saved.
    smoothing: str or float, optional
        Options are "low" for minimal smoothing (e.g. MIMF), "high" for large
        smoothing (e.g. GA), "default" for medium smoothing for other cases,
        or "choose center" for finding the center of a MIMF PSF
    detection_threshold: str, optional
        Options are "standard-deviation" to set threshold=median + (3 * std) or
        "pixel-wise" to use photutils' detect_threshold() function (used only
        for normal operations). User can also pass a float which will be used
        as the sigma value in ndimage.gaussian_filter." to the smoothing
        parameter description
    save : bool, optional
        Save out all found psfs file
    num_peaks: int
        Number of peaks to find, will overwrite defaults based on smoothing

    Returns
    -------
    x_list : list
        x positions of segments
    y_list : list
        y positions of segments
    """
    # Use smoothing to identify the segments of the foreground star
    if smoothing == 'high':
        gauss_sigma = 26
        npeaks = np.inf
    elif smoothing == 'low':
        gauss_sigma = 1
        npeaks = 1
    elif smoothing == 'default':
        gauss_sigma = 5
        npeaks = np.inf
    elif smoothing == 'choose center':
        gauss_sigma = 26
        npeaks = 1
    elif isinstance(smoothing, (float, int)):
        gauss_sigma = smoothing
        npeaks = np.inf

    if num_peaks is None:
        num_peaks = npeaks

    data = data.astype(float)
    smoothed_data = ndimage.gaussian_filter(data, sigma=gauss_sigma)

    # Use photutils.find_peaks to locate all PSFs in image
    num_psfs, coords, threshold = count_psfs(smoothed_data, gauss_sigma, npeaks=num_peaks,
                                             detection_threshold=detection_threshold, choose=False)
    x_list, y_list = map(list, zip(*coords))

    # Use labeling to map locations of objects in array
    # (Kept for possible alternate countrate calculations; see count_rate_total)
    objects = ndimage.label(smoothed_data > threshold)[0]
    # NOTE: num_objects might not equal num_psfs

    # Calculate count rate
    countrate, val = utils.count_rate_total(data, objects, num_psfs, x_list, y_list, countrate_3x3=True, log=LOGGER)

    segment_labels = utils.match_psfs_to_segments(x_list, y_list, smoothing)
    all_cols = utils.create_cols_for_coords_counts(x_list, y_list, countrate, val,
                                                   labels=segment_labels,
                                                   inds=range(len(x_list)))

    # If the countrate for a PSF is 0, remove that row (if we couldn't find a count rate for it in count_rate_total)
    all_cols = [col for col in all_cols if float(col[3]) != 0]

    if save is True:
        all_found_psfs_path = save_all_found_psfs_file(all_cols, guider, root, out_dir)
    else:
        all_found_psfs_path = None

    return x_list, y_list, countrate, all_found_psfs_path


def save_all_found_psfs_file(all_cols, guider, root, out_dir):
    """Save out all found psfs file

    Parameters
    ----------
    all_cols : list
        List of lists, where each sublist contains the following for each
        segment: the id letter, x position, y position, and countrate. All
        of which are strings.
    guider : int
        Guider number (1 or 2)
    root : str
        Name used to create the output directory, {out_dir}/out/{root}
    out_dir : str
        Where output files will be saved.
    """
    all_found_psfs_path = os.path.join(out_dir, 'unshifted_all_found_psfs_{}_G{}.txt'.format(root, guider))

    # Write catalog of all identified PSFs
    utils.write_cols_to_file(all_found_psfs_path,
                             labels=['label', 'y', 'x', 'countrate'],
                             cols=all_cols, log=LOGGER)

    return all_found_psfs_path


def save_psf_center_file(center_cols, guider, root, out_dir):
    """Save out psf center file for low smoothing (MIMF) cases only

    Parameters
    ----------
    center_cols :

    guider : int
        Guider number (1 or 2)
    root : str
        Name used to create the output directory, {out_dir}/out/{root}
    out_dir : str
        Where output files will be saved.
    """
    psf_center_path = os.path.join(out_dir, 'unshifted_psf_center_{}_G{}.txt'.format(root, guider))
    utils.write_cols_to_file(psf_center_path,
                             labels=['y', 'x', 'countrate'],
                             cols=center_cols, log=LOGGER)

    return psf_center_path


def create_seed_image(data, guider, root, out_dir, smoothing='default',
                      detection_threshold='standard-deviation', psf_size=None, all_found_psfs_file=None,
                      num_peaks=None):
    """Create a seed image leaving only the foreground star by removing
    the background and any background stars, and setting the background
    to zero.

    Parameters
    ----------
    data : 2-D numpy array
        Image data
    guider : int
        Guider number (1 or 2)
    root : str
        Name used to create the output directory, {out_dir}/out/{root}
    out_dir : str
        Where output files will be saved.
    smoothing: str or float, optional
        Options are "low" for minimal smoothing (e.g. MIMF), "high" for large
        smoothing (e.g. GA), "default" for medium smoothing for other cases,
        or "choose center" for finding the center of a MIMF PSF
    detection_threshold: str, optional
        Options are "standard-deviation" to set threshold=median + (3 * std) or
        "pixel-wise" to use photutils' detect_threshold() function (used only
        for normal operations)
    psf_size: int, optional
        Set the size of the stamps to use when cutting out PSFs from the image.
        Input is the edge of the square size in pixels (e.g. if 100, the stamp
        will be 100px x 100px). If not set, default values will be used based
        on smoothing choice.
    all_found_psfs_file: str, optional
        A pre-made all_found_psfs file to use when creating the pseudo-FGS
        image rather than making a new one by smoothing the code. This can
        be used when MAGIC's current smoothing methods aren't sufficient in
        blocking background segments and PSFs need to be deleted from the
        MAGIC-made all found PSFs file.
    num_peaks: int
        Number of peaks to find, will overwrite defaults based on smoothing

    Returns
    -------
    seed_image : 2-D numpy array
        New image with no background and adjusted PSF values
    """
    if psf_size is None:
        if smoothing == 'high':
            psf_size = 150
        else:
            psf_size = 100

    # If it's the MIMF case, we need to center the postage stamp on the PSF center
    if smoothing == 'low':
        smoothing = 'choose center'

    if all_found_psfs_file is None:
        # Generate PSF locations from original data; don't save out here
        x_list, y_list, _, _ = create_all_found_psfs_file(data, guider, root, out_dir, smoothing,
                                                          detection_threshold, save=False, num_peaks=num_peaks)
    else:
        # Read in file
        in_table = asc.read(all_found_psfs_file)
        x_list, y_list = in_table['x'], in_table['y']

    # Cut out square postage stamps around the segments
    postage_stamps = []
    for x, y in zip(x_list, y_list):
        position = (x, y)  # x,y
        size = (psf_size, psf_size)  # y,x pixels
        cutout = Cutout2D(data, position, size)
        postage_stamps.append(cutout)

    # Find the median of the background (without the postage stamps) and subtract it from the postage stamps
    old_bkgrd = data.copy()
    for stamp in postage_stamps:
        old_bkgrd[stamp.slices_original[0], stamp.slices_original[1]] = np.full_like(stamp.data, np.nan)

    # Do 2x sigma clipping with sigma = 3 (returning an array where clipped data are nans)
    import warnings
    from astropy.utils.exceptions import AstropyUserWarning
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=AstropyUserWarning)
        old_bkgrd = sigma_clip(old_bkgrd, sigma=3, cenfunc='mean', masked=False, copy=False, axis=[0, 1])
        old_bkgrd = sigma_clip(old_bkgrd, sigma=3, cenfunc='mean', masked=False, copy=False, axis=[0, 1])
    med = np.nanmedian(old_bkgrd)

    final_stamps = []
    for cutout in postage_stamps:
        cutout.data = cutout.data - med
        final_stamps.append(cutout)

    # Set the entire background plus any background stars to 0 (May change later with thermal info)
    seed_image = np.zeros_like(data)
    for stamp in final_stamps:
        seed_image[stamp.slices_original[0], stamp.slices_original[1]] = stamp.data

    return seed_image


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
# MAIN FUNCTIONS
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


def convert_im(input_im, guider, root, out_dir=None, nircam=True,
               nircam_det=None, normalize=True, norm_value=12.0,
               norm_unit="FGS Magnitude", smoothing='default',
               detection_threshold='standard-deviation',
               psf_size=None, all_found_psfs_file=None, gs_catalog=None,
               coarse_pointing=False, jitter_rate_arcsec=None,
               logger_passed=False, itm=False, num_peaks=None):
    """Takes NIRCam or FGS image and converts it into an FGS-like image.

    Parameters
    ----------
    input_im : str
        Filepath for the input (NIRCam or FGS) image
    guider : int
        Guider number (1 or 2)
    root : str
        Name used to create the output directory, {out_dir}/out/{root}
    out_dir : str, optional
        Where output files will be saved. If not provided, the
        image(s) will be saved within the repository at
        jwst_magic/. This path is the level outside the out/root/ dir
    nircam : bool, optional
        Denotes if the input_image is an FGS or NIRCam image. If True,
        the image will be converted to FGS format. Unless out_dir is
        specified, the FGS-formatted image will be saved to
        ../out/{root}/FGS_imgs/{root}_binned_pad_norm.fits
    nircam_det : str, optional
        The detector of a provided NIRCam image. If left blank, the
        detector will be extracted from the header of the NIRCam FITS
        file.
    normalize : bool, optional
        Denotes if the image will be normalized. If True, norm_value
        and norm_unit will be used to determine the normalization value
    norm_value : str or float, optional
        Specifies the Guide Star ID or the count rate/magnitude to which
        to normalize.
    norm_unit : str, optional
        Specifies the unit of norm_value ("FGS Magnitude", "FGS countrate",
        or "Guide Star ID")
    smoothing : str or float, optional
        Options are "low" for minimal smoothing (e.g. MIMF), "high" for large
        smoothing (e.g. GA), "default" for medium smoothing for other cases,
        or "choose center" for finding the center of a MIMF PSF. User can also
        pass a float which will be used as the sigma value in ndimage.gaussian_filter.
    detection_threshold : str, optional
        Options are "standard-deviation" to set threshold=median + (3 * std)
        or "pixel-wise" to use photutils' detect_threshold() function (used
        only for normal operations)
    psf_size : int, optional
        Set the size of the stamps to use when cutting out PSFs from the image.
        Input is the edge of the square size in pixels (e.g. if 100, the stamp
        will be 100px x 100px). If not set, default values will be used based
        on smoothing choice.
    all_found_psfs_file : str, optional
        A pre-made all_found_psfs file to use when creating the pseudo-FGS
        image rather than making a new one in the code. This can be used
        when MAGIC's current smoothing methods aren't sufficient in
        blocking background segments and PSFs need to be deleted from the
        MAGIC-made all found PSFs file in the backend.
    gs_catalog : str, optional
        Guide star catalog version to query. E.g. 'GSC242'. None will use
        the default catalog as defined in teh FGS Count Rate Module.
    coarse_pointing : bool, optional
        Denotes if the image will have a Gaussian filter applied to
        simulate the effects of jitter when the observatory is in
        coarse pointing rather than fine guide.
    jitter_rate_arcsec : None, optional
        The rate of the spacecraft jitter, in arcseconds per second,
        that will be used to apply the Gaussian filter if
        coarse_pointing is True.
    logger_passed : bool, optional
        Denotes if a logger object has already been generated.
    itm : bool, optional
        If this image come from the ITM simulator (important for normalization).
    num_peaks: int
        Number of peaks to find, will overwrite defaults based on smoothing

    Returns
    -------
    data : 2-D numpy array
        Image formatted like a raw FGS image

    Raises
    ------
    TypeError
        The input filename has more than one frame.
    ValueError
        An input NIRCam file has an obstruction in the pupil.
    """
    # Set up out dir(s)
    out_dir = utils.make_out_dir(out_dir, OUT_PATH, root)
    utils.ensure_dir_exists(out_dir)

    # Start logging
    if not logger_passed:
        utils.create_logger_from_yaml(__name__, out_dir_root=out_dir, root=root, level='DEBUG')

    # Set up hdr_dict to add header information to
    fgs_hdr_dict = {}

    try:
        LOGGER.info("Image Conversion: " +
                    "Beginning image conversion to guider {} FGS image".format(guider))
        LOGGER.info("Image Conversion: Input image is expected to be in units of ADU/sec (countrate)")

        data = fits.getdata(input_im, header=False)
        header = fits.getheader(input_im, ext=0)

        if len(data.shape) > 2:
            raise TypeError('Expecting a single frame or slope image.')

        # Check if this is an ITM image and the itm flag is set correctly (backwards compatibility)
        try:
            origin = header['ORIGIN'].strip()
            if origin == 'ITM':
                try:
                    assert itm is True
                except AssertionError:
                    itm = True
                    LOGGER.warning("Deprecation Warning: This is an ITM image, setting itm flag to 'True'")
        except KeyError:
            origin = None

        # Try to check that the units on the input image are as expected (Dn/s = ADU/s; *_rate.fits)
        try:
            header_sci = fits.getheader(input_im, extname='sci')
        except KeyError:
            header_sci = {}

        for hdr in [header, header_sci]:
            if 'BUNIT' in hdr:
                input_unit = hdr['BUNIT'].lower()
            if 'PHOTMJSR' in hdr:
                photmjsr = hdr['PHOTMJSR']
            if 'DATAMODL' in hdr:
                datamodel = hdr['DATAMODL']

            if 'DETECTOR' in hdr:
                detector = hdr['DETECTOR']  # e.g. 'NRCA3'
            elif nircam and isinstance(nircam_det, str):
                detector = 'NRC'+nircam_det

        # Remove bad pixels from input images if possible. If not, we'll use the bad pixel masks
            # NIRCam -> use dq array is available, use CRDS file 2nd
            # FGS Full Frame -> use dq array is available (but no saturated flags), use DHAS mask 2nd
            # Padded TRK image -> have to use DHAS file (no dq array; TRK box is confirmed to be in the right spot)
        try:
            dq_array = fits.getdata(input_im, extname='DQ')
            dq_array, _ = utils.convert_bad_pixel_mask_data(dq_array, nircam=nircam)
        except KeyError:
            dq_array = None

        try:
            if dq_array is None:
                detector  # check if variable exists, needed to pull mask file
            try:
                data = bad_pixel_correction(data, nircam, detector, dq_array)
                LOGGER.info(f"Image Conversion: Bad pixels removed from image using "
                            f"{'DQ array from image' if dq_array is not None else 'Bad Pixel Mask'}.")
            except FileNotFoundError:
                LOGGER.error('Image Conversion: Cannot find DQ file in repository. **No DQ data added.**')

        except NameError:
            LOGGER.warning("Image Conversion: Data not run through bad pixel removal step. Unable to pull "
                           "necessary detector information from input image.")

        # Remove distortion from NIRCam or FGS cal data, but not from padded TRK data nor rate images
        # as they cannot be run through the pipeline without lots of extra steps
        distortion = True  # is there distortion in the image
        try:
            if datamodel != 'GuiderCalModel' and input_unit == 'mjy/sr':
                LOGGER.info("Image Conversion: Removing distortion from data using the JWST Pipeline's Resample step.")
                # Update HDUList object and read it into the image model
                with fits.open(input_im) as hdulist:
                    hdulist['SCI'].data = data
                    with ImageModel(hdulist, skip_fits_update=False) as model:
                        result = ResampleStep.call(model, save_results=False)

                # Crop data back to (2048, 2048), cutting out the top and right to keep the origin
                LOGGER.info(f"Image Conversion: Cutting undistorted data from {result.data.shape} to (2048, 2048)")
                data = result.data[0:2048, 0:2048]
                distortion = False
        except NameError:
            LOGGER.info("Image Conversion: Skipping removing distortion from image due to missing either "
                        "DATAMODL or BUNIT information.")

        # Turn cal images into rate images
        try:
            if input_unit == 'mjy/sr':
                convert_to_adu_s = photmjsr
                data /= convert_to_adu_s
                LOGGER.info('Image Conversion: Input is a Cal image. Converting from MJy/sr to ADU/s')
            elif input_unit == 'dn/s':
                LOGGER.info('Image Conversion: Image in correct units of ADU/s.')
        except NameError:
            LOGGER.info("Image Conversion: Can't check image type because of missing "
                        "BUNIT keyword. User should confirm the input image is a rate image.")
            pass

        # Create raw FGS image...

        # Remove pedestal from NIRCam or FGS data
        # pedestal should be taken out in refpix correction - only run if that hasn't been run
        # and if not labeled as test data which is made without a pedestal
        if 'S_REFPIX' in header.keys() and header['S_REFPIX'] == 'COMPLETE':
            LOGGER.info("Image Conversion: Skipping removing pedestal - Reference pixel correction run in pipeline.")
        elif 'TEST' in header.keys() and header['TEST'] == 'True':
            LOGGER.info("Image Conversion: Skipping removing pedestal - Test flag found in image header.")
        else:
            data = remove_pedestal(data, nircam, itm)

        # -------------- From NIRCam --------------
        if nircam:
            LOGGER.info("Image Conversion: This is a NIRCam image")

            # Check that the pupil is clear
            try:
                pupil_keyword = header['PUPIL']
                if pupil_keyword in ['CLEAR', 'Imaging Pupil']:
                    pass
                else:
                    raise ValueError(
                        'NIRCam "PUPIL" header keyword for provided file is {}. '.format(pupil_keyword) +
                        'Only the CLEAR/Imaging Pupil can be used to realistically simulate FGS images.'
                    )
            except KeyError:
                pass

            # Rotate the NIRCAM image into FGS frame
            nircam_scale, data = transform_nircam_image(data, guider, nircam_det, header)
            # Pad image
            data = resize_nircam_image(data, nircam_scale, FGS_PIXELS, guider)

        # -------------- From FGS --------------
        else:
            LOGGER.info("Image Conversion: This is an FGS image")
            # Check if header keyword is equal to fgs raw to determine if rotation to raw is needed
            if origin is not None and origin.upper() == 'FGSRAW':  # this is a magic-team keyword that should only be in test files
                LOGGER.info("Image Conversion: Data is already provided in raw frame; no rotation done")
                LOGGER.warning("Assume input guider is same as output guider; no rotation done")
            else:
                LOGGER.info(
                    "Image Conversion: Expect that data provided is in science/DMS frame; rotating to raw FGS frame.")
                data = coordinate_transforms.transform_sci_to_fgs_raw(data, guider)

        # Apply Gaussian filter to simulate coarse pointing
        if coarse_pointing:
            pixel_scale = nircam_scale if nircam else globals()['FGS{}_SCALE'.format(guider)]

            data = apply_coarse_pointing_filter(data, jitter_rate_arcsec, pixel_scale)
            LOGGER.info("Image Conversion: Applied Gaussian filter to simulate "
                        "coarse pointing with jitter of {:.3f} arcsec/sec".format(jitter_rate_arcsec))

        # Normalize the image, if the "normalize" flag is True
        # The ITM simulations are only created for relative SNR so they need to
        # normalized to one before anything else happens
        if itm:
            LOGGER.info("Image Conversion: This is an ITM image.")
            data -= data.min()  # set minimum at 0.
            data /= data.sum()  # set total countrate to 1.
            if not norm_value:
                norm_value = 12
                norm_unit = 'FGS Magnitude'
                LOGGER.warning("Image Conversion: No normalization was specified but is required for an ITM image. "
                               "Using FGS Magnitude of 12.")

        if normalize or itm:
            # Remove the background and background stars and output a seed image with just the foreground stars
            data = create_seed_image(data, guider, root, out_dir, smoothing,
                                     detection_threshold, psf_size, all_found_psfs_file, num_peaks=num_peaks)

            # Convert magnitude/countrate to FGS countrate using new count rate module
            # Take norm_value and norm_unit to pass to count rate module
            fgs_countrate, fgs_mag = renormalize.convert_to_countrate_fgsmag(norm_value, norm_unit, guider, gs_catalog)

            # Normalize the data
            data = utils.correct_image(data) # Correct any negative or inf values before normalizing
            data = normalize_data(data, fgs_countrate)
            LOGGER.info("Image Conversion: Normalizing to {} FGS Countrate (FGS Mag: {})".format(fgs_countrate,
                                                                                                 fgs_mag))

        try:
            if all_found_psfs_file is None:
                # Save out all found PSFs file once the data has been normalized
                x_list, y_list, cr_list, all_found_psfs_path = create_all_found_psfs_file(data, guider, root, out_dir,
                                                                                          smoothing,
                                                                                          detection_threshold,
                                                                                          save=True, num_peaks=num_peaks)
            else:
                # Write the same file out in the correct directory with the correct name
                table = asc.read(all_found_psfs_file)
                colnames = table.colnames
                all_cols = [[str(i) for i in table[name].tolist()] for name in colnames]
                all_cols = list(map(list, zip(*all_cols)))
                all_found_psfs_path = save_all_found_psfs_file(all_cols, guider, root, out_dir)

            # Save out psf center file for no smoothing case
            if smoothing == 'low':
                LOGGER.info(
                    "Image Conversion: No smoothing chosen for MIMF case, so calculating PSF center")

                x_center, y_center, cr_center, _ = create_all_found_psfs_file(data, guider, root, out_dir,
                                                                              smoothing='choose center',
                                                                              detection_threshold=detection_threshold,
                                                                              save=False, num_peaks=num_peaks)
                psf_center_path = save_psf_center_file([[y_center[0], x_center[0], cr_center[0]]], guider, root, out_dir)

                LOGGER.info("Image Conversion: PSF center y,x,cr = {}, {}, {} vs Guiding knot y,x,cr = {}, {}, {}".format(
                    y_center[0], x_center[0], cr_center[0], y_list[0], x_list[0], cr_list[0]))
            else:
                psf_center_path = None
        except TypeError as e:
            if str(e) == "object of type 'NoneType' has no len()":
                LOGGER.warning('Image Conversion: No PSFs were found in this image. '
                               'Cannot write out an all found PSFs file.')
                all_found_psfs_path = None
                psf_center_path = None
            else:
                raise TypeError(str(e))

        # Update header information
        fgs_hdr_dict['IN_FILE'] = (os.path.basename(input_im), 'Input image')
        fgs_hdr_dict['IN_INSTR'] = ('NIRCAM' if nircam else 'FGS', 'Input instrument')
        fgs_hdr_dict['IN_DET'] = (nircam_det if nircam else f'FGS', 'Input detector')
        fgs_hdr_dict['OUT_DET'] = (f'GUIDER{guider}', 'Output guider')
        fgs_hdr_dict['DISTORT'] = (distortion, 'Is the image distorted')
        fgs_hdr_dict['SMOOTHIN'] = (smoothing, 'Smoothing used')
        if normalize:
            fgs_hdr_dict['NORMUNIT'] = (norm_unit, 'Normalization unit')
            fgs_hdr_dict['NORMVALU'] = (norm_value, 'Normalization value')
            if norm_unit.lower() == 'guide star id':
                ra, dec = renormalize.query_guide_star_catalog(gs_id=norm_value)
                fgs_hdr_dict['GS_RA'] = (ra, 'RA of guide star')
                fgs_hdr_dict['GS_DEC'] = (dec, 'DEC of guide star')

    except Exception as e:
        LOGGER.exception(f'{repr(e)}: {e}')
        raise

    return data, all_found_psfs_path, psf_center_path, fgs_hdr_dict


def write_fgs_im(data, out_dir, root, guider, hdr_dict=None, fgsout_path=None):
    """Writes an array of FGS data to the appropriate file:
    {out_dir}/out/{root}/FGS_imgs/{root}_G{guider}.fits

    Parameters
    ----------
    data : 2-D numpy array
        FGS image data
    out_dir : str, optional
        Where output files will be saved. If not provided, the
        image(s) will be saved within the repository at
        jwst_magic/
    root : str
        Name used to create the output directory, {out_dir}/out/{root}
    guider : int
        Guider number (1 or 2)
    hdr_dict : dict, optional
        Dictionary of header information to
    fgsout_path : str, optional
        Alternate directory in which to save the FGS files. If not
        provided, the FGS images will be saved to
        {out_dir}/out/{root}/FGS_imgs/

    Returns
    -------
    fgsout_path : str
        Filepath for the output FGS image
    """
    # Correct any negative values in the data
    data = utils.correct_image(data)

    # Define output path
    output_path_save = utils.make_out_dir(out_dir, OUT_PATH, root)
    utils.ensure_dir_exists(output_path_save)
    if not fgsout_path:
        fgsout_path = os.path.join(output_path_save, 'FGS_imgs')
    fgsout_file = os.path.join(fgsout_path, 'unshifted_{}_G{}.fits'.format(root, guider))

    # Load header file needed for DHAS
    header_file = os.path.join(DATA_PATH, f'header_g{guider}.fits')
    hdr = fits.getheader(header_file, ext=0)
    hdr.add_blank('DHAS-Required Header Information', before='DATE')
    hdr.add_blank('', before='DATE')

    # Add MAGIC-related header information
    if hdr_dict is not None:
        for key, (value, comment) in hdr_dict.items():
            hdr.set(key, value=value, comment=comment, before='NAXIS')
    hdr.add_history('This pseudo-FGS image was created by MAGIC on '
                    f'{datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")}')
    hdr.add_blank('MAGIC Information', before='IN_FILE')
    hdr.add_blank('', before='IN_FILE')

    header_list = [hdr, None]
    data_list = [None, data]

    # Write FITS file
    utils.write_fits(fgsout_file, data_list, header=header_list, log=LOGGER)

    return fgsout_path
