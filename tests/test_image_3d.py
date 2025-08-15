# pytest unit tests for UCAIR3D Image3D (API-preserving)
# -----------------------------------------------------------------------------
# Adjust imports below to match your package name if needed.
# If your package is named "ucair3d", this should work as-is.
# If you're running tests directly next to image3D.py, you can also do:
#   from image3D import Image3D, ViewDir

import numpy as np
import nibabel as nib
import pytest

# Import the library from the package root. Running pytest from the repo root makes
# `ucair3d` importable as long as the package folder exists and has __init__.py files.
# If you prefer not to install with `pip install -e .`, add a tests/conftest.py that
# inserts the repo root on sys.path (see chat instructions).
from ucair3d.components.image3D import Image3D
from ucair3d.enumerations import ViewDir

# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

class _DummyParent:
    def __init__(self, display_convention="RAS"):
        self.display_convention = display_convention


@pytest.fixture
def dummy_parent():
    return _DummyParent("RAS")


@pytest.fixture
def ras_nifti_small():
    """Create a small RAS-oriented NIfTI image with known spacing & origin.
    Data order will be (X, Y, Z) == (cols, rows, slices).
    """
    x, y, z = 5, 4, 3
    data = np.arange(x * y * z, dtype=np.int16).reshape(x, y, z)
    # Simple RAS affine: diag with spacing, plus translation
    dx, dy, dz = 0.7, 0.8, 1.2
    origin = (10.0, 20.0, 30.0)
    aff = np.array([
        [dx, 0,  0,  origin[0]],
        [0,  dy, 0,  origin[1]],
        [0,  0,  dz, origin[2]],
        [0,  0,  0,  1.0],
    ], dtype=float)
    img = nib.Nifti1Image(data, aff)
    # set pixdim for spacing
    hdr = img.header.copy()
    pixdim = hdr['pixdim']
    pixdim[1:4] = [dx, dy, dz]
    img.header['pixdim'] = pixdim
    return img, (dx, dy, dz), origin


@pytest.fixture
def image3d_populated(dummy_parent, ras_nifti_small, tmp_path):
    nifti, spacing, origin = ras_nifti_small
    im3d = Image3D(dummy_parent)
    test_path = tmp_path / "vol.nii.gz"
    nib.save(nifti, str(test_path))
    im3d.populate_with_nifti(nifti, str(test_path), base_name="vol")
    return im3d, spacing, origin


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

def test_populate_with_nifti_metadata(image3d_populated):
    im3d, (dx, dy, dz), origin = image3d_populated
    assert im3d.file_type == 'nifti'
    assert im3d.data is not None and im3d.data.ndim == 3
    assert im3d.dx == pytest.approx(dx)
    assert im3d.dy == pytest.approx(dy)
    assert im3d.dz == pytest.approx(dz)
    # shape bookkeeping (data is x,y,z == cols,rows,slices)
    assert im3d.num_cols == im3d.data.shape[0]
    assert im3d.num_rows == im3d.data.shape[1]
    assert im3d.num_slices == im3d.data.shape[2]
    # orientation should be RAS for canonicalized images
    assert im3d.x_dir == 'R'
    assert im3d.y_dir == 'A'
    assert im3d.z_dir == 'S'
    # origin & min/max
    assert len(im3d.origin) == 3
    assert im3d.data_min <= im3d.data_max


def test_get_slice_shapes_and_flips(image3d_populated):
    im3d, _spacing, _origin = image3d_populated
    data = im3d.data
    # AX (z plane): with RAS (x='R', y='A'), we expect flipud on data[:, :, k]
    k = 1
    ax_slice = im3d.get_slice(ViewDir.AX.dir, k)
    expected_ax = np.flipud(data[:, :, k])
    assert ax_slice.shape == expected_ax.shape
    assert np.array_equal(ax_slice, expected_ax)

    # SAG (x plane): with y='A' => flip along rows (axis=0) of data[x, :, :]
    x = 2
    sag_slice = im3d.get_slice(ViewDir.SAG.dir, x)
    expected_sag = np.flip(data[x, :, :], axis=0)
    assert sag_slice.shape == expected_sag.shape
    assert np.array_equal(sag_slice, expected_sag)

    # COR (y plane): with x='R' => flipud on data[:, y, :]
    y = 3 - 1  # within bounds (num_rows == data.shape[1] == 4)
    cor_slice = im3d.get_slice(ViewDir.COR.dir, y)
    expected_cor = np.flipud(data[:, y, :])
    assert cor_slice.shape == expected_cor.shape
    assert np.array_equal(cor_slice, expected_cor)


def test_get_slice_out_of_bounds_returns_none(image3d_populated):
    im3d, *_ = image3d_populated
    assert im3d.get_slice(ViewDir.AX.dir, -1) is None
    assert im3d.get_slice(ViewDir.AX.dir, im3d.num_slices) is None
    assert im3d.get_slice(ViewDir.SAG.dir, im3d.num_cols) is None
    assert im3d.get_slice(ViewDir.COR.dir, im3d.num_rows) is None


def test_voxel_world_roundtrip(image3d_populated):
    im3d, *_ = image3d_populated
    ijk = np.array([2, 1, 1], dtype=float)
    xyz = im3d.voxel_to_world(ijk)
    ijk_back = im3d.world_to_voxel(xyz)
    # numerical round trip; compare to within 1e-6 then round
    assert np.allclose(ijk, ijk_back, atol=1e-6)


@pytest.mark.parametrize("view, pick_vox", [
    (ViewDir.AX.dir,  lambda sh: (min(sh[0]-1, 2), min(sh[1]-1, 2), 1)),  # vary x,y; z fixed
    (ViewDir.SAG.dir, lambda sh: (1, min(sh[1]-1, 2), 1)),                # vary y,z; x fixed
    (ViewDir.COR.dir, lambda sh: (min(sh[0]-1, 2), 1, 1)),                # vary x,z; y fixed
])
def test_screen_image_roundtrip(image3d_populated, view, pick_vox):
    im3d, *_ = image3d_populated
    sh = im3d.data.shape  # (x, y, z)
    vx, vy, vz = pick_vox(sh)
    # Forward: voxel -> screen
    plot_col, plot_row, slice_idx = im3d.imageijk_to_screenxy(view, vx, vy, vz)
    # Back: screen -> voxel
    ijk = im3d.screenxy_to_imageijk(view, int(plot_col), int(plot_row), int(slice_idx))
    assert ijk is not None
    # Exact integer equality
    assert int(ijk[0]) == int(vx)
    assert int(ijk[1]) == int(vy)
    assert int(ijk[2]) == int(vz)
