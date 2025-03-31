"""
    UCAIR3D
"""

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QMainWindow

import sys
import os
import config

# project classes and modules
from UCAIR3DMainWindow import Ui_MainWindow
from viewport import Viewport
from enumerations import ViewDir


class UCAIR3D(QMainWindow):
    """
    what

    """

    def __init__(self, input_args=None):
        super().__init__()

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.vp_1 = Viewport(self, vp_id='vp_1', view_dir=ViewDir.AX, num_vols=4)
        self.ui.ul_viewport_frame.layout().addWidget(self.vp_1)



if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    # stylesheet for UI look and feel
    with open(os.path.join(config.QSS_PATH, "breezeDarkStylesheet.qss"), 'r') as file:
        stylesheet = file.read()
    # replace relative paths in the stylesheet with the absolute path
    stylesheet = stylesheet.replace('../icons', config.ICON_PATH.replace('\\', '/'))
    app.setStyleSheet(stylesheet)

    mainWindow = UCAIR3D(config.ARGS)

    mainWindow.show()
    sys.exit(app.exec_())
