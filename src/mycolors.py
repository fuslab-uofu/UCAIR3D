import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

# Assuming custom_colors_rgb and colormap are already defined
custom_colors_rgb = [
    (0, 128, 0),    # Green
    (0, 0, 255),    # Blue
    (255, 0, 0),    # Red
    (255, 255, 0),  # Yellow
    (128, 0, 128),  # Purple
    (255, 165, 0),  # Orange
    (0, 255, 255)   # Cyan
]

# Normalize RGB values to range [0, 1]
custom_colors_rgb = [(r / 255, g / 255, b / 255) for r, g, b in custom_colors_rgb]

# Create the colormap
colormap = mcolors.ListedColormap(custom_colors_rgb)

# Plot a colorbar to visualize the colormap
plt.figure(figsize=(8, 1))
plt.imshow(np.arange(7).reshape(1, -1), cmap=colormap)
plt.colorbar(ticks=np.arange(7), orientation='horizontal')
plt.show()
