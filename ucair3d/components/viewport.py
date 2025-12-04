import numpy as np
import pyqtgraph as pg

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
    Change the default mouse cursor to a small green cross.
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
    Tracks Ctrl key globally and applies a cursor to any registered widgets
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
        self.mouse_click_callback = None
        self._press_pos = None  # Track where press occurred for click detection
        self._press_point_data = None  # Track which point was pressed
        # self.current_point = None  # Track the currently selected marker

    def set_mouse_press_callback(self, callback):
        self.mouse_press_callback = callback

    def set_mouse_click_callback(self, callback):
        self.mouse_click_callback = callback

    def mousePressEvent(self, event):
        # find the spot that was pressed and pass it to custom callback
        clicked_spots = self.pointsAt(event.pos())
        if len(clicked_spots) > 0:
            clicked_spot = clicked_spots[0]  # Assume only one point is clicked
            point_data = clicked_spot.data()  # Access the metadata for the point

            # Store press position and point for click detection
            self._press_pos = event.pos()
            self._press_point_data = point_data

            # call the custom callback if provided
            if self.mouse_press_callback:
                self.mouse_press_callback(event, point_data)
            else:
                # Preserve default behavior
                super().mousePressEvent(event)
        else:
            self._press_pos = None
            self._press_point_data = None
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        # Check if this was a click (press and release at same location)
        if self._press_pos is not None and self._press_point_data is not None:
            # Check if release position is close to press position (within click threshold)
            release_pos = event.pos()
            if self._press_pos is not None:
                delta = (release_pos - self._press_pos).manhattanLength()
                # Qt's default click threshold is typically around 4-6 pixels
                if delta <= 6 and self.mouse_click_callback:
                    # This was a click - call the click callback
                    # Create a synthetic event for the callback
                    self.mouse_click_callback(event, self._press_point_data)
            
            # Clear press tracking
            self._press_pos = None
            self._press_point_data = None
        
        super().mouseReleaseEvent(event)


class Viewport(QWidget):
    """ This class displays one or more 3D images. It is interactive and allows the user to pan, zoom, and scroll
    through images. Multiple images can be stacked on top of each other to create overlays. The user can also paint
    (modify the voxel values) and add markers to the image. Tools are provided for modifying the colormap and opacity
    of the images. The calling class must provide the view desired view direction (axial, coronal, sagittal).
    The calling class must also provide the maximum number of image allowed in the stack.
    A viewport is a subclass of QWidget and can be added to a layout in a QMainWindow.
    """
    # Marker colors - easily modifiable for development
    # Colors are RGBA tuples: (R, G, B, Alpha) with values 0-255
    IDLE_MARKER_COLOR = (255, 0, 0, 255)      # red - unselected markers (fill)
    SELECTED_MARKER_COLOR = (255, 0, 0, 255)  #  (50, 130, 246, 255)  # blue - selected markers (fill)
    EDITING_MARKER_COLOR = (0, 255, 0, 255)   # green - selected markers in edit mode (fill, draggable)
    
    # Marker outline colors - can be different from fill colors
    IDLE_MARKER_OUTLINE_COLOR = (255, 0, 0, 255)        # red - unselected markers (outline)
    SELECTED_MARKER_OUTLINE_COLOR = (0, 255, 0, 255)  # green - selected markers (outline)
    EDITING_MARKER_OUTLINE_COLOR = (0, 255, 0, 255)   # green - selected markers in edit mode (outline)
    
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
        self.marker_mode = 'idle' # 'idle', 'adding', 'dragging', 'editing'
        self._selection_locked = False  # Prevent deselection while adding/editing markers (until Done is clicked)
        self._edit_mode = False  # Track if we're in edit mode (allows dragging)
        self.marker_moved = False
        self.selected_marker = None
        self._marker_counter = 0
        self._edit_start_position = None  # Store original position when entering edit mode
        # Marker colors - use class variables (can be overridden per instance if needed)
        self.idle_marker_color = self.IDLE_MARKER_COLOR
        self.selected_marker_color = self.SELECTED_MARKER_COLOR
        self.temp_marker_color = self.EDITING_MARKER_COLOR
        self.idle_marker_outline_color = self.IDLE_MARKER_OUTLINE_COLOR
        self.selected_marker_outline_color = self.SELECTED_MARKER_OUTLINE_COLOR
        self.temp_marker_outline_color = self.EDITING_MARKER_OUTLINE_COLOR
        # Pens use outline colors, brushes use fill colors
        self.idle_pen = pg.mkPen(self.idle_marker_outline_color, width=1)
        self.idle_brush = pg.mkBrush(self.idle_marker_color)
        self.selected_pen = pg.mkPen(self.selected_marker_outline_color, width=2)
        self.selected_brush = pg.mkBrush(self.selected_marker_color)
        self.temp_pen = pg.mkPen(self.temp_marker_outline_color, width=1)
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
        font = QFont("Courier New", 8)  # use a monospaced font for better alignment
        self.coordinates_label.setFont(font)
        # Enable word wrap so the label can display multiple lines
        self.coordinates_label.setWordWrap(False)  # We'll use explicit newlines
        # one‑decimal world format; this string defines the numeric field width
        world_sample = "-000.0"  # ← change this once if you ever need wider fields
        self._world_prec = 1
        self._world_field_width = len(world_sample)
        self._vox_field_width = 3
        # choose letters for the sample (RAS or xyz doesn't change total width)
        axis_labels = ("R", "A", "S") if self.display_convention.upper() == "RAS" else ("x", "y", "z")
        # Calculate width based on the longer line (world coordinates line)
        world_sample_line = f"{axis_labels[0]}:{world_sample} {axis_labels[1]}:{world_sample} {axis_labels[2]}:{world_sample}"
        vox_sample_line = f"col:000 row:000 slice:000"
        metrics = QFontMetrics(self.coordinates_label.font())
        world_width = getattr(metrics, "horizontalAdvance", metrics.width)(world_sample_line)
        vox_width = getattr(metrics, "horizontalAdvance", metrics.width)(vox_sample_line)
        # Use the wider of the two lines, and set height for two lines
        width = max(world_width, vox_width)
        line_height = metrics.height()
        self.coordinates_label.setFixedWidth(width)
        self.coordinates_label.setFixedHeight(line_height * 2)  # Two lines
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
        self.image_view.getView().scene().mouseMoveEvent = self._mouse_move

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

        # this is the plot item for creating points. Customized to capture mouse press and mouse click events
        self.scatter = CustomScatterPlotItem()
        self.scatter.set_mouse_press_callback(self._scatter_mouse_press)
        self.scatter.set_mouse_click_callback(self._scatter_mouse_click)
        self.image_view.getView().addItem(self.scatter)


        # connect the mouse click event to the graphics scene
        # optionally, profile this slot by wrapping it in the profiler
        if self.parent.debug_mode:
            self.image_view.getView().scene().mousePressEvent = self._mouse_press_wrapper
        else:
            self.image_view.getView().scene().mousePressEvent = self._mouse_press

        # connect the mouse release event to the graphics scene
        self.image_view.getView().scene().mouseReleaseEvent = self._mouse_release

        # connect the mouse move event to the graphics scene
        self.image_view.getView().scene().mouseMoveEvent = self._mouse_move

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
    def add_marker(self, image_col, image_row, image_slice, image_index, new_id=None):
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
        #     print(f"add_marker() image_col: {image_col}, image_row: {image_row}, image_slice: {image_slice}, "
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
                # # create a unique id for the new  marker
                # marker_id = shortuuid.ShortUUID().random(length=8)  # short, unique, and (marginally) human-readable
                # # FIXME: check to see if this id is already in use (is that possible?)
                # Create a simple sequential ID, like "LM_1", "LM_2", etc.
                self._marker_counter += 1
                marker_id = f"MK_{self.id}_{self._marker_counter}"
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

    def marker_sync_counter(self):
        """
        Update _marker_counter to be higher than any existing marker ID.
        This ensures that new markers created after loading landmarks won't conflict with existing IDs.
        Marker IDs are in the format: "MK_{self.id}_{counter}"
        """
        max_counter = 0
        for slice_idx, markers in self.slice_markers.items():
            for marker in markers:
                marker_id = marker.get('id', '')
                # Parse marker ID format: "MK_{vp_id}_{counter}"
                if marker_id.startswith(f"MK_{self.id}_"):
                    try:
                        counter_str = marker_id.split('_')[-1]
                        counter = int(counter_str)
                        max_counter = max(max_counter, counter)
                    except (ValueError, IndexError):
                        # If parsing fails, ignore this marker ID
                        pass
        # Set counter to max found + 1, or keep current if it's already higher
        self._marker_counter = max(self._marker_counter, max_counter)

    def marker_clear_selected(self, notify=True):
        """
        Sets all points in this viewport to unselected.
        Respects _selection_locked flag to prevent clearing during add mode.

        :return:
        """

        # if self.parent.debug_mode:  # print debug messages
        #     print(f"marker_clear_selected() for viewport {self.id}")

        # Don't clear selection if it's locked (during add mode until Done)
        if self._selection_locked:
            return

        for slice_idx, points in self.slice_markers.items():
            for pt in points:
                pt['is_selected'] = False
        self.selected_marker = None
        self._update_markers_display()
        if notify:
            self.markers_cleared_signal.emit(self.id)

    def marker_set_add_mode(self, _is_adding):
        """Can be called by external class to toggle marker add mode."""
        if _is_adding:
            self.marker_mode = 'adding'
            self._edit_mode = False  # Exit edit mode when entering add mode
            # Don't lock selection yet - allow clearing when entering add mode
            # Selection will be locked after a marker is actually added
            self._selection_locked = False
        else:
            self._selection_locked = False  # Unlock selection first, before clearing
            self.marker_mode = 'idle'
            self._edit_mode = False

    def marker_set_edit_mode(self, _is_editing, restore_position=False):
        """
        Can be called by external class to toggle marker edit mode.
        
        :param _is_editing: bool - True to enter edit mode, False to exit
        :param restore_position: bool - If True when exiting edit mode, restore marker to original position (for Cancel)
        """
        if _is_editing:
            self._edit_mode = True
            # Lock selection while editing (similar to add mode)
            self._selection_locked = True
            # Save the current position of the selected marker for potential restore on cancel
            if self.selected_marker is not None:
                self._edit_start_position = {
                    'image_col': self.selected_marker['image_col'],
                    'image_row': self.selected_marker['image_row'],
                    'image_slice': self.selected_marker['image_slice']
                }
            # Don't change marker_mode here - it stays as 'idle' until dragging starts
            # Update marker display immediately to show editing color
            self._update_markers_display()
        else:
            self._edit_mode = False
            self._selection_locked = False  # Unlock selection when done editing
            # Restore marker position if canceling (restore_position=True)
            if restore_position and self._edit_start_position is not None and self.selected_marker is not None:
                # Restore the original position
                self.selected_marker['image_col'] = self._edit_start_position['image_col']
                self.selected_marker['image_row'] = self._edit_start_position['image_row']
                self.selected_marker['image_slice'] = self._edit_start_position['image_slice']
                self._edit_start_position = None  # Clear saved position
                # Update display to show restored position
                self._update_markers_display()
            else:
                # Not restoring - clear saved position (Done was clicked, keep changes)
                self._edit_start_position = None
            if self.marker_mode == 'dragging':
                self.marker_mode = 'idle'  # Exit dragging mode if we were dragging
            # Update marker display immediately to show selected color (if still selected)
            if not restore_position or self._edit_start_position is None:  # Only update if we didn't already update above
                self._update_markers_display()

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

    def refresh_preserve_extent(self, use_blend_opacity=None):
        """
        Refresh the viewport without changing the current view extent.
        
        :param use_blend_opacity: If True, use blend_opacity instead of opacity for Image3D objects.
                                  If None, uses the stored value from previous calls (defaults to False if never set).
        """
        # If not explicitly provided, use stored value (for internal calls like _slice_changed)
        if use_blend_opacity is None:
            use_blend_opacity = getattr(self, '_use_blend_opacity', False)
        
        # save the current view state (extent)
        view_box = self.image_view.getView()
        current_range = view_box.viewRange()  # [[x_min, x_max], [y_min, y_max]]
        # # FIXME: temp
        # print(f"current_range: {current_range}")

        self.refresh(use_blend_opacity=use_blend_opacity)

        # restore the view range
        view_box.setRange(
            xRange=current_range[0],
            yRange=current_range[1],
            padding=0  # Disable padding to restore exact range
        )

        # FIXME: temp
        # my_debug_stop = 24

    def refresh(self, use_blend_opacity=False):
        """
        Should be called when one of the images displayed in the viewport changes. Sets the image item, and connects the
        histogram widget to the image item. Also updates the overlay images.
        
        :param use_blend_opacity: If True, use blend_opacity instead of opacity for Image3D objects
        """
        # Store flag as instance variable for use in _update_overlays() which is called from _slice_changed()
        self._use_blend_opacity = use_blend_opacity

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

                    # if the Image3D object does not have display-related information, then set some defaults
                    disp_min = getattr(im_obj, "display_min", im_obj.data_min)
                    disp_max = getattr(im_obj, "display_max", im_obj.data_max)
                    # Use blend_opacity if flag is set and attribute exists, otherwise use opacity
                    if use_blend_opacity and hasattr(im_obj, "blend_opacity"):
                        opacity = getattr(im_obj, "blend_opacity", 1.0)
                    else:
                        opacity = getattr(im_obj, "opacity", 1.0)
                    lut = getattr(im_obj, "lut", None)

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

                    # Set the levels to prevent LUT rescaling based on the slice content
                    main_image.setLevels([disp_min, disp_max])
                    # apply the opacity of the Image3D object to the ImageItem
                    main_image.setOpacity(opacity)
                    if isinstance(lut, np.ndarray):
                        main_image.setLookupTable(lut)  # LUT path (discrete or continuous)
                    else:
                        # optional fallback if you ever store names for continuous:
                        if getattr(im_obj, "colormap_kind", None) == "continuous" and isinstance(im_obj.colormap_source,
                                                                                                 str):
                            lut = getattr(im_obj, "lut", None)
                            if isinstance(lut, np.ndarray):
                                main_image.setLookupTable(lut)  # works for discrete & continuous
                            else:
                                name = getattr(im_obj, "colormap_source", None)
                                if isinstance(name, str):
                                    # optional: try name only if you know pyqtgraph has it
                                    main_image.setColorMap(name)

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
                    self._update_overlay_slice(ind, use_blend_opacity=use_blend_opacity)  # uses self.current_slice_index

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
        Displays on two lines: patient coordinates on top, voxel coordinates below.
        """
        vox_w = getattr(self, "_vox_field_width", 3)
        world_w = getattr(self, "_world_field_width", 8)  # derived from world_sample in __init__
        prec = getattr(self, "_world_prec", 1)

        def fmt_int(v):
            return f"{int(v):>{vox_w}d}" if isinstance(v, (int, np.integer)) else " " * vox_w

        def fmt_float(v):
            return f"{float(v):>{world_w}.{prec}f}" if (v is not None) else " " * world_w

        # world (patient) coordinate labels - first line
        labels = ("x", "y", "z")
        if getattr(self, "display_convention", "").upper() == "RAS":
            labels = ("R", "A", "S")
        if world is not None and len(world) == 3:
            x, y, z = world
            world_txt = f"{labels[0]}:{fmt_float(x)} {labels[1]}:{fmt_float(y)} {labels[2]}:{fmt_float(z)}"
        else:
            blank = " " * world_w
            world_txt = f"{labels[0]}:{blank} {labels[1]}:{blank} {labels[2]}:{blank}"

        # image (voxel) coordinate labels - second line
        vox_txt = f"col:{fmt_int(col)} row:{fmt_int(row)} slice:{fmt_int(slc)}"

        # Combine with newline: patient coordinates on top, voxel coordinates below
        self.coordinates_label.setText(world_txt + "\n" + vox_txt)

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
            self._handle_out_of_bounds_persistent_label()

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
        # Note: _update_overlays() is called from _slice_changed(), which doesn't have use_blend_opacity context
        # We'll use an instance variable to track this, or default to False for internal calls
        use_blend_opacity = getattr(self, '_use_blend_opacity', False)
        for layer_index in range(self.background_image_index + 1, self.num_vols_allowed):
            if self.image3D_obj_stack[layer_index] is not None:
                self._update_overlay_slice(layer_index, use_blend_opacity=use_blend_opacity)
            else:
                if self.array2D_stack[layer_index] is not None:
                    self.array2D_stack[layer_index].clear()

        self._update_markers_display()

    def _update_overlay_slice(self, layer_index, use_blend_opacity=False):
        """
        Update the overlay image with the current slice from the overlay data. If layer_index is out of bounds of the
        overlay, just return.
        
        :param layer_index: Index of the overlay layer to update
        :param use_blend_opacity: If True, use blend_opacity instead of opacity for Image3D objects
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

        #  levels and opacity
        # if the Image3D object does not have display-related information, then set some defaults
        disp_min = getattr(overlay_image_object, "display_min", overlay_image_object.data_min)
        disp_max = getattr(overlay_image_object, "display_max", overlay_image_object.data_max)
        # Use blend_opacity if flag is set and attribute exists, otherwise use opacity
        if use_blend_opacity and hasattr(overlay_image_object, "blend_opacity"):
            opacity = getattr(overlay_image_object, "blend_opacity", 1.0)
        else:
            opacity = getattr(overlay_image_object, "opacity", 1.0)
        lut = getattr(overlay_image_object, "lut", None)

        # Fixed levels prevent per-slice LUT rescaling
        image_item.setLevels([disp_min, disp_max])
        image_item.setOpacity(opacity)
        if isinstance(lut, np.ndarray):
            image_item.setLookupTable(lut)
        else:
            if getattr(overlay_image_object, "colormap_kind", None) == "continuous" and isinstance(
                    overlay_image_object.colormap_source, str):
                lut = getattr(overlay_image_object, "lut", None)
                if isinstance(lut, np.ndarray):
                    image_item.setLookupTable(lut)  # works for discrete & continuous
                else:
                    name = getattr(overlay_image_object, "colormap_source", None)
                    if isinstance(name, str):
                        # optional: try name only if you know pyqtgraph has it
                        image_item.setColorMap(name)

    def _update_image_object(self):
        """Update the display min and max of the active Image3D object.
        This is the slot for the signal emitted when the user interacts with the histogram widget.
        The histogram widget automatically updates the imageItem, so we also need to update the Image3D object."""
        pass

    def _profile_method(self, method, *args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()

        method(*args, **kwargs)

        profiler.disable()
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
        ps.print_stats(10)
        print(s.getvalue())  # Or log to a file if preferred

    def _handle_out_of_bounds_persistent_label(self):
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

    def _scatter_mouse_press(self, evt, mkr):
        """
        When user presses on a marker. If the marker is already selected and in edit mode, allow it to be dragged.
        Selection of unselected markers happens in _scatter_mouse_click (on click, not press).

        :param evt: the pressing on a marker event
        :param mkr: the marker that was pressed
        :return:
        """
        if self.mark_im is not None and self.mark_im.matches_event(evt):
            # only respond to the event if the interaction method matches (for example, shift + left click)
            if mkr is not None:
                # If marker is already selected and in edit mode, can start dragging
                if mkr.get('is_selected') and self._edit_mode:
                    self.marker_mode = 'dragging'
                
                # Reset drag flag to track if marker was actually moved
                self.marker_moved = False

    def _scatter_mouse_click(self, evt, mkr):
        """
        When user clicks on a marker (press and release at same location).
        If the marker is not already selected, select it now.
        Respects _selection_locked to prevent selecting different markers during add mode.

        :param evt: the clicking on a marker event
        :param mkr: the marker that was clicked
        :return:
        """
        if self.mark_im is not None and self.mark_im.matches_event(evt):
            # only respond to the event if the interaction method matches (for example, shift + left click)
            if mkr is not None:
                # If selection is locked, only allow clicking on the already-selected marker
                if self._selection_locked:
                    if not mkr.get('is_selected'):
                        # Trying to select a different marker while locked - ignore
                        return
                # Select the marker if it's not already selected
                if not mkr.get('is_selected'):
                    self.marker_select(mkr, True)

    def _mouse_press_wrapper(self, event):
        self._profile_method(self._mouse_press, event)

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
                if self.marker_mode == 'adding':
                    plot_x = int(plot_xy.x())
                    plot_y = int(plot_xy.y())
                    plot_data_crs = self.plotxyz_to_plotdatacrs(plot_x, plot_y, self.current_slice_index)
                    if plot_data_crs is not None:
                        image_crs = self.plotdatacrs_to_imagecrs(plot_data_crs[0], plot_data_crs[1], plot_data_crs[2])
                        if image_crs is not None:
                            new_point = self.add_marker(image_crs[0], image_crs[1], image_crs[2],
                                                        0)  # TODO: image index
                            if new_point is not None:
                                self.marker_select(new_point, False)
                                self.marker_mode = 'dragging'
                                self._selection_locked = True  # Lock selection after adding marker (until Done)
                                self._update_markers_display()
                                self.marker_added_signal.emit(new_point, self.id)
                                handled = True
                else:
                    # clicked while not adding but still in marker interaction state → maybe deselect
                    # Only deselect if selection is not locked (i.e., not in add mode)
                    if len(self.scatter.pointsAt(plot_xy)) == 0 and not self._selection_locked:
                        self.marker_clear_selected()
                    # fall through to default PG handling

        if not handled:
            # pass the event back to pyqtgraph for any further processing
            self.original_mouse_press(event)

    def _mouse_move(self, event):
        # -------- guards & setup -------------------------------------------------
        if self.background_image_index is None:
            # Still let the default ViewBox behavior run for panning/zoom, etc.
            return self.original_mouse_move(event)

        bg = self.image3D_obj_stack[self.background_image_index]
        if bg is None:
            return self.original_mouse_move(event)

        # NEW guard: if left button pressed and not in marker drag mode, skip coords
        if (event.buttons() & Qt.LeftButton) and self.marker_mode != 'dragging':
            # let ViewBox handle panning/zoom/etc., but do not update coords
            return self.original_mouse_move(event)

        # Ensure we get move events even without a button pressed (usually true, but harmless)
        try:
            self.image_view.getView().setMouseTracking(True)
            self.image_view.getView().viewport().setMouseTracking(True)
        except Exception:
            pass

        # Lazy init throttling state (~60 FPS)
        if not hasattr(self, "_drag_hz_timer"):
            from PyQt5 import QtCore
            self._drag_hz_timer = QtCore.QElapsedTimer()
            self._drag_hz_timer.start()
            self._drag_throttle_ms = 16  # ~60 Hz

        do_heavy = self._drag_hz_timer.elapsed() >= getattr(self, "_drag_throttle_ms", 16)

        # -------- hit testing & mapping -----------------------------------------
        scene_xy = event.scenePos()
        imv_item = self.image_view.getImageItem()

        # Quick OOB: no image or pointer not over the image item in scene coords
        if imv_item is None or not imv_item.sceneBoundingRect().contains(scene_xy):
            # Keep coord label "persistent" with last valid voxel & world (blanks 2 components)
            if do_heavy:
                self._handle_out_of_bounds_persistent_label()
                self._drag_hz_timer.restart()
            # Pass through to original behavior (keeps default hover/pan UX intact)
            return self.original_mouse_move(event)

        # Map scene -> item (plot) space
        plot_pt = imv_item.mapFromScene(scene_xy)
        plot_x, plot_y = int(plot_pt.x()), int(plot_pt.y())

        # Pixel de-dup: if we haven't moved to a new plot pixel, only do throttled label tick / brush flow
        same_pixel = (getattr(self, "_last_plot_x", None) == plot_x and
                      getattr(self, "_last_plot_y", None) == plot_y)

        # Map plot -> plot-data CRS (x,y,slice) and then -> image (c,r,s)
        imv_crs = self.plotxyz_to_plotdatacrs(plot_x, plot_y, self.current_slice_index)
        if imv_crs is None:
            if do_heavy:
                self._handle_out_of_bounds_persistent_label()
                self._drag_hz_timer.restart()
            return self.original_mouse_move(event)

        im3d_crs = self.plotdatacrs_to_imagecrs(imv_crs[0], imv_crs[1], imv_crs[2])
        if im3d_crs is None:
            if do_heavy:
                self._handle_out_of_bounds_persistent_label()
                self._drag_hz_timer.restart()
            return self.original_mouse_move(event)

        c, r, s = int(im3d_crs[0]), int(im3d_crs[1]), int(im3d_crs[2])

        # -------- coordinate label + world conversion ---------------------------
        # ---- Throttle heavy conversions/label updates to ~60 Hz ----
        do_heavy = self._drag_hz_timer.elapsed() >= getattr(self, "_drag_throttle_ms", 16)
        world = None
        if do_heavy and hasattr(bg, "voxel_to_world"):
            try: # Avoid small numpy allocations in hot path (tuple->list->array is cheap enough)
                wx, wy, wz = bg.voxel_to_world(np.array([c, r, s], dtype=np.int32))
                world = (wx, wy, wz)
                self._last_valid_world = world
            except Exception:
                self._last_valid_world = None
        # else: keep previous world to avoid churn # Note: coords label only needs throttled refresh
        if do_heavy:
            self._set_coords_label(c, r, s, world)
            self._drag_hz_timer.restart()

        # Cache last inside position/voxel for persistence & dedup
        self._last_mouse_inside = True
        self._last_plot_x, self._last_plot_y = plot_x, plot_y
        self._last_valid_im3d_crs = (c, r, s)

        # -------- interaction handling ------------------------------------------
        # Brush flow should not be blocked by pixel dedup (continuous stroke)
        if self.interaction_state == 'painting':
            self._apply_brush(plot_x, plot_y, True)
            return
        if self.interaction_state == 'erasing':
            self._apply_brush(plot_x, plot_y, False)
            return

        # Fast path for marker drag (rate-limited signal emission)
        if self.marker_mode == 'dragging' and (self.selected_marker is not None):
            sm = self.selected_marker
            self.marker_moved = True

            # Update data model
            sm['plot_x'] = plot_x
            sm['plot_y'] = plot_y
            sm['image_col'] = c
            sm['image_row'] = r
            sm['image_slice'] = s

            # Update graphics item if present
            gi = sm.get('graphics_item', None)
            if gi is not None and hasattr(gi, 'setPos'):
                gi.setPos(plot_x, plot_y)
            else:
                if hasattr(self, "_update_selected_marker_item_fast"):
                    self._update_selected_marker_item_fast(sm)
                elif do_heavy:
                    self._update_markers_display()

            if do_heavy:
                self.marker_moved_signal.emit(sm, self.id, self.view_dir)

            return

        # Default pass-through so ViewBox pans/zooms/ROIs continue to work
        return self.original_mouse_move(event)

    def _mouse_release(self, event):
        """
        :param event:
        :return:
        Disable painting, erasing, and dragging point actions and pass the event back to pyqtgraph.
        """
        # DEBUG:
        # print("_mouse_release")

        # self.interaction_state = None
        if self.mark_im is not None and self.mark_im.matches_event(event):
            self.marker_mode = 'idle'

        # pass event back to pyqtgraph for any further processing
        self.original_mouse_release(event)

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
                # Determine brush and pen colors based on marker state
                if marker['is_selected']:
                    if self._edit_mode:
                        marker_brush = self.temp_brush  # editing color - draggable
                        marker_pen = self.temp_pen
                    else:
                        marker_brush = self.selected_brush  # selected color
                        marker_pen = self.selected_pen
                else:
                    marker_brush = self.idle_brush  # idle color - not selected
                    marker_pen = self.idle_pen
                
                spots.append(
                    {
                        'pos': (plot_xy[0], plot_xy[1]), 'data': marker,
                        'brush': marker_brush,
                        'pen': marker_pen,
                    } )

            # FIXME: testing and debugging
            # print(f"spots: {spots}")

            self.scatter.setData(spots=spots)
        else:
            self.scatter.clear()
