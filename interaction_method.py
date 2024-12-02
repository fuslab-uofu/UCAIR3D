""" interaction_method.py
Part of the SPRITE package, a Simple Python Radiological Image viewing Tool
Author: Michelle Kline, UCAIR, University of Utah Department of Radiology and Imaging Sciences
2023-2024

This module defines the optional method to be used for interacting with a Viewport.
A combination of a button and a modifier key is used to define the interaction method. For example, shift+left-click
might be used to pan, while ctrl+right-click might be used to zoom.
"""

from PyQt5.QtCore import Qt


class InteractionMethod:
    """This module defines an optional method for interacting with a Viewport.
       A combination of buttons and modifier keys can be used to define the interaction method.
       Examples:
            # Single button with a single modifier
            paint_im = InteractionMethod(Qt.LeftButton, Qt.ShiftModifier)

            # Multiple buttons with a single modifier
            paint_im = InteractionMethod([Qt.LeftButton, Qt.RightButton], Qt.ShiftModifier)

            # Single button with multiple modifiers
            paint_im = InteractionMethod(Qt.LeftButton, [Qt.ShiftModifier, Qt.ControlModifier])

            # Multiple buttons with multiple modifiers
            paint_im = InteractionMethod([Qt.LeftButton, Qt.MiddleButton], [Qt.ShiftModifier, Qt.ControlModifier])

            # Get readable names
            print("Buttons:", paint_im.get_button_names())
            print("Modifiers:", paint_im.get_modifier_names())
    """

    def __init__(self, _buttons, _modifiers=None):
        # Define dictionaries to map buttons and modifiers to their string names
        self.button_names = {
            Qt.LeftButton: "left",
            Qt.RightButton: "right",
            Qt.MiddleButton: "middle",
        }

        self.modifier_names = {
            Qt.ShiftModifier: "shift",
            Qt.ControlModifier: "ctrl",
            Qt.AltModifier: "alt",
        }

        # Define valid buttons and modifiers
        self.valid_buttons = list(self.button_names.keys())
        self.valid_modifiers = list(self.modifier_names.keys())

        # Ensure _buttons is a list (to support multiple buttons)
        if isinstance(_buttons, list):
            self.buttons = _buttons
        else:
            self.buttons = [_buttons]

        # Validate each button in the list
        for button in self.buttons:
            if button not in self.valid_buttons:
                raise ValueError(f"""Invalid button: {self.button_names.get(button, "unknown")}
                                     Valid buttons are: {list(self.button_names.values())}""")

        # Handle modifiers, ensuring it is a list
        if _modifiers is not None:
            if isinstance(_modifiers, list):
                self.modifiers = _modifiers
            else:
                self.modifiers = [_modifiers]

            # Validate each modifier in the list
            for modifier in self.modifiers:
                if modifier not in self.valid_modifiers:
                    raise ValueError(f"""Invalid modifier: {self.modifier_names.get(modifier, "unknown")}
                                         Valid modifiers are: {list(self.modifier_names.values())}""")
        else:
            self.modifiers = []

    def get_button_names(self):
        """Returns a list of button names for the current InteractionMethod instance."""
        return [self.button_names[btn] for btn in self.buttons]

    def get_modifier_names(self):
        """Returns a list of modifier names for the current InteractionMethod instance."""
        return [self.modifier_names[mod] for mod in self.modifiers]

    def matches_event(self, event):
        """Checks if the event matches the InteractionMethod's buttons and modifiers."""
        # Check if event button matches any button in self.buttons
        if event.button() not in self.buttons:
            return False

        # Check if event modifiers match all modifiers in self.modifiers
        for mod in self.modifiers:
            if not (event.modifiers() & mod):
                return False

        return True
