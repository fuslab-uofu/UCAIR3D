# ucair3d/components/colormap_combo.py
from PyQt5.QtCore import pyqtSignal
from superqt import QColormapComboBox

class ColormapCombo(QColormapComboBox):
    """
    Custom class derived from superqt QColormapComboBox.
    Emits colormap_changed_signal(cmap_pyqtgraph) whenever the selection changes.
    """
    colormap_changed_signal = pyqtSignal(object)  # emits pyqtgraph-compatible colormap

    def __init__(self, _parent=None, _colors=None, _tag=None):
        super().__init__(_parent)
        self.palette = _colors or []  # list of superqt colormap objects or names
        if self.palette:
            self.addColormaps(self.palette)

        # FIXME (your comment): keep renames here for now; can be moved out later
        # Make sure there are enough items before renaming to avoid index errors
        if self.count() > 2:
            self.setItemText(1, 'navia (for T2/T2*)')
            self.setItemText(2, 'lipari (for T1)')

        # default to first colormap in list (if any)
        if self.count() > 0:
            self.colormap = self.currentColormap().to_pyqtgraph()
        else:
            self.colormap = None

        if _tag:
            self.setObjectName(_tag)
            css_string = f"""
                QComboBox#{_tag} {{
                    font-family: 'Segoe UI';
                    font-size: 8pt;
                }}
            """
            self.setStyleSheet(css_string)

        self.currentIndexChanged.connect(self.index_changed)

    def index_changed(self, index: int):
        if index < 0:
            return
        cmap_pyqtg = self.currentColormap().to_pyqtgraph()
        self.colormap_changed_signal.emit(cmap_pyqtg)

    def set_index_from_cmap(self, _cmap):
        """_cmap: a superqt colormap object (or name) you want to select by name."""
        if _cmap is None:
            return
        # Try to match by display text
        target_name = getattr(_cmap, "name", None) or str(_cmap)
        self.blockSignals(True)
        for i in range(self.count()):
            if self.itemText(i) == target_name:
                self.setCurrentIndex(i)
                break
        self.blockSignals(False)


# from PyQt5.QtCore import pyqtSignal
# from superqt import QColormapComboBox
#
#
# class ColormapCombo(QColormapComboBox):
#     """
#     Custom class derived from superqt QColormapComboBox. Customized to include the desired list of available colormaps
#     for the LandMarker and LATTE apps.
#     """
#     colormap_changed_signal = pyqtSignal(object)
#
#     def __init__(self, _parent, _colors, _tag=None):
#         super().__init__(_parent)
#
#         self.palette = _colors
#
#         self.addColormaps(self.palette)
#         # FIXME: quick workaround - should be done outside of this class, to keep class generic
#         self.setItemText(1, 'navia (for T2/T2*)')
#         self.setItemText(2, 'lipari (for T1)')
#
#         self.colormap = self.currentColormap().to_pyqtgraph()  # default to first colormap in list
#
#         if _tag:
#             self.setObjectName(_tag)
#             css_string = f"""
#                            QComboBox#{_tag} {{
#                                 font-family: 'Segoe UI';
#                                 font-size: 8pt;
#                             }}
#                             """
#             self.setStyleSheet(css_string)
#
#         self.currentIndexChanged.connect(self.index_changed)
#
#     def index_changed(self, index):
#         if index < 0:
#             return
#         # get the current colormap
#         cmap_pyqtg = self.currentColormap().to_pyqtgraph()
#         self.colormap_changed_signal.emit(cmap_pyqtg)
#
#     def set_index_from_cmap(self, _cmap):
#         self.blockSignals(True)
#         idx = None
#         for i in range(self.count()):
#             if self.itemText == _cmap.name:
#                 self.setCurrentIndex(i)
#                 break
#         self.blockSignals(False)
