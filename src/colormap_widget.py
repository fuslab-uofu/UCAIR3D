import numpy as np
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import pyqtSignal
import matplotlib
from matplotlib.figure import Figure
import matplotlib.pyplot as plt


class ColormapWidget(QWidget):
    changed_signal = pyqtSignal(str)  # Signal to be emitted when selection changes

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        self.label = QLabel('Select Colormap:')
        layout.addWidget(self.label)

        self.colormap_combo = QComboBox()
        model = self.colormap_combo.model()
        self.populate_combo_with_icons()
        self.colormap_combo.activated[str].connect(self.on_combo_changed)
        layout.addWidget(self.colormap_combo)

        self.setLayout(layout)

    def on_combo_changed(self, selected_name):
        # selected_name = self.colormap_combo.currentText()
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
        self.changed_signal.emit(cmap_name)

    def create_colormap_icon(self, cmap_name):
        cmap = matplotlib.colormaps[cmap_name]

        # create an array of discrete values
        num_colors = 10
        discrete_values = np.linspace(0, 1, num_colors)

        fig = Figure()
        ax = fig.add_axes([0, 0, 1, 1])
        for i, value in enumerate(discrete_values):
            ax.add_patch(plt.Rectangle((i / num_colors, 0), 1 / num_colors, 1, color=cmap(value)))
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect('auto')
        ax.set_axis_off()

        icon_path = f"{cmap_name}_icon.png"
        fig.savefig(icon_path)
        plt.close(fig)
        return icon_path

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
            icon_path = self.create_colormap_icon(cmap_name)
            # cmap_icon = f"{cmap_name}_icon.png"
            # icon_path = os.path.join("..\\ui", cmap_icon)
            self.colormap_combo.addItem(QIcon(icon_path), selected_name)
