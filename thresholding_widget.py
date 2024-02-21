""" thresholding_widget.py

"""

from PyQt5.QtWidgets import QSlider, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal

from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas


class ThresholdingWidget(QWidget):
    changed_signal = pyqtSignal(list)  # Signal to be emitted when selection changes

    def __init__(self, parent):
        super().__init__()

        self.parent = parent
        layout = QVBoxLayout()
        label = QLabel("Display Threshold:")

        # the histogram plot
        self.fig = Figure()
        self.ax = self.fig.add_axes([0.1, 0.25, 0.65, 0.65])
        self.ax.set_facecolor("black")
        self.canvas = FigureCanvas(self.fig)
        self.ax.set_title("Histogram of Voxel Intensities")
        self.ax.set_xlabel('Intensity')
        self.ax.set_ylabel('Frequency')
        # self.ax.grid(True)
        self.lower_limit_line = None
        self.upper_limit_line = None
        layout.addWidget(label)
        layout.addWidget(self.canvas)

        # the data display range slider
        label_layout = QHBoxLayout()
        slider_layout = QHBoxLayout()
        label_layout.addWidget(QLabel("Lower Threshold:"))
        label_layout.addWidget(QLabel("Upper Threshold:"))
        self.lower_slider = QSlider(Qt.Horizontal)
        self.lower_slider.setMinimum(0)
        self.lower_slider.setMaximum(1)
        self.lower_slider.setTickInterval(1)
        self.lower_slider.setValue(0)
        self.lower_slider.valueChanged.connect(self.on_slider_changed)
        slider_layout.addWidget(self.lower_slider)
        self.upper_slider = QSlider(Qt.Horizontal)
        self.upper_slider.setMinimum(0)
        self.upper_slider.setMaximum(1)
        self.upper_slider.setTickInterval(1)
        self.upper_slider.setValue(1)
        self.upper_slider.valueChanged.connect(self.on_slider_changed)
        slider_layout.addWidget(self.upper_slider)
        layout.addLayout(label_layout)
        layout.addLayout(slider_layout)

        self.setLayout(layout)

    def plot_histogram(self):
        """ Whenever the user selects a new volume, this function is called to update the histogram plot. """
        self.ax.cla()
        if self.parent.selected_volume is not None:
            vol = self.parent.selected_volume
            # plot_histogram the slider ranges
            self.lower_slider.setMinimum(vol.data_min)
            self.lower_slider.setMaximum(vol.data_max)
            self.lower_slider.setValue(vol.display_min)
            self.upper_slider.setMinimum(vol.data_min)
            self.upper_slider.setMaximum(vol.data_max)
            self.upper_slider.setValue(vol.display_max)
            # plot_histogram the histogram
            self.ax.hist(vol.data.flatten(), range=(vol.data_min, vol.data_max), bins=20, color='white')
            # create vertical lines on the histogram to show the current threshold values
            self.lower_limit_line = self.ax.axvline(vol.display_min, color='yellow')
            self.upper_limit_line = self.ax.axvline(vol.display_max, color='blue')
            self.canvas.draw()

    def on_slider_changed(self):
        if self.lower_limit_line is None or self.upper_limit_line is None:
            return
        # update the position of the vertical lines on the histogram
        lower_val = self.lower_slider.value()
        upper_val = self.upper_slider.value()
        self.lower_limit_line.set_xdata([lower_val, lower_val])
        self.upper_limit_line.set_xdata([upper_val, upper_val])
        self.canvas.draw()
        self.changed_signal.emit([lower_val, upper_val])
