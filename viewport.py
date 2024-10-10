import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QLabel, QSlider, QComboBox
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt

from enumerations import ViewDir


class ColorImageView(pg.ImageView):
    """
    Wrapper around the ImageView class to create a color lookup
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
    """ This class displays one or more 3D images. It is interactive and allows the user to pan, zoom, and scroll
    through images. Multiple images can be stacked on top of each other to create overlays. The user can also paint
    (modify the voxel values) and add markers to the image. Tools are provided for modifying the colormap and opacity
    of the images. The calling class must provide the view desired view direction (axial, coronal, sagittal).
    The calling class must also provide the maximum number of image allowed in the stack.
    A viewport is a subclass of QWidget and can be added to a layout in a QMainWindow.
    """
    def __init__(self, parent, _id, _view_dir, _num_vols, _zoom_method=None, _pan_method=None, _window_method=None):
        super().__init__()

        self.parent = parent
        self.id = _id
        self.view_dir = _view_dir.dir             # ViewDir.AX (axial), ViewDir.COR (coronal), ViewDir.SAG (sagittal)
        self.num_vols_allowed = _num_vols         # number of images (layers) to display
        self.zoom_method = _zoom_method           # TODO: future implementation, custom zoom method
        self.pan_method = _pan_method             # TODO: future implementation, custom pan method
        self.window_method = _window_method       # TODO: future implementation, custom method for windowing

        # initialize widgets and their slots -------------------------------------
        # the main layout for this widget ----------
        main_layout = QVBoxLayout(self)

        # horizontal layout for the coordinates label and tool buttons ----------
        top_layout = QHBoxLayout()
        # coordinates label
        self.coordinates_label = QLabel("Coordinates: ", self)
        font = QFont("Segoe UI", 9)
        font.setItalic(True)
        self.coordinates_label.setFont(font)
        top_layout.addWidget(self.coordinates_label)
        # layer selection combo box
        self.layer_selector = QComboBox(self)
        self.layer_selector.addItems([f"Layer {i}" for i in range(self.num_vols_allowed)])
        self.layer_selector.currentIndexChanged.connect(self._layer_selection_changed)
        top_layout.addWidget(self.layer_selector)
        # add spacing between the buttons and right edge
        top_layout.addStretch()
        # histogram visibility button
        self.histogram_button = QPushButton()
        self.histogram_button.setCheckable(True)
        self.histogram_button.setChecked(False)
        self.histogram_button.setFixedSize(24, 24)
        histogram_icon = QIcon("..\\ui\\colorWheelIcon.svg")
        self.histogram_button.setIcon(histogram_icon)
        self.histogram_button.clicked.connect(self._toggle_histogram)
        top_layout.addWidget(self.histogram_button)
        # crosshair visibility button
        self.crosshair_button = QPushButton()
        self.crosshair_button.setCheckable(True)
        self.crosshair_button.setFixedSize(24, 24)
        crosshair_icon = QIcon("..\\ui\\crosshair_white_icon.svg")
        self.crosshair_button.setIcon(crosshair_icon)
        self.crosshair_button.setIconSize(self.crosshair_button.size())
        self.crosshair_button.clicked.connect(self._toggle_crosshairs)
        top_layout.addWidget(self.crosshair_button)
        # add the top layout to the main layout (above the imageView)
        main_layout.addLayout(top_layout)

        # layout for the image view and opacity slider ----------
        image_view_layout = QHBoxLayout()
        # the image view widget ----------
        self.image_view = ColorImageView()
        self.image_view.getHistogramWidget().setVisible(False)
        self.image_view.ui.menuBtn.setVisible(False)  # hide these for now
        self.image_view.ui.roiBtn.setVisible(False)  # hide these for now
        image_view_layout.addWidget(self.image_view, stretch=2)
        # transparency slider (vertical orientation)
        slider_layout = QVBoxLayout()
        self.opacity_slider = QSlider(Qt.Vertical)
        self.opacity_slider.setRange(0, 100)  # Slider values from 0 to 100
        self.opacity_slider.setValue(100)  # Default to fully opaque
        self.opacity_slider.setTickPosition(QSlider.TicksRight)
        self.opacity_slider.setTickInterval(10)
        self.opacity_slider.valueChanged.connect(self._update_opacity)
        slider_layout.addWidget(self.opacity_slider, alignment=Qt.AlignHCenter)
        image_view_layout.addLayout(slider_layout, stretch=0)
        self.opacity_slider.setVisible(False)
        # add image_view_layout to the main layout
        main_layout.addLayout(image_view_layout)

        # create crosshair lines
        self.horizontal_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('r', width=0.5), movable=False)
        self.vertical_line = pg.InfiniteLine(angle=90, pen=pg.mkPen('r', width=0.5), movable=False)
        self.image_view.addItem(self.horizontal_line, ignoreBounds=True)
        self.image_view.addItem(self.vertical_line, ignoreBounds=True)
        self.show_crosshairs = False
        self.horizontal_line.setVisible(self.show_crosshairs)
        self.vertical_line.setVisible(self.show_crosshairs)

        """ NOTE: the pyqtgraph ImageView object displays only one 3D image at a time. To have overlays, 2D slices 
        are added to the ImageView. For our Viewport object, the main/background image is the 3D array of the data
        member of an Image3D object. Overlay/foreground image is a 2D array (slice) of the 3D array.
        self.image3D_stack stores references to the Image3D objects that this viewport is currently displaying. 
        self.array3D_stack stores the actual 3D array that gets displayed. These arrays may be transposed to match 
        the orientation (ViewDir) of this Viewport.
        self.array2D_stack stores the slices (ImageItems) of the overlay image that will be displayed in the 
        image view. """
        self.image3D_stack = [None] * self.num_vols_allowed
        self.array3D_stack = [None] * self.num_vols_allowed
        self.array2D_stack = [pg.ImageItem()] * (self.num_vols_allowed - 1)
        for i in range(0, (self.num_vols_allowed-1)):
            self.image_view.view.addItem(self.array2D_stack[i])

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

        # keep track of the current layer for histogram interaction
        self.current_layer_index = 0  # Default to the first layer (background)

        # interactive painting
        self.is_painting = False
        # create a brush (kernel) to use for painting. Square, 3x3
        # TODO: implement PaintBrush class to handle different brush shapes, sizes, and colors
        self.kernel = np.array([
            [1, 1, 1],
            [1, 1, 1],
            [1, 1, 1]
        ])
        # radius = 2
        # self.kernel = self.create_circular_kernel(radius)

        # interactive marker placement
        self.is_marking = False
        self.markers = []  # this will be a list of markers
        self.selected_marker = None
        self.dragging_marker = None

        # differentiate between user interacting with histogram widget and histogram updated by the viewport
        self.is_user_histogram_interaction = True

        # connect the mouse move event to the image view
        self.image_view.getView().scene().sigMouseMoved.connect(self._mouse_move)
        # when the timeLine position changes, update the overlays
        self.image_view.timeLine.sigPositionChanged.connect(lambda: self._update_overlays())
        # connect the mouse click event to the image view
        self.image_view.imageItem.mouseClickEvent = self._mouse_click_event
        self.image_view.getHistogramWidget().sigLevelChangeFinished.connect(self._update_image_levels)

    #  -----------------------------------------------------------------------------------------------------------------
    #  "Public" methods ------------------------------------------------------------------------------------------------
    #  -----------------------------------------------------------------------------------------------------------------
    def refresh(self):
        """
        Called when the image displayed in the viewport changes.
        """
        if self.array3D_stack[0] is not None:
            # setImage will cause the histogram signal to be emitted, so prevent the slot from doing anything.
            self.is_user_histogram_interaction = False
            self.image_view.setImage(self.array3D_stack[0], levels=(self.image3D_stack[0].display_min,
                                                                   self.image3D_stack[0].display_max))
            self.is_user_histogram_interaction = True
            self.image_view.getImageItem().getViewBox().invertY(False)
            self.image_view.getImageItem().getViewBox().invertX(True)
        else:
            self.image_view.clear()

        self._update_overlays()

        # refresh the combo box with the current layers in the stack.
        # disconnect the slot before making changes
        try:
            self.layer_selector.currentIndexChanged.disconnect(self._layer_selection_changed)
        except TypeError:
            # if the slot was not connected, ignore the error
            pass
        # clear the combo box
        self.layer_selector.clear()
        # add the main background image
        self.layer_selector.addItem("Background ")
        # add overlay layers if they exist
        for i in range(1, self.num_vols_allowed):
            if self.image3D_stack[i] is not None:
                self.layer_selector.addItem(f"Overlay {i}")
            else:
                self.layer_selector.addItem(f"Empty Layer {i}")
        # reconnect the slot after making changes
        self.layer_selector.currentIndexChanged.connect(self._layer_selection_changed)

        self.image_view.show()

    def add_image(self, image, stack_position):
        """update the stack of 3D images with a new 3D image in the specified position.
        image can be None to clear the volume at the specified position."""
        self.image3D_stack[stack_position] = image  # reference to the image3D object
        if image is not None:
            if self.view_dir == ViewDir.AX.dir:
                # axial view: transpose to (z, x, y)
                self.array3D_stack[stack_position] = np.transpose(self.image3D_stack[stack_position].data, (2, 0, 1))
                ratio = image.dy / image.dx
            elif self.view_dir == ViewDir.COR.dir:
                # TODO: orient image for coronal view
                # coronal view: transpose to (y, x, z)
                self.array3D_stack[stack_position] = np.transpose(self.image3D_stack[stack_position].data, (1, 0, 2))
                ratio = image.dz / image.dx
            else:  # "SAG"
                # TODO: orient image for sagittal view
                # sagittal view: transpose to (x, y, z)
                self.array3D_stack[stack_position] = np.transpose(self.image3D_stack[stack_position].data, (0, 1, 2))
                ratio = image.dz / image.dy
            # set the aspect ratio of the image view
            self.image_view.getView().setAspectLocked(True, ratio=ratio)

       # TODO: update the layer selection combo and active layer

        self.refresh()

    def get_current_slice(self):
        return self.image_view.currentIndex

    # markers ----------------------------------------------------------------------------------------------------------
    def toggle_marking_mode(self, _is_marking):
        """called by external class to toggle marking mode on or off"""
        self.is_marking = _is_marking

    def add_marker(self, x, y, z=None):
        """Add a marker at the specified (x, y) coordinates. z (slice index) is optional."""
        # Create a scatter plot item as a marker
        marker = pg.ScatterPlotItem()
        marker.sigClicked.connect(self.marker_clicked)  # Connect to the signal
        marker.addPoints([{'pos': (x, y), 'brush': pg.mkBrush('r'), 'size': 10}])  # Customize size and color

        # store position and metadata (slice index) with the point
        if z is None:
            slice_index = int(self.image_view.currentIndex)
        else:
            slice_index = z

        marker.addPoints([{
            'pos': (x, y),
            'brush': pg.mkBrush('r'),
            'size': 10,
            'data': {'slice_index': slice_index, 'object_ref': marker}  # Store the marker itself for easy retrieval
        }])

        # add marker to the view
        self.image_view.addItem(marker)

        # store marker for future reference (e.g., clearing markers)
        self.markers.append(marker)

    def clear_markers(self):
        """Remove all markers from the image view."""
        for marker in self.markers:
            self.image_view.removeItem(marker)
        self.markers.clear()

    def marker_clicked(self, plot, points):
        """Handle marker click event."""
        # Store the clicked point for dragging
        if len(points) > 0:
            # assuming only one point is clicked at a time, grab the first point
            clicked_point = points[0]
            # Extract the stored data from the clicked point
            data = clicked_point.data()
            # Retrieve slice index and marker object from the data
            slice_index = data['slice_index']
            clicked_marker = data['object_ref']

            # Define the pen for default and selected markers
            default_pen = pg.mkPen('r', width=1)  # Red pen for default markers
            default_brush = pg.mkBrush('r')  # Default color is red
            selected_pen = pg.mkPen('g', width=2)  # Green pen for selected marker
            selected_brush = pg.mkBrush('g')  # Change to green or any color for selection

            # Reset all markers to the default color
            for marker in self.markers:
                for point in marker.points():
                    point.setPen(default_pen)
                    point.setBrush(default_brush)

            # Change the pen of the clicked marker to indicate selection
            for point in clicked_marker.points():
                point.setPen(selected_pen)
                point.setBrush(selected_brush)

            # Store the newly selected marker
            self.selected_marker = clicked_marker

            # Perform any action you want with the slice_index and clicked_marker
            print(f"Marker clicked at position: {clicked_point.pos()}, Slice index: {slice_index}")

    def import_markers(self, markers):
        """called by external class to import markers from a list of (x, y, z) coordinates."""
        for x, y, z in markers:
            self.add_marker(x, y, z)

    # painting ---------------------------------------------------------------------------------------------------------
    def toggle_painting_mode(self, _is_painting):
        """called by external class to toggle painting modes on or off"""
        self.is_painting = _is_painting
        if self.is_painting:
            # Set the kernel (brush) for drawing
            # self.array2D_stack.setDrawKernel(self.kernel, mask=None, center=(1, 1), mode='set')
            if self.current_layer_index == 0:
                self.image_view.imageItem.setDrawKernel(self.kernel, mask=None, center=(1, 1), mode='set')
            else:
                self.array2D_stack[self.current_layer_index].setDrawKernel(self.kernel, mask=None, center=(1, 1),
                                                                           mode='set')
        else:
            # Disable drawing
            self.array2D_stack[self.current_layer_index].setDrawKernel(None)

    #  -----------------------------------------------------------------------------------------------------------------
    #  "Private" methods -----------------------------------------------------------------------------------------------
    #  -----------------------------------------------------------------------------------------------------------------
    def _update_opacity(self, value):
        """Update the opacity of the active imageItem as well as the Image3D object."""
        opacity_value = value / 100  # convert slider value to a range of 0.0 - 1.0
        if self.current_layer_index == 0:
            self.image_view.getImageItem().setOpacity(opacity_value)
            self.image3D_stack[0].alpha = opacity_value
        else:
            self.array2D_stack[self.current_layer_index-1].setOpacity(opacity_value)
            self.image3D_stack[self.current_layer_index].alpha = opacity_value

        # self.image_view.getImageItem().setOpacity(opacity_value)
        # self.image3D_stack[self.current_layer_index].alpha = opacity_value

    def _update_image_levels(self):
        """Update the display levels of the active Image3D object.
        This is the slot for the signal emitted when the user interacts with the histogram widget.
        The histogram widget automatically updates the imageItem, so we only need to update the Image3D object."""
        if self.is_user_histogram_interaction:
            levels = self.image_view.getHistogramWidget().getLevels()
            self.image3D_stack[self.current_layer_index].display_min = levels[0]
            self.image3D_stack[self.current_layer_index].display_max = levels[1]

    def _layer_selection_changed(self, index):
        """Update the layer associated with histogram settings and interactions."""
        self.current_layer_index = index

        if index == 0:
            # Set the histogram to display stats for the main image (3D MR image)
            if self.array3D_stack[0] is not None:
                self.is_user_histogram_interaction = False
                # self.image_view.setImage(self.array3D_stack[0], levels=(self.image3D_stack[0].display_min,
                #                                                        self.image3D_stack[0].display_max))
                self.image_view.getHistogramWidget().setImageItem(self.image_view.getImageItem())
                self.is_user_histogram_interaction = True
                # Set the histogram widget's color bar back to the default (no LUT for the main image)
                # self.image_view.getImageItem().setLookupTable(None)
                # Reset histogram gradient to default
                # self.image_view.getHistogramWidget().gradient.setColorMap(
                #     pg.colormap.get('viridis'))  # Or any default color map you prefer
                # self.image_view.getHistogramWidget().gradient.loadPreset('grey')  # Use a default grayscale preset

                # Update the histogram for the current layer
                # self.image_view.getHistogramWidget().setImageItem(self.image_view.getImageItem())
                # self.image_view.getHistogramWidget().autoHistogramRange()

                # Optionally refresh the histogram display
                # self.image_view.getHistogramWidget().regionChanged()
        else:
            # Use the overlay layer corresponding to the index
            if self.array3D_stack[index] is not None:
                overlay_slice = self.array3D_stack[index][int(self.image_view.currentIndex), :, :]
                self.array2D_stack[index-1].setImage(overlay_slice, opacity=self.image3D_stack[index].alpha)
                self.is_user_histogram_interaction = False
                self.image_view.getHistogramWidget().setImageItem(self.array2D_stack[index-1])
                self.is_user_histogram_interaction = True
                # self.image_view.getImageItem().setImage(overlay_slice)
                # self.image_view.getImageItem().setLevels([0, 8])  # Adjust levels based on your LUT
                # self.image_view.getImageItem().setLookupTable(self.overlay_lut)  # Apply LUT to overlay
                #
                # # update the histogram widget to display the custom LUT
                # lut_color_map = pg.ColorMap(pos=np.linspace(0, 1, self.overlay_lut.shape[0]),
                #                             color=self.overlay_lut)
                # self.image_view.getHistogramWidget().gradient.setColorMap(lut_color_map)
                # self.image_view.getHistogramWidget().setVisible(False)
            else:
                self.image_view.clear()  # Clear the image view if the layer is empty


    def _mouse_click_event(self, event):
        # Paint action modifies self.temp_image (3D array) at the current slice
        if self.is_painting:
            # Get current slice from ImageView
            current_slice = int(self.image_view.currentIndex)
            print(current_slice)
        else:
            if event.button() == Qt.LeftButton:
                img_item = self.image_view.getImageItem()
                pos = event.pos()
                mouse_point = img_item.mapFromScene(pos)
                if img_item is not None and img_item.sceneBoundingRect().contains(mouse_point):
                    # Transform the scene coordinates to image coordinates
                    img_shape = self.image3D_stack[0].data.shape
                    x = int(pos.x())
                    y = int(pos.y())
                    z = int(self.image_view.currentIndex)  # Get the current slice index

                    # Ensure coordinates are within image bounds
                    if 0 <= x < img_shape[0] and 0 <= y < img_shape[1] and 0 <= z < img_shape[2]:
                        self.add_marker(x, y)

                    print(f"Point added at: x={x}, y={y}, z={z}")

        # Propagate the event for any further processing
        event.ignore()

    def _toggle_crosshairs(self):
        """toggle crosshair visibility"""
        self.show_crosshairs = not self.show_crosshairs
        self.horizontal_line.setVisible(self.show_crosshairs)
        self.vertical_line.setVisible(self.show_crosshairs)

    def _mouse_move(self, pos):
        img_item = self.image_view.getImageItem()
        if img_item is not None and img_item.sceneBoundingRect().contains(pos):
            # Transform the scene coordinates to image coordinates
            mouse_point = img_item.mapFromScene(pos)
            img_shape = self.image3D_stack[0].data.shape
            x = int(mouse_point.x())
            y = int(mouse_point.y())
            z = int(self.image_view.currentIndex)  # Get the current slice index

            # Ensure coordinates are within image bounds
            if 0 <= x < img_shape[0] and 0 <= y < img_shape[1] and 0 <= z < img_shape[2]:
                voxel_value = self.image3D_stack[0].data[x, y, z]
                coordinates_text = "Coordinates: x={:3d}, y={:3d}, z={:3d}, Voxel Value: {:4.2f}".format(x, y, z,
                                                                                                         voxel_value)
                self.coordinates_label.setText(coordinates_text)
                if self.dragging_marker:
                    pass
                    # # Get the position of the mouse
                    # img_item = self.image_view.getImageItem()
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

    def _update_overlays(self):
        """Update the overlay image with the corresponding slice from the array3D."""
        for layer_index in range(0, self.num_vols_allowed-1):
            if self.array3D_stack[layer_index+1] is not None:
                overlay_slice = self.array3D_stack[layer_index+1][int(self.image_view.currentIndex), :, :]
                # Set the data for the overlay ImageItem
                self.is_user_histogram_interaction = False
                self.array2D_stack[layer_index].setImage(overlay_slice)  # opacity=self.image3D_stack[layer_index+1].alpha)
                self.is_user_histogram_interaction = True
                # self.array2D_stack[layer_index].setLevels([0, 8])
                # self.array2D_stack[layer_index].setLookupTable(self.overlay_lut)
            else:
                self.array2D_stack[layer_index].clear()

    def _toggle_histogram(self):
        """toggle the visibility of the histogram/colormap/opacity widget"""
        histogram = self.image_view.getHistogramWidget()
        is_visible = histogram.isVisible()
        histogram.setVisible(not is_visible)
        self.opacity_slider.setVisible(not is_visible)

    # def create_circular_kernel(self, radius):
    #     """Create a circular kernel with the specified radius."""
    #     size = 2 * radius + 1  # Ensure the kernel is large enough to contain the circle
    #     kernel = np.zeros((size, size), dtype=np.uint8)
    #
    #     # Calculate the center of the kernel
    #     center = radius
    #
    #     # Iterate over the kernel's grid and fill in a circle
    #     for y in range(size):
    #         for x in range(size):
    #             # Calculate distance from the center
    #             distance = np.sqrt((x - center) ** 2 + (y - center) ** 2)
    #             if distance <= radius:
    #                 kernel[y, x] = 1
    #
    #     return kernel