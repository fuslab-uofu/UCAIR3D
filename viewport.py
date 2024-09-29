import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QLabel, QSlider
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt

from enumerations import ViewDir


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
        if self.lut is not None:
            self.getImageItem().setLookupTable(self.lut)


class Viewport(QWidget):
    def __init__(self, parent, id, view_dir_, num_vols, coords_outside_, zoom_method_, pan_method_,
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

        self.is_painting = False

        # Store the markers added by the user
        self.markers = []
        self.dragging_marker = None

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
        self.crosshair_button.setIconSize(self.crosshair_button.size())
        self.crosshair_button.clicked.connect(self.toggle_crosshairs)
        top_layout.addWidget(self.crosshair_button)

        # add the top layout to the main layout (above the imageView)
        main_layout.addLayout(top_layout)

        image_view_layout = QHBoxLayout()
        # ImageView for axial view
        self.axial_view = ColorImageView()
        self.axial_view.getHistogramWidget().setVisible(False)
        self.axial_view.ui.menuBtn.setVisible(False)  # hide these for now
        self.axial_view.ui.roiBtn.setVisible(False)  # hide these for now
        image_view_layout.addWidget(self.axial_view, stretch=2)

        # transparency slider for the base layer (vertical orientation)
        slider_layout = QVBoxLayout()
        # self.opacity_label = QLabel("Opacity")
        # slider_layout.addWidget(self.opacity_label, alignment=Qt.AlignHCenter)
        self.opacity_slider = QSlider(Qt.Vertical)
        # self.opacity_slider.setFixedWidth(20)
        self.opacity_slider.setRange(0, 100)  # Slider values from 0 to 100
        self.opacity_slider.setValue(100)  # Default to fully opaque
        self.opacity_slider.setTickPosition(QSlider.TicksRight)
        self.opacity_slider.setTickInterval(10)
        self.opacity_slider.valueChanged.connect(self.update_opacity)
        slider_layout.addWidget(self.opacity_slider, alignment=Qt.AlignHCenter)
        image_view_layout.addLayout(slider_layout, stretch=0)
        self.opacity_slider.setVisible(False)

        # add image_view_layout to the main layout
        main_layout.addLayout(image_view_layout)

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

        # create a brush (kernel) to use for drawing
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

    def update_opacity(self, value):
        """Update the opacity of the base image (volume_stack[0])."""
        opacity_value = value / 100  # Convert slider value to a range of 0.0 - 1.0
        self.axial_view.getImageItem().setOpacity(opacity_value)

    def mouse_click_event(self, event):
        # Paint action modifies self.temp_image (3D array) at the current slice
        if self.is_painting:
            # Get current slice from ImageView
            current_slice = int(self.axial_view.currentIndex)
            print(current_slice)
        else:
            if event.button() == Qt.LeftButton:
                img_item = self.axial_view.getImageItem()
                pos = event.pos()
                mouse_point = img_item.mapFromScene(pos)
                if img_item is not None and img_item.sceneBoundingRect().contains(mouse_point):
                    # Transform the scene coordinates to image coordinates
                    img_shape = self.volume_stack[0].data.shape
                    x = int(pos.x())
                    y = int(pos.y())
                    z = int(self.axial_view.currentIndex)  # Get the current slice index

                    # Ensure coordinates are within image bounds
                    if 0 <= x < img_shape[0] and 0 <= y < img_shape[1] and 0 <= z < img_shape[2]:
                        self.add_marker(x, y)

                    print(f"Point added at: x={x}, y={y}, z={z}")

        # Propagate the event for any further processing
        event.ignore()

    def add_marker(self, x, y):
        """Add a marker at the specified (x, y) coordinates."""
        # Create a scatter plot item as a marker
        marker = pg.ScatterPlotItem()
        marker.sigClicked.connect(self.marker_clicked)  # Connect to the signal
        marker.addPoints([{'pos': (x, y), 'brush': pg.mkBrush('r'), 'size': 10}])  # Customize size and color

        # Store position and metadata (current index) with the point
        slice_index = int(self.axial_view.currentIndex)
        marker_index = len(self.markers)

        marker.addPoints([{
            'pos': (x, y),
            'brush': pg.mkBrush('r'),
            'size': 10,
            'data': {'slice_index': slice_index, 'marker_index': marker_index}  # Store extra info here
        }])

        # Add marker to the view
        self.axial_view.addItem(marker)

        # Store marker for future reference (e.g., clearing markers)
        self.markers.append(marker)

    def clear_markers(self):
        """Remove all markers from the image view."""
        for marker in self.markers:
            self.axial_view.removeItem(marker)
        self.markers.clear()

    def marker_clicked(self, plot, points):
        """Handle marker click event."""
        # Store the clicked point for dragging
        if len(points) > 0:
            self.dragging_marker = points[0]
            print(f"Marker clicked at position: {self.dragging_marker.pos()}, {self.dragging_marker.data()['slice_index']}")

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
                if self.dragging_marker:
                    pass
                    # # Get the position of the mouse
                    # img_item = self.axial_view.getImageItem()
                    # mouse_point = img_item.mapFromScene(pos)
                    #
                    # # Update the position of the marker
                    # x = int(mouse_point.x())
                    # y = int(mouse_point.y())
                    #
                    # # Move the marker to the new position
                    # self.dragging_marker.setData(pos=[(x, y)], brush='r', size=10)

            else:
                self.coordinates_label.setText("")

            self.horizontal_line.setPos(y)
            self.vertical_line.setPos(x)

        else:
            self.coordinates_label.setText("")

    def update_volume_stack(self, new_volume, stack_position):
        """Update the volume stack with a new volume in the specified position."""
        self.volume_stack[stack_position] = new_volume
        if self.view_dir == ViewDir.AX.dir:
            ratio = new_volume.dy / new_volume.dx
        elif self.view_dir == ViewDir.COR.dir:
            ratio = new_volume.dz / new_volume.dx
        else:  # "SAG"
            ratio = new_volume.dz / new_volume.dy
            self.axial_view.getView().setAspectLocked(True, ratio=ratio)

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

    def toggle_painting_mode(self, _is_painting):
        """Toggle between painting and normal modes."""
        self.is_painting = _is_painting
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
        self.opacity_slider.setVisible(not is_visible)

    #
    # def hide_histogram_buttons(self):
    #     """Hide the ROI and MENU buttons in the histogram widget."""
    #     histogram = self.axial_view.getHistogramWidget()
    #     histogram.ui.roiBtn.hide()  # Hide the ROI button
    #     histogram.ui.menuBtn.hide()  # Hide the MENU button
