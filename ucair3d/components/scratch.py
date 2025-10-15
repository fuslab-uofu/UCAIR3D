
if __name__ == "__main__":
    from PyQt5 import QtWidgets
    import sys
    from display_settings import DisplaySettings
    app = QtWidgets.QApplication(sys.argv)
    w = DisplaySettings()
    w.set_colormaps(["Grayscale", "Viridis", "Magma"])
    w.colormapChanged.connect(print)
    w.show()
    sys.exit(app.exec_())
