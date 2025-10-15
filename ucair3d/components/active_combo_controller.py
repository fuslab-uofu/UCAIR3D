# active_combo_controller.py
from PyQt5 import QtCore, QtWidgets

class ActiveComboController(QtCore.QObject):
    """
    Make a set of QComboBoxes mutually 'active'. Whichever box the user interacts with
    becomes the 'active source'. This object emits signals so that the parent widget
    can react (e.g., push the selected image to one or more DisplaySettings widgets in LandMarker).

    Parameters
    ----------
    combos_by_name : dict[str, QComboBox]
        Mapping of a logical name (e.g. 'moving', 'fixed', 'overlay') to its QComboBox.

    Options
    -------
    highlight_active : bool
        When True, sets a dynamic property 'active-combo' on the current box (for QSS highlighting).

    Signals
    -------
    activeComboChanged(str)
        Emitted when the active source combo changes, with the logical role.
    """

    activeComboChanged = QtCore.pyqtSignal(str)

    def __init__(
        self,
        combos_by_name,
        *,
        highlight_active=True,
        parent=None,
    ):
        super().__init__(parent)
        self._combos_by_name = dict(combos_by_name or {})
        self._highlight_active = highlight_active
        self._active_combo = None

        for name, combo in self._combos_by_name.items():
            combo.installEventFilter(self)
            combo.currentIndexChanged.connect(lambda _ix, n=name: self.make_active(n))

        # Optional default: first combo in list becomes active (without applying selection yet)
        if self._combos_by_name:
            first_combo = next(iter(self._combos_by_name))
            self.make_active(first_combo, apply_now=False)

    # ---------------------------- Public API ----------------------------

    def make_active(self, name: str, *, apply_now: bool = True):
        """Programmatically set which combo is 'active'."""
        if name == self._active_combo:
            # if apply_now:
            #     self.apply_current(name)
            return
        self._active_combo = name
        self._update_highlight()
        self.activeComboChanged.emit(name)
        # if apply_now:
        #     self.apply_current(name)

    def active_combo(self) -> str:
        return self._active_combo

    # def apply_current(self, name: str):
    #     """Emit selection (and resolved image if resolver provided) for the given name."""
    #     combo = self._combos_by_name.get(name)
    #     if combo is None:
    #         return
    #
    #     raw_ix = combo.currentIndex()
    #     adj_ix = raw_ix - self._offsets.get(role, 0)
    #     current_text = combo.currentText() if raw_ix >= 0 else ""
    #
    #     # Emit selection info regardless of resolver
    #     self.activeSelectionChanged.emit(role, adj_ix, current_text)
    #
    #     # If there's a placeholder (adj_ix < 0), treat as "no image"
    #     if self._resolver is None or adj_ix < 0:
    #         return
    #
    #     # Resolve to your image object; LandMarker will decide what to do with it
    #     image_obj = None
    #     try:
    #         image_obj = self._resolver(role, adj_ix)
    #     except Exception:
    #         # Resolver errors shouldn't break GUI flow; swallow and skip image emit
    #         image_obj = None
    #
    #     if image_obj is not None:
    #         self.activeImageChanged.emit(image_obj, role)

    # -------------------------- Event handling --------------------------

    def eventFilter(self, obj, event):
        # Make the box active on mouse press or focus-in
        if isinstance(obj, QtWidgets.QComboBox):
            evtype = event.type()
            if evtype in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.FocusIn):
                name = self._name_for_combo(obj)
                if name:
                    self.make_active(name, apply_now=True)
        return super().eventFilter(obj, event)

    # --------------------------- Internals ------------------------------

    def _name_for_combo(self, combo):
        for name, c in self._combos_by_name.items():
            if c is combo:
                return name
        return None

    def _update_highlight(self):
        if not self._highlight_active:
            return
        # Clear
        for combo in self._combos_by_name.values():
            combo.setProperty("active-combo", False)
            combo.style().unpolish(combo)
            combo.style().polish(combo)
            combo.update()
        # Set
        active_combo = self._combos_by_name.get(self._active_combo)
        if active_combo:
            active_combo.setProperty("active-combo", True)
            active_combo.style().unpolish(active_combo)
            active_combo.style().polish(active_combo)
            active_combo.update()
