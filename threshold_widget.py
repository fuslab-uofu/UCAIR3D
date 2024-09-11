"""
threshold_widget.py
Author: Michelle Kline
UCAIR, Department of Radiology and Imaging Sciences, University of Utah
2024

This file contains the ThresholdWidget class, which is a QWidget that contains the display settings for the 3D image.
"""
from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, pyqtSignal

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from Ui_threshold_widget import Ui_ThresholdWidget
from superqt import QRangeSlider, QDoubleRangeSlider


class ThresholdWidget(QtWidgets.QWidget, Ui_ThresholdWidget):
    range_changed_signal = pyqtSignal(tuple)  # signal emitted when range changes (min, max)
    clipping_changed_signal = pyqtSignal(bool)  # signal emitted when clipping changes

    def __init__(self, float_or_whole: str = "whole"):
        super().__init__()
        # float_or_whole is the type of QRangeSlider to create: range of whole numbers (QRangeSlider) or
        # range of floating point numbers (QDoubleRangeSlider)
        self.current_volume = None

        if float_or_whole not in ["whole", "float"]:
            # TODO: raise an error
            return

        self.float_or_whole = float_or_whole
        self.ui = Ui_ThresholdWidget()
        self.ui.setupUi(self)

        # the histogram plot
        self.fig = Figure()
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_facecolor("black")
        self.canvas = FigureCanvas(self.fig)
        self.lower_limit_line = None
        self.upper_limit_line = None
        # self.canvas.setMinimumHeight(100)
        self.ui.plot_frame.layout().addWidget(self.canvas)
        # MMKline FIXME: temp
        self.ui.plot_frame.layout().setContentsMargins(0, 0, 0, 0)

        self.ui.log_scale_checkbox.toggled.connect(self.on_log_scale_button_clicked)
        self.ui.clip_checkbox.toggled.connect(self.on_clip_button_clicked)

        # the range slider
        if float_or_whole == "float":
            self.slider = QDoubleRangeSlider(Qt.Horizontal, self)
        else:
            self.slider = QRangeSlider(Qt.Horizontal, self)
        # this is a workaround to make the slider look like the rest of the app
        self.slider.setStyleSheet("""
        QSlider {
            background-color: none;
        }
        QSlider::add-page:vertical {
            background: none;
            border: none;
        }
        QRangeSlider {
            qproperty-barColor: #005FB8;
        }""")
        self.ui.verticalLayout.insertWidget(2, self.slider)
        self.ui.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.slider.sliderReleased.connect(self.on_slider_released)
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
        if self.float_or_whole == 'float':
            lower_val = str(round(self.current_volume.display_min, 2))
            upper_val = str(round(self.current_volume.display_max, 2))
        else:
            lower_val = str(self.current_volume.display_min)
            upper_val = str(self.current_volume.display_max)
        self.ui.min_display_edit.setText(lower_val)
        self.ui.max_display_edit.setText(upper_val)

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

    def on_log_scale_button_clicked(self):
        if self.ui.log_scale_checkbox.isChecked():
            self.ax.set_yscale('log')
        else:
            self.ax.set_yscale('linear')
        self.canvas.draw()

    def set_volume(self, vol):

        self.current_volume = vol

        if self.current_volume is None:
            # TODO: clear the widgets
            return

        self.slider.blockSignals(True)
        self.slider.setMinimum(self.current_volume.data_min)
        self.slider.setMaximum(self.current_volume.data_max)
        # self.slider.setValue((self.current_volume.data_min, self.current_volume.data_max))
        if self.current_volume.display_min < self.current_volume.data_min:
            self.current_volume.display_min = self.current_volume.data_min
        if self.current_volume.display_max > self.current_volume.data_max:
            self.current_volume.display_max = self.current_volume.data_max
        self.slider.setValue((self.current_volume.display_min, self.current_volume.display_max))
        self.slider.blockSignals(False)

        self.refresh()

    def on_slider_changed(self, vals):
        if self.current_volume is None or self.lower_limit_line is None or self.upper_limit_line is None:
            return
        lower_val = vals[0]
        upper_val = vals[1]

        # update the position of the vertical lines on the histogram
        self.lower_limit_line.set_xdata([lower_val, lower_val])
        self.upper_limit_line.set_xdata([upper_val, upper_val])
        self.canvas.draw_idle()
        self.canvas.flush_events()

        # update the min and max edits
        if self.float_or_whole == 'float':
            lower_val = str(round(vals[0], 2))
            upper_val = str(round(vals[1], 2))
        else:
            lower_val = str(vals[0])
            upper_val = str(vals[1])
        self.ui.min_display_edit.setText(lower_val)
        self.ui.max_display_edit.setText(upper_val)

    def on_slider_released(self):
        if self.current_volume is None or self.lower_limit_line is None or self.upper_limit_line is None:
            return
        vals = self.slider.value()
        lower_val = vals[0]
        upper_val = vals[1]

        self.range_changed_signal.emit((lower_val, upper_val))

    def on_min_edit_changed(self):
        if self.float_or_whole == "whole":
            lower_val = int(self.ui.min_display_edit.text())
            upper_val = int(self.ui.max_display_edit.text())
        else:
            lower_val = float(self.ui.min_display_edit.text())
            upper_val = float(self.ui.max_display_edit.text())

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
        self.range_changed_signal.emit((lower_val, upper_val))

    def on_max_edit_changed(self):
        if self.float_or_whole == "whole":
            upper_val = int(self.ui.max_display_edit.text())
            lower_val = int(self.ui.min_display_edit.text())
        else:
            upper_val = float(self.ui.max_display_edit.text())
            lower_val = float(self.ui.min_display_edit.text())

        if upper_val > self.slider.maximum():
            upper_val = self.slider.maximum()
        elif upper_val <= lower_val:
            if (upper_val-1) >= self.slider.minimum():
                lower_val = upper_val - 1
            else:
                lower_val = self.slider.minimum()
                upper_val = lower_val + 1

        self.slider.setValue((lower_val, upper_val))
        self.range_changed_signal.emit((lower_val, upper_val))

    def on_clip_button_clicked(self):
        self.clipping_changed_signal.emit(self.ui.clip_checkbox.isChecked())
