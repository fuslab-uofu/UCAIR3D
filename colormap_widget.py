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


class ColormapWidget(QWidget):
    changed_signal = pyqtSignal(str)  # Signal to be emitted when selection changes

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        self.label = QLabel('Select Colormap:')
        layout.addWidget(self.label)

        self.colormap_combo = QComboBox()
        self.populate_combo_with_icons()
        self.colormap_combo.currentIndexChanged.connect(self.on_combo_changed)
        layout.addWidget(self.colormap_combo)

        self.setLayout(layout)

    def populate_combo_with_icons(self):
        for cmap_name in [cmap for cmap in ['Gray', 'Accent', 'Blues', 'Greens', 'Grays', 'seismic', 'plasma', 'magma',
                                            'inferno', 'viridis', 'cividis', 'twilight', 'twilight_shifted', 'turbo',
                                            'rainbow']]:
            cmap_icon = f"{cmap_name}_icon.png"
            icon_path = os.path.join("..\\ui", cmap_icon)
            self.colormap_combo.addItem(QIcon(icon_path), cmap_name)

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

    def on_combo_changed(self):
        selected_cmap_name = self.colormap_combo.currentText()
        self.changed_signal.emit(selected_cmap_name)
