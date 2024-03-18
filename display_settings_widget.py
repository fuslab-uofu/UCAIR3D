"""
display_settings_widget.py
Author: Michelle Kline
UCAIR, Department of Radiology and Imaging Sciences, University of Utah
2024

This file contains the DisplaySettins class, which is a QFrame that contains display settings widgets for a 3D image.
"""
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QSlider

from image3D import Image3D

from threshold_widget import ThresholdWidget
from cmap import Colormap
from superqt import QColormapComboBox


class DisplaySettingsWidget(QtWidgets.QFrame):
    display_settings_changed_signal = pyqtSignal(Image3D)  # signal emitted when the display settings change

    def __init__(self):
        super().__init__()

        # display settings widget is connected to a volume so that it can look at the volume's data and create
        # a histogram, and the volume's data type to determine if it should use a whole number or floating point slider
        # for the threshold widget
        self.current_volume = None

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        # the colormap selection combo box
        self.colormap_combo = QColormapComboBox()
        self.colormap_combo.addColormaps(["viridis", "plasma", "magma", "gray"])
        self.layout().addWidget(self.colormap_combo)
        self.colormap_combo.currentIndexChanged.connect(self.on_colormap_changed)

        # the transparency slider
        self.transparency_slider = QSlider()
        self.transparency_slider.setOrientation(QtCore.Qt.Horizontal)
        self.transparency_slider.setMinimum(0)
        self.transparency_slider.setMaximum(100)
        self.transparency_slider.setValue(100)
        self.transparency_slider.valueChanged.connect(self.on_transparency_slider_changed)
        self.layout().addWidget(self.transparency_slider)

        # the threshold widget - range of values to display (aka windowing, aka brightness/contrast)
        # whole number
        self.whole_thresholder = ThresholdWidget("whole")
        self.layout().addWidget(self.whole_thresholder)
        self.whole_thresholder.range_changed_signal.connect(self.handle_range_signal)
        self.whole_thresholder.clipping_changed_signal.connect(self.handle_clipping_signal)
        # floating point
        self.float_thresholder = ThresholdWidget("float")
        self.layout().addWidget(self.float_thresholder)
        self.float_thresholder.range_changed_signal.connect(self.handle_range_signal)
        self.float_thresholder.clipping_changed_signal.connect(self.handle_clipping_signal)
        # default is the whole number slider
        self.float_thresholder.setVisible(False)  # start with the float slider hidden
        self.thresholder = self.whole_thresholder

    def on_colormap_changed(self, idx):
        if self.current_volume is None:
            return
        self.current_volume.colormap = self.colormap_combo.currentText()
        self.display_settings_changed_signal.emit(self.current_volume)

    def on_transparency_slider_changed(self, val):
        if self.current_volume is None:
            return
        self.current_volume.alpha = val / 100
        self.display_settings_changed_signal.emit(self.current_volume)

    def handle_range_signal(self, vals):
        if self.current_volume is None:
            return
        self.current_volume.display_min = vals[0]
        self.current_volume.display_max = vals[1]
        self.display_settings_changed_signal.emit(self.current_volume)

    def handle_clipping_signal(self, val):
        if self.current_volume is None:
            return
        self.current_volume.clipping = val
        self.display_settings_changed_signal.emit(self.current_volume)

    def set_volume(self, vol):
        # this links a volume to the display settings widget
        self.current_volume = vol
        if self.current_volume is None:
            # TODO
            return

        if vol.data_type in ['uint16', 'int16', 'uint8', 'int8', 'uint32', 'int32', 'uint64', 'int64']:
            # this volume is whole numbers or binary - use the whole number slider
            self.thresholder = self.whole_thresholder
            self.whole_thresholder.setVisible(True)
            self.float_thresholder.setVisible(False)
        elif vol.data_type in ['float32', 'float64']:
            # this volume is floating point - use the floating point slider
            self.thresholder = self.float_thresholder
            self.whole_thresholder.setVisible(False)
            self.float_thresholder.setVisible(True)

        # update the display settings widgets with the volume's current settings
        self.colormap_combo.setCurrentText(vol.colormap)
        self.transparency_slider.setValue(int(vol.alpha * 100))
        self.thresholder.set_volume(vol)

    #
    # def on_slider_changed(self, vals):
    #     if self.current_volume is None or self.lower_limit_line is None or self.upper_limit_line is None:
    #         return
    #
    #     lower_val = vals[0]
    #     upper_val = vals[1]
    #
    #     # update the position of the vertical lines on the histogram
    #     self.lower_limit_line.set_xdata([lower_val, lower_val])
    #     self.upper_limit_line.set_xdata([upper_val, upper_val])
    #     self.canvas.draw()
    #
    #     # update the min and max edits
    #     self.ui.min_display_edit.setText(str(lower_val))
    #     self.ui.max_display_edit.setText(str(upper_val))
    #
    #     self.range_changed_signal.emit((lower_val, upper_val), self.current_volume)
    #
    # def on_min_edit_changed(self):
    #     lower_val = int(self.ui.min_display_edit.text())
    #     upper_val = int(self.ui.max_display_edit.text())
    #     # upper_val = int(self.ui.upper_limit_slider.value())
    #
    #     if lower_val < self.slider.minimum():
    #         lower_val = self.slider.minimum()
    #     elif lower_val >= upper_val:
    #         if (lower_val + 1) <= self.slider.maximum():
    #             upper_val = lower_val + 1
    #         else:
    #             upper_val = self.slider.maximum()
    #             lower_val = upper_val - 1
    #
    #         # self.upper_limit_slider.valueChanged.disconnect(self.on_max_slider_changed)
    #         # self.slider.setValue(upper_val)
    #         # self.upper_limit_slider.valueChanged.connect(self.on_max_slider_changed)
    #
    #     self.slider.setValue((lower_val, upper_val))
    #     self.range_changed_signal.emit((lower_val, upper_val), self.current_volume)
    #
    # def on_max_edit_changed(self):
    #     upper_val = int(self.ui.max_display_edit.text())
    #     lower_val = int(self.ui.min_display_edit.text())
    #
    #     if upper_val > self.slider.maximum():
    #         upper_val = self.slider.maximum()
    #     elif upper_val <= lower_val:
    #         if (upper_val-1) >= self.slider.minimum():
    #             lower_val = upper_val - 1
    #         else:
    #             lower_val = self.slider.minimum()
    #             upper_val = lower_val + 1
    #
    #     self.slider.setValue((lower_val, upper_val))
    #     self.range_changed_signal.emit((lower_val, upper_val), self.current_volume)
