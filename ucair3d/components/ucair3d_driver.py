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
nifti = nib.load("D:\ANIMAL\Sumaiya\83 T1_3Dtse_TR625TE16_TSE12_0p33x0p33x0.4mm_ImSc0p1_C5R1_T1.nii.gz")

# Create an Image3D object and populate it
img3d = Image3D(parent)
img3d.populate_with_nifti(nifti, full_path_name="D:\ANIMAL\Sumaiya\83 T1_3Dtse_TR625TE16_TSE12_0p33x0p33x0.4mm_ImSc0p1_C5R1_T1.nii.gz")

# Create a viewport for displaying the image (e.g., axial view)
viewport = Viewport(parent, vp_id="AX", view_dir=ViewDir.AX, num_vols=1)
viewport.add_layer(img3d, stack_position=0)

viewport.show()
app.exec_()