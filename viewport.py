import sys
import nibabel as nib
import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QLabel
from enumerations import ViewDir

class ColorImageView(pg.ImageView):
    """
    Wrapper around the ImageView to create a color lookup
    table automatically as there seem to be issues with displaying
    color images through pg.ImageView.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lut = None

    def updateImage(self, autoHistogramRange=True):
        super().updateImage(autoHistogramRange)
        self.getImageItem().setLookupTable(self.lut)


class MRIViewer(QWidget):
    def __init__(self, nii_file, parent, id, view_dir_, num_vols, coords_outside_, zoom_method_, pan_method_, window_method_=None):
        super().__init__()

        # Store the provided arguments
        self.parent = parent
        self.id = id
        self.view_dir = view_dir_
        self.num_vols = num_vols
        self.coords_outside = coords_outside_
        self.zoom_method = zoom_method_
        self.pan_method = pan_method_
        self.window_method = window_method_

        self.volume_stack = [None] * num_vols

        self.custom_colors_rgba_f = [
            [0.0, 0.0, 0.0],  # background
            [0.89411765, 0.10196078, 0.10980392],  # red
            [0.21568627, 0.49411765, 0.72156863],  # blue
            [0.30196078, 0.68627451, 0.29019608],  # green
            [0.59607843, 0.30588235, 0.63921569],  # purple
            [1., 0.49803922, 0.],                  # orange
            [1., 1., 0.2],                         # yellow
            [0.65098039, 0.3372549, 0.15686275],   # brown
            [0.96862745, 0.50588235, 0.74901961],  # pink
            [0.6, 0.6, 0.6]]                       # gray
        self.custom_colors_rgb_i = np.array(self.custom_colors_rgba_f) * 255
        self.custom_colors_rgb_i = self.custom_colors_rgb_i.astype(np.uint8)

        # Create main layout for this widget
        main_layout = QVBoxLayout(self)

        # Label to display coordinates (Move it here, above the image view)
        self.coordinates_label = QLabel("Coordinates: ", self)
        main_layout.addWidget(self.coordinates_label)

        # Create PyQtGraph ImageView for axial plane
        self.axial_view = ColorImageView()
        main_layout.addWidget(self.axial_view)

        # Create buttons for painting, saving, and toggling the histogram
        button_layout = QHBoxLayout()

        self.paint_button = QPushButton("Toggle Paint Mode")
        self.paint_button.clicked.connect(self.toggle_painting_mode)
        button_layout.addWidget(self.paint_button)

        self.save_button = QPushButton("Save Overlay to Voxels")
        self.save_button.clicked.connect(self.save_overlay_to_voxels)
        button_layout.addWidget(self.save_button)

        # Button to toggle the visibility of the histogram
        self.histogram_button = QPushButton("Toggle Histogram")
        self.histogram_button.clicked.connect(self.toggle_histogram)
        button_layout.addWidget(self.histogram_button)

        # Add the button layout below the ImageView
        main_layout.addLayout(button_layout)

        # Add the overlay image to the same view
        self.overlay_item = pg.ImageItem()
        self.axial_view.view.addItem(self.overlay_item)

        self.axial_view.getView().scene().sigMouseMoved.connect(self.mouse_moved)
        self.axial_view.timeLine.sigPositionChanged.connect(lambda: self.update_overlay(int(self.axial_view.currentIndex)))

        self.base_lut = pg.colormap.get('viridis').getLookupTable(0.0, 1.0, 256)
        self.overlay_lut = self.custom_colors_rgb_i

        # Crosshair visibility flag
        self.show_crosshairs = False

        # Create crosshair lines (invisible initially)
        self.horizontal_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('r', width=0.5), movable=False)
        self.vertical_line = pg.InfiniteLine(angle=90, pen=pg.mkPen('r', width=0.5), movable=False)
        self.axial_view.addItem(self.horizontal_line, ignoreBounds=True)
        self.axial_view.addItem(self.vertical_line, ignoreBounds=True)
        # self.toggle_crosshair_visibility(False)  # Initially hide crosshairs

        # Create a brush/kernel to use for drawing
        # self.kernel = np.array([
        #     [1, 1, 1],
        #     [1, 1, 1],
        #     [1, 1, 1]
        # ])
        radius = 2
        self.kernel = self.create_circular_kernel(radius)
        # Update the views with initial slices and colormap
        self.refresh()

    def create_circular_kernel(self, radius):
        """Create a circular kernel with the specified radius."""
        size = 2 * radius + 1  # Ensure the kernel is large enough to contain the circle
        kernel = np.zeros((size, size), dtype=np.uint8)

        # Calculate the center of the kernel
        center = radius

        # Iterate over the kernel's grid and fill in a circle
        for y in range(size):
            for x in range(size):
                # Calculate distance from the center
                distance = np.sqrt((x - center) ** 2 + (y - center) ** 2)
                if distance <= radius:
                    kernel[y, x] = 1

        return kernel


    def update_overlay(self, index):
        """Update the overlay image with the corresponding slice from the segmentation data."""
        if self.volume_stack[2] is not None:
            overlay_slice = self.volume_stack[2].data[index, :, :]
            self.overlay_item.setImage(overlay_slice)
            self.overlay_item.setLookupTable(self.overlay_lut)

    def toggle_crosshairs(self):
        """Toggle crosshair visibility."""
        self.show_crosshairs = not self.show_crosshairs
        self.toggle_crosshair_visibility(self.show_crosshairs)

    def toggle_crosshair_visibility(self, visible):
        """Show or hide crosshair lines."""
        self.horizontal_line.setVisible(visible)
        self.vertical_line.setVisible(visible)

    def mouse_moved(self, pos):

        img_item = self.axial_view.getImageItem()
        if img_item is not None and img_item.sceneBoundingRect().contains(pos):
            # Transform the scene coordinates to image coordinates
            mouse_point = img_item.mapFromScene(pos)
            img_shape = self.volume_stack[0].data.shape
            x = int(mouse_point.x())
            y = int(mouse_point.y())
            z = int(self.axial_view.currentIndex)  # Get the current slice index

            # Ensure coordinates are within image bounds
            if 0 <= x < img_shape[1] and 0 <= y < img_shape[0]:
                voxel_value = self.volume_stack[0].data[y, x, z]
                coordinates_text = "Coordinates: x={:3d}, y={:3d}, z={:3d}, Voxel Value: {:4.2f}".format(x, y, z,
                                                                                                          voxel_value)
                self.coordinates_label.setText(coordinates_text)
                # self.coordinates_label.setText(f"Coordinates: x={x}, y={y}, z={z}, Voxel Value: {voxel_value}")
                # Update crosshair position if crosshairs are enabled
                # if self.show_crosshairs:
            else:
                self.coordinates_label.setText("")

            self.horizontal_line.setPos(y)
            self.vertical_line.setPos(x)

        else:
            self.coordinates_label.setText("")

    def update_volume_stack(self, new_volume, stack_position):
        """Update the volume stack with a new volume in the specified position."""
        self.volume_stack[stack_position] = new_volume

        self.refresh()

    def refresh(self):
        # Apply segmentation data with fixed levels to match the number of unique values
        if self.volume_stack[0] is not None:
            self.axial_view.setImage(self.volume_stack[0].data.T, levels=(0, 255))
            self.axial_view.getImageItem().getViewBox().invertY(False)
            self.axial_view.getImageItem().setLookupTable(self.base_lut)

        if self.volume_stack[2] is not None:
            # Extract the slice from the overlay image corresponding to the current slice of the base image
            overlay_slice = self.volume_stack[2].data[:, :, int(self.axial_view.currentIndex)]
            # Set the data for the overlay ImageItem
            self.overlay_item.setImage(overlay_slice, opacity=0.5)  # Adjust opacity for transparency
            self.overlay_item.setLookupTable(self.overlay_lut)

            # # self.axial_view.addItem(self.volume_stack[2])
            # # Customize the histogram to reflect discrete colors
            # histogram = self.axial_view.getHistogramWidget()
            # gradient_editor = histogram.gradient
            #
            # # Remove the default continuous gradient and set up discrete ticks
            # gradient_state = {
            #     'mode': 'rgb',
            #     'ticks': [
            #         (0.0, (0, 0, 0, 255)),  # Black for value 0
            #         (0.5, (255, 0, 0, 255)),  # Red for value 1
            #         (1.0, (0, 255, 0, 255))  # Green for value 2
            #     ]
            # }
            #
            # # Apply the new gradient state with discrete ticks
            # gradient_editor.restoreState(gradient_state)

        self.axial_view.show()

    def toggle_painting_mode(self):
        """Toggle between painting and normal modes."""
        self.is_painting = not getattr(self, 'is_painting', False)  # Initialize if not defined
        if self.is_painting:
            # Set the kernel (brush) for drawing
            # self.overlay_item.setDrawKernel(self.kernel, mask=None, center=(1, 1), mode='set')
            self.overlay_item.setDrawKernel(self.kernel, mask=None, center=(1, 1), mode='set')
        else:
            # Disable drawing
            self.overlay_item.setDrawKernel(None)

    def save_overlay_to_voxels(self):
        """Update the underlying voxel data with the painted pixels in the overlay."""
        # Extract the current image from the ImageItem (this includes the painted pixels)
        painted_image = np.rot90(self.axial_view.image)

        # Update the voxel data at the current axial slice with the painted pixels
        self.segmentation_data = painted_image

        # Optional: Refresh the view to show the updated voxel data
        self.refresh()

        # Optional: Save the updated NIfTI file back to disk
        updated_img = nib.Nifti1Image(self.segmentation_data, self.nii_img.affine)
        nib.save(updated_img, 'updated_segmentation.nii')
        print("Overlay saved to voxels and NIfTI file updated.")

    def toggle_histogram(self):
        """Toggle the visibility of the histogram."""
        histogram = self.axial_view.getHistogramWidget()
        is_visible = histogram.isVisible()
        histogram.setVisible(not is_visible)
        self.axial_view.ui.menuBtn.setVisible(not is_visible)
        self.axial_view.ui.roiBtn.setVisible(not is_visible)

    def hide_histogram_buttons(self):
        """Hide the ROI and MENU buttons in the histogram widget."""
        histogram = self.axial_view.getHistogramWidget()
        histogram.ui.roiBtn.hide()  # Hide the ROI button
        histogram.ui.menuBtn.hide()  # Hide the MENU button

