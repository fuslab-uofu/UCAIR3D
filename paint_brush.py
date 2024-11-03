import numpy as np


class PaintBrush:
    def __init__(self, size=1, value=1, shape='square'):
        """
        Initialize the PaintBrush class.

        Parameters:
        size (int): The size of the paint brush (defines the width/height of the kernel).
        value (int): The value of the brush (defines the color of the paint).
        """
        self.size = size
        self.value = value
        self.shape = shape
        self.kernel = None
        self.center = (1, 1)
        self._update_kernel()

    def set_size(self, size):
        """Set the size of the paint brush. For square brushes, the size is the width/height of the kernel.
        For circular brushes, the size is the diameter of the circle."""
        self.size = size
        self._update_kernel()

    def get_size(self):
        """Get the size of the paint brush. For square brushes, the size is the width/height of the kernel.
        For circular brushes, the size is the diameter of the circle."""
        return self.size

    def set_value(self, value):
        """Set the value of the paint."""
        self.value = value
        self._update_kernel()

    def get_value(self):
        """Get the value of the paint."""
        return self.value

    def set_shape(self, shape):
        """Set the shape of the paint brush."""
        if shape not in ['square', 'circle']:
            raise ValueError("Invalid shape. Must be 'square' or 'circle'.")
        self.shape = shape
        self._update_kernel()

    def _update_kernel(self):
        """Update the kernel based on the current brush size and paint value."""
        if self.shape == 'square':
            # Create a kernel with the current size, filled with the current value
            self.kernel = np.full((self.size, self.size), self.value)
            # Set the new kernel to the image item
            self.center = (self.size // 2, self.size // 2)  # Center of the kernel
        elif self.shape == 'circle':
            # TODO
            pass

    # TODO: Create a circular mask to simulate a circular brush
    # could be done by using the mask argument of setDrawKernel. Only circular shape of kernel is "active"

# from Kazem
#         # creating brushes
#         self.brush_dict = {}
#         # brush_dict[1] = np.array([[1]])
#         for b_size in range(1, 20):
#             b_matrix = np.ones((b_size, b_size))
#             x, y = np.mgrid[0:b_size, 0:b_size]
#             c_x = b_size / 2
#             c_y = b_size / 2
#             b_out = (x + 0.5 - c_x) ** 2 + (y + 0.5 - c_y) ** 2 - ((b_size - 0.5) / 2) ** 2
#             b_matrix[b_out > 0] = 0
#             self.brush_dict[b_size] = b_matrix