""" viewport.py
    Author: Michelle Kline

    2024
    Michelle Kline, Department of Radiology and Imaging Sciences, University of Utah
"""

from PyQt5.QtWidgets import QVBoxLayout, QFrame, QLabel
from PyQt5 import QtCore
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
import numpy as np
from toolbar import Toolbar
from enumerations import ViewDir
from interaction_method import InteractionMethod


class Viewport(QFrame):
    """ A Viewport is a collection of Matplotlib and PyQt widgets for displaying 2D slices of 3D radiology images.
    A Viewport allows the user to interactively scroll through slices of an image as well as make adjustments such
    as windowing, zooming and panning. A Viewport also interactively displays image and patient coordinates as the
    cursor is moved over the plot.

    Major attributes
    ----------------
    each Viewport includes:
     - a Matplotlib canvas, figure, and axes
     - view_dir: describes whether this viewport is displaying an axial, sagittal, or coronal view of the volume.
        (see enum ViewDir {AX, SAG, COR})
     - volume_stack: a list of Image3D objects that are displayed in this viewport. Number of volumes allowed is
        determined by num_vols
     - slice_stack: a list of 2D slices of the Image3D objects in volume_stack.

    Major methods
    -------------
    - on_mouse_press: slot for the signal sent when the user clicks anywhere in a viewport.
    - on_mouse_move: slot for the signal sent when the user moves the mouse over a viewport.
    - on_mouse_release: slot for the signal sent when the user releases the mouse button.
    - on_scroll: slot for the signal sent when the user scrolls the mouse wheel over a viewport.
    """

    def __init__(self, parent, id, view_dir_, num_vols, coords_outside_, zoom_method_, pan_method_):
        super(Viewport, self).__init__(parent)

        # identifying info
        self.parent = parent  # main window
        self.id = id
        self.view_dir = view_dir_.dir  # ViewDir.AX, ViewDir.SAG, ViewDir.COR

        # list of references to the volume(s) being displayed in viewport
        self.volume_stack = [None] * num_vols
        # MMK FIXME: maybe no need to store the slice_stack, just the layer_stack
        # the actual 2D slice of data
        self.slice_stack = [None] * num_vols

        # list of Matplotlib imshow plot objects being displayed in the viewport
        self.layer_stack = [None] * num_vols

        # for controlling slice scrolling
        self.current_display_index = 0  # in this context, can refer to row slice, col slice, or slice slice (lol )
        self.max_display_index = 0

        # create a Matplotlib figure and canvas
        self.fig = Figure()
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.fig.subplots_adjust(bottom=0.25)
        self.fig.set_facecolor("black")
        self.ax.set_facecolor("black")

        # hide ticks and tick labels
        self.ax.axis('off')
        self.canvas = FigureCanvas(self.fig)

        self.main_layout = QVBoxLayout(self)
        # main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.addWidget(self.canvas)

        self.coords_outside = coords_outside_
        if self.coords_outside:
            # create a text box to display coordinates outisde the plot
            self.coords_label = QLabel()
            self.coords_label.setMinimumWidth(200)
            self.coords_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.main_layout.addWidget(self.coords_label)
        else:
            self.coords_obj = self.fig.text(0.55, 0.04, '', fontsize=8, color='white')

        self.setLayout(self.main_layout)
        self.setStyleSheet("QFrame#ViewPort {border: 1px solid gray;}")
        # coordinates and cursor data text
        self.direction_chars = view_dir_.chars
        self.voxel_coords = None
        self.cursor_data = []
        self.patient_coords = None
        self.image_coords_string = ""
        self.patient_coords_string = ""
        self.fig.text(0.50, 0.96, self.direction_chars[0], fontsize=8, color='white')
        self.fig.text(0.96, 0.50, self.direction_chars[1], fontsize=8, color='white')
        self.fig.text(0.50, 0.04, self.direction_chars[2], fontsize=8, color='white')
        self.fig.text(0.04, 0.50, self.direction_chars[3], fontsize=8, color='white')

        self.mouse_x = 0
        self.mouse_y = 0

        # this essentially is activating the pan or zoom actions if the mouse button has been pressed.
        self.status = "idle"
        self.zoom_method = zoom_method_
        self.pan_method = pan_method_

        # for syncronizing and resetting zoom and pan
        self.initial_extent = None

        # mouse motion signal for this LMViewport -----------------------------------------
        self.cid_motion_notify = self.canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.cid_button_press = self.canvas.mpl_connect('button_press_event', self.on_mouse_press)
        self.cid_release = self.canvas.mpl_connect('button_release_event', self.on_mouse_release)
        self.cid_scroll = self.canvas.mpl_connect('scroll_event', self.on_scroll)

    def update_volume_stack(self, new_volume, stack_position):
        """ Update the volume stack with a new volume in the specified position. """
        self.volume_stack[stack_position] = new_volume

        if new_volume is not None:
            # for controlling slice scrolling
            if self.view_dir == ViewDir.AX.dir:
                self.max_display_index = new_volume.num_slices
            elif self.view_dir == ViewDir.SAG.dir:
                self.max_display_index = new_volume.num_cols
            else:  # "COR"
                self.max_display_index = new_volume.num_rows

            # for convenience, jump to middle slice
            self.current_display_index = (self.max_display_index // 2)

        self.mouse_x = 0
        self.mouse_y = 0

        self.refresh_plot()

    def goto_slice(self, slice_num):
        """ Display specified slice of Image3D. """
        self.current_display_index = int(slice_num)
        self.refresh_plot()

    def refresh_plot(self, extent=None):
        """ This is called each time anything about the viewport is changed (current slice, colormap, etc.).
        """
        # clear the plot each time, so that plot objects don't accumulate
        self.ax.cla()

        for ind, vol in enumerate(self.volume_stack):
            if vol is not None:
                # TODO: try catch for None returned from get_slice
                self.slice_stack[ind] = vol.get_slice(self.view_dir, self.current_display_index)  # FIXME: need to store?

                # to account for non-isotropic voxel dimensions, set aspect ratio
                if self.view_dir == ViewDir.AX.dir:
                    ratio = vol.dy / vol.dx
                elif self.view_dir == ViewDir.COR.dir:
                    ratio = vol.dz / vol.dx
                else:  # "SAG"
                    ratio = vol.dz / vol.dy

                # need to transpose to make the first axes left-right and second axes up-down
                self.layer_stack[ind] = self.ax.imshow(self.slice_stack[ind].T, origin="lower", aspect=ratio,
                                                       cmap=vol.colormap, alpha=vol.alpha, vmin=vol.display_min,
                                                       vmax=vol.display_max, interpolation=vol.interpolation)
                # this makes values outside the range of the colormap transparent. otherwise, they are the min or max
                # color of the colormap
                if vol.clipping:
                    self.layer_stack[ind].cmap.set_over((0, 0, 0, 0))
                    self.layer_stack[ind].cmap.set_under((0, 0, 0, 0))

                self.layer_stack[ind].format_cursor_data = lambda z: f'{int(z):d}'

                # set extent
                # print(self.initial_extent)
                if extent is not None:
                    self.ax.set_position(extent)

                # save initial plot extent
                if self.initial_extent is None:
                    self.initial_extent = self.ax.get_position()

                # clean up the plot
                self.ax.set_xticklabels([])
                self.ax.set_yticklabels([])
                self.ax.set_xticks([])
                self.ax.set_yticks([])
                self.ax.set_axis_off()

                # cursor data is the actual value of the voxel that the cursor is currently over.
                # the matplotlib navigation toolbar displays this by default. format it to be integer
                # if self.layer_stack[[ind] is not None:
                #     self.layer_stack[ind].format_cursor_data = lambda z: f'{int(z):d}'

                self.canvas.draw()  # necessary

    def sync_extents(self, factor):
        self.parent.sync_extents(self.id, factor)

    def on_mouse_press(self, event):
        """ Slot for the signal sent when the user clicks anywhere in a viewport.
            Handles left, right, or middle (wheel) mouse button press,
            and shift, control, or alt modifiers.
        """
        # no slices currently displayed, do nothing
        if all(obj is None for obj in self.layer_stack):
            return

        self.mouse_x = event.x
        self.mouse_y = event.y
        button = event.button.name
        modifiers = event.modifiers

        # are we zooming?
        if self.zoom_method.button == button:
            if self.zoom_method.modifier:
                if self.zoom_method.modifier in modifiers:
                    self.status = "zooming"
                    return
            else:
                if len(modifiers) == 0:
                    self.status = "zooming"
                    return

        # are we panning?
        if self.pan_method.button == button:
            if self.pan_method.modifier:
                if self.pan_method.modifier in modifiers:
                    self.status = "panning"
                    return
            else:
                if len(modifiers) == 0:
                    self.status = "panning"
                    return

    def on_mouse_move(self, event):
        """ Slot for the signal sent when the user moves the mouse over a viewport.
            Resulting action depends on current viewport status (zooming, panning, idle).
            If idle, the coordinates of the cursor are displayed.
            In addition:
              if zooming, the axes are zoomed in or out based on mouse movement up/down
              if panning, the axes are moved based on mouse movement up/down/left/right
        """
        if all(obj is None for obj in self.layer_stack):
            # no slices currently displayed, do nothing
            return

        if self.status == "panning":
            if event.inaxes is None:
                # the cursor is outside the axes
                return
            fig_width, fig_height = self.fig.get_size_inches() * self.fig.dpi
            dx = (event.x - self.mouse_x) / fig_width
            dy = (event.y - self.mouse_y) / fig_height
            self.mouse_x = event.x
            self.mouse_y = event.y
            # get the current axes position
            ax_pos = self.ax.get_position()
            # update the new axes position
            new_pos = [ax_pos.x0 + dx, ax_pos.y0 + dy, ax_pos.width, ax_pos.height]
            # set the new axes position
            self.ax.set_position(new_pos)
            self.canvas.draw()  # necessary
        elif self.status == "zooming":
            sensitivity = 0.01
            dy = sensitivity * (event.y - self.mouse_y)
            if dy != 0:
                zoom_factor = 1.0 - 0.1 * abs(dy) if dy < 0 else 1.0 / (1.0 - 0.1 * abs(dy))
            else:
                zoom_factor = 1.0  # no zoom

            # get the current axes position
            ax_pos = self.ax.get_position()
            # calculate the change in size based on the zoom factor
            dx_axes = (ax_pos.width - ax_pos.width / zoom_factor) / 2
            dy_axes = (ax_pos.height - ax_pos.height / zoom_factor) / 2
            # update the new axes position
            new_pos = [ax_pos.x0 + dx_axes, ax_pos.y0 + dy_axes, ax_pos.width / zoom_factor,
                       ax_pos.height / zoom_factor]
            # set the new axes position
            self.ax.set_position(new_pos)

            self.canvas.draw()  # necessary

            self.parent.sync_extents(self.id, zoom_factor)
        else:
            if event.inaxes is None:
                # the cursor is outside the axes
                if self.coords_outside:
                    self.coords_label.setText('')
                else:
                    self.coords_obj.set_text('')

                self.canvas.draw()  # necessary
                return

            vol_indices = [index for index, item in enumerate(self.volume_stack) if item is not None]
            if len(vol_indices) == 0:
                return

            # NOTES ABOUT COORDINATES:
            # - The event xdata and ydata of a matplotlib plot are expressed as [col, row] ("plot_col"
            #   and "plot_row"), with the origin in the LOWER left.
            # get the image coordinates of the cursor
            cursor_plot_col, cursor_plot_row = int(event.xdata), int(event.ydata)
            if cursor_plot_col is None or cursor_plot_row is None:
                return

            # extent of the 2D image on the screen
            image_width, image_height = self.slice_stack[vol_indices[0]].shape

            # get the voxel coordinates of the image volume and corresponding patient coordinates of that voxel
            voxel_ijk = self.volume_stack[vol_indices[0]].screenxy_to_imageijk(self.view_dir, cursor_plot_col,
                                                                  cursor_plot_row, self.current_display_index)
            if voxel_ijk is None:
                return

            self.voxel_coords = np.array([voxel_ijk[0], voxel_ijk[1], voxel_ijk[2], 1])
            # convert to patient coords
            self.patient_coords = np.dot(self.volume_stack[vol_indices[0]].transform, self.voxel_coords)
            # the value of the voxel
            self.cursor_data = []
            if 0 <= cursor_plot_col < image_width and 0 <= cursor_plot_row < image_height:
                for ind in vol_indices:
                    if self.slice_stack[ind] is not None:
                        self.cursor_data.append(int(self.slice_stack[ind][cursor_plot_col, cursor_plot_row]))

            self.display_coords()

    def on_mouse_release(self, event):
        """ Captures the event created when the user releases the mouse button. """
        self.status = "idle"

    def on_scroll(self, event):
        """
        Parameters
        ----------
        event

        Returns
        -------
        """
        # no slices currently displayed, do nothing
        if all(obj is None for obj in self.layer_stack):
            return

        if event.button == "up":
            self.current_display_index += 1
        elif event.button == "down":
            self.current_display_index -= 1
        self.current_display_index = np.clip(self.current_display_index, 0, self.max_display_index - 1)

        self.refresh_plot()
        # print("display index: " + str(self.current_display_index))

        if self.voxel_coords is not None:
            if self.view_dir == ViewDir.AX.dir:
                # displaying z slice - AXIAL
                self.voxel_coords[2] = self.current_display_index
            elif self.view_dir == ViewDir.SAG.dir:
                # displaying zy slice - SAGITTAL
                self.voxel_coords[0] = self.current_display_index
            else:  # self.view_dir == "COR"
                # displaying xz slice -  CORONAL
                self.voxel_coords[1] = self.current_display_index
            # convert to patient coords
            vol_indices = [index for index, item in enumerate(self.volume_stack) if item is not None]
            if len(vol_indices) == 0:
                return
            self.patient_coords = np.dot(self.volume_stack[vol_indices[0]].transform, self.voxel_coords)

            self.display_coords()

    def display_coords(self):
        # TODO: different display_convention(s)
        if self.parent.display_convention == "RAS":
            self.image_coords_string = (f'x {self.voxel_coords[0]:>3} '
                                        f'y {self.voxel_coords[1]:>3} '
                                        f'z {self.voxel_coords[2]:>3}')
            pat = np.empty((1, 3))
            if self.patient_coords[0] < 0:
                lr = "L"
                pat[0, 0] = self.patient_coords[0] * -1
            else:
                lr = "R"
                pat[0, 0] = self.patient_coords[0]
            if self.patient_coords[1] < 0:
                ap = "P"
                pat[0, 1] = self.patient_coords[1] * -1
            else:
                ap = "A"
                pat[0, 1] = self.patient_coords[1]
            if self.patient_coords[2] < 0:
                si = "I"
                pat[0, 2] = self.patient_coords[2] * -1
            else:
                si = "S"
                pat[0, 2] = self.patient_coords[2]
            self.patient_coords_string = f'{lr}{pat[0, 0]:>5.1f} {ap}{pat[0, 1]:>5.1f} {si}{pat[0, 2]:>5.1f}'

        if len(self.cursor_data) == 0:
            cursor_data_str = ""
        else:
            cursor_data_str = str(self.cursor_data)

        coord_string = (
                self.image_coords_string + "   " + self.patient_coords_string + "  " + cursor_data_str)
        if self.coords_outside:
            self.coords_label.setText(coord_string)
        else:
            self.coords_obj.set_text(coord_string)

        self.canvas.draw()  # necessary
