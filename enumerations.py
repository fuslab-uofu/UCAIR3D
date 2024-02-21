""" enumerations.py
Part of the SPRITE package, a Simple Python Radiological Image viewing Tool
Author: Michelle Kline, UCAIR, University of Utah Department of Radiology and Imaging Sciences, 2023-2024

This module simply defines enumerations used in the SPRITE package.
"""

from enum import Enum


class ViewDir(Enum):
    """ This is an enumeration of the three orthogonal view orientations. Assumes RAS display convention. Axes chars
     are clockwise from the top. """
    AX = ("axial", ['A', 'L', 'P', 'R'])
    SAG = ("sagittal", ['S', 'P', 'I', 'A'])
    COR = ("coronal", ['S', 'L', 'I', 'R'])

    def __init__(self, dir_, chars_):
        self.dir = dir_
        self.chars = chars_


