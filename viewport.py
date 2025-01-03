import numpy as np
import pyqtgraph as pg
import re
import shortuuid

from PyQt5.QtWidgets import QVBoxLayout, QWidget, QPushButton, QHBoxLayout, QLabel, QSlider, QComboBox
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtCore import Qt, pyqtSignal

from enumerations import ViewDir
from paint_brush import PaintBrush
from interaction_method import InteractionMethod

from pyqtgraph import ScatterPlotItem


class CustomScatterPlotItem(pg.ScatterPlotItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mouse_press_callback = None
        self.mouse_release_callback = None
        # self.current_point = None  # Track the currently selected point

    def set_mouse_press_callback(self, callback):
        self.mouse_press_callback = callback

    def set_mouse_release_callback(self, callback):
        self.mouse_release_callback = callback

    def mousePressEvent(self, event):
        # find the spot that was pressed and pass it to custom callback
        clicked_spots = self.pointsAt(event.pos())
        # if clicked_spots:
        if len(clicked_spots) > 0:
            clicked_spot = clicked_spots[0]  # Assume only one point is clicked
            point_data = clicked_spot.data()  # Access the metadata for the point

            # # FIXME: during testing and dev
            # print(f"CustomScatterPlotItem:_mousePressEvent: {point_data} at position {clicked_spot.pos()}")

            # call the custom callback if provided
            if self.mouse_press_callback:
                self.mouse_press_callback(event, point_data)
            else:
                # Preserve default behavior
                super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.mouse_release_callback:
            self.mouse_release_callback(event)
        super().mouseReleaseEvent(event)  # Ensure default behavior is preserved



class Viewport(QWidget):
    """ This class displays one or more 3D images. It is interactive and allows the user to pan, zoom, and scroll
    through images. Multiple images can be stacked on top of each other to create overlays. The user can also paint
    (modify the voxel values) and add points to the image. Tools are provided for modifying the colormap and opacity
    of the images. The calling class must provide the view desired view direction (axial, coronal, sagittal).
    The calling class must also provide the maximum number of image allowed in the stack.
    A viewport is a subclass of QWidget and can be added to a layout in a QMainWindow.
    """
    # signals to notify parent class of changes in the viewport
    point_added_signal = pyqtSignal(object, object, object)
    point_selected_signal = pyqtSignal(object, object, object)
    point_moved_signal = pyqtSignal(object, object, object)
    slice_changed_signal = pyqtSignal(object, object)


    def __init__(self, parent, _id, _view_dir, _num_vols, _paint_method=None, _erase_method=None, _point_method=None,
                 _zoom_method=None, _pan_method=None, _window_method=None, _alpha_blending=False):
        super().__init__()

        self.parent = parent
        self.id = _id
        self.view_dir = _view_dir.dir  # ViewDir.AX (axial), ViewDir.COR (coronal), ViewDir.SAG (sagittal)
        self.num_vols_allowed = _num_vols  # number of images (layers) to display
        # self.num_vols = 0  # keep track of the number of images currently linked to this viewport
        # self.num_displayed_images = 0  # FIXME: might not be necessary?

        # parent can provide custom methods for interacting with the viewport (e.g., painting, erasing, pointing,
        #   zooming, panning, and windowing)panning, and windowing)
        self.paint_im = _paint_method  # method for painting
        self.erase_im = _erase_method  # method for erasing
        self.point_im = _point_method  # method for making points
        self.zoom_im = _zoom_method  # TODO: future implementation, custom zoom method
        self.pan_im = _pan_method  # TODO: future implementation, custom pan method
        self.window_im = _window_method  # TODO: future implementation, custom method for windowing
        self.interaction_state = None  # implemented values: 'painting', 'erasing'

        # interactive point placement
        self.add_point_mode = False  # if adding points, are we placing a new point?
        self.pending_point_mode = False  # if adding points, are we waiting for the user to complete the point?
        self.drag_point_mode = False  # are we dragging a point to a new location?
        self.point_moved = False
        self.points = []  # this will be a list of point objects?
        self.selected_point = None
        # default colors for points TODO: let parent class update these
        self.idle_point_color = (255, 0, 0, 255)  # red
        self.selected_point_color = (0, 255, 0, 255)  # green
        self.temp_point_color = (255, 255, 0, 255) # yellow
        self.idle_pen = pg.mkPen(self.idle_point_color, width=1)  # red pen for not idle points
        self.idle_brush = pg.mkBrush(self.idle_point_color)
        self.selected_pen = pg.mkPen(self.selected_point_color, width=2)  # green pen for selected point
        self.selected_brush = pg.mkBrush(self.selected_point_color)
        self.temp_pen = pg.mkPen(self.temp_point_color, width=1)  # yellow pen for temporary point
        self.temp_brush = pg.mkBrush(self.temp_point_color)
        # dictionary to store points for each slice
        self.slice_points = {}

        # convenience reference to the background image item
        self.background_image_index = None
        # keep track of the active layer for histogram, colormap, and opacity settings interaction
        self.active_image_index = 0  # default to the first layer (background)
        self.canvas_layer_index = None  # the layer that is currently being painted on
        self.point_layer_index = None  # the layer that points are currently being added to
        self.current_slice_index = 0

        # interactive painting
        self.is_painting = False
        self.is_erasing = False
        self.paint_brush = PaintBrush()

        self.display_convention = "RAS"  # default to RAS (radiological convention) # TODO, make this an input opt.

        # initialize widgets and their slots -------------------------------------
        # the main layout for this widget ----------
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # horizontal layout for the coordinates label and tool buttons ----------
        top_layout = QHBoxLayout()
        # coordinates label
        self.coordinates_label = QLabel("", self)
        font = QFont("Segoe UI", 9)
        font.setItalic(True)
        self.coordinates_label.setFont(font)
        # self.coordinates_label.setAlignment(Qt.AlignVCenter)
        top_layout.addWidget(self.coordinates_label)

        # add spacing between the buttons and right edge
        top_layout.addStretch()
        # histogram visibility button
        # self.histogram_button = QPushButton()
        # self.histogram_button.setCheckable(True)
        # self.histogram_button.setChecked(False)
        # self.histogram_button.setFixedSize(16, 16)
        # histogram_icon = QIcon("..\\ui\\colorWheelIcon.svg")
        # self.histogram_button.setIcon(histogram_icon)
        # self.histogram_button.clicked.connect(self._toggle_histogram)
        # top_layout.addWidget(self.histogram_button)

        # add the top layout to the main layout (above the imageView)
        main_layout.addLayout(top_layout)

        # layout for the image view and opacity slider ----------
        image_view_layout = QHBoxLayout()
        # the image view widget ----------
        self.image_view = pg.ImageView()

        # FIXME: testing
        # self.image_view.setFocusPolicy(Qt.ClickFocus)

        self.original_mouse_press = self.image_view.getView().scene().mousePressEvent
        self.original_mouse_release = self.image_view.getView().scene().mouseReleaseEvent
        self.original_mouse_move = self.image_view.getView().scene().mouseMoveEvent
        self.image_view.getHistogramWidget().setVisible(False)
        self.image_view.ui.menuBtn.setVisible(False)  # hide these for now
        self.image_view.ui.roiBtn.setVisible(False)  # hide these for now
        image_view_layout.addWidget(self.image_view, stretch=2)
        main_layout.addLayout(image_view_layout)

        # create lines for slice intersection guides
        self.axial_line_color = 'r'
        self.sag_line_color = 'y'
        self.cor_line_color = 'g'
        self.slice_line_width = 0.5
        self.horizontal_line = pg.InfiniteLine(angle=0, pen=pg.mkPen('r', width=self.slice_line_width), movable=False)
        self.vertical_line = pg.InfiniteLine(angle=90, pen=pg.mkPen('r', width=self.slice_line_width), movable=False)
        self.horizontal_line_idx = 0
        self.vertical_line_idx = 0
        if self.view_dir == ViewDir.AX.dir:
            self.horizontal_line.setPen(pg.mkPen(self.cor_line_color, width=self.slice_line_width))
            self.vertical_line.setPen(pg.mkPen(self.sag_line_color, width=self.slice_line_width))
        elif self.view_dir == ViewDir.COR.dir:
            self.horizontal_line.setPen(pg.mkPen(self.axial_line_color, width=self.slice_line_width))
            self.vertical_line.setPen(pg.mkPen(self.sag_line_color, width=self.slice_line_width))
        else:  # "SAG"
            self.horizontal_line.setPen(pg.mkPen(self.axial_line_color, width=self.slice_line_width))
            self.vertical_line.setPen(pg.mkPen(self.cor_line_color, width=self.slice_line_width))
        self.image_view.addItem(self.horizontal_line, ignoreBounds=True)
        self.image_view.addItem(self.vertical_line, ignoreBounds=True)
        self.show_slice_guides = True  # default to showing slice guides
        # but don't show them until an image is displayed
        self.horizontal_line.setVisible(False)
        self.vertical_line.setVisible(False)

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
        # image data 2D arrays (slices) - one less than total number of images allowed because these are overlays
        # and 3D background image is always displayed first in the image_view
        self.array2D_stack = [pg.ImageItem() for _ in range(self.num_vols_allowed)]
        for i in range(0, self.num_vols_allowed):
            self.image_view.view.addItem(self.array2D_stack[i])
        # add a canvas mask for painting
        # self.imageItem3D_canvas = pg.ImageItem()
        self.imageItem2D_canvas = pg.ImageItem()
        self.image_view.view.addItem(self.imageItem2D_canvas)

        # this is the plot item for creating points. Customized to capture mouse press and mouse release events
        self.scatter = CustomScatterPlotItem()
        self.scatter.set_mouse_press_callback(self._scatter_mouse_press)
        # self.scatter.set_mouse_release_callback(self._scatter_mouse_release)
        self.image_view.getView().addItem(self.scatter)

        # differentiate between user interacting with histogram widget and histogram updated by the viewport
        # self.is_user_histogram_interaction = True
        # self.image_view.getHistogramWidget().sigLevelChangeFinished.connect(self._update_image_object)
        # self.image_view.getHistogramWidget().sigLookupTableChanged.connect(self._reapply_lut)

        # connect the mouse move event to the graphics scene
        self.image_view.getView().scene().mouseMoveEvent = self._mouse_move
        # self.image_view.getView().scene().sigMouseMoved.connect(self._mouse_move)

        # connect the mouse click event to the graphics scene
        self.image_view.getView().scene().mousePressEvent = self._mouse_press
        # self.image_view.imageItem.mousePressEvent = self._mouse_press

        # connect the mouse release event to the graphics scene
        self.image_view.getView().scene().mouseReleaseEvent = self._mouse_release
        # self.image_view.imageItem.mouseReleaseEvent = self._mouse_release

        # connect the mouse click event to the graphics scene
        # self.image_view.imageItem.mouseClickEvent = self._mouse_click

        # when the timeLine position changes, update the overlays
        self.image_view.timeLine.sigPositionChanged.connect(self._slice_changed)

    #  -----------------------------------------------------------------------------------------------------------------
    #  "Public" methods API --------------------------------------------------------------------------------------------
    #  -----------------------------------------------------------------------------------------------------------------

    def add_layer(self, image, stack_position):
        """
        Update the stack of 3D images with a new 3D image for this viewPort.
        image = None is allowed and will clear the layer at the specified position.
        :param image:
        :param stack_position:
        :return:
        """

        if stack_position > self.num_vols_allowed:
            # TODO: raise an error or warning - the stack position is out of bounds
            return

        self.image3D_obj_stack[stack_position] = image  # not a deep copy, reference to the image3D object
        self.active_image_index = stack_position
        # PyQtGraph expects the first dimension of the array to represent time or frames in a sequence, but when used
        # for static 3D volumes, it expects the first dimension to represent slices (essentially the "depth" dimension
        # for 3D data).
        if image is not None:
            # populate the 3D array stack with the data from this image3D object
            if self.view_dir == ViewDir.AX.dir:
                # axial view: transpose image data (x, y, z) to (z, x, y) for pyqtgraph
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data,
                                                                  (2, 0, 1))
                # FIXME: during testing and dev
                print(f"3D array shape: {self.array3D_stack[stack_position].shape}")

                ratio = image.dy / image.dx
            elif self.view_dir == ViewDir.COR.dir:
                # transpose image data (x, y, z) to (x, z, y) for coronal view, then to (y, x, z) for pyqtgraph
                # then save the transposed array  # FIXME: should z be flipped? like x, -z, y?
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data,
                                                                  (1, 0, 2))
                # FIXME: during testing and dev
                print(f"3D array shape: {self.array3D_stack[stack_position].shape}")

                ratio = image.dz / image.dx
            else:  # "SAG"
                # transpose image data (x, y, z) to (y, z, x) for sagittal view, then (x, y, z) for pyqtgraph
                # then save the transposed array
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data,
                                                                  (0, 1, 2))
                # FIXME: during testing and dev
                print(f"3D array shape: {self.array3D_stack[stack_position].shape}")

                ratio = image.dz / image.dy

            # set the aspect ratio of the image view to match this new image
            # FIXME: is there a better way to do this? Should this be done in refresh()?
            self.image_view.getView().setAspectLocked(True, ratio=ratio)
            # start at middle slice
            self.current_slice_index = (int(self.array3D_stack[stack_position].shape[0] // 2))

            self.refresh_preserve_extent()
            # emit signal to notify parent class that the slice has changed (to update the slice guides in other vps)
            self.slice_changed_signal.emit(self.id, self.current_slice_index)
        else:
            self.array3D_stack[stack_position] = None

            # self.horizontal_line.setVisible(False)
            # self.vertical_line.setVisible(False)

        self.refresh()

        # TODO: update the layer selection combo and active layer

    def goto_slice(self, slice_index):
        """
        Display the specified slice in the image view. Set self.current_slice_index to the specified slice index, then
        calls refresh.

        :param slice_index:
        :return:
        """
        img_item = self.image_view.getImageItem()
        if img_item is not None:
            array3D = self.array3D_stack[self.background_image_index]  # 3D array of data, optionally transposed
            if array3D is not None:
                img_shape = array3D.shape
                if 0 <= slice_index < img_shape[0]:
                    self.current_slice_index = slice_index
                    self.refresh_preserve_extent()

    def remove_layer(self, stack_position):
        # FIXME: this wipes out the image3D object! That is not what we want to do
        self.image3D_obj_stack[stack_position] = None

        self.array3D_stack[stack_position] = None
        # self.array2D_stack[stack_position].clear()
        self.array2D_stack[stack_position] = None
        if stack_position == self.canvas_layer_index:
            self.canvas_layer_index = None
        self.refresh()

    def hide_layer(self, stack_position):
        if self.image3D_obj_stack[stack_position] is None:
            return
        if stack_position == self.background_image_index:
            self.image_view.getImageItem().setVisible(False)
        else:
            self.array2D_stack[stack_position].setVisible(False)

    def show_layer(self, stack_position):
        if self.image3D_obj_stack[stack_position] is None:
            return
        if stack_position == self.background_image_index:
            self.image_view.getImageItem().setVisible(True)
        else:
            self.array2D_stack[stack_position].setVisible(True)

    def move_layer_up(self):
        # TODO
        pass

    def move_layer_down(self):
        # TODO
        pass

    def get_current_slice(self):
        return self.image_view.currentIndex

    # points -----------------------------------------------------------------------------------------------------------

    # def set_point_selected(self, point):
    #     """
    #     Sets the specified point as selected. Deselects all other points in this viewport.
    #
    #     :param point:
    #     :return:
    #     """
    #     # first clear any (all?) selected point(s?) (assumes more than one can be selected at once?)
    #     self.clear_selected_points()

    def toggle_point_selected(self, point_id, is_selected):
        """
        Sets the point with the specified id as selected. Deselects all other points in this viewport.
        Since this is called by a parent class, no need to emit signal.

        :param point_id:
        :param is_selected:
        :return:
        """
        if is_selected:
            self.clear_selected_points()

        point = self.find_point_by_id(point_id)
        if point is not None:
            point['is_selected'] = not point['is_selected']  # toggle selection

        self._update_points_display()

    def find_point_by_id(self, point_id):
        """
        Find the point with the specified ID across all slices.

        :param point_id: str (unique ID of the point)
        :return: tuple (slice_index, point_data) if found, otherwise None
        """
        for slice_idx, points in self.slice_points.items():
            for pt in points:
                if pt['id'] == point_id:
                    return pt
        return None

    def clear_selected_points(self):
        """
        Sets all points in this viewport to unselected.

        :return:
        """
        for slice_idx, points in self.slice_points.items():
            for pt in points:
                pt['is_selected'] = False
        self.selected_point = None

    def set_add_point_mode(self, _is_adding):
        """Can be called by external class to toggle add_point mode."""
        self.add_point_mode = _is_adding

    def set_pending_point_mode(self, _pending):
        self.pending_point_mode = _pending

    def clear_points(self):
        """Remove all points from the image view."""
        for point in self.points:
            self.image_view.removeItem(point)
        self.points.clear()

    def import_points(self, points):
        """called by external class to import points from a list of (x, y, z) coordinates."""
        pass
        # for x, y, z in points:
        #     self.add_point(x, y, z)

    # painting ---------------------------------------------------------------------------------------------------------
    # def toggle_painting_mode(self, which_layer, _is_painting):
    #     """Called by external class to toggle painting mode on or off."""
    #     # painting should only be done on the layer that is identified by which_layer
    #     if self.image3D_obj_stack[which_layer] is None:
    #         # TODO: raise an error or warning - no layer selected
    #         return
    #     self.canvas_layer_index = which_layer
    #     self.is_painting = _is_painting
    #
    #     if self.is_painting:
    #         # enable painting on this layer
    #         self._update_canvas()
    #         self.setCursor(QCursor(Qt.CrossCursor))
    #     else:
    #         # disable painting on this layer
    #         self._disable_paint_brush(self.canvas_layer_index)
    #         self.setCursor(QCursor(Qt.ArrowCursor))

    def update_paint_brush(self, brush):
        """Update the paint brush settings. Called by external class to update the paint brush settings,
        applies updated brush to current paint layer, if is_painting."""
        self.paint_brush.set_size(brush.size)
        self.paint_brush.set_value(brush.value)
        self.paint_brush.set_shape(brush.shape)

        # if self.canvas_layer_index is None:
        #     return
        # if self.is_painting:
        #     self._update_canvas()

    def set_canvas_layer(self, index):
        """Set the canvas layer for painting."""
        self.canvas_layer_index = index

    def refresh_preserve_extent(self):
        """
        Refresh the viewport without changing the current view extent.
        """
        # save the current view state (extent)
        view_box = self.image_view.getView()
        current_range = view_box.viewRange()  # [[x_min, x_max], [y_min, y_max]]

        self.refresh()

        # restore the view range
        view_box.setRange(
            xRange=current_range[0],
            yRange=current_range[1],
            padding=0  # Disable padding to restore exact range
        )

    def refresh(self):
        """
        Should be called when one of the images displayed in the viewport changes. Sets the image item, and connects the
        histogram widget to the image item. Also updates the overlay images.
        """

        self.image_view.clear()

        # the image stack may have empty slots, so we need to find the first non-empty image to display
        found_bottom_image = False
        self.background_image_index = None

        for ind, im_obj in enumerate(self.image3D_obj_stack):
            if im_obj is None:
                continue
            else:
                if not found_bottom_image:
                    # this is the bottom image in the stack and will be set as the 3D background image item in the
                    # image view
                    im_data = self.array3D_stack[ind]  # the (optionally transposed) 3D array
                    # self.is_user_histogram_interaction = False  # prevent the histogram from updating the image3D object
                    # setImage causes the z-slider slot to be called, which resets the current slice index to 0
                    # disconnect slot to prevent this from happening
                    try:
                        # disconnect the slot before making changes
                        self.image_view.timeLine.sigPositionChanged.disconnect(self._slice_changed)
                    except TypeError:
                        # if the slot was not connected, ignore the error
                        pass
                    self.image_view.setImage(im_data)
                    # FIXME: set aspect ratio based on base image? What about overlay?
                    if self.view_dir == ViewDir.AX.dir:
                        self.image_view.view.setAspectLocked(True, ratio=im_obj.dx / im_obj.dy)
                    elif self.view_dir == ViewDir.COR.dir:
                        self.image_view.view.setAspectLocked(True, ratio=im_obj.dx / im_obj.dz)
                    else:  # "SAG"
                        self.image_view.view.setAspectLocked(True, ratio=im_obj.dy / im_obj.dz)

                    self.image_view.timeLine.sigPositionChanged.connect(self._slice_changed)

                    # FIXME: testing
                    # self.scatter_items = [pg.ScatterPlotItem() for _ in range(im_data.shape[0])]
                    # for scatter in self.scatter_items:
                    #     self.image_view.getView().addItem(scatter)

                    main_image = self.image_view.getImageItem()
                    # Set the levels to prevent LUT rescaling based on the slice content
                    main_image.setLevels([im_obj.display_min, im_obj.display_max])
                    # apply the opacity of the Image3D object to the ImageItem
                    main_image.setOpacity(im_obj.alpha)
                    main_image.setLookupTable(im_obj.lookup_table)

                    # FIXME: correct? # radiological convention = RAS+ notation
                    #  (where patient is HFS??, ie, patient right is on the left of the screen, and patient posterior
                    #  at the bottom of the screen?)
                    self.image_view.getImageItem().getViewBox().invertY(False)
                    if im_obj.x_dir == 'R':
                        # x increases from screen right to left if RAS+ notation (and patient is HFS?)
                        self.image_view.getImageItem().getViewBox().invertX(True)

                    # self.is_user_histogram_interaction = True
                    self.background_image_index = ind
                    found_bottom_image = True
                else:
                    # this is an overlay image, so we need to get a slice of it and set it as an overlay
                    self._update_overlay_slice(ind)  # uses self.current_slice_index

                # set the current slice index to the first slice of the background image
                try:
                    # disconnect the slot before making changes
                    self.image_view.timeLine.sigPositionChanged.disconnect(self._slice_changed)
                except TypeError:
                    # if the slot was not connected, ignore the error
                    pass
                self.image_view.setCurrentIndex(self.current_slice_index)
                self.image_view.timeLine.sigPositionChanged.connect(self._slice_changed)

        # update the crosshairs
        if self.background_image_index is None:
            # no image to display, so hide slice guides, even if visibility is set to True
            self.horizontal_line.setVisible(False)
            self.vertical_line.setVisible(False)
        else:
            self.horizontal_line.setVisible(self.show_slice_guides)
            self.vertical_line.setVisible(self.show_slice_guides)
            if self.show_slice_guides:
                self.horizontal_line.setPos(self.horizontal_line_idx)
                self.vertical_line.setPos(self.vertical_line_idx)

        self._update_points_display()

        self.image_view.show()

    #  -----------------------------------------------------------------------------------------------------------------
    #  "Private" methods -----------------------------------------------------------------------------------------------
    #  -----------------------------------------------------------------------------------------------------------------



    def _slice_changed(self):
        """
        Simply update self.current_slice_index from the imageView's current slice. Called when the z-slicer has changed.
        :return:
        """
        self.current_slice_index = self.image_view.currentIndex

        self.refresh_preserve_extent()

        self.slice_changed_signal.emit(self.id, self.current_slice_index)

    def _update_overlays(self):
        """
        When the slice index has changed, manually update the overlay image(s) with the corresponding slice from
        the array3D.

        :return:
        """
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

        self._update_points_display()

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
            # self.is_user_histogram_interaction = False
            overlay_image_item.setImage(overlay_slice)
            # Set the levels to prevent LUT rescaling based on the slice content
            overlay_image_item.setLevels([overlay_image_object.display_min, overlay_image_object.display_max])
            overlay_image_item.setOpacity(overlay_image_object.alpha)
            overlay_image_item.setLookupTable(overlay_image_object.lookup_table)
            # self.is_user_histogram_interaction = True

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

            # self.is_user_histogram_interaction = True
        # else:
        #     self.array2D_stack[layer_index].clear()

    def _update_opacity(self, value):
        """Update the opacity of the active imageItem as well as the Image3D object."""
        if self.image_view.getImageItem() is None:
            return
        # if self.active_image_index is None:
        #     # TODO: raise an error or warning - no layer selected
        #     return
        opacity_value = value / 100  # convert slider value to a range of 0.0 - 1.0
        if self.active_image_index == 0:
            self.image_view.getImageItem().setOpacity(opacity_value)
            self.image3D_obj_stack[0].alpha = opacity_value
        else:
            self.array2D_stack[self.active_image_index].setOpacity(opacity_value)
            self.image3D_obj_stack[self.active_image_index].alpha = opacity_value

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
                    if im.lookup_table is not None:
                        self.image_view.getImageItem().setLookupTable(im.lookup_table)
                else:
                    if self.array2D_stack[ind] is not None:
                        self.array2D_stack[ind].setLookupTable(im.lookup_table)

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

    def plotdatacr_to_plotxy(self, plot_data_col, plot_data_row):
        """
        Convert plot data coordinates to plot x and y coordinates. This method is used to convert the plot data
        coordinates to the plot x and y coordinates that are used by the scatter plot item.

        :param plot_data_col:
        :param plot_data_row:
        :return: plot_x, plot_y
        """
        image3D_obj = self.image3D_obj_stack[self.background_image_index]

        xy = None
        if image3D_obj is not None:
            if self.display_convention == 'RAS':
                if self.view_dir == ViewDir.AX.dir:
                    # patient right is on the left of the screen, and patient posterior at the bottom of the screen
                    if image3D_obj.x_dir == 'R':  # x-axis is inverted, so plot_x increases right to left
                        plot_x = plot_data_col
                    else:  # 'L'
                        plot_x = image3D_obj.num_cols - 1 - plot_data_col
                    if image3D_obj.y_dir == 'A':
                        plot_y = plot_data_row
                    else:  # 'P'
                        plot_y = image3D_obj.num_rows - 1 - plot_data_row
                elif self.view_dir == ViewDir.SAG.dir:
                    # patient anterior is on the left of the screen, and patient inferior is at the bottom
                    if image3D_obj.z_dir == 'S':
                        # image3D slices increase front to back
                        # plot data row increases bottom to top
                        plot_y = plot_data_row
                    else:  # 'I'
                        plot_y = image3D_obj.num_slices - 1 - plot_data_row
                    if image3D_obj.y_dir == 'A':
                        # image3D voxel rows increase bottom to top
                        # x-axis is inverted, so plot_col increases right to left
                        plot_x = plot_data_col
                    else:  # 'P'
                        plot_x = image3D_obj.num_rows - 1 - plot_data_col
                elif self.view_dir == ViewDir.COR.dir:
                    # patient right is on the left of the screen, and patient inferior is at the bottom
                    if image3D_obj.x_dir == 'R':
                        # image3D columns increase right to left
                        # x-axis is inverted, so plot_col also increases right to left
                        plot_x = plot_data_col
                    else:  # 'L'
                        plot_x = image3D_obj.num_cols - 1 - plot_data_col
                    if image3D_obj.z_dir == 'S':
                        # image3D slices increase front to back
                        # plot rows increase bottom to top
                        plot_y = plot_data_row
                    else:  # 'I'
                        plot_y = image3D_obj.num_slices - 1 - plot_data_row

                xy = np.array([plot_x, plot_y])

        return xy

    def plotxyz_to_plotdatacrs(self, plot_x, plot_y, plot_z):
        """
        Convert the x, y, and z (slice index) plot coordinates to the col, row, slice coordinates of the underlying
        3D image data.
        :param plot_x:
        :param plot_y:
        :param plot_z:
        :return:
        """

        # the Image3D object that the plot data originates from. Only needed here for info about axes directions
        image3D_obj = self.image3D_obj_stack[self.background_image_index]

        crs = None
        if image3D_obj is not None:
            if self.display_convention == 'RAS':
                if self.view_dir == ViewDir.AX.dir:
                    # patient right is on the left of the screen, and patient posterior at the bottom of the screen
                    if image3D_obj.x_dir == 'R': # x-axis is inverted, so plot_x increases right to left
                        plot_data_col = plot_x
                    else:  # 'L'
                        plot_data_col = image3D_obj.num_cols - 1 - plot_x
                    if image3D_obj.y_dir == 'A':
                        plot_data_row = plot_y
                    else:  # 'P'
                        plot_data_row = image3D_obj.num_rows - 1 - plot_y
                    if image3D_obj.z_dir == 'S':
                        plot_data_slice = plot_z
                    else:  # 'I'
                        plot_data_slice = image3D_obj.num_slices - 1 - plot_z
                elif self.view_dir == ViewDir.SAG.dir:
                    # patient anterior is on the left of the screen, and patient inferior is at the bottom
                    if image3D_obj.z_dir == 'S':
                        # image3D slices increase front to back
                        # plot data row increases bottom to top
                        plot_data_row = plot_y
                    else:  # 'I'
                        plot_data_row = image3D_obj.num_slices - 1 - plot_y
                    if image3D_obj.x_dir == 'R':
                        # image3D columns increase right to left
                        # plot slice increases back to front
                        plot_data_slice = plot_z
                        # voxel_slice = image3D_obj.num_cols - 1 - plot_col
                    else:  # 'A'
                        plot_data_slice = image3D_obj.num_cols - 1 - plot_z
                        # voxel_slice = plot_col
                    if image3D_obj.y_dir == 'A':
                        # image3D voxel rows increase bottom to top
                        # x-axis is inverted, so plot_col increases right to left
                        plot_data_col =  plot_x
                    else:  # 'P'
                        plot_data_col = image3D_obj.num_rows - 1 - plot_x
                elif self.view_dir == ViewDir.COR.dir:
                    # patient right is on the left of the screen, and patient inferior is at the bottom
                    if image3D_obj.x_dir == 'R':
                        # image3D columns increase right to left
                        # x-axis is inverted, so plot_col also increases right to left
                        plot_data_col = plot_x
                    else:  # 'L'
                        plot_data_col = image3D_obj.num_cols - 1 - plot_x
                    if image3D_obj.y_dir == 'A':
                        # image3D rows increase bottom to top
                        # plot slice increases front to back
                        plot_data_slice = plot_z
                    else:  # 'P'
                        plot_data_slice = image3D_obj.num_rows - 1 - plot_z
                    if image3D_obj.z_dir == 'S':
                        # image3D slices increase front to back
                        # plot rows increase bottom to top
                        plot_data_row = plot_y
                    else:  # 'I'
                        plot_data_row = image3D_obj.num_slices - 1 - plot_y

                crs = np.array([plot_data_col, plot_data_row, plot_data_slice])

        return crs

    def imagecrs_to_plotdatacrs(self, voxel_col, voxel_row, voxel_slice):
        """
        Taking into account the current display convention (RAS, etc.), find the plot data col,row,slice (crs)
        coordinates from the image3D object data crs coordinates. Note that the plot data may be transposed from the
        image3D to match the orientation of the viewport.

        :param voxel_col:
        :param voxel_row:
        :param voxel_slice:
        :return: crs np.array([plot_col, plot_row, plot_slice])
        """
        # return self.plotdatacrs_to_imagecrs(voxel_col, voxel_row, voxel_slice)  # a trick

        image3D_obj = self.image3D_obj_stack[self.background_image_index]

        crs = None
        if image3D_obj is not None:
            if self.display_convention == 'RAS':
                if self.view_dir == ViewDir.AX.dir:
                    # patient right is on the left of the screen, and patient posterior at the bottom of the screen
                    if image3D_obj.x_dir == 'R':  # voxel columns increase right to left
                        plot_data_col = voxel_col  # x-axis is inverted, so plot_x also increases right to left
                    else:  # 'L'
                        plot_data_col = image3D_obj.num_cols - 1 - voxel_col
                    if image3D_obj.y_dir == 'A':
                        plot_data_row = voxel_row
                    else:  # 'P'
                        plot_data_row = image3D_obj.num_rows - 1 - voxel_row
                    if image3D_obj.z_dir == 'S':
                        plot_data_slice = voxel_slice
                    else:  # 'I'
                        plot_data_slice = image3D_obj.num_slices - 1 - voxel_slice
                elif self.view_dir == ViewDir.SAG.dir:
                    # patient anterior is on the left of the screen, and patient inferior is at the bottom
                    if image3D_obj.z_dir == 'S':
                        # image3D slices increase front to back
                        # plot data row increases bottom to top
                        plot_data_row = voxel_slice
                    else:  # 'I'
                        plot_data_row = image3D_obj.num_slices - 1 - voxel_slice
                    if image3D_obj.x_dir == 'R':
                        # image3D columns increase right to left
                        # plot slice increases back to front *NOTE slicer does front to back here
                        plot_data_slice = voxel_col
                        # voxel_slice = image3D_obj.num_cols - 1 - plot_col
                    else:  # 'A'
                        plot_data_slice = image3D_obj.num_cols - 1 - voxel_col
                        # voxel_slice = plot_col
                    if image3D_obj.y_dir == 'A':
                        # image3D voxel rows increase bottom to top
                        # x-axis is inverted, so plot_col increases right to left
                        plot_data_col = voxel_row
                    else:  # 'P'
                        plot_data_col = image3D_obj.num_rows - 1 - voxel_row
                elif self.view_dir == ViewDir.COR.dir:
                    # patient right is on the left of the screen, and patient inferior is at the bottom
                    if image3D_obj.x_dir == 'R':
                        # image3D columns increase right to left
                        # x-axis is inverted, so plot_col also increases right to left
                        plot_data_col = voxel_col
                    else:  # 'L'
                        plot_data_col = image3D_obj.num_cols - 1 - voxel_col
                    if image3D_obj.y_dir == 'A':
                        # image3D rows increase bottom to top
                        # plot slice increases front to back
                        plot_data_slice = voxel_row
                    else:  # 'P'
                        plot_data_slice = image3D_obj.num_rows - 1 - voxel_row
                    if image3D_obj.z_dir == 'S':
                        # image3D slices increase front to back
                        # plot rows increase bottom to top
                        plot_data_row = voxel_slice
                    else:  # 'I'
                        plot_data_row = image3D_obj.num_slices - 1 - voxel_slice

                crs = np.array([plot_data_col, plot_data_row, plot_data_slice])

        return crs

    def plotdatacrs_to_imagecrs(self, plot_col, plot_row, plot_slice):
        """
        Taking into account the current display convention (RAS, etc.), finds col,row,slice (crs) coordinates of Image3D
        object from the plot data crs coordinates. Note that plot crs are in the coordinate space of the plot data,
        which may be transposed from the original Image3D to match the orientation of the viewport.

        :param plot_col:
        :param plot_row:
        :param plot_slice:
        :return: crs: np.array([voxel_col, voxel_row, voxel_slice])
        """
        image3D_obj = self.image3D_obj_stack[self.background_image_index]

        crs = None
        if image3D_obj is not None:
            if self.display_convention == 'RAS':
                if self.view_dir == ViewDir.AX.dir:
                    # patient right is on the left of the screen, and patient posterior at the bottom of the screen
                    if image3D_obj.x_dir == 'R':  # voxel columns increase right to left
                        voxel_col = plot_col # x-axis is inverted, so plot_x also increases right to left
                    else:  # 'L'
                        voxel_col = image3D_obj.num_cols - 1 - plot_col
                    if image3D_obj.y_dir == 'A':
                        voxel_row = plot_row
                    else:  # 'P'
                        voxel_row = self.num_rows - 1 - plot_row
                    if image3D_obj.z_dir == 'S':
                        voxel_slice = plot_slice
                    else:  # 'I'
                        voxel_slice = image3D_obj.num_slices - 1 - plot_slice
                elif self.view_dir == ViewDir.SAG.dir:
                    # patient anterior is on the left of the screen, and patient inferior is at the bottom
                    if image3D_obj.z_dir == 'S':
                        # image3D slices increase front to back
                        # plot row increases bottom to top
                        voxel_slice = plot_row
                    else:  # 'I'
                        voxel_slice = image3D_obj.num_slices - 1 - plot_row
                    if image3D_obj.x_dir == 'R':
                        # image3D columns increase right to left
                        # plot slice increases back to front *NOTE slicer does front to back here
                        voxel_col = plot_slice
                    else:  # 'A'
                        voxel_col = image3D_obj.num_cols - 1 - plot_slice
                    if image3D_obj.y_dir == 'A':
                        # image3D voxel rows increase bottom to top
                        # x-axis is inverted, so plot_col increases right to left
                        voxel_row = plot_col
                    else:  # 'P'
                        voxel_row = image3D_obj.num_rows - 1 - plot_col
                elif self.view_dir == ViewDir.COR.dir:
                    # patient right is on the left of the screen, and patient inferior is at the bottom
                    if image3D_obj.x_dir == 'R':
                        # image3D columns increase right to left
                        # x-axis is inverted, so plot_col also increases right to left
                        voxel_col = plot_col
                    else:  # 'L'
                        voxel_col = image3D_obj.num_cols - 1 - plot_col
                    if image3D_obj.y_dir == 'A':
                        # image3D rows increase bottom to top
                        # plot slice increases front to back
                        voxel_slice = plot_row
                    else:  # 'P'
                        voxel_slice = image3D_obj.num_rows - 1 - plot_row
                    if image3D_obj.z_dir == 'S':
                        # image3D slices increase front to back
                        # plot rows increase bottom to top
                        voxel_row = plot_slice
                    else:  # 'I'
                        voxel_row = image3D_obj.num_slices - 1 - plot_slice

                crs = np.array([voxel_col, voxel_row, voxel_slice])

        return crs

    def _mouse_press(self, event):
        """
        Capture mouse press event and handle painting point-related actions before passing the event back to pyqtgraph.

        :param event:
        :return:
        """
        # FIXME: during testing and dev
        # print(f"_mouse_press scene: {event.scenePos()}")

        img_item = self.image_view.getImageItem()
        if img_item is None:
            # nothing to do
            return

        if self.paint_im is not None and self.paint_im.matches_event(event):
            self.interaction_state = 'painting'
            self._mouse_move(event)
        elif self.erase_im is not None and self.erase_im.matches_event(event):
            self.interaction_state = 'erasing'
            self._mouse_move(event)
        elif self.point_im is not None and self.point_im.matches_event(event):
            # for example, if the shift key is currently pressed
            if self.add_point_mode:  # adding point
                scene_xy = event.scenePos()
                if img_item.sceneBoundingRect().contains(scene_xy):
                    # transform the scene coordinates to 3D plot coordinates
                    plot_xy = img_item.mapFromScene(scene_xy)
                    plot_x = int(plot_xy.x())
                    plot_y = int(plot_xy.y())
                    # FIXME: during testing and dev
                    print(f"_mouse_press plot coordinates: x: {plot_x}, y: {plot_y}")

                    plot_data_crs = self.plotxyz_to_plotdatacrs(plot_x, plot_y, self.current_slice_index)
                    # FIXME: during testing and dev
                    print(f"_mouse_press plot data coordinates: col: {plot_data_crs[0]}, row: {plot_data_crs[1]}, slice: {plot_data_crs[2]}")

                    image_crs = self.plotdatacrs_to_imagecrs(plot_data_crs[0], plot_data_crs[1], plot_data_crs[2])
                    # FIXME: during testing and dev
                    print(f"_mouse_press image3D coordinates: col: {image_crs[0]}, row: {image_crs[1]}, slice: {image_crs[2]}")

                    # add a point at the clicked screen position
                    new_point = self.add_point(plot_x, plot_y, plot_data_crs[0], plot_data_crs[1], plot_data_crs[2])
                    if new_point is not None:
                        # set this new point as the selected point
                        self.select_point(new_point, False)
                        self.drag_point_mode = True  # user can drag the point to new position before mouse release
                        # update points display
                        self._update_points_display()
                        # emit point created signal
                        self.point_added_signal.emit(new_point, self.id, self.view_dir)
                else:
                    # pass the event back to pyqtgraph for any further processing
                    self.original_mouse_press(event)
            else:
                # pass the event back to pyqtgraph for any further processing
                self.original_mouse_press(event)
        else:
            self.interaction_state = None  # No interaction matches

            # pass the event back to pyqtgraph for any further processing
            self.original_mouse_press(event)

    def _mouse_move(self, event):
        """
        :param event:
        :return:
        Update the coordinates label and crosshairs with the current mouse position, apply paint brush if painting,
        move point if dragging.
        """

        # position of the cursor in the scene (origin in upper left corner of the whole viewport scene)
        scene_xy_qpoint = event.scenePos()

        # FIXME: during testing and dev
        # print(f"Scene coordinates: {scene_xy_qpoint}")

        if self.background_image_index is None or self.image3D_obj_stack[self.background_image_index] is None:
            # nothing to do
            return

        # use the background image to get the coordinates
        # the background image is always the ImageView's image item
        # ideally, this would be the high-res medical image, but user is allowed to load overlays (heatmap,
        #   segementation, masks, etc.) without having a background layer loaded
        img_item = self.image_view.getImageItem()  # should be same image referenced by self.background_image_index
        data_array = self.array3D_stack[self.background_image_index]  # 3D array of data, optnly. transposed
        background_image_obj = self.image3D_obj_stack[self.background_image_index]  # image3D object
        if img_item is None or not img_item.sceneBoundingRect().contains(scene_xy_qpoint):
            #  position is outside the scene bounding rect, just clear the coords label
            self.coordinates_label.setText("")
        else:
            # transform the scene coordinates to 2D image coordinates (origin in lower right corner of the image)
            # NOTE: lower RIGHT instead of lower LEFT because of the inverted x-axis
            plot_mouse_point = img_item.mapFromScene(scene_xy_qpoint)
            plot_x = int(plot_mouse_point.x())
            plot_y = int(plot_mouse_point.y())

            # FIXME: during testing and dev
            print(f"Plot coordinates: x: {plot_x}, y: {plot_y}")

            # get the voxel indices of the cursor in the 3D image data
            # NOTE: PyQtGraph expects the first dimension of the 3D array to represent time or frames in a sequence,
            #  but when used for static 3D volumes, it expects the first dimension to represent slices (essentially
            #  the "depth" dimension for 3D data). So I have reshaped the 3D arrays such that the first dimension is
            #  the z-axis, the second is the x-axis, and the third is the y-axis.

            plot_data_crs = self.plotxyz_to_plotdatacrs(plot_x, plot_y, self.current_slice_index)

            # FIXME: during testing and dev
            print(f"Plot data coordinates: col: {plot_data_crs[0]}, row: {plot_data_crs[1]}, slice: {plot_data_crs[2]}")

            image_crs = self.plotdatacrs_to_imagecrs(plot_data_crs[0], plot_data_crs[1], plot_data_crs[2])

            # FIXME: during testing and dev
            print(f"Image3D coordinates: col: {image_crs[0]}, row: {image_crs[1]}, slice: {image_crs[2]}")

            # get the value of all voxels at this position
            # voxel_values = [data_array[plot_data_crs[0], plot_data_crs[1], plot_data_crs[2]]]
            # TODO
            # data_arrays = [arr for arr in self.array3D_stack if arr is not None]
            # if len(data_arrays) > 1:
            #     for i in range(1, len(data_arrays)):
            #         voxel_values.append(data_arrays[i][plot_x, plot_y, self.current_slice_index])

            # FIXME: during testing and dev
            # if self.is_painting and self.imageItem2D_canvas.image is not None:
            # print(f"canvas: {self.imageItem2D_canvas.image[x, y]}")

            # update the coordinates label
            coordinates_text = "col:{:3d}, row:{:3d}, slice:{:3d}".format(image_crs[0], image_crs[1], image_crs[2])
            # append voxel values for each image
            # for value in voxel_values:
            #     coordinates_text += ", {:4.2f} ".format(value)
            self.coordinates_label.setText(coordinates_text)

            # if painting, erasing, or dragging point
            # print(f"draging point mode: {self.drag_point_mode}, current point: {self.current_point}")
            if self.interaction_state == 'painting':
                self._apply_brush(plot_x, plot_y, True)
            elif self.interaction_state == 'erasing':
                self._apply_brush(plot_x, plot_y, False)
            elif self.drag_point_mode and self.selected_point is not None:  # FIXME: need to check point_im?
                # dragging point
                self.point_moved = True
                # FIXME: during testing and dev
                print(f"new coords plot data: {plot_data_crs[0]}, {plot_data_crs[1]}, {plot_data_crs[2]}")
                print(f"new coords image crs: {image_crs[0]}, {image_crs[1]}, {image_crs[2]}")
                self.selected_point['plot_x'] = plot_x  # voxel index into the 3D array
                self.selected_point['plot_y'] = plot_y  # voxel index into the 3D array
                self.selected_point['plot_data_col']: plot_data_crs[0]# voxel index into the 3D plot data
                self.selected_point['plot_data_row']: plot_data_crs[1]# voxel index into the 3D plot data
                self.selected_point['plot_data_slice']: plot_data_crs[2]# voxel index into the 3D plot data
                self.selected_point['image_col'] = image_crs[0]  # voxel index into the 3D array
                self.selected_point['image_row'] = image_crs[1]
                self.selected_point['image_slice'] = image_crs[2]

                # update the ScatterPlotItem to reflect the new position
                self._update_points_display()
                self.point_moved_signal.emit(self.selected_point, self.id, self.view_dir)
            else:
                # probably panning - pass the event back to pyqtgraph for any further processing
                self.original_mouse_move(event)
            # else:
            #     # position is outside the image bounds, just clear the coords label
            #     self.coordinates_label.setText("")

    def _mouse_release(self, event):
        """
        :param event:
        :return:
        Disable painting, erasing, and dragging point actions and pass the event back to pyqtgraph.
        """
        # FIXME: during testing and dev
        print("_mouse_release")

        self.interaction_state = None
        self.drag_point_mode = False

        # notify parent that point was moved
        # if self.selected_point is not None and self.point_moved:
        #     self.point_moved = False
        #     self.point_moved_signal.emit(self.selected_point, self.id, self.view_dir)

        # pass event back to pyqtgraph for any further processing
        self.original_mouse_release(event)

    def _update_canvas(self):
        """Update the canvas for painting. Masks the painting area using allowed values."""
        if self.image3D_obj_stack[self.canvas_layer_index] is None or self.array3D_stack[
            self.canvas_layer_index] is None:
            # FIXME: raise an error or warning?
            return

        if not self.is_painting:
            # TODO APPLY the mask to the paint image
            self.imageItem2D_canvas.clear()

        # mask the paint image to create a canvas for painting
        paint_image_object = self.image3D_obj_stack[self.canvas_layer_index]
        if hasattr(paint_image_object, 'get_canvas_labels'):
            allowed_values = np.array(paint_image_object.get_canvas_labels())  # , dtype=canvas_slice.dtype.type
            if allowed_values is None:
                return
            # paint_value = self.paint_brush.get_value()  # Value to paint with
            paint_value = self.paint_brush.get_value()  # canvas_slice.dtype.type(

            # get the current slice of the paint image
            if self.canvas_layer_index == self.background_image_index:
                paint_image_slice = self.image_view.getImageItem().image
            else:
                paint_image_slice = self.array2D_stack[self.canvas_layer_index].image

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


    # def _enable_paint_brush(self, which_layer):
    #     """Enable or refresh the paint brush on the specified layer."""
    #     if self.image3D_obj_stack[which_layer] is None or self.array3D_stack[which_layer] is None:
    #         return
    #     if which_layer == self.background_image_index:
    #         canvas_image = self.image_view.imageItem
    #     else:
    #         canvas_image = self.array2D_stack[which_layer]
    #
    #     self.canvas_layer_index = which_layer
    #     self._update_canvas()
    #
    # def _disable_paint_brush(self, which_layer):
    #     if self.image3D_obj_stack[which_layer] is None:
    #         return
    #     if which_layer == self.background_image_index:
    #         self.image_view.imageItem.setDrawKernel(None)
    #     else:
    #         self.array2D_stack[which_layer].setDrawKernel(None)
    #     # TODO: save the painted data to the Image3D object

    def _apply_brush(self, x, y, painting):
        """
        :param x:
        :param y:
        :param painting:
        :return:
        Apply the current paint brush to the canvas image at the specified (x, y) coordinates.
        """
        # this method written by Kazem (thank you!)

        if self.canvas_layer_index is None:
            # FIXME: notify user that no layer is selected for painting?
            return

        data = self.array3D_stack[self.canvas_layer_index]
        data_slice = data[int(self.image_view.currentIndex), :, :]  # arrays have been transposed

        # Define the range for the brush area
        half_brush = self.paint_brush.get_size() // 2
        x_start = max(0, x - half_brush)
        x_end = min(data_slice.shape[0], x + half_brush + 1)
        y_start = max(0, y - half_brush)
        y_end = min(data_slice.shape[1], y + half_brush + 1)

        # Create a mask for the brush area within the bounds of data
        brush_area = data_slice[x_start:x_end, y_start:y_end]

        paint_image_object = self.image3D_obj_stack[self.canvas_layer_index]
        if not hasattr(paint_image_object, 'get_canvas_labels'):
            # FIXME: raise an error or warning?
            return
        allowed_values = np.array(paint_image_object.get_canvas_labels())  # array of label values that can be painted
        mask = np.isin(brush_area, allowed_values)

        # apply active label or 0 to canvas, depending on painting or erasing
        if painting:
            brush_area[mask] = self.paint_brush.get_value()
        else:
            # erasing
            brush_area[mask] = 0

        # update only the modified slice in the 3D array
        # TODO: this is where we can implement an undo stack, saving changes to one slice at a time
        # FIXME: this seems to be directly modifying the image3D object, which is not what we want
        data[int(self.image_view.currentIndex), :, :] = data_slice

        # update the appropriate ImageView ImageItem
        # preserve the current zoom and pan state, prevents image from resetting to full extent
        view_range = self.image_view.view.viewRange()
        if self.canvas_layer_index == self.background_image_index:
            self.image_view.setImage(data)
        else:
            self.array2D_stack[self.canvas_layer_index].setImage(data_slice)
        self.image_view.view.setRange(xRange=view_range[0], yRange=view_range[1],
                                      padding=0)
        # try:
        #     # disconnect the slot before making changes
        #     self.image_view.timeLine.sigPositionChanged.disconnect(self._slice_changed)
        # except TypeError:
        #     # if the slot was not connected, ignore the error
        #     pass
        # self.image_view.setCurrentIndex(self.current_slice_index)  # preserve the current slice
        # # reconnect the slot
        # self.image_view.timeLine.sigPositionChanged.connect(self._slice_changed)

    def add_point(self, plot_x, plot_y, plot_data_col, plot_data_row, plot_data_slice, new_id=None):
        """
        Add a point at the specified plot coordinates. The point is added to the list of points in the current slice.

        :param plot_data_col:
        :param plot_data_row:
        :param plot_data_slice:
        :param new_id: str (optional, unique id for the new point, for same point id in multiple viewports [landmarks])
        :return: new_point
        """
        new_point = None

        # FIXME: use the image specified by point_layer_index, not necessarily the background_image_index?
        # img_item = self.image_view.getImageItem()  # the image item of the ImageView widget
        array3D = self.array3D_stack[self.background_image_index]  # 3D array of data, optionally transposed
        # image3D_obj = self.image3D_obj_stack[self.background_image_index]  # image3D object

        # shape is in the form (slices, cols, rows)
        img_shape = array3D.shape  # shape of the 3D array, transposed from Image3D object

        # FIXME: during testing and dev
        print(f"Plot coordinates: x: {plot_x}, y: {plot_y}")

        # FIXME: during testing and dev
        print(f"Plot data coordinates: col: {plot_data_col}, row: {plot_data_row}, slice: {plot_data_slice}")

        if (0 <= plot_data_col < img_shape[1] and 0 <= plot_data_row < img_shape[2] and
                0 <= plot_data_slice < img_shape[0]):
            image_crs = self.plotdatacrs_to_imagecrs(plot_data_col, plot_data_row, plot_data_slice)

            # FIXME: during testing and dev
            print(f"Image3D coordinates: col: {image_crs[0]}, row: {image_crs[1]}, slice: {image_crs[2]}")

            # if coordinates are within image bounds
            if plot_data_slice not in self.slice_points:
                self.slice_points[plot_data_slice] = []
            if new_id is not None:
                # use the provided id
                point_id = new_id
            else:
                # create a unique id for the new  point
                point_id = shortuuid.ShortUUID().random(length=8)  # short, unique, and human-readable is
                # FIXME: check to see if this id is already in use (is that possible?)
            # add the point with additional metadata
            new_point = {
                'plot_x': plot_x,
                'plot_y': plot_y,
                'plot_data_col': plot_data_col,      # voxel index into the 3D plot data
                'plot_data_row': plot_data_row,      # voxel index into the 3D plot data
                'plot_data_slice': plot_data_slice,  # voxel index into the 3D plot data
                'id': point_id,
                'image_col': image_crs[0],      # voxel index into the image3D object data
                'image_row': image_crs[1],      # voxel index into the image3D object data
                'image_slice': image_crs[2],    # voxel index into the image3D object data
                'is_selected': False  # might not be necessary if only one point can be selected at a time
            }
            self.slice_points[plot_data_slice].append(new_point)

        # # update points display
        # self._update_points_display()
        # else:  # TODO: handle other display conventions
        #     pass

        return new_point

    # def _add_point_at(self, _im_idx: int, x: int, y: int, z: int):
    #     """
    #     :param _im_idx: uint (index of the image in the stack)
    #     :param x: uint (column index)
    #     :param y: uint (row index)
    #     :param z: uint (slice index)
    #     :return: new point item
    #     Add a custom scatterplot item (point) at the specified (x, y) coordinates. z (slice index) is optional.
    #     Add point to list of points in this viewport, and connect a point press event to the point.
    #     """
    #
    #     # validate that x, y, and z are non-negative
    #     if x < 0 or y < 0 or (z is not None and z < 0):
    #         raise ValueError("x, y, and z (if provided) must be non-negative integers.")
    #
    #     # # create a scatter plot item as a point
    #     # custom_point = CustomScatterPlotItem(im_idx=_im_idx, sl_idx=z, col_idx=x, row_idx=y)
    #
    #     # add point to the current slice
    #     if z not in self.slice_points:
    #         self.slice_points[z] = []
    #     self.slice_points[z].append((x, y))
    #
    #     # update points display
    #     self._update_points_display()
    #
    #     # # Temporarily disconnect the signal before adding points
    #     # try:
    #     #     custom_point.sigPressed.disconnect(self._point_pressed)
    #     # except TypeError:
    #     #     pass  # Signal was not connected
    #     #
    #     # # customize size and color. CAUTION: this will trigger the mouse_pressed event of custom_point
    #     # custom_point.addPoints([{'pos': (x, y), 'brush': self.temp_brush, 'size': 10}])
    #     #
    #     # # add point to the view
    #     # self.image_view.addItem(custom_point)
    #     #
    #     # # store point for future reference (e.g., clearing points)
    #     # self.points.append(custom_point)
    #     #
    #     # # connect the point press event to the point
    #     # custom_point.sigPressed.connect(self._point_pressed)
    #
    #     # FIXME: during testing and dev
    #     print(f"Point added at: x={x}, y={y}, z={z}")
    #
    #     # return custom_point

    def _update_points_display(self):
        """
        Update the display of points on the image view. Only display points for the current slice.

        :return:
        """
        # get points for the current slice
        current_slice = int(self.image_view.currentIndex)
        points = self.slice_points.get(current_slice, [])

        # print(points)

        # update ScatterPlotItem
        if len(points) > 0:
            spots = [
                {
                    'pos': (point['plot_x'], point['plot_y']), 'data': point,
                    'brush': self.selected_brush if point['is_selected'] else self.idle_brush,
                }
                for point in points
            ]
            # FIXME: testing and debugging
            # print(f"spots: {spots}")
            self.scatter.setData(spots=spots)
        else:
            self.scatter.clear()

    def select_point(self, point, notify):
        """
        Set specified point as selected. Deselect any other point that was previously selected. Update the
        display of points. Optionally notify the parent class.

        :param point: dict (point data)
        :param notify: bool (whether to notify the parent class)
        :return:
        """
        if point is not None:
            if self.selected_point is not None:
                # deselect previously selected point
                self.selected_point['is_selected'] = False
            point['is_selected'] = True
            self.selected_point = point
            self.current_slice_index = point['plot_data_slice']
            self.refresh_preserve_extent()
            if notify:
                self.point_selected_signal.emit(point, self.id, self.view_dir)


    def _scatter_mouse_press(self, event, point):
        """
        When user clicks on a point. If the point is not already selected, select it. If the point
        is already selected, allow it to be dragged to a new position.

        :param event:
        :return:
        """
        if self.point_im is not None and self.point_im.matches_event(event):
            # only respond to the event if the interaction method matches (for example, shift + left click)
            if point is not None:
                is_selected = point.get('is_selected')
                if not is_selected:
                    self.select_point(point, True)
                else:
                    # this point was already selected, allow it to be dragged to a new position
                    self.drag_point_mode = True

                # FIXME: during testing and dev
                print(f"_scatter_mouse_press: {point}")

        # if point is not already selected, select it and set dragging mode to true

        # if point is already selected, just set dragging mode to true

    # def _scatter_mouse_release(self, event):
    #     """
    #     When user releases mouse button on a point.
    #     :param event:
    #     :return:
    #     """
    #     # FIXME: during testing and dev
    #     print("_scatter_mouse_release")
    #
    #     self.drag_point_mode = False


    # def _point_clicked(self, scatter, clicked_points):
    #     """
    #     Handle point click by toggling its selected flag. Notify the parent class about the clicked point.
    #
    #     :param scatter: The ScatterPlotItem object. (not used)
    #     :param clicked_points: The list of clicked points (contains instances of Point).
    #     """
    #     # FIXME: during testing and dev
    #     print("_point_clicked")
    #
    #     if not clicked_points:
    #         return
    #
    #     # assume only one point can be clicked (get the first point in the list)  # FIXME: iterate through list
    #     clicked_point = clicked_points[0]
    #     clicked_pos = clicked_point.pos()  # Get the (x, y) position of the point
    #     current_slice = int(self.image_view.currentIndex)
    #
    #     # find the clicked point by position in the slice_points data structure
    #     for point in self.slice_points.get(current_slice, []):
    #         if point['voxel_col'] == clicked_pos[0] and point['voxel_row'] == clicked_pos[1]:
    #             point['is_selected'] = not point['is_selected']  # toggle selection
    #             self.current_point = point
    #         else:
    #             point['is_selected'] = False
    #
    #     if self.current_point is not None:
    #         # update the display of points
    #         self._update_points_display()
    #         # notify the parent class about the selected point
    #         self.point_selected_signal.emit(point['id'], point['is_selected'], self.id, self.view_dir)

    # def get_point_by_id_and_slice(self, point_id, slice_index):
    #     """
    #     Get the point with the specified ID from the specified slice.
    #
    #     :param point_id: str (unique ID of the point)
    #     :param slice_index: int (slice index)
    #     :return: dict (point data)
    #     """
    #     if slice_index in self.slice_points:
    #         return self.slice_points[slice_index].get(point_id, None)
    #     return None


    # def _point_pressed(self, clicked_point, stacked_points, event):
    #     """
    #     :param clicked_point:
    #     :param stacked_points:
    #     :param event:
    #     :return:
    #     Handle point pressed event.
    #     """
    #
    #     if self.point_im is not None and self.point_im.matches_event(event):
    #         # only respond to the event if the interaction method matches (for example, shift + left click)
    #         # FIXME: during testing and dev
    #         print("point pressed")
    #
    #         if self.add_point_mode:
    #             return
    #
    #         if self.pending_point_mode:
    #             # if the point is in pending mode, then the point is being dragged to a new position
    #             self.drag_point_mode = True
    #         else:
    #             # FIXME: need to handle case where multiple points are stacked on top of each other
    #             # if len(stacked_points) > 0:
    #             #     # assuming only one point is clicked at a time, grab the first point
    #             #     clicked_point = stacked_points[0]
    #             #     slice_index = clicked_point.z
    #             self.set_selected(clicked_point)
    #
    #
    #         # FIXME: during testing and dev
    #         print(f"point clicked at position: {clicked_point.x}, {clicked_point.y}, Slice index: {clicked_point.z}")
    #
    #         self.drag_point_mode = True
    #
    #         # emit signal to notify the parent class that a point was clicked
    #         # TODO


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
