""" viewport.py
    Author: Michelle Kline

    LATTE App, 2023
    Michelle Kline, Department of Radiology and Imaging Sciences, University of Utah
    SeyyedKazem HashemizadehKolowri, PhD, Deparment of Radiology and Imaging Sciences, University of Utah
"""

import numpy as np
# import dicom_numpy
import nibabel as nib
import os

from enumerations import ViewDir


class Image3D:
    """
    """

    def __init__(self, parent):
        # identification stuff
        self.parent = parent
        # the following help with saving metadata about the registered images, deformation fields, segmentations, etc.
        # created using the image3D class
        self.file_type = ''       # 'dicom' or 'nifti'
        self.full_file_name = ''  # full path and name of the dataset
        self.file_path = ''       # path to the dataset
        self.file_name = ''       # file name, including extension(s)
        self.file_base_name = ''  # file name without extension(s)

        # the actual voxel data
        self.data = None
        self.canonical_data = None  # FIXME: remove this? Is it used?
        self.data_type = None

        # for NIfTI images, keep a reference to the (canonical) Nibabel object
        self.canonical_nifti = None

        # geometry and stats
        self.header = None
        self.dx = 1
        self.dy = 1
        self.dz = 1
        self.num_rows = 1
        self.num_cols = 1
        self.num_slices = 1
        self.scan_direction = None
        self.data_min = None
        self.data_max = None

        # orientation
        self.transform = np.eye(4)  # the affine transformation for finding patient coordinates
        self.x_dir = None
        self.y_dir = None
        self.z_dir = None

        self.origin = None
        self.resolution = None
        self.shape = None

        self.visible = True


    # def populate(self, dataset, dataset_type, dataset_name):
    #     """
    #     Parameters
    #     ----------
    #     dataset
    #     dataset_type
    #     dataset_name
    #
    #     Returns
    #     -------
    #
    #     """
    #     if dataset_type == 'dicom':
    #         is_enhanced = hasattr(dataset[0], 'SOPClassUID') and dataset[0].SOPClassUID.name.startswith('Enhanced')
    #         self.populate_with_dicom(dataset, dataset_name, is_enhanced)
    #     elif dataset_type == 'nifti':
    #         self.populate_with_nifti(dataset, dataset_name)
    #     else:
    #         print('Unsupported data type ' + str(dataset_type))
    #         return
    #
    #     self.data_min = np.min(self.data)
    #     self.data_max = np.max(self.data)

    def populate_with_dicom(self, datasets, dataset_name, is_enhanced=False):
        """
        Populate this Image3D with image data and metadata from a DICOM dataset.
            -- CURRENTLY NOT IMPLEMENTED --

        Parameters
        ----------
        datasets
        dataset_name
        is_enhanced

        Returns
        -------

        """
        pass

    def populate_with_nifti(self, nifti_image, full_path_name, base_name=None, settings_dict=None):
        """
        Populates the Image3D with data loaded from a NIfTI file using NiBabel.
            Stores volume information, including affine transformation matrix for translating image ijk
            coordinates to patient coordinates.
        :param nifti_image: NIfTI imageobject
        :param full_path_name: full path and name of the file
        :param base_name: base name of the file (without extension)
        :param settings_dict: settings dictionary for the parent
        :return: None
        """
        canonical_image = nib.as_closest_canonical(nifti_image)
        self.canonical_nifti = canonical_image  # keep a reference to the canonical image

        # the voxel_ndarray created by combine_slices has shape [cols, rows, slices]
        # FIXME: is this the right way to get the data? or should we use get_fdata() (which I believe casts to float)?
        voxel_ndarray = np.asanyarray(canonical_image.dataobj).astype(nifti_image.header.get_data_dtype())
        self.data = voxel_ndarray
        self.header = canonical_image.header
        # self.data_type =nifti_image.get_data_dtype().name
        self.data_type = str(self.data.dtype)

        self.full_file_name = full_path_name
        self.file_path = os.path.dirname(full_path_name)
        self.file_name = os.path.basename(full_path_name)
        if base_name is not None:
            self.file_base_name = base_name
        else:
            base_name = os.path.splitext(self.file_name)[0]
            self.file_base_name = os.path.splitext(base_name)[0]  # remove any potential additional extensions (.nii.gz)
        self.file_type = 'nifti'

        self.dx = canonical_image.header['pixdim'][1:4][0]  # ROW height
        self.dy = canonical_image.header['pixdim'][1:4][1]  # COL width
        # FIXME: need to consider spacing between slices?
        self.dz = canonical_image.header['pixdim'][1:4][2]
        self.num_rows = self.data.shape[1]  # notice order here - num_rows = shape[1] = y
        self.num_cols = self.data.shape[0]  # num_cols = shape[0] = x
        self.num_slices = self.data.shape[2]

        # image ijk coord to patient coord affine
        self.transform = canonical_image.affine
        ax_codes = nib.orientations.aff2axcodes(self.transform)
        self.x_dir = ax_codes[0]  # 'R' or 'L'
        self.y_dir = ax_codes[1]  # 'A' or 'P'
        self.z_dir = ax_codes[2]  # 'S' or 'I'

        self.data_min = np.min(self.data)
        self.data_max = np.max(self.data)

        # self.geometry = {'shape' : self.data.shape, 'spacing' : [self.dx, self.dy, self.dz], 'origin' : self.transform[:3, 3]}
        self.origin = [self.transform[:3, 3][0], self.transform[:3, 3][1], self.transform[:3, 3][2]]
        self.resolution = [self.dx, self.dy, self.dz]
        self.shape = [self.data.shape[0], self.data.shape[1], self.data.shape[2]]

    def get_slice(self, view, slice_num):
        """
        Parameters
        ----------
        view
        slice_num

        Returns
        -------

        """
        if view == ViewDir.AX.dir:
            if 0 <= slice_num < self.num_slices:
                vol_slice = self._get_z_slice(slice_num)
            else:
                return None
        elif view == ViewDir.SAG.dir:
            if 0 <= slice_num < self.num_cols:
                vol_slice = self._get_x_slice(slice_num)
            else:
                return None
        elif view == ViewDir.COR.dir:
            if 0 <= slice_num < self.num_rows:
                vol_slice = self._get_y_slice(slice_num)
            else:
                return None
        else:  # problem
            vol_slice = None

        return vol_slice

    def _get_x_slice(self, slice_num):
        """ Return a 2D slice along the plane formed by the y and z axes of the volume/image.
            This is a column slice, SAGITTAL.
            If necessary, reorients the resulting slice to account for current display convention and image orientation.

            Parameters
            ----------
            view
            slice_num

            Returns
            -------
        """
        # indexing for numpy volume loaded with Nibabel from NIfTI is Fortran style [col, row, slice]
        if self.parent.display_convention == 'RAS':
            if self.y_dir == 'A':
                x_slice = np.flip(self.data[slice_num, :, :], axis=0)
            else:  # 'P'
                x_slice = self.data[slice_num, :, :]
        else:  # TODO
            x_slice = None
        return x_slice

    def _get_y_slice(self, slice_num):
        """ Return a 2D slice along the plane formed by the x and z axes of the volume/image.
            This is a row slice, CORONAL
            If necessary, reorients the resulting slice to account for current display convention and image orientation.

            Parameters
            ----------
            slice_num

            Returns
            -------
        """
        # indexing for numpy volume loaded with Nibabel from NIfTI is Fortran style [col, row, slice]
        if self.parent.display_convention == 'RAS':
            if self.x_dir == 'R':
                # R_S
                y_slice = np.flipud(self.data[:, slice_num, :])
            else:
                # L_S
                y_slice = self.data[:, slice_num, :]
        else:  # TODO
            y_slice = None

        return y_slice

    def _get_z_slice(self, slice_num):
        """ Returns a 2D slice along the plane formed by the x and y axes of the volume/image.
            This is a slice-slice (haha), AXIAL.
            If necessary, reorients the resulting slice to account for current display convention and image orientation.

            Parameters
            ----------
            slice_num

            Returns
            -------
        """
        # indexing for numpy volume loaded with Nibabel from NIfTI is Fortran style [col, row, slice]
        if self.parent.display_convention == 'RAS':
            if self.x_dir == 'R':
                if self.y_dir == 'A':
                    # RA_
                    z_slice = np.flipud(self.data[:, :, slice_num])
                else:
                    # RP_
                    z_slice = np.flipud(np.fliplr(self.data[:, :, slice_num]))
            else:
                if self.y_dir == 'A':
                    # LA_
                    z_slice = self.data[:, :, slice_num]
                else:
                    # LP_
                    z_slice = np.fliplr(self.data[:, :, slice_num])
        else:  # TODO
            z_slice = None

        return z_slice

    def screenxy_to_imageijk(self, slice_orientation, plot_col, plot_row, slice_index):
        """ Taking into account the current display convention (RAS, etc.), find image i,j,k (voxel) coordinates
            corresponding to slice orientation and screen x,y (column, row) coordinates.
        """
        if self.parent.display_convention == "RAS":
            if slice_orientation == ViewDir.AX.dir:
                # patient right is on the left of the screen, and patient posterior at the bottom
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
                # patient anterior is on the left of the screen, and patient inferior is at the bottom
                voxel_x = slice_index
                if self.y_dir == 'A':
                    voxel_y = self.num_rows - 1 - plot_col
                else:  # 'P'
                    voxel_y = plot_col
                voxel_z = plot_row
                ijk = np.array([voxel_x, voxel_y, voxel_z])
            elif slice_orientation == ViewDir.COR.dir:
                # patient right is on the left of the screen, and patient inferior is at the bottom
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
            # TODO
            ijk = None

        return ijk

    def imageijk_to_screenxy(self, slice_orientation, voxel_x, voxel_y, voxel_z):
        """ Taking into account the current display convention (RAS, etc.), find screen x,y (column, row) coordinates
            and current display index (current slice) corresponding to slice orientation and image i,j,k (voxel)
            coordinates.
        """
        if self.parent.display_convention == "RAS":
            if slice_orientation == ViewDir.AX.dir:
                # assuming patient right is on the left of the screen, and patient posterior at the bottom
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
                # assuming patient anterior is on the left of the screen, and patient inferior is at the bottom
                slice_index = voxel_x
                if self.y_dir == 'A':
                    plot_col = self.num_rows - 1 - voxel_y
                else:
                    plot_col = voxel_y
                plot_row = voxel_z
                xyz = np.array([plot_col, plot_row, slice_index])
            elif slice_orientation == ViewDir.COR.dir:
                # assuming patient right is on the left of the screen, and patient inferior is at the bottom
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
            # TODO
            xyz = None

        return xyz
