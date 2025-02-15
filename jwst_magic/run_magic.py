"""Run JWST MaGIC end-to-end

~Description

Authors
-------
    - Keira Brooks
    - Lauren Chambers

Use
---
    This module can be executed in a Python shell as such:
    ::
        from jwst_magic.convert_image import convert_image_to_raw_fgs
        convert_image_to_raw_fgs.convert_im(input_im, guider, root,
            nircam=True, nircam_det=None, norm_value=None, norm_unit=None,
            out_dir=None):

    Required arguments:
        ``input_image`` - filepath for the input (NIRCam or FGS) image
        ``guider`` - number for guider 1 or guider 2
        ``root`` - will be used to create the output directory, ./out/{root}
    Optional arguments:
        ``nircam`` - denotes if the input_image is an FGS or NIRCam
            image. If True, the image will be converted to FGS format.
            Unless out_dir is specified, the FGS-formatted image will
            be saved to ../out/{root}/FGS_imgs/{root}_binned_pad_norm.fits
        ``nircam_det`` - used to specify the detector of a provided
            NIRCam image. If left blank, the detector will be extracted
            from the header of the NIRCam FITS file.
        ``norm_value`` and ``norm_unit`` - used to normalize the input
            NIRCam image, to a desired number of FGS counts.
        ``out_dir`` - where output FGS image(s) will be saved. If not
            provided, the image(s) will be saved to ../out/{root}.
"""

# Standard Library Imports
import logging
import os
import shutil

# Third Party Imports
import matplotlib
if matplotlib.get_backend() != 'Qt5Agg':
    matplotlib.use('Qt5Agg')  # Make sure that we are using Qt5
print('Using backend: ', matplotlib.get_backend())
import numpy as np

# Local Imports
from jwst_magic.convert_image import background_stars, convert_image_to_raw_fgs, renormalize
from jwst_magic.fsw_file_writer import buildfgssteps, write_files
from jwst_magic.star_selector import select_psfs
from jwst_magic.utils import utils

# Define paths
PACKAGE_PATH = os.path.dirname(os.path.realpath(__file__))
OUT_PATH = os.path.split(PACKAGE_PATH)[0]  # Location of out/ and logs/ directory

# Start logger
LOGGER = logging.getLogger(__name__)


def run_all(image, guider, root=None, norm_value=None, norm_unit=None,
            nircam_det=None, nircam=True, smoothing='default', detection_threshold='standard-deviation',
            steps=None, guiding_selections_file=None, bkgd_stars=False,
            bkgrdstars_hdr=None, out_dir=None, convert_im=True,
            star_selection=True, file_writer=True, mainGUIapp=None, copy_original=True,
            normalize=True, coarse_pointing=False, jitter_rate_arcsec=None, itm=False,
            shift_id_attitude=True, thresh_factor=0.6, use_oss_defaults=False, override_bright_guiding=False,
            logger_passed=False, log_filename=None):
    """
    This function will take any FGS or NIRCam image and create the outputs needed
    to run the image through the DHAS or other FGS FSW simulator. If no incat or
    reg file are provided, the user will be prompted to use a GUI for selecting
    the guide star and reference stars necessary for the FSW.

    Parameters
    ----------
    image: str
        The path to the image.
    guider: int
        Which guider is being used: 1 or 2
    root: str, optional
        The root desired for output images if different than root in image
    norm_value: float, optional
        The value to be used for normalization (depends on norm_unit)
    norm_unit: str, optional
        The unit to be used for normalization (expecting "FGS Counts" or "FGS Magnitude")
    nircam_det: str, optional
        The NIRCam detector used for this observation. Only applicable for NIRCam
        images and if cannot be parsed from header.
    nircam: bool, optional
        If this is a FGS image, set this flag to False
    smoothing: str, optional
        Options are "low" for minimal smoothing (e.g. MIMF), "high" for large
        smoothing (e.g. GA), or "default" for medium smoothing for other cases
    detection_threshold: str, optional
        Used in detecting stars in the convert_image section. Options are "standard-deviation"
        to set threshold=median + (3 * std) or "pixel-wise" to use photutils' detect_threshold()
        function (used only for normal operations)
    steps: list of strings, optional
        List of the steps to be completed
    guiding_selections_file: list of str, optional
        If this image comes with an incat or reg file, the file path
    bkgd_stars : boolean, optional
        Add background stars to the image?
    bkgrdstars_hdr : dict, optional
        Header information about the background stars to be added to the
        header of the pseudo-FGS image
    out_dir : str, optional
        Where output FGS image(s) will be saved. If not provided, the
        image(s) will be saved to ../out/{root}.
    convert_im : boolean, optional
        Run the convert_image module?
    star_selection : boolean, optional
        Run the  star_selector module?
    file_writer : boolean, optional
        Run the fsw_file_writer module?
    mainGUIapp : PyQt5.QtCore.QCoreApplication instance, optional
        The QApplication instance of the main GUI, if it is already
        open.
    copy_original : boolean, optional
        Copy the original data to {out_dir}/{root}?
    normalize : boolean, optional
        Normalize the provided image during convert_image?
    coarse_pointing : boolean, optional
        Apply jitter to simulate coarse pointing?
    jitter_rate_arcsec : float, optional
        If coarse_pointing is true, the rate of jitter in arcseconds
        per second to apply in the form of a Gaussian filter.
    itm : bool, Optional
        If this image come from the ITM simulator (important for normalization).
    thresh_factor : float
        The thresh_factor (aka count rate uncertainty factor) to use when writing
        FSW files.
    use_oss_defaults : bool
        Populate the DHAS files with the default numbers OSS would use. Should
        only be True when testing photometry override files
    override_bright_guiding: bool
        If the user wants to guarantee that their provided threshold factor will be used,
        regardless of the 3x3 count rate, they will set this parameter to True. When set
        to False, if the 3x3 count rate is above the OSS trigger, the threshold and
        threshold factors will be replaced.
    logger_passed : bool, optional
        Denotes if a logger object has already been generated.
    log_filename : str, optional
        File name for logger object, used to go into pseudo-FGS image header
    """

    # Determine filename root
    root = utils.make_root(root, image)

    # Determine output directory
    out_dir_root = utils.make_out_dir(out_dir, OUT_PATH, root)
    utils.ensure_dir_exists(out_dir_root)

    # Set up logging
    if not logger_passed:
        _, log_filename = utils.create_logger_from_yaml(__name__, out_dir_root=out_dir_root, root=root, level='DEBUG')

    LOGGER.info("Package directory: {}".format(PACKAGE_PATH))
    LOGGER.info("Processing request for {}.".format(root))
    LOGGER.info("All data will be saved in: {}".format(out_dir_root))
    LOGGER.info("Input image: {}".format(os.path.abspath(image)))

    # Copy input image into out directory
    if copy_original:
        try:
            shutil.copy(os.path.abspath(image), out_dir_root)
        except shutil.SameFileError:
            pass

    # Either convert provided NIRCam image to an FGS image...
    if convert_im:
        fgs_im, all_found_psfs_file, psf_center_file, fgs_hdr_dict = \
            convert_image_to_raw_fgs.convert_im(image, guider, root,
                                                out_dir=out_dir,
                                                nircam=nircam,
                                                nircam_det=nircam_det,
                                                normalize=normalize,
                                                norm_value=norm_value,
                                                norm_unit=norm_unit,
                                                smoothing=smoothing,
                                                detection_threshold=detection_threshold,
                                                coarse_pointing=coarse_pointing,
                                                jitter_rate_arcsec=jitter_rate_arcsec,
                                                logger_passed=True,
                                                itm=itm)

        # Add logging information to fgs image header
        fgs_hdr_dict['LOG_FILE'] = (os.path.basename(log_filename), 'Log filename')

        if bkgd_stars:
            if not normalize and not itm:
                norm_value = np.sum(fgs_im[fgs_im > np.median(fgs_im)])
                norm_unit = "FGS Counts"
            fgs_im = background_stars.add_background_stars(fgs_im, bkgd_stars,
                                                           norm_value, norm_unit,
                                                           guider, save_file=True,
                                                           root=root, out_dir=out_dir)
            for key, value in bkgrdstars_hdr.items():
                fgs_hdr_dict[key] = value

        # Write converted image
        convert_image_to_raw_fgs.write_fgs_im(fgs_im, out_dir, root, guider, fgs_hdr_dict)
        LOGGER.info("*** Image Conversion COMPLETE ***")
    # Or, if an FGS image was provided, use it!
    else:
        fgs_im = image
        all_found_psfs_file = os.path.join(out_dir_root, 'unshifted_all_found_psfs_{}_G{}.txt'.format(root, guider))
        if smoothing == 'low':
            psf_center_file = os.path.join(out_dir, 'unshifted_psf_center_{}_G{}.txt'.format(root, guider))
        else:
            psf_center_file = None
        LOGGER.info("Assuming that the input image is a raw FGS image")

    # Select guide & reference PSFs
    if star_selection:
        guiding_selections_path_list, all_found_psfs, center_pointing_file, psf_center_file = select_psfs.select_psfs(
            fgs_im, root, guider,
            all_found_psfs_path=all_found_psfs_file,
            guiding_selections_file_list=guiding_selections_file,
            psf_center_path=psf_center_file,
            smoothing=smoothing,
            out_dir=out_dir,
            logger_passed=True, mainGUIapp=mainGUIapp)
        LOGGER.info("*** Star Selection: COMPLETE ***")

    # Create all files for FSW/DHAS/FGSES/etc.
    if file_writer:
        out_dir = utils.make_out_dir(out_dir, OUT_PATH, root)

        # If you're planning to write out FSW files using the OSS default values, you need to calculate and pass
        # in the catalog countrate of the guide star
        if use_oss_defaults:
            fgs_countrate, _ = renormalize.convert_to_countrate_fgsmag(norm_value, norm_unit, guider)
        else:
            fgs_countrate = None

        # Shift the image and write out new fgs_im, guiding_selections, all_found_psfs, and psf_center files
        if steps is None:
            steps = ['ID', 'ACQ1', 'ACQ2', 'LOSTRK']

        threshold_factor_per_config = []
        fgs_files_objs = [] #np.empty((len(guiding_selections_path_list), len(steps)))
        for i, guiding_selections_file in enumerate(guiding_selections_path_list):
            # Change out_dir to write data to guiding_config_#/ sub-directory next to the selections file
            if 'guiding_config' in guiding_selections_file:
                out_dir_fsw = os.path.join(out_dir, 'guiding_config_{}'.format(
                    guiding_selections_file.split('guiding_config_')[1].split('/')[0]))
            else:
                out_dir_fsw = out_dir

            if shift_id_attitude:
                fgs_im_fsw, guiding_selections_file_fsw, psf_center_file_fsw = buildfgssteps.shift_to_id_attitude(
                    fgs_im, root, guider, out_dir_fsw, guiding_selections_file=guiding_selections_file,
                    all_found_psfs_file=all_found_psfs, center_pointing_file=center_pointing_file,
                    psf_center_file=psf_center_file, logger_passed=True)
            else:
                fgs_im_fsw = fgs_im
                guiding_selections_file_fsw = guiding_selections_file
                psf_center_file_fsw = psf_center_file

            for j, step in enumerate(steps):
                fgs_files_obj = buildfgssteps.BuildFGSSteps(
                    fgs_im_fsw, guider, root, step, out_dir=out_dir_fsw, thresh_factor=thresh_factor,
                    logger_passed=True, guiding_selections_file=guiding_selections_file_fsw,
                    psf_center_file=psf_center_file_fsw, shift_id_attitude=shift_id_attitude,
                    use_oss_defaults=use_oss_defaults, catalog_countrate=fgs_countrate,
                    override_bright_guiding=override_bright_guiding
                )
                threshold_factor_per_config.append(fgs_files_obj.thresh_factor)
                fgs_files_objs.append(fgs_files_obj)

        # Loop through thresholds for multiple configs and pick largest
        try:
            max_thresh_factor = np.max(threshold_factor_per_config)
        except ValueError:
            # If we are not writing out files, use the default thresh_factor value
            max_thresh_factor = thresh_factor
        if len(np.unique(threshold_factor_per_config)) != 1:
            LOGGER.info(f"FSW File Writing: The selections provided had more than one required threshold factor. Using the largest threshold factor: {max_thresh_factor}")

        # Write out the files with the new count rate threshold
        k = 0
        for i, guiding_selections_file in enumerate(guiding_selections_path_list):
            for step in steps:
                fgs_files_obj = fgs_files_objs[k]
                # For cases where the threshold factor is allowed to change from one config to the next
                if (not use_oss_defaults) or (not override_bright_guiding):
                    fgs_files_obj.threshold = max_thresh_factor * fgs_files_obj.countrate
                    fgs_files_obj.thresh_factor = max_thresh_factor
                write_files.write_all(fgs_files_obj)
                k += 1
            LOGGER.info(f"*** Finished FSW File Writing for Selection #{i+1} ***")

        LOGGER.info("*** FSW File Writing: COMPLETE ***")

    LOGGER.info("*** Run COMPLETE ***")
    try:
        return max_thresh_factor
    except UnboundLocalError:
        return None
