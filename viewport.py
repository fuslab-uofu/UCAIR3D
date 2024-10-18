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
        # top_layout.addWidget(self.layer_selector)
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
        # self.image_view = ColorImageView()
        self.image_view = pg.ImageView()
        # self.image_view.getHistogramWidget().setVisible(False)
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
        # self.opacity_slider.setVisible(False)
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
        self.image3D_obj_stack stores references to the Image3D objects that this viewport is currently displaying. 
        self.array3D_stack stores the actual 3D array that gets displayed. These arrays may be transposed to match 
        the orientation (ViewDir) of this Viewport.
        self.array2D_stack stores the slices (ImageItems) of the overlay image that will be displayed in the 
        image view. """
        self.image3D_obj_stack = [None] * self.num_vols_allowed
        self.array3D_stack = [None] * self.num_vols_allowed
        self.array2D_stack = [pg.ImageItem()] * (self.num_vols_allowed)
        for i in range(0, self.num_vols_allowed):
            self.image_view.view.addItem(self.array2D_stack[i])
        self.num_vols = 0  # keep track of the number of images currently linked to this viewport

        # FIXME: might not be necessary?
        self.num_displayed_layers = 0
        # keep track of the current layer for histogram interaction
        self.current_layer_index = None  # default to the first layer (background)
        self.current_slice_index = 0

        # # FIXME: temp during dev. These will be set by the main app
        # self.overlay_lut = np.array(
        #     [[0, 0, 0, 0],  # black
        #      [228, 25, 27, 255],  # red
        #      [54, 126, 184, 255],  # blue
        #      [76, 175, 74, 255],  # green
        #      [151, 77, 163, 255],  # purple
        #      [255, 127, 0, 255],  # orange
        #      [255, 255, 51, 255],  # yellow
        #      [165, 85, 40, 255],  # brown
        #      [246, 128, 191, 255]],  # pink
        #     dtype='uint8')

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
        self.image_view.getHistogramWidget().sigLevelChangeFinished.connect(self._update_image_object)
        # hist = pg.HistogramLUTItem()
        self.image_view.getHistogramWidget().sigLookupTableChanged.connect(self._reapply_lut)

    #  -----------------------------------------------------------------------------------------------------------------
    #  "Public" methods API --------------------------------------------------------------------------------------------
    #  -----------------------------------------------------------------------------------------------------------------

    def add_layer(self, image, stack_position):
        """Update the stack of 3D images with a new 3D image for this viewPort.
        image = None is allowed and will clear the layer at the specified position."""

        # if self.num_vols == self.num_vols_allowed:
        #     return
        # if stack_position is None:
        #     if self.num_vols == 0:
        #         return
        # else:

        if stack_position > self.num_vols_allowed:
            # TODO: raise an error or warning - the stack position is out of bounds
            return
        self.image3D_obj_stack[stack_position] = image  # not a deep copy, reference to the image3D object
        self.current_layer_index = stack_position

        if image is not None:
            # populate the 3D array stack with the data from this image3D object
            if self.view_dir == ViewDir.AX.dir:
                # axial view: transpose to (z, x, y)
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data, (2, 0, 1))
                ratio = image.dy / image.dx
                # start at middle slice
                self.current_slice_index = int(self.array3D_stack[stack_position].shape[0] // 2)
                # print(self.id, self.array3D_stack[stack_position].shape, self.current_slice_index)
            elif self.view_dir == ViewDir.COR.dir:
                # TODO: orient image for coronal view
                # coronal view: transpose to (y, x, z)
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data, (1, 0, 2))
                ratio = image.dz / image.dx
                # start at middle slice
                self.current_slice_index = int(self.array3D_stack[stack_position].shape[0] // 2)
                # print(self.id, self.array3D_stack[stack_position].shape, self.current_slice_index)
            else:  # "SAG"
                # TODO: orient image for sagittal view
                # sagittal view: transpose to (x, y, z)
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data, (0, 1, 2))
                ratio = image.dz / image.dy
                # start at middle slice
                self.current_slice_index = int(self.array3D_stack[stack_position].shape[0] // 2)
                # print(self.id, self.array3D_stack[stack_position].shape, self.current_slice_index)

            # set the aspect ratio of the image view
            self.image_view.getView().setAspectLocked(True, ratio=ratio)
        else:
            self.array3D_stack[stack_position] = None

       # TODO: update the layer selection combo and active layer

        self.refresh()

    def remove_layer(self, stack_position):
        # TODO
        pass

    def move_layer_up(self):
        # TODO
        pass

    def move_layer_down(self):
        # TODO
        pass

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
        if self.current_layer_index is None:
            # TODO: raise an error or warning - no layer selected
            return
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

    def refresh(self):
        """
        Should be called when one of the images displayed in the viewport changes. Sets the image item, and connects the histogram
        widget to the image item. Also updates the overlay images.
        """
        # the image stack may have empty slots, so we need to find the first non-empty image to display
        found_bottom_image = False
        for ind, im_data in enumerate(self.array3D_stack):
            if im_data is None:
                continue
            else:
                if not found_bottom_image:
                    # this is the "bottom" image and will be set as the 3D image item in the image view
                    self.is_user_histogram_interaction = False  # prevent the histogram from updating the image3D object
                    self.image_view.setImage(self.array3D_stack[ind])
                    main_image = self.image_view.getImageItem()
                    # apply the opacity of the Image3D object to the ImageItem
                    main_image.setOpacity(self.image3D_obj_stack[ind].alpha)
                    main_image.setLookupTable(self.image3D_obj_stack[ind].colormap)
                    # connect the histogram widget to the main image item
                    # self.image_view.getHistogramWidget().setImageItem(main_image)
                    # # update the histogram widget with eh colormap of the Image3D object
                    # hist_widget = self.image_view.ui.histogram
                    # gradient_editor = hist_widget.gradient
                    # new_gradient_state = {
                    #     'ticks': [(0.0, self.image3D_obj_stack[ind].colormap[0]),
                    #               (0.5, self.image3D_obj_stack[ind].colormap[int(len(self.image3D_obj_stack[ind].colormap) // 2)]),
                    #               (1.0, self.image3D_obj_stack[ind].colormap[-1])],
                    #     'mode': 'rgb'
                    # }
                    # # apply the new gradient to the GradientEditorItem
                    # gradient_editor.restoreState(new_gradient_state)
                    # self.image_view.updateImage()
                    self.image_view.getImageItem().getViewBox().invertY(False)
                    self.image_view.getImageItem().getViewBox().invertX(True)
                    self.is_user_histogram_interaction = True
                    found_bottom_image = True
                else:
                    # this is an overlay image, so we need to get a slice of it and set it as an overlay
                    self._update_overlay_slice(ind)

        self.image_view.setCurrentIndex(self.current_slice_index)

        # refresh the combo box with the current layers in the stack.
        try:
            # disconnect the slot before making changes
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
            if self.image3D_obj_stack[i] is not None:
                self.layer_selector.addItem(f"Overlay {i}")
            else:
                self.layer_selector.addItem(f"Empty Layer {i}")
        # reconnect the slot after making changes
        self.layer_selector.currentIndexChanged.connect(self._layer_selection_changed)

        self.image_view.show()

    #  -----------------------------------------------------------------------------------------------------------------
    #  "Private" methods -----------------------------------------------------------------------------------------------
    #  -----------------------------------------------------------------------------------------------------------------

    def _update_overlays(self):
        """Update the overlay image with the corresponding slice from the array3D."""
        found_bottom_overlay = False
        for layer_index in range(0, self.num_vols_allowed):
            if self.array3D_stack[layer_index] is not None:
                if not found_bottom_overlay:
                    found_bottom_overlay = True
                    continue
                else:
                    self._set_overlay_slice(layer_index)
            # else:
            #     self.array2D_stack[layer_index].clear()

    def _update_overlay_slice(self, layer_index):
        """Update the overlay image with the current slice from the array3D."""
        if self.array3D_stack[layer_index] is not None:
            overlay_image_object = self.image3D_obj_stack[layer_index]
            overlay_data = self.array3D_stack[layer_index]
            overlay_slice = overlay_data[int(self.image_view.currentIndex), :, :]
            overlay_image_item = self.array2D_stack[layer_index]
            # apply the slice to the overlay ImageItem
            self.is_user_histogram_interaction = False
            overlay_image_item.setImage(overlay_slice)
            overlay_image_item.setOpacity(overlay_image_object.alpha)
            overlay_image_item.setLookupTable(overlay_image_object.colormap)
            # self.image_view.getHistogramWidget().setImageItem(overlay_image_item)
            # hist_widget = self.image_view.ui.histogram
            # gradient_editor = hist_widget.gradient
            # # apply the colormap of this image to the histogram widget
            # new_gradient_state = {
            #     'ticks': [(0.0, overlay_image_object.colormap[0]),
            #               (0.5,
            #                overlay_image_object.colormap[int(len(overlay_image_object.colormap) // 2)]),
            #               (1.0, overlay_image_object.colormap[-1])],
            #     'mode': 'rgb'
            # }
            # gradient_editor.restoreState(new_gradient_state)

            # self.image_view.updateImage()

            # # Manually reapply the LUT of the base image to ensure it doesn't change
            # if self.current_layer_index != 0:
            #     base_image_item = self.image_view.getImageItem()  # Assuming the base image is layer 0
            #     base_image_item.setLookupTable(self.image3D_obj_stack[0].colormap)  # Reapply the base image LUT

            self.is_user_histogram_interaction = True
        # else:
        #     self.array2D_stack[layer_index].clear()

    def _set_overlay_slice(self, layer_index):
        """Update the overlay image with the current slice from the array3D."""
        if self.array3D_stack[layer_index] is not None:
            overlay_image_object = self.image3D_obj_stack[layer_index]
            overlay_data = self.array3D_stack[layer_index]
            overlay_slice = overlay_data[int(self.image_view.currentIndex), :, :]
            overlay_image_item = self.array2D_stack[layer_index]
            # apply the slice to the overlay ImageItem
            self.is_user_histogram_interaction = False
            overlay_image_item.setImage(overlay_slice)
            # self.image_view.setCurrentIndex(self.current_slice_index)
            overlay_image_item.setOpacity(overlay_image_object.alpha)
            overlay_image_item.setLookupTable(overlay_image_object.colormap)
            # self.image_view.getHistogramWidget().setImageItem(overlay_image_item)
            # hist_widget = self.image_view.ui.histogram
            # gradient_editor = hist_widget.gradient
            # # apply the colormap of this image to the histogram widget
            # new_gradient_state = {
            #     'ticks': [(0.0, overlay_image_object.colormap[0]),
            #               (0.5,
            #                overlay_image_object.colormap[int(len(overlay_image_object.colormap) // 2)]),
            #               (1.0, overlay_image_object.colormap[-1])],
            #     'mode': 'rgb'
            # }
            # gradient_editor.restoreState(new_gradient_state)

            # self.image_view.updateImage()

            # # Manually reapply the LUT of the base image to ensure it doesn't change
            # if self.current_layer_index != 0:
            #     base_image_item = self.image_view.getImageItem()  # Assuming the base image is layer 0
            #     base_image_item.setLookupTable(self.image3D_obj_stack[0].colormap)  # Reapply the base image LUT

            self.is_user_histogram_interaction = True
        # else:
        #     self.array2D_stack[layer_index].clear()

    def _update_opacity(self, value):
        """Update the opacity of the active imageItem as well as the Image3D object."""
        if self.current_layer_index is None:
            # TODO: raise an error or warning - no layer selected
            return
        opacity_value = value / 100  # convert slider value to a range of 0.0 - 1.0
        if self.current_layer_index == 0:
            self.image_view.getImageItem().setOpacity(opacity_value)
            self.image3D_obj_stack[0].alpha = opacity_value
        else:
            self.array2D_stack[self.current_layer_index].setOpacity(opacity_value)
            self.image3D_obj_stack[self.current_layer_index].alpha = opacity_value

        # self.image_view.getImageItem().setOpacity(opacity_value)
        # self.image3D_obj_stack[self.current_layer_index].alpha = opacity_value

    def _update_image_object(self):
        """Update the display min and max of the active Image3D object.
        This is the slot for the signal emitted when the user interacts with the histogram widget.
        The histogram widget automatically updates the imageItem, so we also need to update the Image3D object."""
        if self.is_user_histogram_interaction:
            # only do this if the user has interacted with the histogram. Not when the histogram is programmatically
            # updated by another method.
            if self.current_layer_index is None:
                # TODO: raise an error or warning - no layer selected
                return
            levels = self.image_view.getHistogramWidget().getLevels()
            self.image3D_obj_stack[self.current_layer_index].display_min = levels[0]
            self.image3D_obj_stack[self.current_layer_index].display_max = levels[1]
        # TODO: update Image3D colormap, too?

    def _reapply_lut(self):
        # ensure the LUT remains as you defined it
        found_bottom_image = False
        for ind, im in enumerate(self.image3D_obj_stack):
            if im is None:
                continue
            else:
                if not found_bottom_image:
                    found_bottom_image = True
                    if im.colormap is not None:
                        self.image_view.getImageItem().setLookupTable(im.colormap)
                else:
                    if self.array2D_stack[ind] is not None:
                        self.array2D_stack[ind].setLookupTable(im.colormap)

        # for i in range(0, self.num_vols_allowed):
        #     if self.array3D_stack[i] is not None:
        #         self.array2D_stack[i].setLookupTable(self.image3D_obj_stack[i].colormap)
        # if self.image3D_obj_stack[0].colormap is not None:
        #     self.image_view.getImageItem().setLookupTable(self.image3D_obj_stack[0].colormap)
            # self.image_view.updateImage()

    def _layer_selection_changed(self, index):
        """Update the layer associated with histogram settings and interactions."""
        self.current_layer_index = index

        if index == 0:
            # set the histogram to display stats for the main image (3D MR image)
            if self.array3D_stack[index] is not None:
                self.is_user_histogram_interaction = False
                main_image = self.image_view.getImageItem()
                # TODO: set alpha slider to this image's alpha value?

                self.image_view.getHistogramWidget().setImageItem(main_image)
                # Retrieve and set the levels (brightness/contrast) for the main image
                levels = (self.image3D_obj_stack[0].display_min, self.image3D_obj_stack[0].display_max)
                self.image_view.getHistogramWidget().setLevels(*levels)
                self.is_user_histogram_interaction = True
                # TODO: retrieve and apply the LUT for the new active layer

        else:
            # use the overlay layer corresponding to the index
            if self.array3D_stack[index] is not None:
                overlay_slice = self.array3D_stack[index][int(self.image_view.currentIndex), :, :]
                self.array2D_stack[index].setImage(overlay_slice, opacity=self.image3D_obj_stack[index].alpha)

                self.is_user_histogram_interaction = False
                # Connect the histogram to the selected layer
                self.image_view.getHistogramWidget().setImageItem(self.array2D_stack[index])

                # retrieve and apply the display levels (brightness/contrast) for the new active layer
                levels = (self.image3D_obj_stack[index].display_min, self.image3D_obj_stack[index].display_max)
                self.image_view.getHistogramWidget().setLevels(*levels)

                # retrieve and apply the LUT for the new active layer
                lut = self.image3D_obj_stack[index].lut
                if lut is not None:
                    self.array2D_stack[index].setLookupTable(lut)
                self.is_user_histogram_interaction = True
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
                    img_shape = self.image3D_obj_stack[0].data.shape
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
        if self.current_layer_index is None:
            return
        img_item = self.image_view.getImageItem()
        if self.image3D_obj_stack[self.current_layer_index] is None:
            return
        if img_item is not None and img_item.sceneBoundingRect().contains(pos):
            # Transform the scene coordinates to image coordinates
            mouse_point = img_item.mapFromScene(pos)
            if self.image3D_obj_stack[self.current_layer_index] is None:
                return
            img_shape = self.image3D_obj_stack[self.current_layer_index].data.shape
            x = int(mouse_point.x())
            y = int(mouse_point.y())
            z = int(self.image_view.currentIndex)  # Get the current slice index

            # Ensure coordinates are within image bounds
            if 0 <= x < img_shape[0] and 0 <= y < img_shape[1] and 0 <= z < img_shape[2]:
                voxel_value = self.image3D_obj_stack[self.current_layer_index].data[x, y, z]
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

    def _toggle_histogram(self):
        """toggle the visibility of the histogram/colormap/opacity widget"""
        histogram = self.image_view.getHistogramWidget()
        is_visible = histogram.isVisible()
        histogram.setVisible(not is_visible)
        if self.current_layer_index is None:
            return
        if self.image3D_obj_stack[self.current_layer_index] is not None:
            self.image_view.getImageItem().setLookupTable(self.image3D_obj_stack[self.current_layer_index].colormap)
            # self.image_view.updateImage()

        # self._set_histogram_colormap(self.image3D_obj_stack[self.current_layer_index].colormap)
        self.opacity_slider.setVisible(not is_visible)

    # def _set_histogram_colormap(self, colormap):
    #     """ Set the histogram widget's colormap to match the LUT of the current layer. """
    #     if colormap is not None:
    #         self.image_view.ui.histogram.setImageItem(self.image_view.getImageItem())
    #         self.image_view.getImageItem().setLookupTable(colormap)
    #         self.image_view.updateImage()
    #


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