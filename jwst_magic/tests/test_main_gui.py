"""Collection of unit tests to verify the correct function of the Main GUI
of the MAGIC tool.

Authors
-------
    - Shannon Osborne

Use
---
    ::
        pytest test_main_gui.py

Notes
-----
    Add the line `@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")`
    above tests that call pyqt5
"""
# Standard Library Imports
import os
import shutil
import sys
from unittest.mock import patch

# Third Party Imports
import numpy as np
JENKINS = '/home/developer/workspace/' in os.getcwd()
if not JENKINS:
    from PyQt5 import QtCore
    from PyQt5.QtWidgets import QDialogButtonBox, QApplication
import pytest

# Local Imports
from jwst_magic.utils import utils

if not JENKINS:
    from jwst_magic.mainGUI import MainGui

SOGS = utils.on_sogs_network()
if not SOGS:
    from pytestqt import qtbot

ROOT = "test_main"
__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
TEST_DIRECTORY = os.path.join(__location__, 'out', ROOT)
DATA_DIRECTORY = os.path.join(__location__, 'data', ROOT)
INPUT_IMAGE = os.path.join(__location__, 'data', 'fgs_data_2_cmimf.fits')
INPUT_IMAGE2 = os.path.join(__location__, 'data', 'nircam_mimf_cal.fits')
COMMAND_FILE = os.path.join(__location__, 'data', 'guiding_selections_test_main_G1.txt')

# Only used if using commissioning naming
COM_PRACTICE_DIR = 'magic_pytest_practice'


def delete_contents(directory):
    if os.path.isdir(directory):
        shutil.rmtree(directory)


@pytest.fixture()
def test_directory(test_dir=TEST_DIRECTORY):
    """Create a test directory for permission management.

    Parameters
    ----------
    test_dir : str
        Path to directory used for testing

    Yields
    -------
    test_dir : str
        Path to directory used for testing
    """
    os.makedirs(test_dir)  # creates directory with default mode=511

    yield test_dir
    print("teardown test directory")
    if os.path.isdir(test_dir):
        shutil.rmtree(test_dir)


@pytest.fixture()
def main_gui():
    """Set up QApplication object for the Main GUI"""
    # global app
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    main_gui = MainGui(root=ROOT, in_file=None, out_dir=__location__,
                       segment_guiding=True, app=app, itm=False)

    return main_gui


@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")
@pytest.mark.skipif(not SOGS, reason="SOGS naming not available")
def test_change_practice_commissioning(main_gui):
    """
    Check that re-setting the practice name in the naming method section
    doesn't re-run the fgscountrate call
    """
    # Set main GUI parameters
    main_gui.buttonGroup_guider.buttons()[0].setChecked(True)  # set to guider 2

    # Set naming method
    main_gui.buttonGroup_name.buttons()[0].setChecked(True)  # set commissioning naming method
    main_gui.comboBox_practice.setCurrentIndex(0)
    main_gui.comboBox_car.setCurrentText('OTE-07')
    main_gui.lineEdit_obs.setText('01')

    # Re-set practice
    with patch.object(main_gui, 'update_apt_gs_values') as mock:
        main_gui.comboBox_practice.setCurrentIndex(1)

    assert not mock.called, 'method should not have been called'


@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")
@pytest.mark.skipif(not SOGS, reason="SOGS naming not available")
def test_change_car_and_obs_commissioning(main_gui):
    """
    Check that updating the car and obs in the naming method section
    re-runs the fgscountrate call and updates values

    Note: This test is meant to be run on SOGS and assumings the APT file hasn't been
    updated. If this test fails due to a mis-match of APT information, check the APT
    file by hand
    """
    # Set main GUI parameters
    main_gui.buttonGroup_guider.buttons()[1].setChecked(True)  # set to guider 1

    # Set naming method
    main_gui.buttonGroup_name.buttons()[0].setChecked(True)  # set commissioning naming method
    main_gui.comboBox_practice.setCurrentText(COM_PRACTICE_DIR)
    main_gui.comboBox_car.setCurrentText('LOS-02')
    main_gui.lineEdit_obs.setText('02')
    main_gui.pushButton_commid.click()  # handle editingfinished not being called in code

    # Check Attributes
    assert main_gui.program_id == 1410
    assert main_gui.observation_num == 2
    assert main_gui.visit_num == 1

    assert main_gui.lineEdit_normalize.text() == 'S433000025'
    assert main_gui.gs_id == 'S433000025'
    np.testing.assert_almost_equal(main_gui.gs_ra, 118.192795288963, decimal=4)
    np.testing.assert_almost_equal(main_gui.gs_dec, -74.1609932764399, decimal=4)

    # Re-set CAR & OBS
    main_gui.lineEdit_obs.setText('06')
    main_gui.comboBox_car.setCurrentText('OTE-13')
    main_gui.pushButton_commid.click()

    # Re-Check Attributes
    assert main_gui.program_id == 1148
    assert main_gui.observation_num == 6
    assert main_gui.visit_num == 1

    assert main_gui.lineEdit_normalize.text() == 'N42J000231'
    assert main_gui.gs_id == 'N42J000231'
    np.testing.assert_almost_equal(main_gui.gs_ra, 268.01618875394, decimal=4)
    np.testing.assert_almost_equal(main_gui.gs_dec, 74.5987576983134, decimal=4)


@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")
@pytest.mark.skipif(not SOGS, reason="SOGS naming not available")
def test_update_apt_button_commissioning(main_gui):
    """
    Check that if the "update apt" button is pressed in the naming method section
    re-runs the fgscountrate call and updates values

    Note: This test is meant to be run on SOGS and assumings the APT file hasn't been
    updated. If this test fails due to a mis-match of APT information, check the APT
    file by hand
    """
    # Set main GUI parameters
    main_gui.buttonGroup_guider.buttons()[1].setChecked(True)  # set to guider 1

    # Set naming method
    main_gui.buttonGroup_name.buttons()[0].setChecked(True)  # set commissioning naming method
    main_gui.comboBox_practice.setCurrentText(COM_PRACTICE_DIR)
    main_gui.comboBox_car.setCurrentText('OTE-13')
    main_gui.lineEdit_obs.setText('06')
    main_gui.pushButton_commid.click()

    # Check Attributes
    assert main_gui.program_id == 1148
    assert main_gui.observation_num == 6
    assert main_gui.visit_num == 1

    assert main_gui.lineEdit_normalize.text() == 'N42J000231'
    assert main_gui.gs_id == 'N42J000231'
    np.testing.assert_almost_equal(main_gui.gs_ra, 268.01618875394, decimal=4)
    np.testing.assert_almost_equal(main_gui.gs_dec, 74.5987576983134, decimal=4)

    # Re-set APT number and press button
    main_gui.lineEdit_commid.setText('1410')
    main_gui.pushButton_commid.click()
    #QtCore.QTimer.singleShot(0, main_gui.pushButton_commid.clicked)

    # Re-Check Attributes
    assert main_gui.program_id == 1410
    assert main_gui.observation_num == 6
    assert main_gui.visit_num == 1

    assert main_gui.lineEdit_normalize.text() == 'S433000025'
    assert main_gui.gs_id == 'S433000025'
    np.testing.assert_almost_equal(main_gui.gs_ra, 118.192795, decimal=4)
    np.testing.assert_almost_equal(main_gui.gs_dec, -74.160993, decimal=4)


@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")
def test_use_apt_button_manual(main_gui, test_directory):
    """
    Test that re-setting apt to blank re-sets program id/obs/visit attributes
    """
    # Set main GUI parameters
    main_gui.buttonGroup_guider.buttons()[1].setChecked(True)  # set to guider 1

    # Set basic info
    main_gui.buttonGroup_name.buttons()[1].setChecked(True)  # set manual naming method
    main_gui.lineEdit_root.setText(ROOT)  # set root
    main_gui.textEdit_out.setText(__location__)  # set out directory
    main_gui.lineEdit_manualid.setText('1151')
    main_gui.lineEdit_manualobs.setText('01')
    main_gui.pushButton_manualid.click()

    # Check Attributes
    assert main_gui.program_id == 1151
    assert main_gui.observation_num == 1
    assert main_gui.visit_num == 1

    assert main_gui.lineEdit_normalize.text() == 'N42J000231'
    assert main_gui.gs_id == 'N42J000231'
    np.testing.assert_almost_equal(main_gui.gs_ra, 268.016188, decimal=4)
    np.testing.assert_almost_equal(main_gui.gs_dec, 74.598757, decimal=4)

    # Reset to blank
    main_gui.lineEdit_manualid.setText('')
    main_gui.lineEdit_manualobs.setText('')
    main_gui.pushButton_manualid.click()

    # Re-check attributes
    assert main_gui.program_id == ''
    assert main_gui.observation_num == ''
    assert main_gui.visit_num == ''

    assert main_gui.lineEdit_normalize.text() == ''
    assert main_gui.gs_id == ''
    assert main_gui.gs_ra == ''
    assert main_gui.gs_dec == ''


apt_parameters = [(pytest.param("commissioning", 0, 'SOF', marks=pytest.mark.skipif(not SOGS, reason="SOGS naming not available"))),
                  (pytest.param("commissioning", 0, 'POF', marks=pytest.mark.skipif(not SOGS, reason="SOGS naming not available"))),
                  (pytest.param("manual", 1, 'SOF', marks=pytest.mark.skipif(SOGS, reason="SOGS naming not available"))),
                  (pytest.param("manual", 1, 'POF', marks=pytest.mark.skipif(SOGS, reason="SOGS naming not available")))]
@pytest.mark.parametrize('type, button_name , filetype', apt_parameters)
@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")
def test_apt_gs_populated(qtbot, main_gui, test_directory, type, button_name, filetype):
    """
    Test APT info + GS Info are populated into segment guiding SOF and POF GUIs
    correctly for both manual and commissioning naming methods
    """
    # Initialize main window
    qtbot.addWidget(main_gui)

    # Set general input
    qtbot.keyClicks(main_gui.lineEdit_inputImage, INPUT_IMAGE)
    qtbot.mouseClick(main_gui.buttonGroup_name.buttons()[button_name], QtCore.Qt.LeftButton)  # set naming method
    qtbot.mouseClick(main_gui.buttonGroup_guider.buttons()[1], QtCore.Qt.LeftButton)  # set to guider 1

    # Set practice information
    if type == 'commissioning':
        main_gui.comboBox_practice.setCurrentText(COM_PRACTICE_DIR)
        main_gui.comboBox_car.setCurrentText('OTE-13')
        main_gui.lineEdit_obs.setText('05')
        main_gui.pushButton_commid.click()

        assert main_gui.buttonGroup_name.buttons()[0].isChecked()
        assert main_gui.lineEdit_obs.text() == '05'
        assert main_gui.lineEdit_commid.text() == '1148'

        # Delete contents of directory to avoid auto-populating with old data
        delete_contents(main_gui.textEdit_name_preview.toPlainText())

    elif type == 'manual':
        qtbot.keyClicks(main_gui.lineEdit_root, ROOT)  # set root
        qtbot.keyClicks(main_gui.textEdit_out, __location__)  # set out directory
        qtbot.mouseClick(main_gui.buttonGroup_guider.buttons()[1], QtCore.Qt.LeftButton)
        qtbot.keyClicks(main_gui.lineEdit_manualid, '1148')
        qtbot.keyClicks(main_gui.lineEdit_manualobs, '05')
        qtbot.mouseClick(main_gui.pushButton_manualid, QtCore.Qt.LeftButton)

        assert main_gui.buttonGroup_name.buttons()[1].isChecked()
        assert main_gui.lineEdit_manualid.text() == '1148'
        assert main_gui.lineEdit_manualobs.text() == '05'
        assert main_gui.lineEdit_root.text() == ROOT
        assert main_gui.textEdit_out.toPlainText() == __location__

    assert main_gui.buttonGroup_guider.checkedButton().text() == '1'
    assert main_gui.program_id == 1148
    assert main_gui.observation_num == 5
    assert main_gui.visit_num == 1

    # Set detector
    main_gui.radioButton_NIRCam.setChecked(True)
    main_gui.comboBox_detector.setCurrentText('B2')
    assert main_gui.comboBox_detector.currentText() == 'B2'

    # Set threshold
    main_gui.lineEdit_threshold.clear()
    qtbot.keyClicks(main_gui.lineEdit_threshold, '0.9')

    # Go to segment guiding
    main_gui.groupBox_imageConverter.setChecked(False)
    main_gui.groupBox_starSelector.setChecked(False)
    main_gui.groupBox_fileWriter.setChecked(False)
    main_gui.groupBox_segmentGuiding.setChecked(True)

    # Set up SOF
    if filetype == 'SOF':
        qtbot.mouseClick(main_gui.radioButton_regfileSegmentGuiding, QtCore.Qt.LeftButton)
        assert main_gui.radioButton_regfileSegmentGuiding.isChecked()

        # Check the pre-populated data (path to root_dir, contents are 0 txt files)
        if type == 'commissioning':
            assert main_gui.lineEdit_regfileSegmentGuiding.text() == main_gui.textEdit_name_preview.toPlainText()
        elif type == 'manual':
            assert main_gui.lineEdit_regfileSegmentGuiding.text() == os.path.join(__location__, 'out', ROOT)
        assert main_gui.comboBox_guidingcommands.count() == 0

        # Change to path that has guiding selections files
        main_gui.lineEdit_regfileSegmentGuiding.clear()
        qtbot.keyClicks(main_gui.lineEdit_regfileSegmentGuiding, os.path.join(__location__, 'data'))
        qtbot.keyClick(main_gui.lineEdit_regfileSegmentGuiding, '\r')  # hit enter
        assert main_gui.lineEdit_regfileSegmentGuiding.text() == os.path.join(__location__, 'data')

        # Check the box that contains the COMMAND_FILE
        i = [i for i in range(main_gui.comboBox_guidingcommands.count()) if COMMAND_FILE.split('/')[-1] in
             main_gui.comboBox_guidingcommands.itemText(i)]
        main_gui.comboBox_guidingcommands.model().item(i[0], 0).setCheckState(QtCore.Qt.Checked)
        assert len(main_gui.comboBox_guidingcommands.checkedItems()) == 1
        assert COMMAND_FILE.split('/')[-1] in main_gui.comboBox_guidingcommands.checkedItems()[0].text()
        assert os.path.isfile(COMMAND_FILE)

    elif filetype == 'POF':
        qtbot.mouseClick(main_gui.radioButton_photometryOverride, QtCore.Qt.LeftButton)

    def handle_dialog():
        try:
            assert main_gui._test_sg_dialog.lineEdit_programNumber.text() == '1148'
            assert main_gui._test_sg_dialog.lineEdit_observationNumber.text() == '5'
            assert main_gui._test_sg_dialog.lineEdit_visitNumber.text() == '1'
            if filetype == 'SOF':
                assert main_gui._test_sg_dialog.lineEdit_RA.text() != ''
                assert main_gui._test_sg_dialog.lineEdit_Dec.text() != ''
                assert main_gui._test_sg_dialog.lineEdit_countrateUncertainty.text() == '0.9'
                assert main_gui._test_sg_dialog.comboBox_detector.currentText() == 'NRCB2'
            qtbot.mouseClick(main_gui._test_sg_dialog.buttonBox.button(QDialogButtonBox.Ok), QtCore.Qt.LeftButton)
        except AssertionError:
            # If something raising an error above, need to close the pop up gui anyway
            qtbot.mouseClick(main_gui._test_sg_dialog.buttonBox.button(QDialogButtonBox.Ok), QtCore.Qt.LeftButton)

    with qtbot.capture_exceptions() as exceptions:
        QtCore.QTimer.singleShot(500, handle_dialog)
        qtbot.mouseClick(main_gui.pushButton_run, QtCore.Qt.LeftButton, delay=1)

    if filetype == 'SOF':
        # check the lack of PA entry causes an error
        expected_err = 'could not convert string to float:'

    elif filetype == 'POF':
        # check the bad countrate value causes an error
        expected_err = 'Countrate factor out of range for count_rate_factor'

    assert expected_err in str(exceptions[0][1]), "Wrong error captured. Caught: '{}', Expected: '{}'".format(
        str(exceptions[0][1]), expected_err)


@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")
@pytest.mark.skipif(not SOGS, reason="SOGS naming not available")
@patch('jwst_magic.mainGUI.MainGui.mismatched_apt_guider_dialog', autospec=True)
def test_apt_guider_disagree_commissioning(mock_dialog, main_gui):
    """
    Check that if the APT program expects a guider that doesn't match
    the guider chosen in MAGIC, a pop up appears
    """
    # For commissioning method
    # Guider set after choosing CAR/Obs
    main_gui.buttonGroup_name.buttons()[0].setChecked(True)  # set commissioning naming method
    main_gui.comboBox_practice.setCurrentText(COM_PRACTICE_DIR)
    main_gui.comboBox_car.setCurrentText('OTE-07')
    main_gui.lineEdit_obs.setText('01')
    main_gui.pushButton_commid.click()

    # Check setting to the matching guider is fine
    main_gui.buttonGroup_guider.buttons()[1].click()  # set to guider 1
    assert mock_dialog.call_count == 0  # Check dialog box doesn't pop up

    # Check setting the wrong guider fails
    main_gui.buttonGroup_guider.buttons()[0].click()  # set to guider 2
    assert mock_dialog.called  # Check dialog box pops up

    # Check it works setting the guider before choosing CAR/Obs
    main_gui.lineEdit_obs.setText('02')
    assert mock_dialog.called  # Check dialog box pops up


@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")
@patch("jwst_magic.mainGUI.MainGui.mismatched_apt_guider_dialog", autospec=True)
def test_apt_guider_disagree_manual(mock_dialog, main_gui, test_directory):
    """
    Check that if the APT program expects a guider that doesn't match
    the guider chosen in MAGIC, a pop up appears
    """
    # For manual method
    # Guider set after choosing CAR/Obs
    main_gui.buttonGroup_name.buttons()[1].setChecked(True)  # set manual naming method
    main_gui.lineEdit_root.setText(ROOT)  # set root
    main_gui.textEdit_out.setText(__location__)  # set out directory
    main_gui.lineEdit_manualid.setText('1151')
    main_gui.lineEdit_manualobs.setText('01')
    main_gui.pushButton_manualid.click()

    # Check setting to the matching guider is fine
    main_gui.buttonGroup_guider.buttons()[1].click()  # set to guider 1
    assert mock_dialog.call_count == 0  # Check dialog box doesn't pop up

    # Check setting the wrong guider fails
    main_gui.buttonGroup_guider.buttons()[0].click()  # set to guider 2
    assert mock_dialog.called  # Check dialog box pops up

    # Check it works setting the guider before choosing CAR/Obs
    main_gui.lineEdit_manualobs.setText('02')
    main_gui.pushButton_manualid.click()
    assert mock_dialog.called  # Check dialog box pops up


@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")
def test_sg_commands(qtbot, main_gui):
    """
    Test that the segment guiding section of the GUI behaves as expected,
    particularly in terms of populating the checkable combobox
    """

    shifted_file = 'shifted_guiding_selections_test_main_G1_config1.txt'
    unshifted_file = 'unshifted_guiding_selections_test_main_G1_config1.txt'

    # Set General Input
    main_gui.buttonGroup_name.buttons()[1].setChecked(True)  # set manual naming method
    main_gui.lineEdit_root.setText(ROOT)  # set root
    main_gui.textEdit_out.setText(os.path.join(__location__, 'data'))  # set out directory
    main_gui.buttonGroup_guider.buttons()[1].click()  # set to guider 1

    # Go to segment guiding
    main_gui.groupBox_imageConverter.setChecked(False)
    main_gui.groupBox_starSelector.setChecked(False)
    main_gui.groupBox_fileWriter.setChecked(False)
    main_gui.groupBox_segmentGuiding.setChecked(True)

    # Check that the path in the lineedit_regfile_guiding is correct
    assert main_gui.lineEdit_regfileSegmentGuiding.text() == os.path.join(__location__, 'data', 'out', ROOT)

    # Check that the contents of the regfile star selector combobox are correct
    assert main_gui.comboBox_regfileStarSelector.count() == 0

    # Check that the contents of the checkable combobox is shifted only
    cmds = [main_gui.comboBox_guidingcommands.itemText(i) for i in range(main_gui.comboBox_guidingcommands.count())]
    assert len(cmds) == 1
    assert cmds[0] == 'Command 1: ' + shifted_file

    # Switch radio button to unshifted
    main_gui.buttonGroup_segmentGuiding_idAttitude.buttons()[1].click()
    assert main_gui.radioButton_unshifted.isChecked()

    # Check that the path in the lineedit_regfile_guiding hasn't changed
    assert main_gui.lineEdit_regfileSegmentGuiding.text() == os.path.join(__location__, 'data', 'out', ROOT)

    # Check that the contents of the checkable combobox is unshifted only
    cmds = [main_gui.comboBox_guidingcommands.itemText(i) for i in range(main_gui.comboBox_guidingcommands.count())]
    assert len(cmds) == 1
    assert cmds[0] == 'Command 1: ' + unshifted_file

    # Change the path and select a command
    main_gui.lineEdit_regfileSegmentGuiding.clear()
    qtbot.keyClicks(main_gui.lineEdit_regfileSegmentGuiding, os.path.join(__location__, 'data'))
    qtbot.keyClick(main_gui.lineEdit_regfileSegmentGuiding, '\r')  # hit enter
    assert main_gui.lineEdit_regfileSegmentGuiding.text() == os.path.join(__location__, 'data')

    i = [i for i in range(main_gui.comboBox_guidingcommands.count()) if COMMAND_FILE.split('/')[-1] in
         main_gui.comboBox_guidingcommands.itemText(i)]
    main_gui.comboBox_guidingcommands.model().item(i[0], 0).setCheckState(QtCore.Qt.Checked)
    assert len(main_gui.comboBox_guidingcommands.checkedItems()) == 1

    # Flip back to shifted and confirm the path is back to the original
    main_gui.buttonGroup_segmentGuiding_idAttitude.buttons()[0].click()
    assert main_gui.radioButton_shifted.isChecked()
    assert main_gui.lineEdit_regfileSegmentGuiding.text() == os.path.join(__location__, 'data', 'out', ROOT)

    # Flip back to unshifted and confirm the path is also back to the original and nothing is checked
    main_gui.buttonGroup_segmentGuiding_idAttitude.buttons()[1].click()
    assert main_gui.lineEdit_regfileSegmentGuiding.text() == os.path.join(__location__, 'data', 'out', ROOT)
    assert len(main_gui.comboBox_guidingcommands.checkedItems()) == 0


@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")
def test_shifted_data(main_gui):
    """
    Check that if shifted data is created, the following parts of
    the GUI are updated:
     -  "Use shifted to ID attitude" radio button in SG is selected
     - Contents of combobox are all shifted
     - Shifted file preview is interactive
    """
    shifted_file = 'shifted_guiding_selections_test_main_G1_config1.txt'
    unshifted_file = 'unshifted_guiding_selections_test_main_G1_config1.txt'

    # Set General Input
    main_gui.buttonGroup_name.buttons()[1].setChecked(True)  # set manual naming method
    main_gui.lineEdit_root.setText(ROOT)  # set root
    main_gui.textEdit_out.setText(os.path.join(__location__, 'data'))  # set out directory
    main_gui.buttonGroup_guider.buttons()[1].click()  # set to guider 1

    # Go to segment guiding
    main_gui.groupBox_imageConverter.setChecked(False)
    main_gui.groupBox_starSelector.setChecked(False)
    main_gui.groupBox_fileWriter.setChecked(False)
    main_gui.groupBox_segmentGuiding.setChecked(True)

    # Check that since shifted data is in the out/root directory, that's the default radio button selected
    assert main_gui.radioButton_shifted.isChecked()

    # Check that the path in the lineedit_regfile_guiding is correct
    assert main_gui.lineEdit_regfileSegmentGuiding.text() == os.path.join(__location__, 'data', 'out', ROOT)

    # Check that the contents of the checkable combobox is shifted only
    cmds = [main_gui.comboBox_guidingcommands.itemText(i) for i in range(main_gui.comboBox_guidingcommands.count())]
    assert len(cmds) == 1
    assert cmds[0] == 'Command 1: ' + shifted_file

    # Check file previews
    assert main_gui.comboBox_showcommandsconverted.isEnabled()
    assert main_gui.comboBox_showcommandsshifted.isEnabled()

    # Check 1 option is available in converted image preview
    convert_cmds = [main_gui.comboBox_showcommandsconverted.itemText(i) for i in
                    range(main_gui.comboBox_showcommandsconverted.count())]
    assert len(convert_cmds) == 2
    assert convert_cmds[0] == '- Guiding Command -'
    assert convert_cmds[1] == 'Command 1: ' + unshifted_file

    # Check 1 option is available in shifted image preview
    shift_cmds = [main_gui.comboBox_showcommandsshifted.itemText(i) for i in
                  range(main_gui.comboBox_showcommandsshifted.count())]
    assert len(shift_cmds) == 1
    assert shift_cmds[0] == 'Command 1: ' + shifted_file


@pytest.mark.skipif(JENKINS, reason="Can't import PyQt5 on Jenkins server.")
@pytest.mark.skipif(not SOGS, reason="SOGS naming not available")
def test_commissioning_naming_input_errors(qtbot, main_gui):
    """Test that the correct errors come up when bad inputs are loaded in commissioning naming"""

    # Initialize main window
    qtbot.addWidget(main_gui)

    # Set general input
    qtbot.mouseClick(main_gui.buttonGroup_name.buttons()[0], QtCore.Qt.LeftButton)  # set naming method
    qtbot.mouseClick(main_gui.buttonGroup_guider.buttons()[0], QtCore.Qt.LeftButton)  # set to guider 2
    main_gui.comboBox_practice.setCurrentText(COM_PRACTICE_DIR)
    main_gui.comboBox_car.setCurrentText('OTE-13')
    main_gui.lineEdit_obs.setText('01')

    # Set up file name issue (with a good normalization)
    main_gui.lineEdit_inputImage.setText(INPUT_IMAGE)
    main_gui.comboBox_normalize.setCurrentText('FGS Magnitude')
    main_gui.lineEdit_normalize.setText('14')
    main_gui.pushButton_delbackgroundStars.click()

    with qtbot.capture_exceptions() as exceptions:
        qtbot.mouseClick(main_gui.pushButton_run, QtCore.Qt.LeftButton, delay=1)

    expected_err = "but the user has read in a file that is not a cal.fits file or a padded trk image"
    assert expected_err in str(exceptions[0][1]), \
        f"Wrong error captured. Caught: '{str(exceptions[0][1])}', Expected: '{expected_err}'"

    # Set up count rate issue (with a good image)
    main_gui.lineEdit_inputImage.setText(INPUT_IMAGE2)
    main_gui.comboBox_normalize.setCurrentText('FGS countrate')
    main_gui.lineEdit_normalize.setText('4000000')
    main_gui.pushButton_delbackgroundStars.click()

    with qtbot.capture_exceptions() as exceptions:
        qtbot.mouseClick(main_gui.pushButton_run, QtCore.Qt.LeftButton, delay=1)

    expected_err = "but the user has set the normalization to FGS Countrate"
    assert expected_err in str(exceptions[0][1]), \
        f"Wrong error captured. Caught: '{str(exceptions[0][1])}', Expected: '{expected_err}'"
