""" image3D.py
    Author: Michelle Kline

    UCAIR3D App, 2023–2025
    Michelle Kline, Department of Radiology and Imaging Sciences, University of Utah
    SeyyedKazem HashemizadehKolowri, PhD, Department of Radiology and Imaging Sciences, University of Utah

    Notes
    -----
    This refactor keeps the public API and attributes intact while consolidating
    duplicate orientation logic, adding small helpers, and documenting data order.

    Data order (after canonicalization):
        self.data has shape (C, R, S) == (x, y, z)
        where x = columns (left→right), y = rows (top→bottom), z = slices

    Display convention assumed here: 'RAS' (Right, Anterior, Superior).
"""
from __future__ import annotations

import os
import numpy as np
import nibabel as nib
try:
    import pyqtgraph as pg
except Exception:
    pg = None

from ..enumerations import ViewDir


class Image3D:
    """
    A simple 3D image container with orientation-aware slice extraction and
    voxel/world coordinate helpers.

    Public attributes:
        parent, file_type, full_file_name, file_path, file_name, file_base_name,
        data, canonical_data, data_type, canonical_nifti, header,
        dx, dy, dz, num_rows, num_cols, num_slices, scan_direction,
        data_min, data_max, transform, x_dir, y_dir, z_dir,
        origin, resolution, shape, visible

    Public methods:
        populate_with_dicom(...)
        populate_with_nifti(nifti_image, full_path_name, base_name=None, settings_dict=None)
        get_slice(view, slice_num)
        _get_x_slice(slice_num)
        _get_y_slice(slice_num)
        _get_z_slice(slice_num)
        screenxy_to_voxelijk(slice_orientation, plot_col, plot_row, slice_index)
        voxelijk_to_screenxy(slice_orientation, voxel_x, voxel_y, voxel_z)

    Private helpers (API-neutral):
        _slice_2d(view, index)
        _clamp_index(axis_len, idx)
        _clamp_voxel(r, c, p)
        voxel_to_world(ijk)
        world_to_voxel(xyz)
    """

    def __init__(self, parent):
        # identification
        self.parent = parent
        self.file_type = ''        # 'dicom' or 'nifti'
        self.full_file_name = ''   # full path and name of the dataset
        self.file_path = ''        # path to the dataset
        self.file_name = ''        # file name, including extension(s)
        self.file_base_name = ''   # file name without extension(s)

        # voxel data & data type
        self.data: np.ndarray | None = None
        self.canonical_data = None  # kept for compatibility (unused)
        self.data_type = None

        # keep reference to canonical NiBabel image
        self.canonical_nifti: nib.Nifti1Image | None = None

        # geometry & stats
        self.header = None
        self.dx = 1.0
        self.dy = 1.0
        self.dz = 1.0
        self.num_rows = 1
        self.num_cols = 1
        self.num_slices = 1
        self.scan_direction = None
        self.data_min = None
        self.data_max = None

        # orientation
        self.transform = np.eye(4)  # affine ijk→world
        self.x_dir = None  # 'R' or 'L'
        self.y_dir = None  # 'A' or 'P'
        self.z_dir = None  # 'S' or 'I'

        self.origin = None
        self.resolution = None
        self.shape = None

        self.visible = True

        # --- add: UI/display defaults used by Viewport ---
        # Window/level range to display (fallback to data_min/max when set later)
        self.display_min = None  # float | None
        self.display_max = None  # float | None
        # Overall opacity and clipping behavior
        self.alpha = 1.0  # 0.0..1.0
        self.clipping = False  # if True, outside [display_min, display_max] is transparent
        # Default colormap: CET-L1 if available, else gray
        if pg is not None and hasattr(pg, "colormap"):
            try:
                self.colormap = pg.colormap.get("CET-L1")
            except Exception:
                self.colormap = pg.colormap.get("gray")
        else:
            self.colormap = None  # Viewport will still run; you can set later if pg isn’t present

    # ---------------------------------------------------------------------
    # Loading / population
    # ---------------------------------------------------------------------
    def populate_with_dicom(self, datasets, dataset_name, is_enhanced: bool = False):
        """Populate from a DICOM series (not yet implemented in this version)."""
        # Placeholder to preserve API; implement as needed
        pass

    def populate_with_nifti(self, nifti_image, full_path_name, base_name=None):
        """
        Populate from a NIfTI image using NiBabel.

        Parameters
        ----------
        nifti_image : nib.Nifti1Image
        full_path_name : str
        base_name : Optional[str]
        """
        # For neuro/medical images (especially NIfTI), the standard most tools use is RAS+:
        # - Right is the positive x direction
        # - Anterior is the positive y direction
        # - Superior is the positive z direction
        # as_closest_canonical() will flip and/or permute axes to match this convention.
        # The affine transform will be adjusted accordingly.
        # There is no resampling or data type conversion here; the original data type is preserved.
        self.canonical_nifti = nib.as_closest_canonical(nifti_image)

        # Load voxel data eagerly for interactive use; preserve on-disk dtype
        self.data = np.asanyarray(self.canonical_nifti.dataobj).astype(nifti_image.header.get_data_dtype())
        self.header = self.canonical_nifti.header
        self.data_type = str(self.data.dtype)

        # Filenames / types
        self.full_file_name = full_path_name
        self.file_path = os.path.dirname(full_path_name)
        self.file_name = os.path.basename(full_path_name)
        if base_name is not None:
            self.file_base_name = base_name
        else:
            base_name_only = os.path.splitext(self.file_name)[0]
            self.file_base_name = os.path.splitext(base_name_only)[0]  # handles .nii.gz
        self.file_type = 'nifti'

        # Spacing (NiBabel header pixdim is float32; cast to float for safety)
        self.dx = float(self.canonical_nifti.header['pixdim'][1:4][0])  # ROW height
        self.dy = float(self.canonical_nifti.header['pixdim'][1:4][1])  # COL width
        self.dz = float(self.canonical_nifti.header['pixdim'][1:4][2])

        # Dimensions: data shape is (cols=x, rows=y, slices=z)
        self.num_rows = int(self.data.shape[1])
        self.num_cols = int(self.data.shape[0])
        self.num_slices = int(self.data.shape[2])

        # Affine & axis codes
        self.transform = self.canonical_nifti.affine
        ax_codes = nib.orientations.aff2axcodes(self.transform)
        self.x_dir, self.y_dir, self.z_dir = ax_codes[0], ax_codes[1], ax_codes[2]

        # Min/max & geometry summaries
        self.data_min = float(np.min(self.data))
        self.data_max = float(np.max(self.data))
        self.origin = list(self.transform[:3, 3])
        self.resolution = [self.dx, self.dy, self.dz]
        self.shape = [int(s) for s in self.data.shape]

        if self.display_min is None: self.display_min = self.data_min
        if self.display_max is None: self.display_max = self.data_max

    # ---------------------------------------------------------------------
    # Slice extraction (public API preserved)
    # ---------------------------------------------------------------------
    def get_slice(self, view, slice_num):
        """
        Return a 2D slice for the requested view direction and slice index,
        respecting RAS display convention and stored axis codes.
        """
        if view == ViewDir.AX.dir:
            if 0 <= slice_num < self.num_slices:
                return self._get_z_slice(slice_num)
            return None
        elif view == ViewDir.SAG.dir:
            if 0 <= slice_num < self.num_cols:
                return self._get_x_slice(slice_num)
            return None
        elif view == ViewDir.COR.dir:
            if 0 <= slice_num < self.num_rows:
                return self._get_y_slice(slice_num)
            return None
        else:
            return None

    def _get_x_slice(self, slice_num):
        """SAGITTAL: slice along x index (y–z plane), with orientation flips to match RAS display."""
        # Data is (x, y, z) == (cols, rows, slices)
        if self.parent.display_convention == 'RAS':
            if self.y_dir == 'A':
                x_slice = np.flip(self.data[slice_num, :, :], axis=0)
            else:  # 'P'
                x_slice = self.data[slice_num, :, :]
        else:
            # Other conventions can be added as needed
            x_slice = self.data[slice_num, :, :]
        return x_slice

    def _get_y_slice(self, slice_num):
        """CORONAL: slice along y index (x–z plane), with orientation flips to match RAS display."""
        if self.parent.display_convention == 'RAS':
            if self.x_dir == 'R':
                y_slice = np.flipud(self.data[:, slice_num, :])
            else:  # 'L'
                y_slice = self.data[:, slice_num, :]
        else:
            y_slice = self.data[:, slice_num, :]
        return y_slice

    def _get_z_slice(self, slice_num):
        """AXIAL: slice along z index (x–y plane), with orientation flips to match RAS display."""
        if self.parent.display_convention == 'RAS':
            if self.x_dir == 'R':
                if self.y_dir == 'A':
                    z_slice = np.flipud(self.data[:, :, slice_num])
                else:  # 'P'
                    z_slice = np.flipud(np.fliplr(self.data[:, :, slice_num]))
            else:  # 'L'
                if self.y_dir == 'A':
                    z_slice = self.data[:, :, slice_num]
                else:  # 'P'
                    z_slice = np.fliplr(self.data[:, :, slice_num])
        else:
            z_slice = self.data[:, :, slice_num]
        return z_slice

    # Convenience (internal)—not used by callers, but helpful for maintenance
    def _slice_2d(self, view, index):
        if view == ViewDir.AX.dir:
            return self._get_z_slice(self._clamp_index(self.num_slices, index))
        if view == ViewDir.SAG.dir:
            return self._get_x_slice(self._clamp_index(self.num_cols, index))
        if view == ViewDir.COR.dir:
            return self._get_y_slice(self._clamp_index(self.num_rows, index))
        return None

    @staticmethod
    def _clamp_index(axis_len, idx):
        return int(np.clip(idx, 0, axis_len - 1))

    def _clamp_voxel(self, r, c, p):
        r = int(np.clip(r, 0, self.data.shape[1] - 1))
        c = int(np.clip(c, 0, self.data.shape[0] - 1))
        p = int(np.clip(p, 0, self.data.shape[2] - 1))
        return r, c, p

    # ---------------------------------------------------------------------
    # Coordinate transforms
    # ---------------------------------------------------------------------
    def voxel_to_world(self, ijk):
        """Map voxel (i,j,k) → world (x,y,z) using affine."""
        return nib.affines.apply_affine(self.transform, ijk)

    def world_to_voxel(self, xyz):
        """Map world (x,y,z) → voxel (i,j,k) using inverse affine."""
        inv_aff = np.linalg.inv(self.transform)
        return nib.affines.apply_affine(inv_aff, xyz)

    # ---------------------------------------------------------------------
    # Screen↔voxel conversions (public API preserved)
    # ---------------------------------------------------------------------
    def screenxy_to_voxelijk(self, slice_orientation, plot_col, plot_row, slice_index):
        """Given screen (x=col, y=row) in the current orientation, return voxel ijk coords into the canonical data. """
        if self.parent.display_convention == "RAS":
            if slice_orientation == ViewDir.AX.dir:
                # right on left, posterior at bottom
                if self.x_dir == 'L':
                    voxel_x = plot_col
                else:  # 'R'
                    voxel_x = self.num_cols - 1 - plot_col
                if self.y_dir == 'A':
                    voxel_y = plot_row
                else:  # 'P'
                    voxel_y = self.num_rows - 1 - plot_row
                voxel_z = slice_index
                ijk = np.array([voxel_x, voxel_y, voxel_z])
            elif slice_orientation == ViewDir.SAG.dir:
                # anterior on left, inferior at bottom
                voxel_x = slice_index
                if self.y_dir == 'A':
                    voxel_y = self.num_rows - 1 - plot_col
                else:  # 'P'
                    voxel_y = plot_col
                voxel_z = plot_row
                ijk = np.array([voxel_x, voxel_y, voxel_z])
            elif slice_orientation == ViewDir.COR.dir:
                # right on left, inferior at bottom
                if self.x_dir == 'L':
                    voxel_x = plot_col
                else:  # 'R'
                    voxel_x = self.num_cols - 1 - plot_col
                voxel_y = slice_index
                voxel_z = plot_row
                ijk = np.array([voxel_x, voxel_y, voxel_z])
            else:
                ijk = None
        else:
            # Other conventions could be implemented here
            ijk = None
        return ijk

    def voxelijk_to_screenxy(self, slice_orientation, voxel_x, voxel_y, voxel_z):
        """Inverse of screenxy_to_voxelijk for RAS: return (plot_col, plot_row, slice_index)."""
        if self.parent.display_convention == "RAS":
            if slice_orientation == ViewDir.AX.dir:
                if self.x_dir == 'L':
                    plot_col = voxel_x
                else:
                    plot_col = self.num_cols - 1 - voxel_x
                if self.y_dir == 'A':
                    plot_row = voxel_y
                else:
                    plot_row = self.num_rows - 1 - voxel_y
                slice_index = voxel_z
                xyz = np.array([plot_col, plot_row, slice_index])
            elif slice_orientation == ViewDir.SAG.dir:
                slice_index = voxel_x
                if self.y_dir == 'A':
                    plot_col = self.num_rows - 1 - voxel_y
                else:
                    plot_col = voxel_y
                plot_row = voxel_z
                xyz = np.array([plot_col, plot_row, slice_index])
            elif slice_orientation == ViewDir.COR.dir:
                if self.x_dir == 'L':
                    plot_col = voxel_x
                else:
                    plot_col = self.num_cols - 1 - voxel_x
                slice_index = voxel_y
                plot_row = voxel_z
                xyz = np.array([plot_col, plot_row, slice_index])
            else:
                xyz = None
        else:
            xyz = None
        return xyz
