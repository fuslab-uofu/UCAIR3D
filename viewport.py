import numpy as np
import pyqtgraph as pg
import re

from PyQt5.QtWidgets import QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QLabel, QSlider, QComboBox
from PyQt5.QtGui import QIcon, QFont, QCursor
from PyQt5.QtCore import Qt, QEvent

from enumerations import ViewDir
from paint_brush import PaintBrush


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
        self.view_dir = _view_dir.dir  # ViewDir.AX (axial), ViewDir.COR (coronal), ViewDir.SAG (sagittal)
        self.num_vols_allowed = _num_vols  # number of images (layers) to display
        self.zoom_method = _zoom_method  # TODO: future implementation, custom zoom method
        self.pan_method = _pan_method  # TODO: future implementation, custom pan method
        self.window_method = _window_method  # TODO: future implementation, custom method for windowing

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
        self.layer_selector.setVisible(False)
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
        self.image_view = pg.ImageView()
        self.original_mouse_press = self.image_view.getView().scene().mousePressEvent
        self.original_mouse_release = self.image_view.getView().scene().mouseReleaseEvent
        self.original_mouse_move = self.image_view.getView().scene().mouseMoveEvent
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
        self.image3D_obj_stack stores references to the Image3D objects that this viewport is currently displaying. 
        self.array3D_stack stores the actual 3D array that gets displayed. These arrays may be transposed to match 
        the orientation (ViewDir) of this Viewport.
        self.array2D_stack stores the slices (ImageItems) of the overlay image that will be displayed in the 
        image view. """
        self.image3D_obj_stack = [None] * self.num_vols_allowed  # Image3D objects
        self.array3D_stack = [None] * self.num_vols_allowed  # image data 3D arrays
        self.array2D_stack = [pg.ImageItem() for _ in range(self.num_vols_allowed)]  # image data 2D arrays (slices)
        for i in range(0, self.num_vols_allowed):
            self.image_view.view.addItem(self.array2D_stack[i])
        # add a canvas mask for painting
        # self.imageItem3D_canvas = pg.ImageItem()
        self.imageItem2D_canvas = pg.ImageItem()
        self.image_view.view.addItem(self.imageItem2D_canvas)
        self.num_vols = 0  # keep track of the number of images currently linked to this viewport

        # FIXME: might not be necessary?
        self.num_displayed_images = 0

        # convenience reference to the background image item
        self.background_image_index = None
        # keep track of the active layer for histogram, colormap, and opacity settings interaction
        self.active_image_index = None  # default to the first layer (background)
        self.paint_layer_index = None  # the layer that is currently being painted on
        self.current_slice_index = 0

        # interactive painting
        self.is_painting = False
        self.is_erasing = False
        self.paint_brush = PaintBrush()

        # interactive marker placement
        self.is_marking = False
        self.is_dragging_marker = False
        self.markers = []  # this will be a list of markers
        self.selected_marker = None
        self.dragging_marker = None

        # differentiate between user interacting with histogram widget and histogram updated by the viewport
        self.is_user_histogram_interaction = True
        self.image_view.getHistogramWidget().sigLevelChangeFinished.connect(self._update_image_object)
        self.image_view.getHistogramWidget().sigLookupTableChanged.connect(self._reapply_lut)

        # connect the mouse move event to the graphics scene
        self.image_view.getView().scene().mouseMoveEvent = self._mouse_move
        # self.image_view.getView().scene().sigMouseMoved.connect(self._mouse_move)

        # connect the mouse click event to the graphics scene
        self.image_view.getView().scene().mousePressEvent = self._mouse_press
        # self.image_view.imageItem.mousePressEvent = self._mouse_press

        # connect the mouse release event to the graphics scene
        self.image_view.getView().scene().mouseReleaseEvent = self._mouse_release
        # self.image_view.imageItem.mouseReleaseEvent = self._mouse_release

        # when the timeLine position changes, update the overlays
        self.image_view.timeLine.sigPositionChanged.connect(lambda: self._update_overlays())

    #  -----------------------------------------------------------------------------------------------------------------
    #  "Public" methods API --------------------------------------------------------------------------------------------
    #  -----------------------------------------------------------------------------------------------------------------

    def add_layer(self, image, stack_position):
        """Update the stack of 3D images with a new 3D image for this viewPort.
        image = None is allowed and will clear the layer at the specified position."""

        if stack_position > self.num_vols_allowed:
            # TODO: raise an error or warning - the stack position is out of bounds
            return

        self.image3D_obj_stack[stack_position] = image  # not a deep copy, reference to the image3D object
        self.active_image_index = stack_position

        if image is not None:
            # populate the 3D array stack with the data from this image3D object
            if self.view_dir == ViewDir.AX.dir:
                # axial view: transpose to (z, x, y)
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data,
                                                                  (2, 0, 1))
                ratio = image.dy / image.dx
                # start at middle slice
                self.current_slice_index = int(self.array3D_stack[stack_position].shape[0] // 2)
                # print(self.id, self.array3D_stack[stack_position].shape, self.current_slice_index)
            elif self.view_dir == ViewDir.COR.dir:
                # TODO: orient image for coronal view
                # coronal view: transpose to (y, x, z)
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data,
                                                                  (1, 0, 2))
                ratio = image.dz / image.dx
                # start at middle slice
                self.current_slice_index = int(self.array3D_stack[stack_position].shape[0] // 2)
                # print(self.id, self.array3D_stack[stack_position].shape, self.current_slice_index)
            else:  # "SAG"
                # TODO: orient image for sagittal view
                # sagittal view: transpose to (x, y, z)
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data,
                                                                  (0, 1, 2))
                ratio = image.dz / image.dy
                # start at middle slice
                self.current_slice_index = int(self.array3D_stack[stack_position].shape[0] // 2)
                # print(self.id, self.array3D_stack[stack_position].shape, self.current_slice_index)

            # set the aspect ratio of the image view to match this new image
            # FIXME: is there a better way to do this? Should this be done in refresh()?
            self.image_view.getView().setAspectLocked(True, ratio=ratio)
        else:
            self.array3D_stack[stack_position] = None

        # TODO: update the layer selection combo and active layer

        self.refresh()

    def remove_layer(self, stack_position):
        self.image3D_obj_stack[stack_position] = None
        self.array3D_stack[stack_position] = None
        # self.array2D_stack[stack_position].clear()
        self.array2D_stack[stack_position] = None
        self.refresh()

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
    def toggle_painting_mode(self, which_layer, _is_painting):
        """Called by external class to toggle painting mode on or off."""
        # painting should only be done on the layer that is identified by which_layer
        if self.image3D_obj_stack[which_layer] is None:
            # TODO: raise an error or warning - no layer selected
            return
        self.paint_layer_index = which_layer
        self.is_painting = _is_painting

        if self.is_painting:
            # enable painting on this layer
            self._update_canvas()
            self.setCursor(QCursor(Qt.CrossCursor))
        else:
            # disable painting on this layer
            self._disable_paint_brush(self.paint_layer_index)
            self.setCursor(QCursor(Qt.ArrowCursor))

    def update_paint_brush(self, brush):
        """Update the paint brush settings. Called by external class to update the paint brush settings,
        applies updated brush to current paint layer, if is_painting."""
        self.paint_brush.set_size(brush.size)
        self.paint_brush.set_value(brush.value)
        self.paint_brush.set_shape(brush.shape)

        # if self.paint_layer_index is None:
        #     return
        # if self.is_painting:
        #     self._update_canvas()

    def refresh(self):
        """
        Should be called when one of the images displayed in the viewport changes. Sets the image item, and connects the
        histogram widget to the image item. Also updates the overlay images.
        """
        self.image_view.clear()

        # the image stack may have empty slots, so we need to find the first non-empty image to display
        found_bottom_image = False
        for ind, im_obj in enumerate(self.image3D_obj_stack):
            if im_obj is None:
                continue
            else:
                if not found_bottom_image:
                    # this is the bottom image in the stack and will be set as the 3D background image item in the
                    # image view
                    im_data = self.array3D_stack[ind]
                    self.is_user_histogram_interaction = False  # prevent the histogram from updating the image3D object
                    self.image_view.setImage(im_data)
                    main_image = self.image_view.getImageItem()
                    # Set the levels to prevent LUT rescaling based on the slice content
                    main_image.setLevels([im_obj.display_min, im_obj.display_max])
                    # apply the opacity of the Image3D object to the ImageItem
                    main_image.setOpacity(im_obj.alpha)
                    main_image.setLookupTable(im_obj.colormap)

                    # self.image_view.updateImage()
                    self.image_view.getImageItem().getViewBox().invertY(False)
                    self.image_view.getImageItem().getViewBox().invertX(True)
                    self.is_user_histogram_interaction = True
                    self.background_image_index = ind
                    found_bottom_image = True
                else:
                    # this is an overlay image, so we need to get a slice of it and set it as an overlay
                    self._update_overlay_slice(ind)  # uses self.current_slice_index

        # self._update_canvas() # uses self.current_slice_index

        self.image_view.setCurrentIndex(self.current_slice_index)

        # refresh the combo box with the current layers in the stack.
        # try:
        #     # disconnect the slot before making changes
        #     self.layer_selector.currentIndexChanged.disconnect(self._layer_selection_changed)
        # except TypeError:
        #     # if the slot was not connected, ignore the error
        #     pass
        # # clear the combo box
        # self.layer_selector.clear()
        # # add the main background image
        # self.layer_selector.addItem("Background ")
        # # add overlay layers if they exist
        # for i in range(1, self.num_vols_allowed):
        #     if self.image3D_obj_stack[i] is not None:
        #         self.layer_selector.addItem(f"Overlay {i}")
        #     else:
        #         self.layer_selector.addItem(f"Empty Layer {i}")
        # # reconnect the slot after making changes
        # self.layer_selector.currentIndexChanged.connect(self._layer_selection_changed)

        self.image_view.show()

    #  -----------------------------------------------------------------------------------------------------------------
    #  "Private" methods -----------------------------------------------------------------------------------------------
    #  -----------------------------------------------------------------------------------------------------------------

    def _update_overlays(self):
        """Update the overlay image(s) with the corresponding slice from the array3D."""
        if self.background_image_index == self.num_vols_allowed - 1:
            # the bottom image is at the top of the stack - there are no overlay images
            return
        # loop through images in the stack above the background image
        for layer_index in range(self.background_image_index + 1, self.num_vols_allowed):
            if self.image3D_obj_stack[layer_index] is not None:
                self._update_overlay_slice(layer_index)
            else:
                if self.array2D_stack[layer_index] is not None:
                    self.array2D_stack[layer_index].clear()
        # self._update_canvas()

        # update coordinates to reflect the current slice (so it updates without needing to move the mouse)
        coordinates_text = self.coordinates_label.text()
        if len(coordinates_text) > 0:
            pattern = r"x=\s*\d+,\s*y=\s*\d+,\s*z=\s*(\d+)"
            new_z = self.image_view.currentIndex
            # substitute the new z value
            new_string = re.sub(pattern, lambda m: m.group(0).replace(m.group(1), f"{new_z:3d}"), coordinates_text)
            self.coordinates_label.setText(new_string)

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
            # Set the levels to prevent LUT rescaling based on the slice content
            overlay_image_item.setLevels([overlay_image_object.display_min, overlay_image_object.display_max])
            overlay_image_item.setOpacity(overlay_image_object.alpha)
            overlay_image_item.setLookupTable(overlay_image_object.colormap)
            self.is_user_histogram_interaction = True

            # def _set_overlay_slice(self, layer_index):
            #     """Set the overlay image with the current slice from the array3D."""
            #     if self.array3D_stack[layer_index] is not None:
            #         overlay_image_object = self.image3D_obj_stack[layer_index]
            #         overlay_data = self.array3D_stack[layer_index]
            #         overlay_slice = overlay_data[int(self.image_view.currentIndex), :, :]
            #         overlay_image_item = self.array2D_stack[layer_index]
            #         # apply the slice to the overlay ImageItem
            #         self.is_user_histogram_interaction = False
            #         overlay_image_item.setImage(overlay_slice)
            #         # Set the levels to [0, 2] to avoid LUT rescaling based on the slice content
            #         overlay_image_item.setLevels([0, 2])  # FIXME: during dev
            #         overlay_image_item.setOpacity(overlay_image_object.alpha)
            #         overlay_image_item.setLookupTable(overlay_image_object.colormap)
            #         # self.image_view.updateImage()

            # # Manually reapply the LUT of the base image to ensure it doesn't change
            # if self.active_image_index != 0:
            #     base_image_item = self.image_view.getImageItem()  # Assuming the base image is layer 0
            #     base_image_item.setLookupTable(self.image3D_obj_stack[0].colormap)  # Reapply the base image LUT

            self.is_user_histogram_interaction = True
        # else:
        #     self.array2D_stack[layer_index].clear()

    def _update_canvas(self):
        """Update the canvas for painting. Masks the painting area using allowed values."""
        if self.image3D_obj_stack[self.paint_layer_index] is None or self.array3D_stack[self.paint_layer_index] is None:
            # FIXME: raise an error or warning?
            return

        if not self.is_painting:
            # TODO APPLY the mask to the paint image
            self.imageItem2D_canvas.clear()

        # mask the paint image to create a canvas for painting
        paint_image_object = self.image3D_obj_stack[self.paint_layer_index]
        if hasattr(paint_image_object, 'get_canvas_labels'):
            allowed_values = np.array(paint_image_object.get_canvas_labels())  # , dtype=canvas_slice.dtype.type
            if allowed_values is None:
                return
            # paint_value = self.paint_brush.get_value()  # Value to paint with
            paint_value = self.paint_brush.get_value()  # canvas_slice.dtype.type(

            # get the current slice of the paint image
            if self.paint_layer_index == self.background_image_index:
                paint_image_slice = self.image_view.getImageItem().image
            else:
                paint_image_slice = self.array2D_stack[self.paint_layer_index].image

            colors = [
                (255, 255, 255, 0),  # white for 0
                (255, 0, 0, 255),  # red for 1
                (0, 255, 0, 255),  # green for 2
                (0, 0, 255, 255),  # blue for 3
                (255, 255, 0, 255)  # yellow for 4
            ]

            # masked canvas: 0 where paint is allowed, -1 * paint_value where it’s not allowed
            temp_mask = np.where(np.isin(paint_image_slice, allowed_values), 0, (-1 * paint_value))
            self.imageItem2D_canvas.setImage(temp_mask)
            # mask_lookup_table = paint_image_object.colormap
            # # self.imageItem2D_canvas.setLookupTable(mask_lookup_table)
            color_map = pg.ColorMap(pos=np.linspace(0, 1, 5), color=colors)
            self.imageItem2D_canvas.setColorMap(color_map)
            self.imageItem2D_canvas.setDrawKernel(self.paint_brush.kernel, mask=None, center=self.paint_brush.center,
                                                  mode='add')

            # FIXME: here, we need to fiddle with the colormap to make all but the paint_value transparent
            # color_map = pg.ColorMap(pos=np.linspace(0, 1, 9), color=canvas_image_object.colormap)
            # self.imageItem2D_canvas.setColorMap(color_map)

            # self.imageItem2D_canvas.setDrawKernel(self.paint_brush.kernel, mask=None, center=self.paint_brush.center,
            #                                    mode='add')

    def _update_opacity(self, value):
        """Update the opacity of the active imageItem as well as the Image3D object."""
        if self.active_image_index is None:
            # TODO: raise an error or warning - no layer selected
            return
        opacity_value = value / 100  # convert slider value to a range of 0.0 - 1.0
        if self.active_image_index == 0:
            self.image_view.getImageItem().setOpacity(opacity_value)
            self.image3D_obj_stack[0].alpha = opacity_value
        else:
            self.array2D_stack[self.active_image_index].setOpacity(opacity_value)
            self.image3D_obj_stack[self.active_image_index].alpha = opacity_value

    def _enable_paint_brush(self, which_layer):
        """Enable or refresh the paint brush on the specified layer."""
        if self.image3D_obj_stack[which_layer] is None or self.array3D_stack[which_layer] is None:
            return
        if which_layer == self.background_image_index:
            canvas_image = self.image_view.imageItem
        else:
            canvas_image = self.array2D_stack[which_layer]

        self.paint_layer_index = which_layer
        self._update_canvas()

    def _disable_paint_brush(self, which_layer):
        if self.image3D_obj_stack[which_layer] is None:
            return
        if which_layer == self.background_image_index:
            self.image_view.imageItem.setDrawKernel(None)
        else:
            self.array2D_stack[which_layer].setDrawKernel(None)
        # TODO: save the painted data to the Image3D object

    def _apply_brush(self, x, y, painting):
        """
        :param x:
        :param y:
        :param painting:
        :return:
        Apply the current paint brush to the canvas image at the specified (x, y) coordinates.
        """
        # this method written by Kazem (thank you!)
        # FIXME during dev
        self.paint_layer_index = 2

        data = self.array3D_stack[self.paint_layer_index]
        data_slice = data[int(self.image_view.currentIndex), :, :]

        # Define the range for the brush area
        half_brush = self.paint_brush.get_size() // 2
        x_start = max(0, x - half_brush)
        x_end = min(data_slice.shape[0], x + half_brush + 1)
        y_start = max(0, y - half_brush)
        y_end = min(data_slice.shape[1], y + half_brush + 1)

        # Create a mask for the brush area within the bounds of data
        brush_area = data_slice[x_start:x_end, y_start:y_end]

        paint_image_object = self.image3D_obj_stack[self.paint_layer_index]
        if not hasattr(paint_image_object, 'get_canvas_labels'):
            # FIXME: raise an error or warning?
            return
        allowed_values = np.array(paint_image_object.get_canvas_labels())  # , dtype=canvas_slice.dtype.type
        mask = np.isin(brush_area, allowed_values)

        # apply active label or 0 depending on painting or erasing
        if painting:
            brush_area[mask] = self.paint_brush.get_value()
        else:
            # erasing
            brush_area[mask] = 0

        # update only the modified slice in the 3D array
        data[int(self.image_view.currentIndex), :, :] = data_slice
        # Update the displayed image
        if self.paint_layer_index == self.background_image_index:
            view_range = self.image_view.view.viewRange()
            self.image_view.setImage(data)
            self.image_view.view.setRange(xRange=view_range[0], yRange=view_range[1],
                                          padding=0)  # preserve the current zoom and pan state
            self.image_view.setCurrentIndex(self.current_slice_index)  # preserve the current slice
        else:
            self.array2D_stack[self.paint_layer_index].setImage(data_slice)

    def _update_image_object(self):
        """Update the display min and max of the active Image3D object.
        This is the slot for the signal emitted when the user interacts with the histogram widget.
        The histogram widget automatically updates the imageItem, so we also need to update the Image3D object."""
        pass
        # if self.is_user_histogram_interaction:
        #     # only do this if the user has interacted with the histogram. Not when the histogram is programmatically
        #     # updated by another method.
        #     if self.active_image_index is None:
        #         # TODO: raise an error or warning - no layer selected
        #         return
        #     levels = self.image_view.getHistogramWidget().getLevels()
        #     self.image3D_obj_stack[self.active_image_index].display_min = levels[0]
        #     self.image3D_obj_stack[self.active_image_index].display_max = levels[1]
        # # TODO: update Image3D colormap, too?

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

    def _layer_selection_changed(self, index):
        """Update the layer associated with histogram settings and interactions."""
        self.active_image_index = index

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

    def _mouse_press(self, event):
        """
        :param event:
        :return:
        Capture mouse press event and handle painting and marking actions before passing the event back to pyqtgraph.
        """
        # FIXME: during testing and dev
        print("Mouse pressed")
        print(f"Screen coordinates: {event.scenePos()}")

        if event.modifiers() & Qt.ShiftModifier:
            if event.button() == Qt.LeftButton:
                # shift + left click = painting
                self.is_painting = True
            elif event.button() == Qt.RightButton:
                # shift + right click = erasing
                self.is_erasing = True

        # FIXME: might not work as expected. Maybe just modify the current pixel and don't specifically
        #  call _mouse_move()?
        # if self.is_painting or self.is_erasing:
        #     self._mouse_move(event)

        # TODO: implement marking mode

        # pass the event back to pyqtgraph for any further processing
        self.original_mouse_press(event)

        # # Paint action modifies self.temp_image (3D array) at the current slice
        # if self.is_painting:
        #     # Get current slice from ImageView
        #     current_slice = int(self.image_view.currentIndex)
        #     print(f"Current slice {current_slice}")
        # elif self.is_marking:
        #     if event.button() == Qt.LeftButton:
        #         img_item = self.image_view.getImageItem()
        #         pos = event.pos()
        #         mouse_point = img_item.mapFromScene(pos)
        #         if img_item is not None and img_item.sceneBoundingRect().contains(mouse_point):
        #             # Transform the scene coordinates to image coordinates
        #             img_shape = self.image3D_obj_stack[0].data.shape
        #             x = int(pos.x())
        #             y = int(pos.y())
        #             z = int(self.image_view.currentIndex)  # Get the current slice index
        #
        #             # ensure coordinates are within image bounds
        #             if 0 <= x < img_shape[0] and 0 <= y < img_shape[1] and 0 <= z < img_shape[2]:
        #                 self.add_marker(x, y)
        #
        #             print(f"Point added at: x={x}, y={y}, z={z}")
        #
        # # propagate the event for any further processing
        # event.ignore()

        # if self.is_painting:
        #     # Get current slice from ImageView
        #     current_slice = int(self.image_view.currentIndex)
        #     print(f"Current slice {current_slice}")
        # elif self.is_marking:
        #     if event.button() == Qt.LeftButton:
        #         img_item = self.image_view.getImageItem()
        #         pos = event.pos()
        #         mouse_point = img_item.mapFromScene(pos)
        #         if img_item is not None and img_item.sceneBoundingRect().contains(mouse_point):
        #             # Transform the scene coordinates to image coordinates
        #             img_shape = self.image3D_obj_stack[0].data.shape
        #             x = int(pos.x())
        #             y = int(pos.y())
        #             z = int(self.image_view.currentIndex)  # Get the current slice index
        #
        #             # ensure coordinates are within image bounds
        #             if 0 <= x < img_shape[0] and 0 <= y < img_shape[1] and 0 <= z < img_shape[2]:
        #                 self.add_marker(x, y)
        #
        #             print(f"Point added at: x={x}, y={y}, z={z}")

    def _mouse_move(self, event):
        """
        :param pos:
        :return:
        Update the coordinates label and crosshairs with the current mouse position, apply paint brush if painting,
        move marker if dragging.
        """
        # print("Mouse moved")
        # print(pos)

        if self.background_image_index is None or self.image3D_obj_stack[self.background_image_index] is None:
            return

        # use the background image to get the coordinates
        # the background image is always the image view's image item
        # ideally, this would be the high-res medical image, but user is allowed to load overlays (heatmap,
        # segementation, masks, etc.) without having a background layer loaded.
        pos = event.scenePos()
        img_item = self.image_view.getImageItem()  # should be same image referenced by self.background_image_index
        if img_item is None or not img_item.sceneBoundingRect().contains(pos):
            #  position is outside the scene bounding rect, just clear the coords label
            self.coordinates_label.setText("")
        else:
            # transform the scene coordinates to image coordinates
            mouse_point = img_item.mapFromScene(pos)
            # TODO: account for view direction, only axial implemented here
            img_shape = self.image3D_obj_stack[self.background_image_index].data.shape
            x = int(mouse_point.x())
            y = int(mouse_point.y())
            z = int(self.image_view.currentIndex)  # get the current slice index (same as self.current_slice_index)

            # FIXME: during testing and dev
            print(f"Image coordinates: {x}, {y}, {z}")

            # update the crosshairs
            self.horizontal_line.setPos(y)
            self.vertical_line.setPos(x)
            if 0 <= x < img_shape[0] and 0 <= y < img_shape[1] and 0 <= z < img_shape[2]:
                # if coordinates are within image bounds
                # get the value of all voxels at this position
                voxel_values = [self.image3D_obj_stack[self.background_image_index].data[x, y, z]]
                image_objs = [im for im in self.image3D_obj_stack if im is not None]
                if len(image_objs) > 1:
                    for i in range(1, len(image_objs)):
                        voxel_values.append(image_objs[i].data[x, y, z])

                # FIXME: during testing and dev
                # if self.is_painting and self.imageItem2D_canvas.image is not None:
                # print(f"canvas: {self.imageItem2D_canvas.image[x, y]}")

                # update the coordinates label
                coordinates_text = "x={:3d}, y={:3d}, z={:3d}".format(x, y, z)
                # append voxel values for each image
                for value in voxel_values:
                    coordinates_text += ", {:4.2f} ".format(value)
                self.coordinates_label.setText(coordinates_text)

                # if painting, erasing, or dragging marker
                if self.is_painting:
                    self._apply_brush(x, y, True)
                elif self.is_erasing:
                    self._apply_brush(x, y, False)
                elif self.is_dragging_marker:
                    # TODO
                    # # Get the position of the mouse
                    # img_item = self.image_view.getImageItem()
                    # mouse_point = img_item.mapFromScene(pos)
                    #
                    # # Update the position of the marker
                    # x = int(mouse_point.x())
                    # y = int(mouse_point.y())
                    #
                    # # Move the marker to the new position
                    # self.is_dragging_marker.setData(pos=[(x, y)], brush='r', size=10)
                    pass
                else:
                    # probably panning - pass the event back to pyqtgraph for any further processing
                    self.original_mouse_move(event)

            else:
                # position is outside the image bounds, just clear the coords labe
                self.coordinates_label.setText("")

    def _mouse_release(self, event):
        """
        :param event:
        :return:
        Disable painting, erasing, and dragging marker actions and pass the event back to pyqtgraph.
        """
        # FIXME: during testing and dev
        print("Mouse Released")

        self.is_painting = False
        self.is_erasing = False
        self.is_dragging_marker = False
        # pass event back to pyqtgraph for any further processing
        self.original_mouse_release(event)

    def _toggle_crosshairs(self):
        """toggle crosshair visibility"""
        self.show_crosshairs = not self.show_crosshairs
        self.horizontal_line.setVisible(self.show_crosshairs)
        self.vertical_line.setVisible(self.show_crosshairs)

    def _toggle_histogram(self):
        """toggle the visibility of the histogram/colormap/opacity widget"""
        histogram = self.image_view.getHistogramWidget()
        is_visible = histogram.isVisible()
        histogram.setVisible(not is_visible)
        # if self.active_image_index is None:
        #     return
        # if self.image3D_obj_stack[self.active_image_index] is not None:
        #     self.image_view.getImageItem().setLookupTable(self.image3D_obj_stack[self.active_image_index].colormap)
        # self.image_view.updateImage()

        # self._set_histogram_colormap(self.image3D_obj_stack[self.active_image_index].colormap)
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
