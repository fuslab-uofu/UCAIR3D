import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets
import numpy as np

from PyQt5.QtWidgets import QVBoxLayout, QFrame, QLabel, QMessageBox
from PyQt5.QtCore import Qt

from enumerations import ViewDir


class Viewport(QFrame):
    """
    A Viewport that uses PyQtGraph to display 2D slices of 3D radiology images.
    Allows scrolling through slices using arrow keys, interactively displaying coordinates,
    and updating voxel values when the user draws (Shift + Left Mouse Click).
    """

    def __init__(self, parent, id, view_dir_, num_vols, coords_outside_, zoom_method_, pan_method_,
                 window_method_=None):
        super(Viewport, self).__init__(parent)

        # Identifying info
        self.parent = parent  # main window
        self.id = id
        self.view_dir = view_dir_.dir  # ViewDir.AX, ViewDir.SAG, ViewDir.COR

        # List of references to the volume(s) being displayed in viewport
        self.volume_stack = [None] * num_vols
        self.slice_stack = [None] * num_vols

        # For controlling slice scrolling
        self.current_display_index = 0
        self.max_display_index = 0

        # Replace Matplotlib with PyQtGraph ImageView
        self.image_view = pg.ImageView()
        self.image_view.ui.roiBtn.hide()
        self.image_view.ui.menuBtn.hide()

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.image_view)

        self.coords_outside = coords_outside_
        if self.coords_outside:
            self.coords_label = QLabel()
            self.coords_label.setMinimumWidth(200)
            self.coords_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.coords_label.setStyleSheet("#coords_label {background-color: black; font-size:10px; color: white;}")
            self.main_layout.addWidget(self.coords_label)

        self.setLayout(self.main_layout)
        self.setStyleSheet("#Viewport {border: 1px solid gray; background-color: black;}")

        # Track painting state
        self.is_painting = False

        # Mouse event connections for scrolling and dragging
        self.image_view.view.mouseDragEvent = self.mouse_drag_event

        # Enable keyboard focus so we can capture key events
        self.setFocusPolicy(Qt.StrongFocus)

        self.voxel_coords = None

    def update_volume_stack(self, new_volume, stack_position):
        """Update the volume stack with a new volume in the specified position."""
        self.volume_stack[stack_position] = new_volume

        if new_volume is not None:
            if self.view_dir == ViewDir.AX.dir:
                self.max_display_index = new_volume.num_slices
            elif self.view_dir == ViewDir.SAG.dir:
                self.max_display_index = new_volume.num_cols
            else:  # "COR"
                self.max_display_index = new_volume.num_rows

            self.current_display_index = self.max_display_index // 2
        self.refresh_plot()

    def refresh_plot(self):
        """Refresh the viewport when slice or other parameters change."""
        for ind, vol in enumerate(self.volume_stack):
            if vol is not None and vol.visible:
                self.slice_stack[ind] = vol.get_slice(self.view_dir, self.current_display_index)
                if self.slice_stack[ind] is None:
                    QMessageBox.warning(self, "Oh snap!", "Problem getting volume slice.", QMessageBox.Ok)
                    return
                self.image_view.setImage(self.slice_stack[ind], autoRange=False, autoLevels=False)
                self.image_view.getImageItem().getViewBox().invertY(False)

    def mouse_drag_event(self, event):
        """Handle mouse drag events for drawing or panning."""
        if all(obj is None for obj in self.slice_stack):
            return

        if self.parent.is_painting:
            # If painting mode is enabled, paint voxels during drag
            if event.isStart():
                print("Starting drag to paint")
            event.accept()

            coords = self.image_view.getImageItem().mapFromScene(event.pos())
            cursor_plot_col = int(coords.x())
            cursor_plot_row = int(coords.y())

            print(f' col: {cursor_plot_col}, row: {cursor_plot_row}')

            if cursor_plot_col is not None and cursor_plot_row is not None:
                voxel_ijk = self.volume_stack[0].screenxy_to_imageijk(self.view_dir, cursor_plot_col,
                                                                      cursor_plot_row,
                                                                      self.current_display_index)
                if voxel_ijk is not None:
                    # Update voxel value
                    self.update_voxel_value(voxel_ijk, 1000)
            if event.isFinish():
                print("Finished drag to paint")

        else:
            # If painting mode is not enabled, perform default panning behavior
            event.ignore()

    def update_voxel_value(self, voxel, new_value):
        """
        Update the voxel at the given (i, j, k) coordinates in the 3D volume.
        """
        i, j, k = voxel
        for ind, vol in enumerate(self.volume_stack):
            if vol is not None and vol.visible:
                vol.data[i, j, k] = new_value
                self.slice_stack[ind] = vol.get_slice(self.view_dir, self.current_display_index)
                self.refresh_plot()

    def keyPressEvent(self, event):
        """Handle key press events for scrolling through slices with up and down arrow keys."""
        if event.key() == Qt.Key_Up:
            self.current_display_index += 1
        elif event.key() == Qt.Key_Down:
            self.current_display_index -= 1

        self.current_display_index = np.clip(self.current_display_index, 0, self.max_display_index - 1)
        self.refresh_plot()
        event.accept()

