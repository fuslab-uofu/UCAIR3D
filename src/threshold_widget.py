"""
threshold_widget.py
Author: Michelle Kline
UCAIR, Department of Radiology and Imaging Sciences, University of Utah
2024

This file contains the ThresholdWidget class, which is a QWidget that contains the display settings for the 3D image.
"""
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, pyqtSignal

from image3D import Image3D
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.colors as mcolors
from matplotlib import pyplot as plt

from Ui_threshold_widget import Ui_ThresholdWidget
from superqt import QRangeSlider


class ThresholdWidget(QtWidgets.QWidget, Ui_ThresholdWidget):
    range_changed_signal = pyqtSignal(tuple, Image3D)  # signal emitted when range changes (min, max, volume)

    def __init__(self):
        super().__init__()

        self.current_volume = None
        # self.dtype = _dtype
        # self.parent = _parent

        self.ui = Ui_ThresholdWidget()
        self.ui.setupUi(self)

        # the histogram plot
        self.fig = Figure()
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_facecolor("black")
        self.canvas = FigureCanvas(self.fig)
        self.lower_limit_line = None
        self.upper_limit_line = None
        self.canvas.setMinimumHeight(100)
        self.ui.plot_frame.layout().addWidget(self.canvas)

        # the range slider
        self.slider = QRangeSlider(Qt.Horizontal, self)
        # this is a workaround to make the slider look like the rest of the app
        self.slider.setStyleSheet("""QSlider {
                                            background-color: none;
                                        }
                                        QSlider::add-page:vertical {
                                            background: none;
                                            border: none;
                                        }
                                        QRangeSlider {
                                            qproperty-barColor: #9FCBFF;
                                        }""")
        self.slider.setMaximumWidth(400)
        self.ui.verticalLayout.insertWidget(2, self.slider)
        self.slider.valueChanged.connect(self.on_slider_changed)

        # the min and max edits
        self.ui.min_display_edit.returnPressed.connect(self.on_min_edit_changed)
        self.ui.max_display_edit.returnPressed.connect(self.on_max_edit_changed)

    def refresh(self):
        if self.current_volume is None:
            return

        # update the histogram plot
        self.plot_histogram()

        # update the min and max edits
        self.ui.min_display_edit.setText(str(self.current_volume.display_min))
        self.ui.max_display_edit.setText(str(self.current_volume.display_max))

        # update the position of the vertical lines on the histogram
        self.lower_limit_line.set_xdata([self.current_volume.display_min, self.current_volume.display_min])
        self.upper_limit_line.set_xdata([self.current_volume.display_max, self.current_volume.display_max])
        self.canvas.draw()

        # update the min and max sliders
        self.slider.setValue((self.current_volume.display_min, self.current_volume.display_max))

    def plot_histogram(self):
        """ Whenever a new current volume is set, this function is called to update the histogram plot. """
        self.ax.cla()
        if self.current_volume is not None:
            # plot_histogram the slider ranges

            # plot_histogram the histogram
            self.ax.hist(self.current_volume.data.flatten(),
                         range=(self.current_volume.data_min, self.current_volume.data_max), color='white', bins=50)  # bins=20
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

    def set_volume(self, vol):

        self.current_volume = vol

        if self.current_volume is None:
            # TODO: clear the widgets
            return

        self.slider.setMinimum(self.current_volume.data_min)
        self.slider.setMaximum(self.current_volume.data_max)
        self.slider.setValue((self.current_volume.display_min, self.current_volume.display_max))

        self.refresh()

    def on_slider_changed(self, vals):
        if self.current_volume is None or self.lower_limit_line is None or self.upper_limit_line is None:
            return

        lower_val = vals[0]
        upper_val = vals[1]

        # update the position of the vertical lines on the histogram
        self.lower_limit_line.set_xdata([lower_val, lower_val])
        self.upper_limit_line.set_xdata([upper_val, upper_val])
        self.canvas.draw()

        # update the min and max edits
        self.ui.min_display_edit.setText(str(lower_val))
        self.ui.max_display_edit.setText(str(upper_val))

        self.range_changed_signal.emit((lower_val, upper_val), self.current_volume)

    def on_min_edit_changed(self):
        lower_val = int(self.ui.min_display_edit.text())
        upper_val = int(self.ui.max_display_edit.text())
        # upper_val = int(self.ui.upper_limit_slider.value())

        if lower_val < self.slider.minimum():
            lower_val = self.slider.minimum()
        elif lower_val >= upper_val:
            if (lower_val + 1) <= self.slider.maximum():
                upper_val = lower_val + 1
            else:
                upper_val = self.slider.maximum()
                lower_val = upper_val - 1

            # self.upper_limit_slider.valueChanged.disconnect(self.on_max_slider_changed)
            # self.slider.setValue(upper_val)
            # self.upper_limit_slider.valueChanged.connect(self.on_max_slider_changed)

        self.slider.setValue((lower_val, upper_val))
        self.range_changed_signal.emit((lower_val, upper_val), self.current_volume)

    def on_max_edit_changed(self):
        upper_val = int(self.ui.max_display_edit.text())
        lower_val = int(self.ui.min_display_edit.text())

        if upper_val > self.slider.maximum():
            upper_val = self.slider.maximum()
        elif upper_val <= lower_val:
            if (upper_val-1) >= self.slider.minimum():
                lower_val = upper_val - 1
            else:
                lower_val = self.slider.minimum()
                upper_val = lower_val + 1

        self.slider.setValue((lower_val, upper_val))
        self.range_changed_signal.emit((lower_val, upper_val), self.current_volume)
