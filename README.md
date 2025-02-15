<p align="center">
    <img src ="magic_logo.png" alt="MAGIC logo" width="275"/>
</p>



# Multi-Application Guiding Interface for Commissioning (MAGIC)

[![PyPI - License](https://img.shields.io/pypi/l/Django.svg)](https://github.com/spacetelescope/jwst_magic/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/Python-3.7%20%7C%203.8%20%7C%203.9-blue.svg)](https://www.python.org/)
[![STScI](https://img.shields.io/badge/powered%20by-STScI-blue.svg?colorA=707170&colorB=3e8ddd&style=flat)](http://www.stsci.edu)
[![Build Status](https://ssbjenkins.stsci.edu/job/STScI/job/jwst_magic/job/main/badge/icon)](https://ssbjenkins.stsci.edu/job/STScI/job/jwst_magic/job/main/)

> **WARNING**: As of April 2022, active development and maintenance has ceased on this project since it was expected and developed to be used solely during JWST OTE Commissioning which is complete.
*No further support of this project should be expected.*

For use internal to STScI, please clone our mirror repository on grit: https://grit.stsci.edu/JWST-FGS/jwst-magic/
For developers, see the GitHub repository: https://github.com/spacetelescope/jwst_magic/

Please note that MAGIC has only been developed and used on MacOS machines. Any use on a different operating system may result in errors.

----------

The Multi-Application Guiding Interface for Commissioning (MAGIC) package provides convenient access to  numerous ancillary tools that will be used, as the name suggests, with the JWST FGS during OTE Commissioning. The package allows for user interaction with commissioning data and creates files that are needed for the operation of the flight software and the execution of visits.

**For more details on these tools and how to use them, please see the [MAGIC User's Guide](./docs/magic_user_guide).**

These tools comprise of four main components that can be run individually or together:

### 1. NIRCam or FGS science to FGS raw image conversion (``convert_image``)
This module will convert a JWST input image (from *any* NIRCam or FGS detector) to a pseudo-FGS raw image. This pseudo-FGS raw image is *not* a simulated image, but an expectation of the image that the FGS flight software will see. This module appropriately rotates the image from the science frame if necessary, adjusts the pixel scale and image size if converting from a NIRCam image, corrects bad pixels, and normalizes the image to the magnitude and count rates of a specified guide star.

### 2. Star Selection Tool (``star_selector``)
This module takes in a raw FGS image and allows the user to choose the guide and reference star PSFs using a GUI.


### 3. Flight Software File Writer (``fsw_file_writer``)
This module creates all the files necessary to test guide and reference star candidates in an FGS raw image, with different flight software simulators. This includes all the files necessary to run the ID, ACQ1, ACQ2, and TRK steps in these simulators.


### 4. Segment Guiding Tool (``segment_guiding``)
Allows the user to override the guide star catalog with the selected guide and reference star PSFs that will be used to facilitate guiding on unstacked and/or un-phased PSFs during JWST OTE commissioning.


Installation notes
------------------
This package was developed in a Python ≥3.7 environment.

##### To install

1. ``$ cd`` into the directory where you want to keep the package

2. Clone the repository to your local machine (we recommend you have SSH keys set up).
    If you are on GitHub:
    ```
    git clone git@github.com:spacetelescope/jwst_magic.git
    ```
    OR, using GitLab:
    ```
    git clone git@grit.stsci.edu:JWST-FGS/jwst-magic.git
    ```

3. Create a MAGIC-specific environment by navigating to the directory where the `setup.py` file lives in the `jwst_magic` package and create a new conda environment, for example named 'magic', from the `environment.yml` file:

    ```
    conda env create --name magic --file=environment.yml
    ```
    And activate it:
    ```
    conda activate magic
    ```

4. You will need the `jwst-fgs-countrate` module in order to run MAGIC. Clone the repository to your local machine.

    ```
    git clone git@github.com:spacetelescope/jwst-fgs-countrate.git
    ```

5. Install the `jwst-fgs-countrate` package by navigating to the directory where the `setup.py` file lives in the `jwst-fgs-countrate` package and installing it using `pip`:

    ```
    cd jwst-fgs-countrate/

    pip install -e .
    ```

6. Install the `jwst_magic` package by navigating to the directory where the `setup.py` file lives in the `jwst_magic` package and installing it using `pip`:

    ```
    cd jwst-magic/

    pip install -e .
    ```

7. (Optional) In order to run MAGIC fully as intended, you will need to copy a set of proprietary files to your local repository. If you feel you should have access to these files, reach out to the current maintainer of this code for more information. MAGIC can still be run without these files, but not all files will be written out and some of image files may be missing some of the expected noise components.


The `jwst_magic` package installation process will also check for the following package dependencies, and automatically install them using pip if they are not found:
  * `astropy`
  * `matplotlib`
  * `numpy`
  * `photutils`
  * `PyQt5`
  * `pysiaf`
  * `pytest`
  * `pyyaml`
  * `requests`
  * `jwst`

Running the Tools
-----------------
These tools are best run in the `IPython` terminal, in the conda environment where you have installed `jwst_magic`. Activate your environment, and launch the GUI with the following steps:

    In[1]: import jwst_magic

    In[2]: jwst_magic.run_tool_GUI()

If you see the print out `Warning: Cannot check for newest reference files.`, there are a few possible issues:
* You may not be connected to the internet
* You may have a problem with your CRDS cache, in which case:
   * Delete your CRDS cache directory (in your /home directory)
   * Re-import MAGIC in a new `IPython` session (which will re-download your cache)

Known Issues
-----------------
As with all software packages, there are several known issues for MAGIC. A current list of known issues is available[here](./docs/known_issues.md).

Documentation
-----------------
For the full documentation, including step-by-step directions for using this package, see the [MAGIC User's Guide](./docs/magic_user_guide).

Contributing
-----------------
> **WARNING**: No further development of this project is expected. This section remains solely for completeness.

There are two pages to review before you begin contributing to the `jwst_magic` package.
The first is our [style guide](./style_guide/style_guide.md) and the second is our suggested [git workflow page](./style_guide/git_workflow.md), which contains an in-depth explanation of the workflow.

The following is an example of a best work flow for contributing to the project
(adapted from the [`spacetelescope` `jwql` contribution guidelines](https://github.com/spacetelescope/jwql)):

1. Create a branch off of the `jwst_magic` repository using the [JIRA](https://jira.stsci.edu/projects/JWSTFGS/summary) issue name plus a
   short description of the issue (e.g. `JWSTFGS-375-fix-fgs-image-conversion`)
2. Make your software changes.
3. Push that branch to your personal GitHub repository (i.e. origin).
4. On the `jwst_magic` repository, create a pull request that merges the branch into `jwst_magic:main`.
5. Assign a reviewer from the team for the pull request.
6. Iterate with the reviewer over any needed changes until the reviewer accepts and merges your branch.
7. Delete your local copy of your branch.

Versioning
-----------------
> **WARNING**: No further development of this project is expected. This section remains solely for completeness.

This repository follows the principles of ["Semantic Versioning"](https://semver.org/), such that

> Given a version number MAJOR.MINOR.PATCH, increment the:
> 1. MAJOR version when you make incompatible API changes,
> 2. MINOR version when you add functionality in a backwards compatible manner, and
> 3. PATCH version when you make backwards compatible bug fixes.

When releasing a new version, developers should change the version number in `setup.py`, merge this change in a PR, and then release the package via the GitHub interface.

Code of Conduct
-----------------
> **WARNING**: No further development of this project is expected. This section remains solely for completeness.

Users and contributors to `jwst_magic` should adhere to the [Code of Conduct](./CODE_OF_CONDUCT.md).
Any issues or violations pertaining to the Code of Conduct should be brought to the attention of a MAGIC team member listed below.

Questions
-----------------
No further development of this project is expected, so no support will be given to future questions. We encourage you to look to the documentation for answers.

Code Maintainer
-----------------
* Shannon Osborne (GitHub: @shanosborne)

Development Team
-----------------
* Shannon Osborne (GitHub: @shanosborne)
* Keira Brooks (GitHub: @kjbrooks)
* Sherie Holfeltz
* Lauren Chambers (GitHub: @laurenmarietta)
* Kathryn St. Laurent
