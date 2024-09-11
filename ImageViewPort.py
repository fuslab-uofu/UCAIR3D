from PyQt5.QtWidgets import QVBoxLayout, QWidget, QMessageBox

from enumerations import ViewDir
import pyqtgraph as pg
import numpy as np


class ImageViewPort(QWidget):
    def __init__(self, parent, id, view_dir_, num_vols, coords_outside_, zoom_method_, pan_method_,
                 window_method_=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.image_view = pg.ImageView()
        self.layout.addWidget(self.image_view)
        self.setLayout(self.layout)

        self.nii_data = None

        # identifying info
        self.parent = parent  # main window
        self.id = id
        self.view_dir = view_dir_.dir  # ViewDir.AX, ViewDir.SAG, ViewDir.COR

        # list of references to the volume(s) being displayed in viewport
        self.volume_stack = [None] * num_vols
        # the actual 2D slice of data
        self.slice_stack = [None] * num_vols
        # list of Matplotlib imshow plot objects being displayed in the viewport
        self.layer_stack = [None] * num_vols

        # for controlling slice scrolling
        self.current_display_index = 0  # in this context, can refer to row slice, col slice, or "slice slice" (lol )
        self.max_display_index = 0

        # for interactive windowing
        self.mouse_x = 0
        self.mouse_y = 0

        # this essentially is activating the pan or zoom actions if the mouse button has been pressed.
        self.status = "idle"
        self.zoom_method = zoom_method_
        self.pan_method = pan_method_
        self.window_method = window_method_

        # for syncronizing and resetting zoom and pan
        self.initial_extent = None

        self.image_view.scene.sigMouseClicked.connect(self.mouse_clicked)

    def update_volume_stack(self, new_volume, stack_position):
        """ Update the volume stack with a new volume in the specified position. """
        self.volume_stack[stack_position] = new_volume

        self.nii_data = new_volume.data

        if new_volume is not None:
            # for controlling slice scrolling
            if self.view_dir == ViewDir.AX.dir:
                self.max_display_index = new_volume.num_slices
            elif self.view_dir == ViewDir.SAG.dir:
                self.max_display_index = new_volume.num_cols
            else:  # "COR"
                self.max_display_index = new_volume.num_rows

            # for convenience, jump to middle slice
            self.current_display_index = (self.max_display_index // 2)

        self.mouse_x = 0
        self.mouse_y = 0

        self.refresh_plot()

    def refresh_plot(self):
        for ind, vol in enumerate(self.volume_stack):
            if vol is not None and vol.visible:
                self.slice_stack[ind] = vol.get_slice(self.view_dir, self.current_display_index)
                if self.slice_stack[ind] is None:
                    QMessageBox.warning(self, "Oh snap!", "Problem getting volume slice.", QMessageBox.Ok)
                    return
                if self.slice_stack[ind] is not None:
                    self.image_view.setImage(np.flipud(self.slice_stack[ind]))

    def mouse_clicked(self, event):
        mouse_point = self.image_view.getImageItem().mapFromScene(event.scenePos())
        x = int(mouse_point.x())
        y = int(mouse_point.y())
        print(f"Mouse clicked at: {x}, {y}")
