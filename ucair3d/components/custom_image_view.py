import sys
from PyQt5.QtWidgets import QApplication
from pyqtgraph import ImageView
import numpy as np

class CustomImageView(ImageView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def wheelEvent(self, event):
        # Get the current value of the time slider
        current_value = self.timeLine.value()
        # Determine the direction of the scroll
        delta = event.angleDelta().y()
        # Update the slider value based on the scroll direction
        if delta > 0:
            new_value = current_value + 1
        else:
            new_value = current_value - 1
        # Ensure the new value is within the slider's range
        new_value = max(0, min(new_value, self.timeLine.maximum()))
        # Set the new value to the time slider
        self.timeLine.setValue(new_value)