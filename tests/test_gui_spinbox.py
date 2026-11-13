"""Regression: qfluentwidgets spin boxes on Qt 6.12 collapse the line edit to 1px.

The gui.widgets subclasses must keep the value visible left of the steppers,
through resizes and value changes.
"""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from refer_to_me.gui.widgets import DoubleSpinBox, SpinBox


def test_spinbox_line_edit_visible(qapp):
    w = QWidget()
    layout = QVBoxLayout(w)
    spin = SpinBox(w)
    spin.setRange(0, 65535)
    spin.setValue(8765)
    layout.addWidget(spin)
    dbl = DoubleSpinBox(w)
    dbl.setRange(0.5, 1.0)
    dbl.setValue(0.5)
    layout.addWidget(dbl)
    w.resize(600, 200)
    w.show()
    qapp.processEvents()

    for box in (spin, dbl):
        geo = box.lineEdit().geometry()
        assert geo.width() == box.width() - 75
        assert geo.width() > 50
        assert geo.height() == box.height() - 2

    # survives container resize and value changes
    w.resize(800, 200)
    qapp.processEvents()
    spin.setValue(1234)
    dbl.setValue(0.85)
    qapp.processEvents()
    for box in (spin, dbl):
        assert box.lineEdit().geometry().width() == box.width() - 75
    assert spin.lineEdit().text() == "1234"
    w.close()
