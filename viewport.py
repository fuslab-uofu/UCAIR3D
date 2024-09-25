import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QLabel
from PyQt5.QtGui import QIcon, QFont


class ColorImageView(pg.ImageView):
    """
    Wrapper around the ImageView to create a color lookup
    table automatically
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lut = None

    def updateImage(self, autoHistogramRange=True):
        super().updateImage(autoHistogramRange)
        self.getImageItem().setLookupTable(self.lut)


class MRIViewer(QWidget):
    def __init__(self, nii_file, parent, id, view_dir_, num_vols, coords_outside_, zoom_method_, pan_method_,
                 window_method_=None):
        super().__init__()

        self.parent = parent
        self.id = id
        self.view_dir = view_dir_
        self.num_vols = num_vols
        self.coords_outside = coords_outside_
        self.zoom_method = zoom_method_
        self.pan_method = pan_method_
        self.window_method = window_method_
        self.volume_stack = [None] * num_vols

        # FIXME: temp during dev. These will be set by the main app
        self.overlay_lut = np.array(
            [[0, 0, 0, 0],  # black
             [228, 25, 27, 255],  # red
             [54, 126, 184, 255],  # blue
             [76, 175, 74, 255],  # green
             [151, 77, 163, 255],  # purple
             [255, 127, 0, 255],  # orange
             [255, 255, 51, 255],  # yellow
             [165, 85, 40, 255],  # brown
             [246, 128, 191, 255]],  # pink
            dtype='uint8')

        # the main layout for this widget
        main_layout = QVBoxLayout(self)

        # horizontal layout for the coordinates label and buttons
        top_layout = QHBoxLayout()
        # coordinates label
        self.coordinates_label = QLabel("Coordinates: ", self)
        font = QFont("Segoe UI", 9)
        font.setItalic(True)
        self.coordinates_label.setFont(font)
        top_layout.addWidget(self.coordinates_label)

        # add spacing between the buttons and right edge
        top_layout.addStretch()

        # histogram visibility button
        self.histogram_button = QPushButton()
        self.histogram_button.setCheckable(True)
        self.histogram_button.setChecked(False)
        self.histogram_button.setFixedSize(24, 24)
        histogram_icon = QIcon("..\\ui\\colorWheelIcon.svg")
        self.histogram_button.setIcon(histogram_icon)
        self.histogram_button.clicked.connect(self.toggle_histogram)
        top_layout.addWidget(self.histogram_button)

        # crosshair visibility button
        self.crosshair_button = QPushButton()
        self.crosshair_button.setCheckable(True)
        self.crosshair_button.setFixedSize(24, 24)
        crosshair_icon = QIcon("..\\ui\\crosshair_white_icon.svg")
        self.crosshair_button.setIcon(crosshair_icon)
        self.crosshair_button.clicked.connect(self.toggle_crosshairs)
        top_layout.addWidget(self.crosshair_button)



        # add the top layout to the main layout (above the imageView)
        main_layout.addLayout(top_layout)

        # ImageView for axial plane
        self.axial_view = ColorImageView()
        self.axial_view.getHistogramWidget().setVisible(False)
        self.axial_view.ui.menuBtn.setVisible(False)  # hide these for now
        self.axial_view.ui.roiBtn.setVisible(False)  # hide these for now
        main_layout.addWidget(self.axial_view)

        # layout for painting and saving buttons (placed below the ImageView)
        button_layout_bottom = QHBoxLayout()
        self.paint_button = QPushButton("Toggle Paint Mode")
        self.paint_button.clicked.connect(self.toggle_painting_mode)
        button_layout_bottom.addWidget(self.paint_button)
        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self.save_overlay_to_voxels)
        button_layout_bottom.addWidget(self.save_button)
        main_layout.addLayout(button_layout_bottom)

        # This is the main (background/base) image
        self.main_image_3D = None

        # Add the overlay image to the same view
        self.seg_image_3D = None
        self.seg_image_2D = pg.ImageItem()
        self.axial_view.view.addItem(self.seg_image_2D)

        self.axial_view.getView().scene().sigMouseMoved.connect(self.mouse_moved)
        self.axial_view.timeLine.sigPositionChanged.connect(
            lambda: self.update_overlay(int(self.axial_view.currentIndex)))

        # Create crosshair lines (invisible initially)
        self.horizontal_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('r', width=0.5), movable=False)
        self.vertical_line = pg.InfiniteLine(angle=90, pen=pg.mkPen('r', width=0.5), movable=False)
        self.axial_view.addItem(self.horizontal_line, ignoreBounds=True)
        self.axial_view.addItem(self.vertical_line, ignoreBounds=True)
        # crosshair visibility flag
        self.show_crosshairs = False
        self.horizontal_line.setVisible(self.show_crosshairs)
        self.vertical_line.setVisible(self.show_crosshairs)

        # Create a brush/kernel to use for drawing
        self.kernel = np.array([
            [1, 1, 1],
            [1, 1, 1],
            [1, 1, 1]
        ])

        # radius = 2
        # self.kernel = self.create_circular_kernel(radius)
        # Update the views with initial slices and colormap
        # self.refresh()

        self.axial_view.imageItem.mouseClickEvent = self.mouse_click_event

    def mouse_click_event(self, event):
        # Paint action modifies self.temp_image (3D array) at the current slice
        if self.is_painting:
            # Get current slice from ImageView
            current_slice = int(self.axial_view.currentIndex)
            print(current_slice)

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

    def toggle_crosshairs(self):
        """Toggle crosshair visibility."""
        self.show_crosshairs = not self.show_crosshairs
        self.horizontal_line.setVisible(self.show_crosshairs)
        self.vertical_line.setVisible(self.show_crosshairs)

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
            if 0 <= x < img_shape[0] and 0 <= y < img_shape[1] and 0 <= z < img_shape[2]:
                voxel_value = self.volume_stack[0].data[x, y, z]
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
        if stack_position == 0:
            # Update the main item with the new volume data
            self.main_image_3D = np.transpose(self.volume_stack[0].data, (2, 0, 1))
        if stack_position == 2:
            # Update the overlay item with the new volume data
            self.seg_image_3D = np.transpose(self.volume_stack[2].data, (2, 0, 1))
            # self.seg_image_3D = self.volume_stack[2].data

        self.refresh()

    def update_overlay(self, index):
        """Update the overlay image with the corresponding slice from the segmentation data."""
        if self.seg_image_3D is not None:
            # overlay_slice = self.seg_image_3D[int(self.axial_view.currentIndex), :, :]
            overlay_slice = self.seg_image_3D[int(self.axial_view.currentIndex), :, :]
            # Set the data for the overlay ImageItem
            self.seg_image_2D.setImage(overlay_slice, opacity=1.0)  # Adjust opacity for transparency
            self.seg_image_2D.setLevels([0, 8])
            self.seg_image_2D.setLookupTable(self.overlay_lut)
            # self.seg_image_2D.getViewBox().invertY(False)
            # self.seg_image_2D.getViewBox().invertX(True)

    def refresh(self):
        if self.main_image_3D is not None:
            self.axial_view.setImage(self.main_image_3D, levels=(0, 255))
            self.axial_view.getImageItem().getViewBox().invertY(False)
            self.axial_view.getImageItem().getViewBox().invertX(True)

        self.update_overlay(self.axial_view.currentIndex)

        self.axial_view.show()

    def toggle_painting_mode(self):
        """Toggle between painting and normal modes."""
        self.is_painting = not getattr(self, 'is_painting', False)  # Initialize if not defined
        if self.is_painting:
            # Set the kernel (brush) for drawing
            # self.seg_image_2D.setDrawKernel(self.kernel, mask=None, center=(1, 1), mode='set')
            self.seg_image_2D.setDrawKernel(self.kernel, mask=None, center=(1, 1), mode='set')
        else:
            # Disable drawing
            self.seg_image_2D.setDrawKernel(None)

    def save_overlay_to_voxels(self):
        """Update the underlying voxel data with the painted pixels in the overlay."""
        pass

    def toggle_histogram(self):
        """Toggle the visibility of the histogram."""
        histogram = self.axial_view.getHistogramWidget()
        is_visible = histogram.isVisible()
        histogram.setVisible(not is_visible)


    def hide_histogram_buttons(self):
        """Hide the ROI and MENU buttons in the histogram widget."""
        histogram = self.axial_view.getHistogramWidget()
        histogram.ui.roiBtn.hide()  # Hide the ROI button
        histogram.ui.menuBtn.hide()  # Hide the MENU button
