"""
"""

class InteractionMethod:
   def __init__(self, button_, modifier_=None):
      self.valid_buttons = ["RIGHT", "LEFT", "MIDDLE"]  # FIXME: wheel?
      self.valid_modifiers = ["shift", "ctrl", "alt"]

      if button_ not in self.valid_buttons:
         raise ValueError("Invalid button value: " + button_)

      if modifier_ is not None and modifier_ not in self.valid_modifiers:
         raise ValueError("Invalid modifier value: " + modifier_)

      self.button = button_
      self.modifier = modifier_


