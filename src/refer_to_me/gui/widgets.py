"""Spin box workaround for qfluentwidgets 1.11.x on Qt 6.12.

Qt 6.12 changed QAbstractSpinBox's internal geometry handling: combined with
qfluentwidgets' inline stepper layout (NoButtons + custom QHBoxLayout), the
internal line edit collapses to 1px wide, hiding the value. These subclasses
restore the edit field to the area left of the stepper buttons.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect
from qfluentwidgets import DoubleSpinBox as _FluentDoubleSpinBox
from qfluentwidgets import SpinBox as _FluentSpinBox

# Right-side stepper area: margin 4 + button 31 + spacing 5 + button 31 + gap 4.
_STEPPER_WIDTH = 75


class _SpinEditFix:
    def _init_spin_fix(self) -> None:
        self.lineEdit().installEventFilter(self)

    def _fix_line_edit(self) -> None:
        edit = self.lineEdit()
        want = QRect(1, 1, max(self.width() - _STEPPER_WIDTH, 10), self.height() - 2)
        if edit.geometry() != want:
            edit.setGeometry(want)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fix_line_edit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fix_line_edit()

    def eventFilter(self, obj, event):
        if obj is self.lineEdit() and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._fix_line_edit()
        return super().eventFilter(obj, event)


class SpinBox(_SpinEditFix, _FluentSpinBox):
    """Fluent SpinBox with the Qt 6.12 line-edit geometry fix."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_spin_fix()


class DoubleSpinBox(_SpinEditFix, _FluentDoubleSpinBox):
    """Fluent DoubleSpinBox with the Qt 6.12 line-edit geometry fix."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_spin_fix()
