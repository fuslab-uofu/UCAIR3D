"""
display_settings_widget.py
Author: Michelle Kline
UCAIR, Department of Radiology and Imaging Sciences, University of Utah
2024

This file contains the DisplaySettings class, which is a custom QFrame that contains display settings widgets for a 3D
image. Colormap selection, transparency threshold_slider, and threshold widget for windowing/brightness/contrast.
"""
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QSlider, QFrame, QLabel
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from image3D import Image3D
import numpy as np

import colorcet as cc
from superqt import QColormapComboBox, QRangeSlider, QDoubleRangeSlider
from qtd_display_settings_widget import Ui_qtd_settings_widget_frame
import pyqtgraph as pg


class DisplaySettingsWidget(QFrame):
    display_settings_changed_signal = pyqtSignal(Image3D)  # signal emitted when the display settings change

    def __init__(self):
        super().__init__()
        """
        The DisplaySettings class is a custom QFrame that contains display settings widgets for a 3D image. Colormap
        selection, transparency threshold_slider, and threshold widget for windowing/brightness/contrast.
        
        """
        # Note that the display settings widget is allowed to update the volume's display settings, but it does not
        # update the volume's data.

        self.ui = Ui_qtd_settings_widget_frame()
        self.ui.setupUi(self)

        # image selection combo box
        self.ui.image_selection_combo.addItem("Select...")
        self.current_image = None
        self.ui.image_selection_combo.setCurrentIndex(0)
        self.images = []
        self.ui.image_selection_combo.currentIndexChanged.connect(self.image_selection_changed)

        # the superqt colormap selection combo box
        self.colormap_combo = QColormapComboBox()

        # there are lots of colormaps to choose from in the Colormap Catalog:
        # https://cmap-docs.readthedocs.io/en/latest/catalog/
        # but note that you must have these colors installe in your environment
        # for example: [landmarker directory]\venv\Lib\site-packages\pyqtgraph\colors\maps
        # self.available_colormaps = [
        #     "colorcet:cet_l1",  # black -> white (linear)
        #     "colorcet:cet_l3",  # black -> red -> yellow -> white (linear)
        #     "colorcet:cet_l4",  # black -> red -> yellow (linear)
        #     "colorcet:cet_l20",  # parula-like (linear)
        #     "colorcet:cet_l13",  # reds (linear)
        #     "colorcet:cet_l14",  # greens (linear)
        #     "colorcet:cet_l15",  # blues (linear)
        #     "colorcet:cet_c11",  # cyclic (rainbow)
        #     "colorcet:cet_cbc1",  # colorblind-friendly (cyclic)
        #     "colorcet:cet_cbl1",  # colorblind-friendly (linear)
        #     "colorcet:cet_d13",  # blue -> white -> green (diverging)
        #     "colorbrewer:set1"]
        self.available_colormaps = [
            "CET-L1",  # bLack -> white (Linear)
            "CET-L3",  # bLack -> red -> yeLLow -> white (Linear)
            "CET-L4",  # bLack -> red -> yeLLow (Linear)
            'cividis',
            'inferno',
            'magma',
            'plasma',
            'viridis',
            "CET-L13",  # reds (Linear)
            "CET-L14",  # greens (Linear)
            "CET-L15",  # bLues (Linear)
            "CET-CBC1",  # coLorbLind-friendLy (cycLic)
            "CET-CBL1",  # coLorbLind-friendLy (Linear)
            "CET-D13"]  # bLue -> white -> green (diverging)
        self.colormap_combo.addColormaps(self.available_colormaps)  # set of 9 colors
        self.colormap_combo.setStyleSheet("""
            QComboBox#colormap_combo {
                  font-family: "Segoe UI";
                  font-size: 9pt;
                  }
                  """)
        self.colormap_combo.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        self.colormap_combo.setMinimumHeight(24)
        self.colormap_combo.setMaximumHeight(24)
        self.ui.colormap_combo_frame.layout().addWidget(self.colormap_combo)
        self.colormap_combo.currentIndexChanged.connect(self.colormap_changed)

        # the transparency slider
        self.ui.transparency_slider.valueChanged.connect(self.transparency_slider_changed)

        # the histogram plot range of values to display (aka windowing, aka brightness/contrast)
        self.fig = Figure()
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_facecolor("black")
        self.canvas = FigureCanvas(self.fig)
        self.lower_limit_line = None
        self.upper_limit_line = None
        # self.canvas.setMinimumHeight(100)
        # self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.ui.hist_plot_frame.layout().addWidget(self.canvas)
        self.ui.log_checkbox.toggled.connect(self.on_log_scale_button_toggled)
        self.ui.clip_checkbox.toggled.connect(self.on_clip_button_toggled)
        # the threshold slider for range of values to display
        # this will either be a QRangeSlider (whole numbers) or QDoubleRangeSlider (floats),
        # depending on the volume's data
        self.range_slider_style = """
                QSlider {
                    background-color: none;
                }
                QSlider::add-page:horizontal {
                    background: none;
                    border: none;
                }
                QSlider::sub-page:horizontal {
                    background: none;
                    border: none;
                }
                QSlider::groove:horizontal {
                    background: black;
                    border: none;
                }
                
                QRangeSlider {
                    qproperty-barColor: #005FB8;
                }"""
        self.threshold_slider = QRangeSlider(Qt.Horizontal, self)
        # bug fix (a hack) for superqt QRangeSlider (https://github.com/pyapp-kit/superqt/issues/201)
        self.threshold_slider.setStyleSheet(self.range_slider_style)
        self.slider_type = "whole"  # default to whole number threshold_slider
        self.ui.hist_slider_frame.layout().addWidget(self.threshold_slider)
        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setMinimum(0)
        self.threshold_slider.setMaximum(100)
        self.threshold_slider.setValue((10, 90))
        self.threshold_slider.blockSignals(False)
        self.threshold_slider.sliderReleased.connect(self.threshold_slider_released)
        self.threshold_slider.valueChanged.connect(self.threshold_slider_changed)
        # the min and max edits for the display threshold
        self.ui.min_edit.returnPressed.connect(self.on_min_edit_changed)
        self.ui.max_edit.returnPressed.connect(self.on_max_edit_changed)
        # self.ui.histogram_frame.setStyleSheet("""
        #     QFrame#histogram_frame{
        #         border: 1px solid gray;
        #     }
        #     """)
        self.ui.min_edit.setText("10")
        self.ui.max_edit.setText("90")

    def image_selection_changed(self, idx):
        if len(self.images) > 0:
            idx = idx - 1  # account for the "Select..." item at index 0
            if 0 <= idx < len(self.images):
                self.current_image = self.images[idx]
            else:
                pass  # TODO clear the display settings widgets

    def set_images(self, images, idx=0):
        self.ui.image_selection_combo.clear()
        self.images = images
        self.ui.image_selection_combo.addItem("Select...")
        for img in images:
            self.ui.image_selection_combo.addItem(img.file_base_name)
        self.ui.image_selection_combo.setCurrentIndex(idx)

    def set_volume(self, img):
        # this links a volume to this display settings widget
        self.current_image = img
        if self.current_image is None:
            # reset colormap to grayscale
            # self.colormap_combo.setCurrentColormap("colorcet:cet_l1")
            self.colormap_combo.setCurrentColormap('CET-L1')
            # reset transparency to 100%
            self.ui.transparency_slider.setValue(100)
            self.ui.pct_label.setText("100%")
            # reset the thresholder widgets
            self.ui.clip_checkbox.setChecked(False)
            self.ui.log_checkbox.setChecked(False)
            self.ax.cla()
            self.canvas.draw()
            self.ui.min_edit.setText("0")
            self.ui.max_edit.setText("100")
            self.threshold_slider.blockSignals(True)
            self.threshold_slider.setMinimum(0)
            self.threshold_slider.setMaximum(100)
            self.threshold_slider.setValue((10, 90))
            self.threshold_slider.blockSignals(False)
        else:
            # initialize the colormap combo based on this volume's current colormap
            if img.colormap is None:
                self.colormap_combo.setCurrentColormap("colorcet:cet_l1")
                img.colormap = self.colormap_combo.currentColormap().to_mpl()
            else:
                pass
                # FIXME
                # try:
                #     self.colormap_combo.setCurrentColormap(vol.colormap.name)
                # except ValueError:
                #     self.colormap_combo.setCurrentColormap("colorcet:cet_l1")
                #     vol.colormap = self.colormap_combo.currentColormap().to_mpl()

            # initialize the transparency slider
            self.ui.transparency_slider.blockSignals(True)
            self.ui.transparency_slider.setValue(int(self.current_image.alpha * 100))
            self.ui.transparency_slider.blockSignals(False)

            # initialize threshold threshold_slider to float or whole type
            self.ui.clip_checkbox.setChecked(self.current_image.clipping)
            self.ui.log_checkbox.setChecked(False)
            if img.data_type in ['uint16', 'int16', 'uint8', 'int8', 'uint32', 'int32', 'uint64', 'int64']:
                # this volume is whole numbers or binary - use the whole number threshold_slider
                if self.slider_type == "float":
                    # we already have a float threshold_slider, so we need to delete it and add a float
                    self.ui.hist_slider_frame.layout().removeWidget(self.threshold_slider)
                    self.threshold_slider.deleteLater()
                    self.threshold_slider = QRangeSlider(Qt.Horizontal, self)
                    self.threshold_slider.sliderReleased.connect(self.threshold_slider_released)
                    self.threshold_slider.valueChanged.connect(self.threshold_slider_changed)
                    self.ui.hist_slider_frame.layout().addWidget(self.threshold_slider)
                self.slider_type = "whole"
            else:  # vol.data_type in ['float32', 'float64']:
                # this volume is floating point - use the float threshold_slider
                if self.slider_type == "whole":
                    # we already have a whole number threshold_slider, so we need to delete it and add a whole
                    self.ui.hist_slider_frame.layout().removeWidget(self.threshold_slider)
                    self.threshold_slider.deleteLater()
                    self.threshold_slider = QDoubleRangeSlider(Qt.Horizontal, self)
                    self.threshold_slider.sliderReleased.connect(self.threshold_slider_released)
                    self.threshold_slider.valueChanged.connect(self.threshold_slider_changed)
                    self.ui.hist_slider_frame.layout().addWidget(self.threshold_slider)
                self.slider_type = "float"
            # this is a workaround to make the threshold_slider look like the rest of the app
            self.threshold_slider.setStyleSheet(self.range_slider_style)
            self.threshold_slider.blockSignals(True)
            self.threshold_slider.setMinimum(self.current_image.data_min)
            self.threshold_slider.setMaximum(self.current_image.data_max)
            self.threshold_slider.setValue((self.current_image.display_min, self.current_image.display_max))
            self.threshold_slider.blockSignals(False)

            # self.threshold_slider.sliderReleased.connect(self.threshold_slider_released)
            # self.threshold_slider.valueChanged.connect(self.threshold_slider_changed)

            self.refresh()

    def refresh(self):
        """
        This refreshes the current value of the display settings widgets based on the current volume. It is only
        called by set_volume for now.
        """
        if self.current_image is None:
            return

        # alpha threshold_slider
        self.ui.transparency_slider.blockSignals(True)
        self.ui.transparency_slider.setValue(int(self.current_image.alpha * 100))
        self.ui.transparency_slider.blockSignals(False)

        # update the histogram plot
        self.plot_histogram()

        # update the min and max edits
        if self.slider_type == 'float':
            lower_val = str(round(self.current_image.display_min, 2))
            upper_val = str(round(self.current_image.display_max, 2))
        else:  # self.slider_type == 'whole':
            lower_val = str(self.current_image.display_min)
            upper_val = str(self.current_image.display_max)
        self.ui.min_edit.setText(lower_val)
        self.ui.max_edit.setText(upper_val)

        # update the position of the vertical lines on the histogram
        self.lower_limit_line.set_xdata([self.current_image.display_min, self.current_image.display_min])
        self.upper_limit_line.set_xdata([self.current_image.display_max, self.current_image.display_max])
        self.canvas.draw()

        # update the threshold threshold_slider
        if self.current_image.display_min < self.threshold_slider.minimum():
            self.current_image.display_min = self.threshold_slider.minimum()
        if self.current_image.display_max > self.threshold_slider.maximum():
            self.current_image.display_max = self.threshold_slider.maximum()
        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setValue((self.current_image.display_min, self.current_image.display_max))
        self.threshold_slider.blockSignals(False)

    def plot_histogram(self):
        """ Whenever a new current volume is set, this function is called to update the histogram plot. """
        self.ax.cla()
        if self.current_image is not None:

            # plot_histogram the histogram
            self.ax.hist(self.current_image.data.flatten(),
                         range=(self.current_image.data_min, self.current_image.data_max), color='white', bins=50)
            # create vertical lines on the histogram to show the current threshold values
            self.lower_limit_line = self.ax.axvline(self.current_image.display_min, color='magenta')
            self.upper_limit_line = self.ax.axvline(self.current_image.display_max, color='blue')

            # self.ax.set_xlabel('Intensity', fontsize=6)
            # self.ax.set_ylabel('Frequency', fontsize=6)
            self.ax.set_title("", fontsize=6)
            self.ax.yaxis.offsetText.set_fontsize(6)
            self.ax.tick_params(axis='both', which='major', labelsize=6, labelcolor='black')
            self.ax.yaxis.offsetText.set_fontsize(6)

            self.canvas.draw()

    def on_min_edit_changed(self):
        """
        When the user updates the min edit, the threshold_slider should be updated to reflect the new min value.
        """
        if self.slider_type == "whole":
            lower_val = int(self.ui.min_edit.text())
            upper_val = int(self.ui.max_edit.text())
        else:  # self.slider_type == "float":
            lower_val = float(self.ui.min_edit.text())
            upper_val = float(self.ui.max_edit.text())

        if lower_val < self.threshold_slider.minimum() or lower_val >= upper_val or lower_val > self.threshold_slider.maximum():
            return

        # update the threshold slider
        # if lower_val < self.threshold_slider.minimum():
        #     lower_val = self.threshold_slider.minimum()
        # elif lower_val >= upper_val:
        #     if (lower_val + 1) <= self.threshold_slider.maximum():
        #         upper_val = lower_val + 1
        #     else:
        #         upper_val = self.threshold_slider.maximum()
        #         lower_val = upper_val - 1
        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setValue((lower_val, upper_val))
        self.threshold_slider.blockSignals(False)

        # update the position of the vertical lines on the histogram
        self.lower_limit_line.set_xdata([lower_val, lower_val])
        self.upper_limit_line.set_xdata([upper_val, upper_val])
        self.canvas.draw()

        # assume lower_val is within range of data values for volume, since we check against
        # threshold_slider min and max
        self.current_image.display_min = lower_val

        # tell main window to update all viewports
        self.display_settings_changed_signal.emit(self.current_image)

    def on_max_edit_changed(self):
        """
        When the user updates the max edit, the threshold_slider should be updated to reflect the new max value.
        """
        if self.slider_type == "whole":
            upper_val = int(self.ui.max_edit.text())
            lower_val = int(self.ui.min_edit.text())
        else:  # self.slider_type == "float":
            upper_val = float(self.ui.max_edit.text())
            lower_val = float(self.ui.min_edit.text())

        if upper_val > self.threshold_slider.maximum() or upper_val <= lower_val or upper_val < self.threshold_slider.minimum():
            return

        # update the threshold slider
        # if upper_val > self.threshold_slider.maximum():
        #     upper_val = self.threshold_slider.maximum()
        # elif upper_val <= lower_val:
        #     if (upper_val-1) >= self.threshold_slider.minimum():
        #         lower_val = upper_val - 1
        #     else:
        #         lower_val = self.threshold_slider.minimum()
        #         upper_val = lower_val + 1
        self.threshold_slider.blockSignals(True)
        self.threshold_slider.setValue((lower_val, upper_val))
        self.threshold_slider.blockSignals(False)

        # update the position of the vertical lines on the histogram
        self.lower_limit_line.set_xdata([lower_val, lower_val])
        self.upper_limit_line.set_xdata([upper_val, upper_val])
        self.canvas.draw()

        # assume upper_val is within range of data values for volume, since we check against
        # threshold_slider min and max
        self.current_image.display_max = upper_val

        # tell main window to update all viewports
        self.display_settings_changed_signal.emit(self.current_image)

    def threshold_slider_changed(self, vals):
        """
        Called when the user moves the threshold_slider. This updates the min and max edits, and range lines on the
        histogram, but does not tell the main window to update the viewports. This is done when the user releases
        the threshold_slider.
        """
        if self.current_image is None or self.lower_limit_line is None or self.upper_limit_line is None:
            return

        lower_val = vals[0]
        upper_val = vals[1]

        # update the position of the vertical lines on the histogram
        self.lower_limit_line.set_xdata([lower_val, lower_val])
        self.upper_limit_line.set_xdata([upper_val, upper_val])
        self.canvas.draw_idle()
        self.canvas.flush_events()

        # update the min and max edits
        if self.slider_type == 'float':
            lower_val = str(round(vals[0], 2))
            upper_val = str(round(vals[1], 2))
        else:  # self.slider_tyep == 'whole':
            lower_val = str(vals[0])
            upper_val = str(vals[1])

        # update the linked min and max edits
        # FIXME: do I need to block signals here?
        self.ui.min_edit.blockSignals(True)
        self.ui.min_edit.setText(lower_val)
        self.ui.min_edit.blockSignals(False)
        self.ui.max_edit.blockSignals(True)
        self.ui.max_edit.setText(upper_val)
        self.ui.max_edit.blockSignals(False)

        # we are not yet updating the volume or sending a signal to the main window to update the viewports
        # instead, we will wait until the user releases the threshold_slider

    def threshold_slider_released(self):
        """
        Called when the user releases the threshold_slider. This is when we update the volume and tell the main window
        to update the viewports.
        """
        if self.current_image is None or self.lower_limit_line is None or self.upper_limit_line is None:
            return

        vals = self.threshold_slider.value()
        lower_val = vals[0]
        upper_val = vals[1]

        # self.current_image.display_min = vals[0]
        # self.current_image.display_max = vals[1]

        # update the volume's display min and max
        self.current_image.display_min = lower_val
        self.current_image.display_max = upper_val

        # tell main window to update all viewports
        self.display_settings_changed_signal.emit(self.current_image)

    def on_log_scale_button_toggled(self):
        if self.ui.log_checkbox.isChecked():
            self.ax.set_yscale('log')
        else:
            self.ax.set_yscale('linear')
        self.canvas.draw()

    def colormap_changed(self, idx):
        if self.current_image is None:
            return
        # update the volume's colormap
        self.current_image.update_colormap(self.available_colormaps[idx])

        # tell main window to update all viewports
        self.display_settings_changed_signal.emit(self.current_image)

    def transparency_slider_changed(self, val):
        if self.current_image is None:
            return

        # update the linked label
        self.ui.pct_label.setText(str(val) + "%")
        # update the volume's alpha
        self.current_image.alpha = val / 100
        # tell main window to update all viewports
        self.display_settings_changed_signal.emit(self.current_image)

    def handle_clipping_signal(self, val):
        if self.current_image is None:
            return
        self.current_image.clipping = val
        self.display_settings_changed_signal.emit(self.current_image)

    def on_clip_button_toggled(self):
        if self.current_image is None:
            return

        # update the volume's clipping flag
        self.current_image.clipping = self.ui.clip_checkbox.isChecked()

        # tell main window to update all viewports
        self.display_settings_changed_signal.emit(self.current_image)
