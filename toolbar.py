from matplotlib.backends.backend_qt5 import NavigationToolbar2QT as NavigationToolbar
from PyQt5.QtWidgets import QToolButton, QActionGroup
from PyQt5.QtGui import QIcon


class Toolbar(NavigationToolbar):
    def __init__(self, canvas_, parent_):
        self.parent = parent_
        self.toolitems = (('Home', 'Reset Extent', 'home', 'home'),
                          (None, None, None, None),
                          ('Paintbrush', 'Enable Paintbrush Tool', ' ', 'on_paintbrush_clicked'),
                          (None, None, None, None),
                          ('Eraser', 'Enable Eraser Tool', ' ', 'on_eraser_clicked'),)

        NavigationToolbar.__init__(self, canvas_, parent_, False)  # False means do not show coords label

        buttons = self.findChildren(QToolButton)
        self.home_button = buttons[1]  # buttons[0] is blank - not sure why
        self.paintbrush_button = buttons[2]
        self.eraser_button = buttons[3]

        # self.setStyleSheet("background-color: #616161;")
        self.setStyleSheet("""
            QToolButton {
                padding: 1px;
                border-radius: 2px;
                background-color: #616161;
            }

            QToolButton:hover {
                border: 1px solid #ffaa00;
            }

            QToolButton:pressed {
                background-color: #ffaa00;
            }
            
            QToolButton:checked {
                background-color: #ffaa00;
            }

            QToolButton:disabled {
                color: #bdc3c7;
            }
        """)

        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)

        # overload the home action to make all viewports reset extent
        actions = self.actions()
        self.home_action = actions[0]
        self.home_action.triggered.connect(self.on_home_clicked)
        actions[2].setIcon(QIcon('..\\ui\\paintbrush_icon.png'))  # FIXME: make sure user is in src dir?
        actions[2].setCheckable(True)
        actions[2].setActionGroup(self.tool_group)
        actions[4].setIcon(QIcon('..\\ui\\eraser_icon.png'))  # FIXME: make sure user is in src dir?
        actions[4].setCheckable(True)
        actions[4].setActionGroup(self.tool_group)

    def on_home_clicked(self):
        if self.parent.initial_extent is not None:
            self.parent.ax.set_position(self.parent.initial_extent)
            self.parent.canvas.draw()
            self.parent.sync_extents(None)

    def on_paintbrush_clicked(self):
        if self.parent.parent.mode == 'paint':
            self.parent.parent.mode = 'idle'  # mode is at LATTE level, not viewport level
            self.paintbrush_button.setChecked(False)  # Uncheck the button

        else:
            self.parent.parent.mode = 'paint'  # mode is at LATTE level, not viewport level

    def on_eraser_clicked(self):
        if self.parent.parent.mode == 'erase':
            self.parent.parent.mode = 'idle'  # mode is at LATTE level, not viewport level
            self.eraser_button.setChecked(False)  # Uncheck the button
        else:
            self.parent.parent.mode = 'erase'  # mode is at LATTE level, not viewport level
