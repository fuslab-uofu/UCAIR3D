import pyqtgraph as pg
from pyqtgraph.Qt import QtGui
import numpy as np
from PyQt5 import QtWidgets
from PyQt5.QtSvg import QSvgGenerator

# Create application
app = QtWidgets.QApplication([])
# Create ImageView widget
image_view = pg.ImageView()

# Generate some example data
data = np.random.normal(size=(100, 100))
image_view.setImage(data)

# Show the ImageView widget
image_view.show()

# Export the image to SVG
exporter = QSvgGenerator()
exporter.export('image.svg')

# Start the Qt event loop
if __name__ == '__main__':
    QtGui.QApplication.instance().exec_()
