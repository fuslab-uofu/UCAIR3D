"""
Minimal PyQt5 app that embeds your Viewport and adds a File>Open action
(or toolbar button) to load a NIfTI file into an Image3D and display it.

Run:
    python demo_viewport_load_nifti.py

Dependencies:
    pip install PyQt5 pyqtgraph nibabel numpy
"""

import sys
from pathlib import Path

import nibabel as nib
import pyqtgraph as pg

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QFileDialog,
    QAction,
    QToolBar,
    QMessageBox,
)
from PyQt5.QtCore import Qt

# --- Import your library pieces -------------------------------------------------
try:
    from ucair3d.components.viewport import Viewport  # type: ignore
    from ucair3d.enumerations import ViewDir  # type: ignore
    from ucair3d.components.image3D import Image3D  # type: ignore
except Exception:
    sys.path.append(str(Path(__file__).resolve().parent))
    from viewport import Viewport  # type: ignore
    from enumerations import ViewDir  # type: ignore
    from components.image3D import Image3D  # type: ignore


# --- Helper ---------------------------------------------------------------------

def nifti_to_image3d(nifti_path: str, parent) -> Image3D:
    """Load NIfTI from file path into an Image3D object."""
    img = nib.load(nifti_path)
    im3d = Image3D(parent)
    im3d.populate_with_nifti(img, nifti_path)
    return im3d


# --- Main Window ----------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UCAIR3D — Simple Viewport Demo")
        self.resize(1200, 800)

        # Viewport expects parent to have .debug_mode
        self.debug_mode = False

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        self.vp = Viewport(
            parent=self,
            vp_id="vp_ax",
            view_dir=ViewDir.AX,
            num_vols=3,
        )
        layout.addWidget(self.vp)

        self._build_menu_and_toolbar()

    def _build_menu_and_toolbar(self):
        open_act = QAction("Open NIfTI…", self)
        open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self.action_open_nifti)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(open_act)

        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.addAction(open_act)
        self.addToolBar(Qt.TopToolBarArea, tb)

    def action_open_nifti(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open NIfTI",
            str(Path.home()),
            "NIfTI files (*.nii *.nii.gz);;All files (*.*)",
        )
        if not path:
            return
        try:
            im3d = nifti_to_image3d(path, parent=self.vp)
        except Exception as e:
            QMessageBox.critical(self, "Failed to Load NIfTI", f"{e}")
            return

        self.vp.add_layer(im3d, stack_position=0)


# --- Entrypoint -----------------------------------------------------------------

def main():
    pg.setConfigOptions(useOpenGL=False, antialias=True)
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
