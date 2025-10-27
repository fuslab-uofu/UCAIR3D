# UCAIR3D

**Utah Center for Advanced Imaging Research (UCAIR) 3D Medical Image Toolkit**

Python-based components for interactively displaying and manipulating 3D medical images.  

Michelle Kline
Utah Center for Advanced Imaging Research
Department of Radiology and Imaging Sciences
University of Utah
michelle.kline@utah.edu
2025


---

## ⚠️ Work in Progress

UCAIR3D is **under active development** and its API, structure, and behavior **may change without notice**.  
It is being released publicly to support open collaboration and to serve as a dependency for the [LandMarker](https://github.com/fuslab-uofu/LandMarker) application.

If you use this code, please expect:
- Incomplete documentation
- Occasional breaking changes between commits
- Ongoing reorganization of classes and files

Feedback, issues, and pull requests are welcome.

---

## Overview

UCAIR3D provides modular classes for 3D medical image visualization and interaction:

- Overlay multiple image layers in the same viewport
- Choose from continuous and discrete colormaps
- Scroll through slices, zoom, and pan interactively
- Adjust brightness/contrast (window/level) and opacity
- Add, move, or delete landmarks and markers
- Paint or annotate directly on the image

These classes are designed to be imported into larger PyQt-based applications rather than run as a stand-alone viewer.

---

## Example Usage

```python
import nibabel as nib
from PyQt5.QtWidgets import QApplication
from ucair3d.components.image3D import Image3D
from ucair3d.components.viewport import Viewport
from ucair3d.enumerations import ViewDir

# Create the Qt application
app = QApplication([])

# Create a simple parent-like object with a display convention
class DummyParent:
    display_convention = "RAS"
    debug_mode = False

parent = DummyParent()

# Load a NIfTI image using nibabel
nifti = nib.load("path_to_nifti.nii.gz")

# Create an Image3D object and populate it
img3d = Image3D(parent)
img3d.populate_with_nifti(nifti, full_path_name="path_to_nifti.nii.gz"")

# Create a viewport for displaying the image (e.g., axial view)
viewport = Viewport(parent, vp_id="AX", view_dir=ViewDir.AX, num_vols=1)
viewport.add_layer(img3d, stack_position=0)

viewport.show()
app.exec_()