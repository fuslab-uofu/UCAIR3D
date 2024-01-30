import sys
import os
import numpy as np

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QComboBox
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal

import matplotlib
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from matplotlib.widgets import RangeSlider


class ThresholdingWidget(QWidget):
    changed_signal = pyqtSignal(list)  # Signal to be emitted when selection changes

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        label = QLabel("Display Threshold:")

        # the histogram plot
        self.fig = Figure()
        self.ax = self.fig.add_axes([0.1, 0.25, 0.65, 0.65])
        self.ax.set_facecolor("black")
        self.canvas = FigureCanvas(self.fig)
        self.ax.set_title("Histogram of Voxel Intensities")
        self.lower_limit_line = None
        self.upper_limit_line = None

        # the data display range slider
        self.slider_ax = self.fig.add_axes([0.1, 0.1, 0.65, 0.03])
        self.slider_ax.text(0.5, 1.5, "Range of Data to Display", transform=self.slider_ax.transAxes,
                            verticalalignment='bottom', horizontalalignment='center')

        self.slider = RangeSlider(self.slider_ax, "", 0, 50)
        self.slider.on_changed(self.on_slider_changed)
        layout.addWidget(label)
        layout.addWidget(self.canvas)

        self.setLayout(layout)

    def update_histogram(self, vol):
        self.ax.cla()
        if vol is not None:
            # nonzero_data = vol.data[vol.data != 0]
            self.ax.hist(vol.data.flatten(), bins=20, color='white')
            # Create the Vertical lines on the histogram
            self.lower_limit_line = self.ax.axvline(vol.data.min(), color='#ffaa00')
            self.upper_limit_line = self.ax.axvline(vol.data.max(), color='#ffaa00')
            plt.show()
            self.canvas.draw()

            self.slider.valmin = vol.data.min()
            self.slider.valmax = vol.data.max()
            self.slider_ax.set_xlim(vol.data.min(), vol.data.max())

    def on_slider_changed(self, vals):
        # update the position of the vertical lines
        self.lower_limit_line.set_xdata([vals[0], vals[0]])
        self.upper_limit_line.set_xdata([vals[1], vals[1]])
        self.changed_signal.emit([vals[0], vals[1]])
