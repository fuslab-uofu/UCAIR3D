""" interaction_method.py
Part of the SPRITE package, a Simple Python Radiological Image viewing Tool
Author: Michelle Kline, UCAIR, University of Utah Department of Radiology and Imaging Sciences
2023-2024

This module defines the method to be used for interactive zooming and panning in a viewport.
A combination of a button and a modifier key is used to define the interaction method. For example, shift+left-click
might be used to pan, while ctrl+right-click might be used to zoom.
"""


class InteractionMethod:
    def __init__(self, button_, modifier_=None):
        self.valid_buttons = ["RIGHT", "LEFT", "MIDDLE"]  # middle is the scroll wheel
        self.valid_modifiers = ["shift", "ctrl", "alt"]

        if button_ not in self.valid_buttons:
            raise ValueError("Invalid button value: " + button_)

        if modifier_ is not None and modifier_ not in self.valid_modifiers:
            raise ValueError("Invalid modifier value: " + modifier_)

        self.button = button_
        self.modifier = modifier_
