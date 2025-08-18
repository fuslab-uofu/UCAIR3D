import numpy as np
import pyqtgraph as pg
import re
import shortuuid

from PyQt5.QtWidgets import QVBoxLayout, QWidget, QHBoxLayout, QLabel, QFrame
from PyQt5.QtGui import QFont, QPainter, QImage, QFontMetrics, QGuiApplication, QPixmap, QColor, QCursor
from PyQt5.QtCore import pyqtSignal, QObject, QEvent, Qt
from PyQt5.QtSvg import QSvgGenerator

from ..enumerations import ViewDir
from .paint_brush import PaintBrush

import cProfile, pstats, io
from functools import wraps


def make_green_cross_cursor(size=15, line_width=2, color=(0, 255, 0)):
    """
    Create a small green cross cursor.
    :param size: total size in pixels
    :param line_width: thickness of the cross lines
    :param color: (R,G,B) tuple
    :return: QCursor
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.setPen(QColor(*color))
    painter.setBrush(QColor(*color))

    mid = size // 2
    # vertical bar
    painter.fillRect(mid - line_width // 2, 0, line_width, size, QColor(*color))
    # horizontal bar
    painter.fillRect(0, mid - line_width // 2, size, line_width, QColor(*color))

    painter.end()

    # hotspot at the center of the cross
    return QCursor(pm, mid, mid)


class WheelEventFilter(QObject):
    def __init__(self, imageView):
        super().__init__()
        self.iv = imageView

    def eventFilter(self, obj, event):
        print(event.type(), QEvent.Wheel)
        if event.type() == QEvent.Wheel:
            # Get the current value of the time slider
            current_value = self.iv.timeLine.value()
            # Determine the direction of the scroll
            delta = event.angleDelta().y()
            # Update the slider value based on the scroll direction
            if delta > 0:
                new_value = current_value + 1
            else:
                new_value = current_value - 1
            # Ensure the new value is within the slider's range
            new_value = max(0, min(new_value, self.iv.timeLine.maximum()))
            # Set the new value to the time slider
            self.iv.timeLine.setValue(new_value)
            return True
        return False







class GlobalCtrlCursorManager(QObject):
    """
    Tracks Ctrl globally and applies a cursor to any registered widgets
    while the mouse is over them. Works even when the widget doesn't have focus.
    """
    def __init__(self):
        super().__init__()
        self._ctrl_down = False
        self._targets = []   # widgets we care about
        # self._cursor = Qt.CrossCursor
        self._cursor = make_green_cross_cursor(size=15, line_width=2)

        app = QGuiApplication.instance()
        if app is not None:
            app.installEventFilter(self)  # receive global KeyPress/KeyRelease

    def set_cursor_shape(self, shape: Qt.CursorShape):
        self._cursor = shape
        self._apply_to_all()  # refresh immediately

    def add_target(self, w):
        if w is None:
            return
        # Make sure we get hover events even without focus
        w.setMouseTracking(True)
        try:
            w.viewport().setMouseTracking(True)  # for QGraphicsView/QAbstractScrollArea (no-op if missing)
        except Exception:
            pass
        w.installEventFilter(self)
        self._targets.append(w)

    # --- internals ---
    def _apply(self, w):
        if self._ctrl_down and w.underMouse():
            w.setCursor(self._cursor)
        else:
            w.unsetCursor()

    def _apply_to_all(self):
        for w in self._targets:
            self._apply(w)

    def eventFilter(self, obj, event):
        et = event.type()

        # 1) Global keyboard tracking (from the app)
        if et == QEvent.KeyPress and event.key() == Qt.Key_Control:
            if not self._ctrl_down:
                self._ctrl_down = True
                self._apply_to_all()
            return False
        if et == QEvent.KeyRelease and event.key() == Qt.Key_Control:
            if self._ctrl_down:
                self._ctrl_down = False
                self._apply_to_all()
            return False

        # 2) Pointer/focus/window changes on targets
        if obj in self._targets:
            if et in (QEvent.Enter, QEvent.Leave, QEvent.HoverMove,
                      QEvent.FocusIn, QEvent.FocusOut,
                      QEvent.WindowDeactivate, QEvent.WindowActivate):
                self._apply(obj)
                return False

            # If this is a QGraphicsView-like, also catch events on its viewport
            try:
                vp = obj.viewport()
            except Exception:
                vp = None
            if vp is not None and obj is vp:  # event came from the viewport
                if et in (QEvent.Enter, QEvent.Leave, QEvent.HoverMove):
                    self._apply(obj)
                    return False

        return False










class CustomImageView(pg.ImageView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.wheelEventFilter = WheelEventFilter(self)
        self.installEventFilter(self.wheelEventFilter)


class CustomScatterPlotItem(pg.ScatterPlotItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mouse_press_callback = None
        self.mouse_release_callback = None
        # self.current_point = None  # Track the currently selected marker

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

            # # DEBUG:
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
    (modify the voxel values) and add markers to the image. Tools are provided for modifying the colormap and opacity
    of the images. The calling class must provide the view desired view direction (axial, coronal, sagittal).
    The calling class must also provide the maximum number of image allowed in the stack.
    A viewport is a subclass of QWidget and can be added to a layout in a QMainWindow.
    """
    # signals to notify parent class of changes in the viewport
    marker_added_signal = pyqtSignal(object, object)
    marker_selected_signal = pyqtSignal(object, object, object)
    markers_cleared_signal = pyqtSignal(object)
    marker_moved_signal = pyqtSignal(object, object, object)
    slice_changed_signal = pyqtSignal(object, object)

    def __init__(self,
                 parent,
                 vp_id,
                 view_dir,
                 num_vols,
                 paint_method=None,
                 erase_method=None,
                 mark_method=None,
                 zoom_method=None,
                 pan_method=None,
                 window_method=None):
        super().__init__()

        self.parent = parent
        self.id = vp_id
        self.view_dir = view_dir.dir  # ViewDir.AX (axial), ViewDir.COR (coronal), ViewDir.SAG (sagittal)
        self.num_vols_allowed = num_vols  # number of images (layers) to display

        # parent can provide custom methods for interacting with the viewport (e.g., painting, erasing, marking,
        #   zooming, panning, and windowing)
        self.paint_im = paint_method  # method for painting
        self.erase_im = erase_method  # method for erasing
        self.mark_im = mark_method  # method for making points
        self.zoom_im = zoom_method  # TODO: future implementation, custom zoom method
        self.pan_im = pan_method  # TODO: future implementation, custom pan method
        self.window_im = window_method  # TODO: future implementation, custom method for windowing
        self.interaction_state = None  # implemented values: 'painting', 'erasing'

        # interactive point placement
        self.add_marker_mode = False  # if adding points, are we placing a new point?
        # self.pending_point_mode = False  # if adding points, are we waiting for the user to complete the point?
        self.drag_marker_mode = False  # are we dragging a point to a new location?
        self.edit_marker_mode = False  # are we editing the location of a point?
        self.marker_moved = False
        self.selected_marker = None
        # default colors for points TODO: let parent class update these
        self.idle_marker_color = (255, 0, 0, 255)  # red
        self.selected_marker_color = (0, 255, 0, 255)  # green
        self.temp_marker_color = (255, 255, 0, 255) # yellow
        self.idle_pen = pg.mkPen(self.idle_marker_color, width=1)  # red pen for not idle points
        self.idle_brush = pg.mkBrush(self.idle_marker_color)
        self.selected_pen = pg.mkPen(self.selected_marker_color, width=2)  # green pen for selected point
        self.selected_brush = pg.mkBrush(self.selected_marker_color)
        self.temp_pen = pg.mkPen(self.temp_marker_color, width=1)  # yellow pen for temporary point
        self.temp_brush = pg.mkBrush(self.temp_marker_color)
        # dictionary to store points for each slice
        self.slice_markers = {}

        # convenience reference to the background image item
        self.background_image_index = None
        # keep track of the active layer for histogram, colormap, and opacity settings interaction
        self.active_image_index = 0     # default to the first layer (background)
        self.canvas_layer_index = None  # the layer index of the image that is currently being painted on
        self.canvas_labels = []         # the labels that are affected by painting
        self.marker_layer_index = None   # the layer that points are currently being added to
        self.current_slice_index = 0

        # interactive painting
        self.is_painting = False
        self.paint_brush = PaintBrush(size=5)

        self.display_convention = "RAS"  # default to RAS (radiological convention) # TODO, make this an input opt.

        # initialize widgets and their slots -------------------------------------
        # the main layout for this widget ----------
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(1)

        # interactive coordinates display --------------------
        coords_frame = QFrame()
        coords_frame.setObjectName("coords_frame")
        coords_frame.setLayout(QHBoxLayout())
        coords_frame.layout().setContentsMargins(0, 0, 0, 0)
        coords_frame.setStyleSheet("background-color: #000000;")
        coords_frame.setStyleSheet(f"QFrame#coords_frame {{border: none;}}")
        self.coordinates_label = QLabel("", self)
        font = QFont("Courier New", 7)  # use a monospaced font for better alignment
        self.coordinates_label.setFont(font)
        # one‑decimal world format; this string defines the numeric field width
        world_sample = "-000.0"  # ← change this once if you ever need wider fields
        self._world_prec = 1
        self._world_field_width = len(world_sample)
        self._vox_field_width = 3
        # choose letters for the sample (RAS or xyz doesn’t change total width)
        axis_labels = ("R", "A", "S") if self.display_convention.upper() == "RAS" else ("x", "y", "z")
        sample = f"col:000 row:000 slice:000  |  {axis_labels[0]}:{world_sample} {axis_labels[1]}:{world_sample} {axis_labels[2]}:{world_sample}"
        metrics = QFontMetrics(self.coordinates_label.font())
        width = getattr(metrics, "horizontalAdvance", metrics.width)(sample)
        self.coordinates_label.setFixedWidth(width)
        # initialize with blanks
        self._set_coords_label(None, None, 0, None)
        coords_frame.layout().addWidget(self.coordinates_label)

        # add the top layout to the main layout (above the imageView)
        main_layout.addWidget(coords_frame)

        # layout for the image view and opacity slider ----------
        image_view_layout = QHBoxLayout()
        # the image view widget ----------
        self.image_view = pg.ImageView()
        self.image_view.setStyleSheet("border: none;")







        # Ensure the ImageView can receive key events
        self.image_view.setFocusPolicy(Qt.StrongFocus)

        # Create or reuse a singleton manager (store on parent/app as convenient)
        self._ctrl_mgr = getattr(QGuiApplication.instance(), "_global_ctrl_mgr", None)
        if self._ctrl_mgr is None:
            self._ctrl_mgr = GlobalCtrlCursorManager()
            setattr(QGuiApplication.instance(), "_global_ctrl_mgr", self._ctrl_mgr)

        # Register targets that the mouse can be "over"
        self._ctrl_mgr.add_target(self.image_view)

        # Register the underlying GraphicsView and its viewport so hover works even if focus doesn't
        try:
            gv_list = self.image_view.getView().scene().views()
            if gv_list:
                gv = gv_list[0]
                gv.setFocusPolicy(Qt.StrongFocus)
                self._ctrl_mgr.add_target(gv)
                self._ctrl_mgr.add_target(gv.viewport())
        except Exception:
            pass







        # access the PlotItem under the time slider
        plot_item = self.image_view.ui.roiPlot  # This is the plot below the image for z/time slider
        # access the bottom axis
        axis = plot_item.getAxis('bottom')
        # change font size
        font = QFont()
        font.setPointSize(8)  # Set to desired font size
        axis.setTickFont(font)

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
        self.cor_line_color = '#447CF9'
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
        # ensure that these lines are always on top
        self.horizontal_line.setZValue(10)
        self.vertical_line.setZValue(10)

        """ NOTE: the pyqtgraph ImageView object displays only one 3D image at a time. To have overlays, 2D slices 
        are added to the ImageView. For our Viewport object, the main/background image is the 3D array of the data
        member of an Image3D object. Overlay/foreground image is a 2D array (slice) of the 3D array.
        self.image3D_obj_stack stores references to the Image3D objects that this viewport is currently displaying. 
        self.array3D_stack stores the actual 3D array that gets displayed. These arrays may be transposed to match 
        the orientation (ViewDir) of this Viewport.
        self.array2D_stack stores the slices (ImageItems) of the overlay image that will be displayed in the 
        image view. 
        
        NIfTI image 3D array --> as closest canonical --> Image3D object data
        Image3D object data --> reorient to axial, coronal, sagittal --> array3D -->"""
        self.image3D_obj_stack = [None] * self.num_vols_allowed  # Image3D objects
        self.array3D_stack = [None] * self.num_vols_allowed  # image data 3D arrays
        # image data 2D arrays (slices) - one less than total number of images allowed because these are overlays
        # and 3D background image is always displayed first in the image_view
        self.array2D_stack = [pg.ImageItem() for _ in range(self.num_vols_allowed)]
        for i in range(0, self.num_vols_allowed):
            self.image_view.view.addItem(self.array2D_stack[i])
        # add a canvas mask for painting
        self.imageItem2D_canvas = pg.ImageItem()
        self.image_view.view.addItem(self.imageItem2D_canvas)

        # this is the plot item for creating points. Customized to capture mouse press and mouse release events
        self.scatter = CustomScatterPlotItem()
        self.scatter.set_mouse_press_callback(self._scatter_mouse_press)
        self.image_view.getView().addItem(self.scatter)

        # connect the mouse move event to the graphics scene
        self.image_view.getView().scene().mouseMoveEvent = self._mouse_move

        # connect the mouse click event to the graphics scene
        # optionally, profile this slot by wrapping it in the profiler
        if self.parent.debug_mode:
            self.image_view.getView().scene().mousePressEvent = self._mouse_press_wrapper
        else:
            self.image_view.getView().scene().mousePressEvent = self._mouse_press

        # connect the mouse release event to the graphics scene
        self.image_view.getView().scene().mouseReleaseEvent = self._mouse_release

        # when the timeLine position changes, update the overlays
        self.image_view.timeLine.sigPositionChanged.connect(self._slice_changed)

        self.graphics_scene = self.image_view.getView().scene()
        self.graphics_scene.wheelEvent = self._wheel_event

        # cache last mouse status/position (for coodinates display)
        self._last_mouse_inside = False
        self._last_plot_x = None
        self._last_plot_y = None
        self._last_valid_im3d_crs = None  # tuple[int,int,int] = (col,row,slc)
        self._last_valid_world = None  # tuple[float,float,float]

    #  -----------------------------------------------------------------------------------------------------------------
    #  "Public" methods API --------------------------------------------------------------------------------------------
    #  -----------------------------------------------------------------------------------------------------------------

    def add_layer(self, im3Dobj, stack_position):
        """
        Update the stack of 3D images with a new 3D image for this viewPort.
        Image = None is allowed and will clear the layer at the specified position.
        :param im3Dobj:
        :param stack_position:
        :return:
        """

        if stack_position > self.num_vols_allowed:
            # TODO: raise an error or warning - the stack position is out of bounds
            return

        self.image3D_obj_stack[stack_position] = im3Dobj  # not a deep copy, reference to the image3D object
        self.active_image_index = stack_position
        # PyQtGraph expects the first dimension of the array to represent time or frames in a sequence, but when used
        # for static 3D volumes, it expects the first dimension to represent slices (essentially the "depth" dimension
        # for 3D data).
        if im3Dobj is not None:
            # populate the array3D stack with the data from this image3D object
            if self.view_dir == ViewDir.AX.dir:
                # axial view: transpose im3Dobj data (x, y, z) to (z, x, y) for pyqtgraph
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data,
                                                                  (2, 0, 1))
                # DEBUG:
                # print(f"3D array shape: {self.array3D_stack[stack_position].shape}")

                ratio = im3Dobj.dy / im3Dobj.dx
            elif self.view_dir == ViewDir.COR.dir:
                # transpose im3Dobj data (x, y, z) to (x, z, y) for coronal view, then to (y, x, z) for pyqtgraph
                # then save the transposed array  # FIXME: should z be flipped? like x, -z, y?
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data,
                                                                  (1, 0, 2))
                # DEBUG:
                # print(f"3D array shape: {self.array3D_stack[stack_position].shape}")

                ratio = im3Dobj.dz / im3Dobj.dx
            else:  # "SAG"
                # transpose im3Dobj data (x, y, z) to (y, z, x) for sagittal view, then (x, y, z) for pyqtgraph
                # then save the transposed array
                self.array3D_stack[stack_position] = np.transpose(self.image3D_obj_stack[stack_position].data,
                                                                  (0, 1, 2))
                # DEBUG:
                # print(f"3D array shape: {self.array3D_stack[stack_position].shape}")

                # ratio = float(im3Dobj.dz / im3Dobj.dy)

            # set the aspect ratio of the image view to match this new image
            # FIXME: is there a better way to do this? Should this be done in refresh()?
            # self.image_view.getView().setAspectLocked(True, ratio=ratio)
            # start at middle slice
            self.current_slice_index = (int(self.array3D_stack[stack_position].shape[0] // 2))

            # emit signal to notify parent class that the slice has changed (to update the slice guides in other vps)
            self.slice_changed_signal.emit(self.id, self.current_slice_index)
        else:
            self.array3D_stack[stack_position] = None
            self.array2D_stack[stack_position].setImage(np.zeros((1, 1)))  # clear the image

            # FIXME: correct?
            self.background_image_index = 0

        # don't use refresh_preserve_extent() here - extent is currently set to some unknown default value
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
        if img_item is not None and self.background_image_index is not None:
            array3D = self.array3D_stack[self.background_image_index]  # 3D array of data, optionally transposed
            if array3D is not None:
                img_shape = array3D.shape
                if 0 <= slice_index < img_shape[0]:
                    self.current_slice_index = slice_index
                    self.refresh_preserve_extent()
                    # self.refresh()

    # def remove_layer(self, stack_position):
    #     # FIXME: this wipes out the image3D object! That is not what we want to do
    #     self.image3D_obj_stack[stack_position] = None
    #
    #     self.array3D_stack[stack_position] = None
    #     # self.array2D_stack[stack_position].clear()
    #     self.array2D_stack[stack_position] = None
    #     if stack_position in self.canvas_layer_index:
    #         self.clear_canvas_layer(stack_position)
    #     self.refresh()

    def hide_layer(self, stack_position):
        if self.image3D_obj_stack[stack_position] is None:
            return
        if self.background_image_index is not None and stack_position == self.background_image_index:
            self.image_view.getImageItem().setVisible(False)
        else:
            self.array2D_stack[stack_position].setVisible(False)
        self.scatter.setVisible(False)

    def show_layer(self, stack_position):
        if self.image3D_obj_stack[stack_position] is None:
            return
        if self.background_image_index is not None and stack_position == self.background_image_index:
            self.image_view.getImageItem().setVisible(True)
        else:
            self.array2D_stack[stack_position].setVisible(True)
        self.scatter.setVisible(True)

    def move_layer_up(self):
        # TODO
        pass

    def move_layer_down(self):
        # TODO
        pass

    def get_current_slice_index(self):
        return self.image_view.currentIndex

    def plotdatacr_to_plotxy(self, plot_data_col, plot_data_row):
        """
        Convert plot data coordinates to plot x and y coordinates. This method is used to convert the plot data
        coordinates to the plot x and y coordinates that are used by the scatter plot item.

        :param plot_data_col: int
        :param plot_data_row: int
        :return: plot_x, plot_y [int, int]
        """
        xy = None

        if self.background_image_index is None:
            return xy

        image3D_obj = self.image3D_obj_stack[self.background_image_index]

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

        crs = None

        if self.background_image_index is None:
            return crs

        # the Image3D object that the plot data originates from. Only needed here for info about axes directions
        image3D_obj = self.image3D_obj_stack[self.background_image_index]

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
        :return: crs np.array([plot_data_col, plot_data_row, plot_data_slice]) or None
        """

        crs = None

        if self.background_image_index is None:
            return crs

        image3D_obj = self.image3D_obj_stack[self.background_image_index]

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

    def plotdatacrs_to_imagecrs(self, plot_data_col, plot_data_row, plot_data_slice):
        """
        Taking into account the current display convention (RAS, etc.), finds col,row,slice (crs) coordinates of Image3D
        object from the plot data crs coordinates. Note that plot crs are in the coordinate space of the plot data,
        which may be transposed from the original Image3D to match the orientation of the viewport.

        :param plot_data_col:
        :param plot_data_row:
        :param plot_data_slice:
        :return: crs: np.array([voxel_col, voxel_row, voxel_slice])
        """

        crs = None

        if self.background_image_index is None:
            return crs

        image3D_obj = self.image3D_obj_stack[self.background_image_index]

        if image3D_obj is not None:
            if self.display_convention == 'RAS':
                if self.view_dir == ViewDir.AX.dir:
                    # patient right is on the left of the screen, and patient posterior at the bottom of the screen
                    if image3D_obj.x_dir == 'R':  # voxel columns increase right to left
                        voxel_col = plot_data_col # x-axis is inverted, so plot_x also increases right to left
                    else:  # 'L'
                        voxel_col = image3D_obj.num_cols - 1 - plot_data_col
                    if image3D_obj.y_dir == 'A':
                        voxel_row = plot_data_row
                    else:  # 'P'
                        voxel_row = image3D_obj.num_rows - 1 - plot_data_row
                    if image3D_obj.z_dir == 'S':
                        voxel_slice = plot_data_slice
                    else:  # 'I'
                        voxel_slice = image3D_obj.num_slices - 1 - plot_data_slice
                elif self.view_dir == ViewDir.SAG.dir:
                    # patient anterior is on the left of the screen, and patient inferior is at the bottom
                    if image3D_obj.z_dir == 'S':
                        # image3D slices increase front to back
                        # plot row increases bottom to top
                        voxel_slice = plot_data_row
                    else:  # 'I'
                        voxel_slice = image3D_obj.num_slices - 1 - plot_data_row
                    if image3D_obj.x_dir == 'R':
                        # image3D columns increase right to left
                        # plot slice increases back to front *NOTE slicer does front to back here
                        voxel_col = plot_data_slice
                    else:  # 'A'
                        voxel_col = image3D_obj.num_cols - 1 - plot_data_slice
                    if image3D_obj.y_dir == 'A':
                        # image3D voxel rows increase bottom to top
                        # x-axis is inverted, so plot_data_col increases right to left
                        voxel_row = plot_data_col
                    else:  # 'P'
                        voxel_row = image3D_obj.num_rows - 1 - plot_data_col
                elif self.view_dir == ViewDir.COR.dir:
                    # patient right is on the left of the screen, and patient inferior is at the bottom
                    if image3D_obj.x_dir == 'R':
                        # image3D columns increase right to left
                        # x-axis is inverted, so plot_data_col also increases right to left
                        voxel_col = plot_data_col
                    else:  # 'L'
                        voxel_col = image3D_obj.num_cols - 1 - plot_data_col
                    if image3D_obj.y_dir == 'A':
                        # image3D rows increase bottom to top
                        # plot slice increases front to back
                        voxel_slice = plot_data_row
                    else:  # 'P'
                        voxel_slice = image3D_obj.num_rows - 1 - plot_data_row
                    if image3D_obj.z_dir == 'S':
                        # image3D slices increase front to back
                        # plot rows increase bottom to top
                        voxel_row = plot_data_slice
                    else:  # 'I'
                        voxel_row = image3D_obj.num_slices - 1 - plot_data_slice

                crs = np.array([voxel_col, voxel_row, voxel_slice])

        return crs

    def update_crosshairs(self):
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

    def export_svg(self, filename='output.svg'):
        """Saves a PyQtGraph ImageView (base + overlay) as an SVG file."""

        # Step 1: Render the ImageView to a QImage
        size = self.image_view.size()
        img = QImage(size.width(), size.height(), QImage.Format_ARGB32)
        painter = QPainter(img)
        self.image_view.render(painter)  # Capture ImageView with overlays
        painter.end()

        # Step 2: Convert the QImage to an SVG
        svg_generator = QSvgGenerator()
        svg_generator.setFileName(filename)
        svg_generator.setSize(size)
        svg_generator.setViewBox(0, 0, size.width(), size.height())

        # Step 3: Draw the QImage onto the SVG
        painter = QPainter(svg_generator)
        painter.drawImage(0, 0, img)
        painter.end()
        print(f"Saved: {filename}")

    # markers ----------------------------------------------------------------------------------------------------------
    def marker_add(self, image_col, image_row, image_slice, image_index, new_id=None):
        """
        Add a marker at the specified image3D voxel coordinates. The marker is added to the list of markers for the
        current slice, but is not plotted until _update_markers_display() is called.

        :param image_col: int
        :param image_row: int
        :param image_slice: int
        :param image_index: int (index of the image in the stack)
        :param new_id: str (optional, unique id for the new marker, for same marker id in multiple viewports [landmarks])
        :return: new_marker: dict (marker data)
        """

        # if self.parent.debug_mode:  # print debug messages
        #     print(f"marker_add() image_col: {image_col}, image_row: {image_row}, image_slice: {image_slice}, "
        #           f"image_index: {image_index}")


        new_marker = None

        # FIXME: use the image specified by marker_layer_index, not necessarily the background_image_index?
        # img_item = self.image_view.getImageItem()  # the image item of the ImageView widget
        array3D = self.array3D_stack[image_index]  # 3D array of data, optionally transposed
        # image3D_obj = self.image3D_obj_stack[self.background_image_index]  # image3D object

        # shape is in the form (slices, cols, rows)
        plot_data_shape = array3D.shape  # shape of the 3D array, transposed from Image3D object
        # coordinates of marker in the 3D array used for plotting. This 3D array is transposed from the image3D object
        # data in the sagittal and coronal cases.
        plot_data_crs = self.imagecrs_to_plotdatacrs(image_col, image_row, image_slice)
        if plot_data_crs is None:
            return None
        if (0 <= plot_data_crs[0] < plot_data_shape[1] and 0 <= plot_data_crs[1] < plot_data_shape[2] and
            0 <= plot_data_crs[2] < plot_data_shape[0]):

            # DEBUG:
            # print(f"Image3D coordinates: col: {image_crs[0]}, row: {image_crs[1]}, slice: {image_crs[2]}")

            # do we have any markers on this slice yet?
            if plot_data_crs[2] not in self.slice_markers:  # slice_markers organized by slice index of the 3D plot data
                self.slice_markers[plot_data_crs[2]] = []
            if new_id is not None:
                # use the provided id
                marker_id = new_id
            else:
                # create a unique id for the new  marker
                marker_id = shortuuid.ShortUUID().random(length=8)  # short, unique, and (marginally) human-readable
                # FIXME: check to see if this id is already in use (is that possible?)
            # add the marker with additional metadata
            new_marker = {
                'id': marker_id,
                'image_col': image_col,      # voxel index in the Image3D object data
                'image_row': image_row,      # voxel index in the Image3D object data
                'image_slice': image_slice,  # voxel index in the Image3D object data
                'is_selected': False  # FIXME: might not be necessary if only one marker can be selected at a time?
            }
            self.slice_markers[plot_data_crs[2]].append(new_marker)

        return new_marker

    def marker_select(self, mkr, notify):
        """
        Set specified point as selected. Deselect any other point that was previously selected. Update the
        display of points. Optionally notify the parent class.

        :param mkr: dict (marker data)
        :param notify: bool (whether to notify the parent class)
        :return:
        """
        # if self.parent.debug_mode:  # print debug messages
        #     print(f"marker_select() with marker {mkr} and notify {notify} for viewport {self.id}")

        if mkr is not None:
            if self.selected_marker is not None:
                # deselect previously selected point
                self.selected_marker['is_selected'] = False
            mkr['is_selected'] = True
            self.selected_marker = mkr
            plot_data_crs = self.imagecrs_to_plotdatacrs(mkr['image_col'], mkr['image_row'], mkr['image_slice'])
            if plot_data_crs is None:
                return  # FIXME: how to handle?

            self.current_slice_index = plot_data_crs[2]
            self.goto_slice(plot_data_crs[2])  # calls refresh_preserve_extent()
            # self.refresh_preserve_extent()
            if notify:
                self.marker_selected_signal.emit(mkr, self.id, self.view_dir)

    def marker_find_by_id(self, point_id):
        """
        Find the point with the specified ID across all slices.

        :param point_id: str (unique ID of the point)
        :return: tuple (slice_index, point_data) if found, otherwise None
        """

        # if self.parent.debug_mode:  # print debug messages
        #     print(f"marker_find_by_id() with id {point_id} for viewport {self.id}")

        for slice_idx, points in self.slice_markers.items():
            for pt in points:
                if pt['id'] == point_id:
                    return pt
        return None

    def marker_delete(self, marker_id):

        # if self.parent.debug_mode:  # print debug messages
        #     print(f"marker_select() with marker {marker_id} for viewport {self.id}")

        for slice_idx, slice_markers in self.slice_markers.items():
            for mk in slice_markers:
                if mk['id'] == marker_id:
                    slice_markers.remove(mk)
                    self._update_markers_display()
                    return

    def marker_delete_all(self):
        self.slice_markers = {}
        self._update_markers_display()

    def marker_clear_selected(self, notify=True):
        """
        Sets all points in this viewport to unselected.

        :return:
        """

        # if self.parent.debug_mode:  # print debug messages
        #     print(f"marker_clear_selected() for viewport {self.id}")

        for slice_idx, points in self.slice_markers.items():
            for pt in points:
                pt['is_selected'] = False
        self.selected_marker = None
        self._update_markers_display()
        if notify:
            self.markers_cleared_signal.emit(self.id)

    def marker_set_add_mode(self, _is_adding):
        """Can be called by external class to toggle marker_add mode."""
        self.add_marker_mode = _is_adding

    # def set_pending_marker_mode(self, _pending):
    #     self.pending_point_mode = _pending

    def marker_set_edit_mode(self, _editing):
        """Can be called by external class to toggle edit_marker mode."""
        self.edit_marker_mode = _editing

    # painting ---------------------------------------------------------------------------------------------------------
    def paint_remove_canvas_label(self, _label_id):
        """ Remove this label id from the list of labels that are allowed to be affected by painting."""
        if _label_id in self.canvas_labels:
            self.canvas_labels.remove(_label_id)

    def paint_set_canvas_layer_index(self, _layer_idx):
        """ Add this layer index to the list of canvas layers. The canvas layer is the image that is being painted on."""
        if _layer_idx < self.num_vols_allowed:
            self.canvas_layer_index = _layer_idx
        #TODO: warn or log

    def paint_add_canvas_label(self, _label_id):
        """ Add this label id to the list of labels that are being painted on the canvas layer."""
        if _label_id not in self.canvas_labels:
            self.canvas_labels.append(_label_id)
            
    def paint_update_brush(self, brush):
        """Update the paint brush settings. Called by external class to update the paint brush settings,
        applies updated brush to current paint layer, if is_painting."""
        self.paint_brush.set_size(brush.size)
        self.paint_brush.set_value(brush.value)  # label id
        self.paint_brush.set_shape(brush.shape)

    def paint_set_brush_label(self, _label_id):
        self.paint_brush.set_value(_label_id)

    def paint_blend_background_with_layer(self, bg_pct, layer_idx, layer_pct):
        pass
    #     """
    #     Blend the current slice of the background image with the current slice of the image specified by layer_idx.
    #     The alpha values are used to generate a weighted sum, thus resulting in an "alpha blended" image.
    #
    #     :param bg_pct: float (0.0 - 1.0)
    #     :param layer_idx: index of the volume to blend with the background
    #     :param layer_pct: float (0.0 - 1.0)
    #     :return: 2D numpy array
    #     """
    #     background_image = self.image3D_obj_stack[0]
    #     background_data = self.array3D_stack[0]
    #     background_slice = (background_data[int(self.image_view.currentIndex), :, :]).astype(np.int32)
    #     background_cmap = pg.colormap.get(background_image.colormap_name)
    #     background_rgb = background_cmap.map(background_slice)
    #
    #     layer_image = self.image3D_obj_stack[layer_idx]
    #     layer_data = self.array3D_stack[layer_idx]
    #     layer_slice = (layer_data[int(self.image_view.currentIndex), :, :]).astype(np.int32)
    #     layer_cmap = pg.colormap.get(layer_image.colormap_name)
    #     layer_rgb = layer_cmap.map(layer_slice)
    #     layer_image_item = self.array2D_stack[layer_idx]
    #
    #     # normalize the slices to 0-255
    #     # background_norm = ((background_slice - np.min(background_slice)) / (np.max(background_slice) - np.min(background_slice))) * 255
    #     # layer_norm = ((layer_slice - np.min(layer_slice)) / (np.max(layer_slice) - np.min(layer_slice))) * 255
    #     background_norm = ((background_slice - np.min(background_data)) / (np.max(background_data) - np.min(background_data))) * 255
    #     layer_norm = ((layer_slice - np.min(layer_data)) / (np.max(layer_data) - np.min(layer_data))) * 255
    #
    #     # slices to colormap
    #     background_rgb = background_cmap.map(background_norm, mode='byte')
    #     layer_rgb = layer_cmap.map(layer_norm, mode='byte')
    #
    #     # blend
    #     blended_slice = bg_pct * background_slice + layer_pct * layer_slice
    #     # blended_slice = (bg_pct * background_rgb + layer_pct * layer_rgb).astype(np.uint8)
    #
    #     # self.image_view.clear()
    #     layer_image_item.setImage(blended_slice)
    #     # layer_image_item.setImage(background_rgb)
    #     # self.image_view.show()
    #     # self.refresh_preserve_extent()

    def refresh_preserve_extent(self):
        """
        Refresh the viewport without changing the current view extent.
        """
        # save the current view state (extent)
        view_box = self.image_view.getView()
        current_range = view_box.viewRange()  # [[x_min, x_max], [y_min, y_max]]
        # # FIXME: temp
        # print(f"current_range: {current_range}")

        self.refresh()

        # restore the view range
        view_box.setRange(
            xRange=current_range[0],
            yRange=current_range[1],
            padding=0  # Disable padding to restore exact range
        )

        # FIXME: temp
        # my_debug_stop = 24

    def refresh(self):
        """
        Should be called when one of the images displayed in the viewport changes. Sets the image item, and connects the
        histogram widget to the image item. Also updates the overlay images.
        """

        # if self.parent.debug_mode:  # print debug messages
        #     print(f"refresh() for viewport {self.id}")

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
                    # disconnect the slot to prevent this from happening
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

                    # if im_obj.clipping:
                    #     # "clip" the image data to the display range (make vals outside range transparent)
                    #     lo = im_obj.display_min
                    #     hi = im_obj.display_max
                    #     dmin = im_obj.data_min
                    #     dmax = im_obj.data_max
                    #     # compute normalized indices into [0…255]
                    #     lo_idx = np.clip(((lo - dmin) / (dmax - dmin) * 255).astype(int), 0, 255)
                    #     hi_idx = np.clip(((hi - dmin) / (dmax - dmin) * 255).astype(int), 0, 255)
                    #     lut = im_obj.colormap.getLookupTable(
                    #         start=0.0,  # maps to cm position 0.0
                    #         stop=1.0,  # maps to cm position 1.0
                    #         nPts=256,
                    #         alpha=True  # include the alpha channel
                    #     )
                    #     lut[:lo_idx, 3] = 0  # below min → transparent
                    #     lut[hi_idx:, 3] = 0  # above max → transparent
                    #     main_image.setLookupTable(lut)
                    # else:
                    # Set the levels to prevent LUT rescaling based on the slice content
                    main_image.setLevels([im_obj.display_min, im_obj.display_max])
                    # apply the opacity of the Image3D object to the ImageItem
                    main_image.setOpacity(im_obj.alpha)
                    main_image.setColorMap(im_obj.colormap)

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

        self._update_markers_display()

        # update the crosshairs
        self.update_crosshairs()

        self.image_view.show()

    #  -----------------------------------------------------------------------------------------------------------------
    #  "Private" methods -----------------------------------------------------------------------------------------------
    #  -----------------------------------------------------------------------------------------------------------------

    def _view_axis_index(self):
        # im3d_crs order is (col, row, slc) == (x, y, z)
        if self.view_dir == ViewDir.AX.dir:
            return 2  # slice axis (z)
        elif self.view_dir == ViewDir.SAG.dir:
            return 0  # col axis (x)
        elif self.view_dir == ViewDir.COR.dir:
            return 1  # row axis (y)
        return 2

    def _image_center_indices(self, bg):
        # im3d_crs order is (col, row, slc) == (x, y, z)
        # NOTE: use the Image3D data shape in (x, y, z) consistent with your im3d_crs
        # If your Image3D uses (z, x, y), adjust accordingly.
        try:
            x, y, z = bg.data.shape[1], bg.data.shape[2], bg.data.shape[0]  # if bg.data is (z, x, y)
            return (x // 2, y // 2, z // 2)
        except Exception:
            return (0, 0, 0)

    def _wheel_event(self, event):
        """Use mouse wheel to step through slices; clamp to [0 .. n_slices-1]."""
        # Figure out how many frames/slices we have
        frames = None
        if self.background_image_index is not None:
            arr = self.array3D_stack[self.background_image_index]
            if arr is not None and arr.ndim >= 3:
                frames = arr.shape[0]
        if frames is None:
            # Fallback: read from the ImageItem if available
            img_item = self.image_view.getImageItem()
            if img_item is not None and getattr(img_item, "image", None) is not None:
                im = img_item.image
                if getattr(im, "ndim", 0) >= 3:
                    frames = im.shape[0]

        if not frames:
            # Nothing to scroll
            event.ignore()
            return

        # Determine wheel direction (Qt5 scene wheel vs. QWheelEvent)
        delta = event.delta() if hasattr(event, "delta") else event.angleDelta().y()
        step = 1 if delta > 0 else -1

        # Clamp and set the new index
        current = int(self.image_view.currentIndex)
        new_idx = max(0, min(frames - 1, current + step))
        if new_idx != current:
            try:
                self.image_view.setCurrentIndex(new_idx)  # preferred
            except Exception:
                try:
                    self.image_view.timeLine.setValue(new_idx)  # fallback
                except Exception:
                    pass

        event.accept()  # swallow default zoom

    def _set_coords_label(self, col=None, row=None, slc=None, world=None):
        """
        Update the coordinates label; keep field names, blank numbers if None.
        World fields use one decimal place and switch to R/A/S when display_convention == 'RAS'.
        """
        vox_w = getattr(self, "_vox_field_width", 3)
        world_w = getattr(self, "_world_field_width", 8)  # derived from world_sample in __init__
        prec = getattr(self, "_world_prec", 1)

        def fmt_int(v):
            return f"{int(v):>{vox_w}d}" if isinstance(v, (int, np.integer)) else " " * vox_w

        def fmt_float(v):
            return f"{float(v):>{world_w}.{prec}f}" if (v is not None) else " " * world_w

        # image (voxel) coordinate labels
        vox_txt = f"col:{fmt_int(col)} row:{fmt_int(row)} slice:{fmt_int(slc)}"

        # world (patient) coordinate labels
        labels = ("x", "y", "z")
        if getattr(self, "display_convention", "").upper() == "RAS":
            labels = ("R", "A", "S")
        if world is not None and len(world) == 3:
            x, y, z = world
            world_txt = f"  |  {labels[0]}:{fmt_float(x)} {labels[1]}:{fmt_float(y)} {labels[2]}:{fmt_float(z)}"
        else:
            blank = " " * world_w
            world_txt = f"  |  {labels[0]}:{blank} {labels[1]}:{blank} {labels[2]}:{blank}"

        self.coordinates_label.setText(vox_txt + world_txt)

    def _slice_changed(self):
        """Update current slice and overlays, update coordinates display."""
        if self.background_image_index is None:
            return

        self.current_slice_index = self.image_view.currentIndex
        self.refresh_preserve_extent()

        # If we know the last plot (x,y) and the mouse was inside, recompute voxel + world
        if self._last_mouse_inside:
            px, py = self._last_plot_x, self._last_plot_y
            if px is not None and py is not None:
                crs = self.plotxyz_to_plotdatacrs(px, py, int(self.current_slice_index))
                if crs is not None:
                    img = self.plotdatacrs_to_imagecrs(crs[0], crs[1], crs[2])
                    if img is not None:
                        bg_img = self.image3D_obj_stack[self.background_image_index]
                        if bg_img is not None and hasattr(bg_img, "voxel_to_world"):
                            wx, wy, wz = bg_img.voxel_to_world(np.array([int(img[0]), int(img[1]), int(img[2])]))
                            self._set_coords_label(int(img[0]), int(img[1]), int(img[2]), world=(wx, wy, wz))
                        else:
                            self._set_coords_label(int(img[0]), int(img[1]), int(img[2]), None)
        else:
            # outside image bounds, so just update the slice index
            self._handle_out_of_bounds()

        self.slice_changed_signal.emit(self.id, self.current_slice_index)

    def _update_overlays(self):
        """
        When the slice index has changed, manually update the overlay image(s) with the corresponding slice from
        the array3D. If slice index is out of range of overlay data, just return.

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

        self._update_markers_display()

        # # update coordinates to reflect the current slice (so it updates without needing to move the mouse)
        # coordinates_text = self.coordinates_label.text()
        # if len(coordinates_text) > 0:
        #     pattern = r"x=\s*\d+,\s*y=\s*\d+,\s*z=\s*(\d+)"
        #     new_z = self.image_view.currentIndex
        #     # substitute the new z value
        #     new_string = re.sub(pattern, lambda m: m.group(0).replace(m.group(1), f"{new_z:3d}"), coordinates_text)
        #     self.coordinates_label.setText(new_string)

    def _update_overlay_slice(self, layer_index):
        """
        Update the overlay image with the current slice from the overlay data. If layer_index is out of bounds of the
        overlay, just return.
        """
        if self.array3D_stack[layer_index] is None:
            return

        overlay_image_object = self.image3D_obj_stack[layer_index]
        overlay_data = self.array3D_stack[layer_index]
        image_item = self.array2D_stack[layer_index]

        # Guard against out-of-range slice index
        idx = int(self.image_view.currentIndex)
        if idx < 0 or idx >= overlay_data.shape[0]:
            image_item.clear()
            return

        # Apply the slice to the overlay ImageItem
        overlay_slice = overlay_data[idx, :, :]
        image_item.setImage(overlay_slice)

        # Clipping / levels
        if getattr(overlay_image_object, "clipping", False):
            # "clip" the image data to the display range (make vals outside range transparent)
            lo = overlay_image_object.display_min
            hi = overlay_image_object.display_max
            dmin = overlay_image_object.data_min
            dmax = overlay_image_object.data_max

            # Avoid divide-by-zero
            rng = (dmax - dmin) if (dmax > dmin) else 1.0

            # Compute normalized indices into [0..255]
            lo_idx = int(np.clip(((lo - dmin) / rng) * 255.0, 0, 255))
            hi_idx = int(np.clip(((hi - dmin) / rng) * 255.0, 0, 255))

            lut = overlay_image_object.colormap.getLookupTable(
                start=0.0, stop=1.0, nPts=256, alpha=True
            )
            # Below min → transparent; above max → transparent
            lut[:lo_idx, 3] = 0
            lut[hi_idx:, 3] = 0

            # Scale remaining alpha by overall layer alpha
            lut[:, 3] = (lut[:, 3].astype(float) * overlay_image_object.alpha).astype(np.uint8)

            image_item.setLookupTable(lut)
        else:
            # Fixed levels prevent per-slice LUT rescaling
            image_item.setLevels([overlay_image_object.display_min, overlay_image_object.display_max])
            image_item.setOpacity(overlay_image_object.alpha)
            image_item.setColorMap(overlay_image_object.colormap)

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

    # def _reapply_lut(self):
    #     # ensure the LUT remains as you defined it
    #     found_bottom_image = False
    #     for ind, im in enumerate(self.image3D_obj_stack):
    #         if im is None:
    #             continue
    #         else:
    #             if not found_bottom_image:
    #                 found_bottom_image = True
    #                 if im.lookup_table is not None:
    #                     self.image_view.getImageItem().setLookupTable(im.lookup_table)
    #             else:
    #                 if self.array2D_stack[ind] is not None:
    #                     self.array2D_stack[ind].setLookupTable(im.lookup_table)
    #
    # def _toggle_histogram(self):
    #     """toggle the visibility of the histogram/colormap/opacity widget"""
    #     histogram = self.image_view.getHistogramWidget()
    #     is_visible = histogram.isVisible()
    #     histogram.setVisible(not is_visible)
    #     # if self.active_image_index is None:
    #     #     return
    #     # if self.image3D_obj_stack[self.active_image_index] is not None:
    #     #     self.image_view.getImageItem().setLookupTable(self.image3D_obj_stack[self.active_image_index].colormap)
    #     # self.image_view.updateImage()
    #
    #     # self._set_histogram_colormap(self.image3D_obj_stack[self.active_image_index].colormap)
    #     self.opacity_slider.setVisible(not is_visible)

    def _mouse_press(self, event):
        """
        Capture mouse press and handle painting/point actions before passing to pyqtgraph as needed.
        """
        img_item = self.image_view.getImageItem()
        if img_item is None:
            return

        handled = False

        scene_xy = event.scenePos()
        plot_xy = img_item.mapFromScene(scene_xy)

        if img_item.sceneBoundingRect().contains(scene_xy):
            # painting / erasing
            if self.paint_im is not None and self.paint_im.matches_event(event):
                self.interaction_state = 'painting'
                self._mouse_move(event)  # apply immediately
                handled = True
            elif self.erase_im is not None and self.erase_im.matches_event(event):
                self.interaction_state = 'erasing'
                self._mouse_move(event)
                handled = True
            # markers
            elif self.mark_im is not None and self.mark_im.matches_event(event):
                if self.add_marker_mode:  # add a new marker at click
                    plot_x = int(plot_xy.x())
                    plot_y = int(plot_xy.y())
                    plot_data_crs = self.plotxyz_to_plotdatacrs(plot_x, plot_y, self.current_slice_index)
                    if plot_data_crs is not None:
                        image_crs = self.plotdatacrs_to_imagecrs(plot_data_crs[0], plot_data_crs[1], plot_data_crs[2])
                        if image_crs is not None:
                            new_point = self.marker_add(image_crs[0], image_crs[1], image_crs[2],
                                                        0)  # TODO: image index
                            if new_point is not None:
                                self.marker_select(new_point, False)
                                self.drag_marker_mode = True
                                self._update_markers_display()
                                self.marker_added_signal.emit(new_point, self.id)
                                handled = True
                else:
                    # clicked while not adding → maybe deselect
                    if len(self.scatter.pointsAt(plot_xy)) == 0 and not self.edit_marker_mode:
                        self.marker_clear_selected()
                    # fall through to default PG handling

        if not handled:
            # pass the event back to pyqtgraph for any further processing
            self.original_mouse_press(event)

    def _mouse_press_wrapper(self, event):
        self._profile_method(self._mouse_press, event)

    def _profile_method(self, method, *args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()

        method(*args, **kwargs)

        profiler.disable()
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        ps.print_stats(10)
        print(s.getvalue())  # Or log to a file if preferred

    def _handle_out_of_bounds(self):
        idx = int(self.image_view.currentIndex)
        axis = self._view_axis_index()
        bg = self.image3D_obj_stack[self.background_image_index]

        # Build a voxel triplet to evaluate world at:
        # - keep last valid in-plane indices if we have them, otherwise image center
        if self._last_valid_im3d_crs is not None:
            base = list(self._last_valid_im3d_crs)
        else:
            base = list(self._image_center_indices(bg))  # returns (col, row, slc)

        base[axis] = idx
        im3d_for_world = tuple(int(v) for v in base)

        # Compute world, then blank two components (only keep the axis that persists)
        world = None
        if hasattr(bg, "voxel_to_world"):
            try:
                wx, wy, wz = bg.voxel_to_world(np.array(im3d_for_world))
                all_world = (wx, wy, wz)
                masked = [None, None, None]
                masked[axis] = all_world[axis]  # keep only the persistent axis
                world = tuple(masked)
            except Exception:
                world = None

        # Persist voxel coord the same way you already do
        kwargs = dict(col=None, row=None, slc=None, world=world)
        if axis == 0:
            kwargs["col"] = idx
        elif axis == 1:
            kwargs["row"] = idx
        else:
            kwargs["slc"] = idx

        self._set_coords_label(**kwargs)
        self._last_mouse_inside = False

    def _mouse_move(self, event):
        if self.background_image_index is None:
            return

        background_image_obj = self.image3D_obj_stack[self.background_image_index]
        if background_image_obj is None:
            return

        scene_xy_qpoint = event.scenePos()
        imv_image_item = self.image_view.getImageItem()

        # OOB case #1: no image item or cursor not over it
        if imv_image_item is None or not imv_image_item.sceneBoundingRect().contains(scene_xy_qpoint):
            self._handle_out_of_bounds()
            return

        # Map to plot coords (note: x-axis inverted in your view)
        plot_mouse_point = imv_image_item.mapFromScene(scene_xy_qpoint)
        plot_x, plot_y = int(plot_mouse_point.x()), int(plot_mouse_point.y())

        # Map to plot-data CRS
        imv_image_crs = self.plotxyz_to_plotdatacrs(plot_x, plot_y, self.current_slice_index)
        if imv_image_crs is None:
            # OOB case #2
            self._handle_out_of_bounds()
            return

        # Map to Image3D CRS
        im3d_crs = self.plotdatacrs_to_imagecrs(imv_image_crs[0], imv_image_crs[1], imv_image_crs[2])
        if im3d_crs is None:
            # OOB case #3
            self._handle_out_of_bounds()
            return

        # ----- In-bounds: update caches and label once -----
        c = int(im3d_crs[0]);
        r = int(im3d_crs[1]);
        s = int(im3d_crs[2])
        world = None
        if hasattr(background_image_obj, "voxel_to_world"):
            wx, wy, wz = background_image_obj.voxel_to_world(np.array([c, r, s]))
            world = (wx, wy, wz)
            self._last_valid_world = world
        else:
            self._last_valid_world = None

        self._last_valid_im3d_crs = (c, r, s)
        self._set_coords_label(c, r, s, world)

        self._last_mouse_inside = True
        self._last_plot_x = plot_x
        self._last_plot_y = plot_y

        # ----- Interactions -----
        if self.interaction_state == 'painting':
            self._apply_brush(plot_x, plot_y, True)
        elif self.interaction_state == 'erasing':
            self._apply_brush(plot_x, plot_y, False)
        elif self.drag_marker_mode:
            if self.selected_marker is not None:
                self.marker_moved = True
                self.selected_marker['plot_x'] = plot_x
                self.selected_marker['plot_y'] = plot_y
                self.selected_marker['image_col'] = c
                self.selected_marker['image_row'] = r
                self.selected_marker['image_slice'] = s
                self._update_markers_display()
                self.marker_moved_signal.emit(self.selected_marker, self.id, self.view_dir)
        else:
            self.original_mouse_move(event)

    def _mouse_release(self, event):
        """
        :param event:
        :return:
        Disable painting, erasing, and dragging point actions and pass the event back to pyqtgraph.
        """
        # DEBUG:
        # print("_mouse_release")

        self.interaction_state = None
        self.drag_marker_mode = False

        # notify parent that point was moved
        # if self.selected_marker is not None and self.marker_moved:
        #     self.marker_moved = False
        #     self.marker_moved_signal.emit(self.selected_marker, self.id, self.view_dir)

        # pass event back to pyqtgraph for any further processing
        self.original_mouse_release(event)

    # def _update_canvas(self):
    #     """Update the canvas for painting. Masks the painting area using allowed values."""
    #     if self.image3D_obj_stack[self.canvas_layer_index] is None or self.array3D_stack[
    #         self.canvas_layer_index] is None:
    #         # FIXME: raise an error or warning?
    #         return
    #
    #     if not self.is_painting:
    #         # TODO APPLY the mask to the paint image
    #         self.imageItem2D_canvas.clear()
    #
    #     # mask the paint image to create a canvas for painting
    #     paint_image_object = self.image3D_obj_stack[self.canvas_layer_index]
    #     if hasattr(paint_image_object, 'get_canvas_labels'):
    #         allowed_values = np.array(paint_image_object.get_canvas_labels())  # , dtype=canvas_slice.dtype.type
    #         if allowed_values is None:
    #             return
    #         # paint_value = self.paint_brush.get_value()  # Value to paint with
    #         paint_value = self.paint_brush.get_value()  # canvas_slice.dtype.type(
    #
    #         # get the current slice of the paint image
    #         if self.canvas_layer_index == self.background_image_index:
    #             paint_image_slice = self.image_view.getImageItem().image
    #         else:
    #             paint_image_slice = self.array2D_stack[self.canvas_layer_index].image
    #
    #         colors = [
    #             (255, 255, 255, 0),  # white for 0
    #             (255, 0, 0, 255),  # red for 1
    #             (0, 255, 0, 255),  # green for 2
    #             (0, 0, 255, 255),  # blue for 3
    #             (255, 255, 0, 255)  # yellow for 4
    #         ]
    #
    #         # masked canvas: 0 where paint is allowed, -1 * paint_value where it’s not allowed
    #         temp_mask = np.where(np.isin(paint_image_slice, allowed_values), 0, (-1 * paint_value))
    #         self.imageItem2D_canvas.setImage(temp_mask)
    #         # mask_lookup_table = paint_image_object.colormap
    #         # # self.imageItem2D_canvas.setLookupTable(mask_lookup_table)
    #         color_map = pg.ColorMap(pos=np.linspace(0, 1, 5), color=colors)
    #         self.imageItem2D_canvas.setColorMap(color_map)
    #         self.imageItem2D_canvas.setDrawKernel(self.paint_brush.kernel, mask=None, center=self.paint_brush.center,
    #                                               mode='add')
    #
    #         # FIXME: here, we need to fiddle with the colormap to make all but the paint_value transparent
    #         # color_map = pg.ColorMap(pos=np.linspace(0, 1, 9), color=canvas_image_object.colormap)
    #         # self.imageItem2D_canvas.setColorMap(color_map)
    #
    #         # self.imageItem2D_canvas.setDrawKernel(self.paint_brush.kernel, mask=None, center=self.paint_brush.center,
    #         #                                    mode='add')


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
        data_slice = data[int(self.image_view.currentIndex), :, :]  # arrays have been transposed - slice is first dim

        # Define the range for the brush area
        half_brush = self.paint_brush.get_size() // 2

        # FIXME: debugging
        # print(f"VIEWPORT paint_brush size: {self.paint_brush.get_size()}")
        # print(f"VIEWPORT half_brush: {half_brush}, x: {x}, y: {y}")

        x_start = max(0, x - half_brush)
        x_end = min(data_slice.shape[0], x + half_brush + 1)
        y_start = max(0, y - half_brush)
        y_end = min(data_slice.shape[1], y + half_brush + 1)

        # Create a mask for the brush area within the bounds of data
        brush_area = data_slice[x_start:x_end, y_start:y_end]

        allowed_values = np.array(self.canvas_labels)  # array of label values that can be painted
        mask = np.isin(brush_area, allowed_values)

        # apply active label or 0 to canvas, depending on painting or erasing
        if painting:
            brush_area[mask] = self.paint_brush.get_value()
        else:
            # erasing
            brush_area[mask] = 0  # assumes null value is 0

        # update only the modified slice in the 3D array
        # TODO: this is where we can implement an undo stack, saving changes to one slice at a time
        # FIXME: this seems to be directly modifying the image3D object, which is not what we want
        data[int(self.image_view.currentIndex), :, :] = data_slice

        # update the appropriate ImageView ImageItem
        # preserve the current zoom and pan state, prevents image from resetting to full extent
        view_range = self.image_view.view.viewRange()
        if self.canvas_layer_index == self.background_image_index:
            slice_index = int(self.image_view.currentIndex)
            self.image_view.setImage(data)
            self.image_view.setCurrentIndex(slice_index)
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

    def _update_markers_display(self):
        """
        Update the display of markers on the image view. Only display markers for the current slice.
        Does not call refresh()

        :return:
        """
        # if self.parent.debug_mode:  # print debug messages
        #     print(f"_update_markers_display() for viewport {self.id}")

        # get markers for the current slice
        current_slice = int(self.image_view.currentIndex)
        markers = self.slice_markers.get(current_slice, [])

        # print(markers)

        # update ScatterPlotItem
        spots = []
        if len(markers) > 0:
            for marker in markers:
                image_data_crs = self.imagecrs_to_plotdatacrs(marker['image_col'], marker['image_row'], marker['image_slice'])
                if image_data_crs is None:
                    continue
                plot_xy = self.plotdatacr_to_plotxy(image_data_crs[0], image_data_crs[1])
                if plot_xy is None:
                    continue
                spots.append(
                    {
                        'pos': (plot_xy[0], plot_xy[1]), 'data': marker,
                        'brush': self.selected_brush if marker['is_selected'] else self.idle_brush,
                    } )
            # FIXME: testing and debugging
            # print(f"spots: {spots}")
            self.scatter.setData(spots=spots)
        else:
            self.scatter.clear()

    def _scatter_mouse_press(self, evt, mkr):
        """
        When user clicks on a marker. If the marker is not already selected, select it. If the marker
        is already selected, allow it to be dragged to a new position.

        :param evt: the clicking on a marker event
        :param mkr: the marker that was clicked
        :return:
        """
        if self.mark_im is not None and self.mark_im.matches_event(evt):
            # only respond to the event if the interaction method matches (for example, shift + left click)
            if mkr is not None:
                if mkr.get('is_selected'):  # and self.edit_marker_mode:
                    self.drag_marker_mode = True
                else:
                    if not self.edit_marker_mode:
                        self.marker_select(mkr, True)
                    else:
                        self.drag_marker_mode = True
                        # DEBUG:
                        print(f'Drag edit marker')

