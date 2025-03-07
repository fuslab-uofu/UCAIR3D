import pandas as pd
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from superqt import QColormapComboBox

# Load the CSV file
df = pd.read_csv("navia.csv")

# Create a colormap from the CSV
colors = [(row["value"], (row["R"], row["G"], row["B"])) for _, row in df.iterrows()]

# Define a LinearSegmentedColormap directly from the data
cmap = LinearSegmentedColormap.from_list("navia", colors)

# Use the colormap in QColormapComboBox
colormap_box = QColormapComboBox()
colormap_box.addColormap("Navia", cmap)

# If using PyQtGraph, apply the colormap as a lookup table (LUT)
lut = np.array([cmap(i / 255)[:3] * 255 for i in range(256)], dtype=np.uint8)

# Apply LUT to a PyQtGraph ImageItem
# imageItem.setLookupTable(lut)
