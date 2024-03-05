# -*- coding: utf-8 -*-

import os

from PyQt5.QtWidgets import (QHBoxLayout, QFrame, QVBoxLayout, QLabel, QComboBox,
                             QLineEdit, QSlider, QSpacerItem, QSizePolicy)
from PyQt5 import QtCore
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import pyqtSignal
# from LMVolume import LMVolume
from image3D import Image3D
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
from matplotlib import pyplot as plt

import numpy as np

from toolbar import Toolbar
from enumerations import ViewDir


class DisplaySettingsWidget(QFrame):
    colormap_changed_signal = pyqtSignal(str, Image3D)  # Signal to be emitted when selection changes, colormap name, vol id
    range_changed_signal = pyqtSignal(list, Image3D)  # Signal to be emitted when selection changes, [lower, upper, vol id]
    transparency_changed_signal = pyqtSignal(int, Image3D)  # Signal to be emitted when selection changes, transparency value, vol id

    def __init__(self, parent, _id, vol=None):
        super().__init__()

        self.parent = parent

        # if the main window has more than one display settings widget, this id will help to distinguish them
        self.id = _id

        self.current_volume = vol

        # make a border around the whole widget
        self.setObjectName("display_settings_widget")
        self.setStyleSheet("QFrame#display_settings_widget{border: 1px solid #666;}")

        # set a fixed width for the widget
        self.setMinimumWidth(400)
        self.setMaximumWidth(400)

        vertical_layout = QVBoxLayout()

        # colormap selection widgets
        # ==============================================================================================================
        colormap_label = QLabel()
        colormap_label.setText("Colormap")
        vertical_layout.addWidget(colormap_label)
        self.colormap_combo = QComboBox()
        self.populate_combo_with_icons()
        self.colormap_combo.activated[str].connect(self.on_combo_activated)
        vertical_layout.addWidget(self.colormap_combo)
        # spacer_item = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        # vertical_layout.addItem(spacer_item)

        # transparency widgets
        # ==============================================================================================================
        transparency_label_edit_layout = QHBoxLayout()
        transparency_label = QLabel()
        transparency_label.setText("Transparency")
        transparency_label_edit_layout.addWidget(transparency_label)
        spacer_item_1 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        transparency_label_edit_layout.addItem(spacer_item_1)
        self.transparency_edit = QLineEdit()
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.transparency_edit.sizePolicy().hasHeightForWidth())
        self.transparency_edit.setSizePolicy(sizePolicy)
        self.transparency_edit.setMinimumSize(QtCore.QSize(50, 24))
        self.transparency_edit.setMaximumSize(QtCore.QSize(50, 24))
        self.transparency_edit.setText(str(100))
        self.transparency_edit.returnPressed.connect(self.on_transparency_edit_changed)
        transparency_label_edit_layout.addWidget(self.transparency_edit)
        percent_label = QLabel()
        percent_label.setText("%")
        transparency_label_edit_layout.addWidget(percent_label)
        vertical_layout.addLayout(transparency_label_edit_layout)
        self.transparency_slider = QSlider()
        self.transparency_slider.setOrientation(QtCore.Qt.Horizontal)
        self.transparency_slider.setMinimum(0)
        self.transparency_slider.setMaximum(100)
        self.transparency_slider.setValue(100)
        self.transparency_slider.valueChanged.connect(self.on_transparency_slider_changed)
        vertical_layout.addWidget(self.transparency_slider)
        # spacer_item_2 = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        # vertical_layout.addItem(spacer_item_2)

        # histogram widgets
        # ==============================================================================================================
        distribution_label = QLabel()
        distribution_label.setText("Display Range")
        vertical_layout.addWidget(distribution_label)
        histogram_vertical_layout = QVBoxLayout()
        vertical_layout.addLayout(histogram_vertical_layout)

        # the histogram plot
        self.fig = Figure()
        self.ax = self.fig.add_axes([0.05, 0.2, 0.95, 0.6])
        self.ax.set_facecolor("black")
        self.canvas = FigureCanvas(self.fig)
        self.lower_limit_line = None
        self.upper_limit_line = None
        self.canvas.setMinimumHeight(100)
        histogram_vertical_layout.addWidget(self.canvas)
        # spacer_item_3 = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        # vertical_layout.addItem(spacer_item_3)

        # labels
        range_labels_layout = QHBoxLayout()
        min_display_label = QLabel()
        min_display_label.setText("Min")
        range_labels_layout.addWidget(min_display_label)
        spacer_item_4 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        range_labels_layout.addItem(spacer_item_4)
        max_display_label = QLabel()
        max_display_label.setText("Max")
        range_labels_layout.addWidget(max_display_label)
        vertical_layout.addLayout(range_labels_layout)

        # min edits and sliders
        range_slider_edits_layout = QHBoxLayout()
        self.min_display_edit = QLineEdit()
        self.min_display_edit.setSizePolicy(sizePolicy)
        self.min_display_edit.setMinimumSize(QtCore.QSize(50, 24))
        self.min_display_edit.setMaximumSize(QtCore.QSize(50, 24))
        self.min_display_edit.setText(str(0))
        self.min_display_edit.returnPressed.connect(self.on_min_edit_changed)
        range_slider_edits_layout.addWidget(self.min_display_edit)
        self.lower_limit_slider = QSlider()
        self.lower_limit_slider.setOrientation(QtCore.Qt.Horizontal)
        self.lower_limit_slider.valueChanged.connect(self.on_min_slider_changed)
        self.lower_limit_slider.setMinimum(0)
        self.lower_limit_slider.setMaximum(1)
        range_slider_edits_layout.addWidget(self.lower_limit_slider)
        # spacer_item_4 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        # range_slider_edits_layout.addItem(spacer_item_4)

        # max edits and sliders
        self.upper_limit_slider = QSlider()
        self.upper_limit_slider.setOrientation(QtCore.Qt.Horizontal)
        self.upper_limit_slider.valueChanged.connect(self.on_max_slider_changed)
        self.upper_limit_slider.setMinimum(0)
        self.upper_limit_slider.setMaximum(1)
        range_slider_edits_layout.addWidget(self.upper_limit_slider)
        self.max_display_edit = QLineEdit()
        self.max_display_edit.setSizePolicy(sizePolicy)
        self.max_display_edit.setMinimumSize(QtCore.QSize(50, 24))
        self.max_display_edit.setMaximumSize(QtCore.QSize(50, 24))
        self.max_display_edit.setText(str(1))
        self.max_display_edit.returnPressed.connect(self.on_max_edit_changed)

        range_slider_edits_layout.addWidget(self.max_display_edit)
        # self.max_display_edit_2 = QtWidgets.QLabel(Form)
        # self.max_display_edit_2.setObjectName("max_display_edit_2")
        # self.range_slider_edits_layout.addWidget(self.max_display_edit_2)
        vertical_layout.addLayout(range_slider_edits_layout)

        self.setLayout(vertical_layout)

    def set_volume(self, vol):

        self.current_volume = vol

        if self.current_volume is None:
            # TODO: clear the widgets
            return

        self.lower_limit_slider.setMinimum(self.current_volume.data_min)
        self.lower_limit_slider.setMaximum(self.current_volume.data_max)
        self.lower_limit_slider.setValue(self.current_volume.display_min)
        self.min_display_edit.setText(str(self.current_volume.display_min))

        self.upper_limit_slider.setMinimum(self.current_volume.data_min)
        self.upper_limit_slider.setMaximum(self.current_volume.data_max)
        self.upper_limit_slider.setValue(self.current_volume.display_max)
        self.max_display_edit.setText(str(self.current_volume.display_max))

        self.plot_histogram()

    # def create_colormap_icon(self, cmap_name):
    #     cmap = matplotlib.colormaps[cmap_name]
    #
    #     # create an array of discrete values
    #     num_colors = 10
    #     discrete_values = np.linspace(0, 1, num_colors)
    #
    #     fig = Figure()
    #     ax = fig.add_axes([0, 0, 1, 1])
    #     for i, value in enumerate(discrete_values):
    #         ax.add_patch(plt.Rectangle((i / num_colors, 0), 1 / num_colors, 1, color=cmap(value)))
    #     ax.set_xlim(0, 1)
    #     ax.set_ylim(0, 1)
    #     ax.set_aspect('auto')
    #     ax.set_axis_off()
    #
    #     icon_path = f"{cmap_name}_icon.png"
    #     fig.savefig(icon_path)
    #     plt.close(fig)
    #     return icon_path

    def populate_combo_with_icons(self):
        for selected_name in ['Grays', 'Blues', 'Greens', 'Reversed Grays', 'Seismic', 'Magma',
                              'Viridis', 'Cividis', 'Twilight', 'Turbo', 'Rainbow', 'Accent', 'Labels']:
            if selected_name == "Grays":
                cmap_name = "gray"
            elif selected_name == "Reversed Grays":
                cmap_name = "Greys"
            elif selected_name == "Seismic":
                cmap_name = "seismic"
            elif selected_name == "Magma":
                selected_name = "magma"
            elif selected_name == "Viridis":
                cmap_name = "viridis"
            elif selected_name == "Cividis":
                cmap_name = "cividis"
            elif selected_name == "Twilight":
                cmap_name = "twilight"
            elif selected_name == "Turbo":
                cmap_name = "turbo"
            elif selected_name == "Rainbow":
                cmap_name = "rainbow"
            elif selected_name == "Labels":
                cmap_name = "tab10"
            else:
                cmap_name = selected_name
            # icon_path = self.create_colormap_icon(cmap_name)
            cmap_icon = f"{cmap_name}_icon.png"
            icon_path = os.path.join("..\\ui", cmap_icon)
            self.colormap_combo.addItem(QIcon(icon_path), selected_name)

    def on_combo_activated(self):
        if self.current_volume is None:
            return

        selected_name = self.colormap_combo.currentText()
        if selected_name == "Grays":
            cmap_name = "gray"
        elif selected_name == "Reversed Grays":
            cmap_name = "Greys"
        elif selected_name == "Seismic":
            cmap_name = "seismic"
        elif selected_name == "Magma":
            selected_name = "magma"
        elif selected_name == "Viridis":
            cmap_name = "viridis"
        elif selected_name == "Cividis":
            cmap_name = "cividis"
        elif selected_name == "Twilight":
            cmap_name = "twilight"
        elif selected_name == "Turbo":
            cmap_name = "turbo"
        elif selected_name == "Rainbow":
            cmap_name = "rainbow"
        elif selected_name == "Labels":
                cmap_name = "tab10"
        else:
            cmap_name = selected_name
        self.colormap_changed_signal.emit(cmap_name, self.current_volume)

    def on_transparency_slider_changed(self):
        if self.current_volume is None:
            return
        value = self.transparency_slider.value()
        self.transparency_edit.setText(str(value))
        self.current_volume.alpha = value / 100
        self.transparency_changed_signal.emit(value, self.current_volume)

    def on_transparency_edit_changed(self):
        if self.current_volume is None:
            return
        value = int(self.transparency_edit.text())
        if value < 0:
            value = 0
        if value > 100:
            value = 100
        self.transparency_slider.setValue(value)

    def plot_histogram(self):
        """ Whenever a new current volume is set, this function is called to update the histogram plot. """
        self.ax.cla()
        if self.current_volume is not None:
            # plot_histogram the slider ranges
            self.lower_limit_slider.setMinimum(self.current_volume.data_min)
            self.lower_limit_slider.setMaximum(self.current_volume.data_max)
            self.lower_limit_slider.setValue(self.current_volume.display_min)
            self.upper_limit_slider.setMinimum(self.current_volume.data_min)
            self.upper_limit_slider.setMaximum(self.current_volume.data_max)
            self.upper_limit_slider.setValue(self.current_volume.display_max)
            # plot_histogram the histogram
            self.ax.hist(self.current_volume.data.flatten(),
                         range=(self.current_volume.data_min, self.current_volume.data_max),
                         bins=20, color='white')
            # create vertical lines on the histogram to show the current threshold values
            self.lower_limit_line = self.ax.axvline(self.current_volume.display_min, color='magenta')
            self.upper_limit_line = self.ax.axvline(self.current_volume.display_max, color='blue')

            # self.ax.set_xlabel('Intensity', fontsize=6)
            # self.ax.set_ylabel('Frequency', fontsize=6)
            self.ax.set_title("", fontsize=6)
            self.ax.yaxis.offsetText.set_fontsize(6)
            self.ax.tick_params(axis='both', which='major', labelsize=6, labelcolor='black')
            self.ax.yaxis.offsetText.set_fontsize(6)

            self.canvas.draw()

    def on_min_slider_changed(self):
        if self.current_volume is None or self.lower_limit_line is None or self.upper_limit_line is None:
            return

        lower_val = self.lower_limit_slider.value()
        upper_val = self.upper_limit_slider.value()
        if lower_val >= upper_val:
            if (lower_val + 1) <= self.upper_limit_slider.maximum():
                upper_val = lower_val + 1
                self.upper_limit_slider.setValue(upper_val)
            else:
                upper_val = self.upper_limit_slider.maximum()
                lower_val = upper_val - 1
                self.lower_limit_slider.setValue(lower_val)
                self.upper_limit_slider.setValue(upper_val)

        # update the position of the vertical lines on the histogram
        self.lower_limit_line.set_xdata([lower_val, lower_val])
        self.upper_limit_line.set_xdata([upper_val, upper_val])
        self.canvas.draw()

        # update the min and max edits
        self.min_display_edit.setText(str(lower_val))
        self.max_display_edit.setText(str(upper_val))

        self.range_changed_signal.emit([lower_val, upper_val], self.current_volume)

    def on_max_slider_changed(self):
        if self.current_volume is None or self.lower_limit_line is None or self.upper_limit_line is None:
            return

        lower_val = self.lower_limit_slider.value()
        upper_val = self.upper_limit_slider.value()
        print("lower_val: ", lower_val, "upper_val: ", upper_val)
        print("self.upper_limit_slider.minimum(): ", self.upper_limit_slider.minimum())
        print("self.upper_limit_slider.maximum(): ", self.upper_limit_slider.maximum())
        print("self.lower_limit_slider.minimum(): ", self.lower_limit_slider.minimum())
        print("self.lower_limit_slider.maximum(): ", self.lower_limit_slider.maximum())
        if upper_val <= lower_val:
            if (upper_val-1) >= self.lower_limit_slider.minimum():
                lower_val = upper_val - 1
                self.lower_limit_slider.setValue(lower_val)
            else:
                lower_val = self.lower_limit_slider.minimum()
                upper_val = lower_val + 1
                self.lower_limit_slider.setValue(lower_val)
                self.upper_limit_slider.setValue(upper_val)

        # update the position of the vertical lines on the histogram
        self.lower_limit_line.set_xdata([lower_val, lower_val])
        self.upper_limit_line.set_xdata([upper_val, upper_val])
        self.canvas.draw()

        # update the min and max edits
        self.min_display_edit.setText(str(lower_val))
        self.max_display_edit.setText(str(upper_val))

        self.range_changed_signal.emit([lower_val, upper_val], self.current_volume)

    def on_min_edit_changed(self):
        lower_val = int(self.min_display_edit.text())
        upper_val = int(self.upper_limit_slider.value())

        if lower_val < self.lower_limit_slider.minimum():
            lower_val = self.lower_limit_slider.minimum()
        elif lower_val > self.lower_limit_slider.maximum():
            lower_val = self.lower_limit_slider.maximum()
        if lower_val >= upper_val:
            if (lower_val + 1) <= self.upper_limit_slider.maximum():
                upper_val = lower_val + 1
            else:
                upper_val = self.upper_limit_slider.maximum()
                lower_val = upper_val - 1

            self.upper_limit_slider.valueChanged.disconnect(self.on_max_slider_changed)
            self.upper_limit_slider.setValue(upper_val)
            self.upper_limit_slider.valueChanged.connect(self.on_max_slider_changed)

        self.lower_limit_slider.setValue(lower_val)

    def on_max_edit_changed(self):
        upper_val = int(self.max_display_edit.text())
        lower_val = int(self.lower_limit_slider.value())

        if upper_val < self.upper_limit_slider.minimum():
            upper_val = self.upper_limit_slider.minimum()
        elif upper_val > self.upper_limit_slider.maximum():
            upper_val = self.upper_limit_slider.maximum()
        if upper_val <= lower_val:
            if (upper_val-1) >= self.lower_limit_slider.minimum():
                lower_val = upper_val - 1
            else:
                lower_val = self.lower_limit_slider.minimum()
                upper_val = lower_val + 1
            self.lower_limit_slider.setValue(lower_val)

        self.upper_limit_slider.setValue(upper_val)