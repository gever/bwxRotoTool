"""
color_picker.py  –  Custom color picker for bwxRotoTool
  • HSV color wheel (click/drag for hue + saturation)
  • Brightness/Value slider
  • Hex input field (type or paste a hex colour)
  • Up to 16 recent-colour swatches (persistent between calls via caller)
"""

import math

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QLineEdit, QPushButton, QSizePolicy,
)
from PyQt6.QtGui import (
    QColor, QPainter, QConicalGradient, QRadialGradient,
    QLinearGradient, QPen, QBrush, QPainterPath,
)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal


# ---------------------------------------------------------------------------
# Color Wheel
# ---------------------------------------------------------------------------
class ColorWheelWidget(QWidget):
    """Circular HSV wheel – click/drag to pick hue and saturation."""

    colorChanged = pyqtSignal(float, float)  # hue, sat  (0-1 each)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._h = 0.0   # hue 0-1
        self._s = 0.0   # saturation 0-1
        self._v = 1.0   # value/brightness 0-1 (owned by slider, mirrored here for rendering)
        self._dragging = False
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------------
    def _cr(self):
        """Return (cx, cy, radius) for current widget dimensions."""
        cx, cy = self.width() / 2, self.height() / 2
        return cx, cy, min(cx, cy) - 6

    # ------------------------------------------------------------------
    def set_hsv(self, h, s, v):
        self._h = max(0.0, min(1.0, h))
        self._s = max(0.0, min(1.0, s))
        self._v = max(0.0, min(1.0, v))
        self.update()

    def set_value(self, v):
        self._v = max(0.0, min(1.0, v))
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy, r = self._cr()

        # --- Clip to circle ---
        circle_path = QPainterPath()
        circle_path.addEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        p.setClipPath(circle_path)

        # --- Layer 1: hue conical gradient (72 stops for smooth blending) ---
        cg = QConicalGradient(cx, cy, 0)
        n_stops = 72
        for i in range(n_stops + 1):
            t = i / n_stops
            # QConicalGradient goes CCW visually, matching atan2 with flipped Y
            c = QColor.fromHsvF(t % 1.0, 1.0, self._v)
            cg.setColorAt(t, c)
        p.fillPath(circle_path, QBrush(cg))

        # --- Layer 2: radial white-to-transparent (desaturates toward centre) ---
        rg = QRadialGradient(cx, cy, r)
        rg.setColorAt(0.0, QColor(255, 255, 255, int(255 * self._v)))
        rg.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(circle_path, QBrush(rg))

        # --- Layer 3: darken for low brightness ---
        if self._v < 1.0:
            dark = QColor(0, 0, 0, int(255 * (1.0 - self._v)))
            p.fillPath(circle_path, QBrush(dark))

        # --- Selection cursor ring ---
        p.setClipping(False)
        angle_rad = self._h * 2 * math.pi
        sx = cx + self._s * r * math.cos(angle_rad)
        sy = cy - self._s * r * math.sin(angle_rad)   # minus: screen Y is down

        p.setPen(QPen(Qt.GlobalColor.black, 2.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(sx, sy), 9, 9)
        p.setPen(QPen(Qt.GlobalColor.white, 1.5))
        p.drawEllipse(QPointF(sx, sy), 9, 9)

    # ------------------------------------------------------------------
    def _pos_to_hs(self, pos):
        cx, cy, r = self._cr()
        dx = pos.x() - cx
        dy = pos.y() - cy          # screen Y (down = positive)
        dist = math.sqrt(dx * dx + dy * dy)
        # Use -dy so atan2 goes CCW visually (matching QConicalGradient)
        h = (math.degrees(math.atan2(-dy, dx)) + 360) % 360 / 360.0
        s = min(dist / r, 1.0) if r > 0 else 0.0
        return h, s

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._h, self._s = self._pos_to_hs(event.position())
            self.update()
            self.colorChanged.emit(self._h, self._s)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._h, self._s = self._pos_to_hs(event.position())
            self.update()
            self.colorChanged.emit(self._h, self._s)

    def mouseReleaseEvent(self, _event):
        self._dragging = False


# ---------------------------------------------------------------------------
# Value / Brightness Slider
# ---------------------------------------------------------------------------
class ValueSlider(QWidget):
    """Horizontal gradient slider controlling the V channel."""

    valueChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 1.0
        self._hue   = 0.0
        self._sat   = 1.0
        self._dragging = False
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    # ------------------------------------------------------------------
    _LEFT_MARGIN  = 12
    _RIGHT_MARGIN = 12

    def set_hue_sat(self, h, s):
        self._hue = h
        self._sat = s
        self.update()

    def set_value(self, v):
        self._value = max(0.0, min(1.0, v))
        self.update()

    # ------------------------------------------------------------------
    def _bar_rect(self):
        m = self._LEFT_MARGIN
        return QRectF(m, 6, self.width() - 2 * m, self.height() - 12)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        br = self._bar_rect()
        path = QPainterPath()
        path.addRoundedRect(br, 6, 6)

        full_color = QColor.fromHsvF(self._hue, self._sat, 1.0)
        lg = QLinearGradient(br.left(), 0, br.right(), 0)
        lg.setColorAt(0, QColor(0, 0, 0))
        lg.setColorAt(1, full_color)
        p.fillPath(path, QBrush(lg))

        # Thin border
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawPath(path)

        # Handle
        hx = br.left() + self._value * br.width()
        hy = br.top() + br.height() / 2
        thumb_color = QColor.fromHsvF(self._hue, self._sat, self._value)
        p.setPen(QPen(QColor(0, 0, 0, 180), 1.5))
        p.setBrush(QBrush(thumb_color))
        p.drawEllipse(QPointF(hx, hy), 9, 9)
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(hx, hy), 9, 9)

    def _pos_to_value(self, pos):
        br = self._bar_rect()
        v = (pos.x() - br.left()) / br.width() if br.width() > 0 else 0
        return max(0.0, min(1.0, v))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._value = self._pos_to_value(event.position())
            self.update()
            self.valueChanged.emit(self._value)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._value = self._pos_to_value(event.position())
            self.update()
            self.valueChanged.emit(self._value)

    def mouseReleaseEvent(self, _event):
        self._dragging = False


# ---------------------------------------------------------------------------
# Colour Swatch
# ---------------------------------------------------------------------------
class ColorSwatch(QWidget):
    """A small clickable colour square."""

    clicked = pyqtSignal(QColor)

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(color.name().upper())

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.setToolTip(color.name().upper())
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(2, 2, self.width() - 4, self.height() - 4), 5, 5)
        p.fillPath(path, QBrush(self._color))
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawPath(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._color)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------
_STYLE = """
QDialog {
    background: #1a1b2e;
    color: #c8d0e8;
}
QLabel {
    color: #9aa5c4;
    font-size: 11px;
    letter-spacing: 0.5px;
}
QLabel#sectionLabel {
    color: #6e7a9a;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
}
QLineEdit {
    background: #252638;
    color: #e2e8f8;
    border: 1px solid #383a5c;
    border-radius: 6px;
    padding: 5px 10px;
    font-family: "Courier New", monospace;
    font-size: 14px;
    selection-background-color: #4f6ed4;
}
QLineEdit:focus {
    border-color: #6c8ff0;
    background: #2c2f4a;
}
QPushButton {
    background: #2c2f4a;
    color: #c8d0e8;
    border: 1px solid #383a5c;
    border-radius: 7px;
    padding: 7px 20px;
    font-size: 12px;
}
QPushButton:hover {
    background: #353859;
    border-color: #4f6ed4;
}
QPushButton#okButton {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #4f6ed4, stop:1 #6c8ff0);
    color: #ffffff;
    border: none;
    font-weight: bold;
}
QPushButton#okButton:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #5a7ee0, stop:1 #7c9ff8);
}
"""


class ColorPickerDialog(QDialog):
    """
    Full custom colour picker.

    Parameters
    ----------
    initial_color : QColor   colour to start with
    history       : list[QColor]   up to 16 recent colours (oldest last)
    parent        : QWidget
    """

    def __init__(self, initial_color: QColor = None, history: list = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Color Picker")
        self.setModal(True)
        self.setMinimumWidth(310)
        self.setStyleSheet(_STYLE)

        self._color   = QColor(initial_color) if initial_color and initial_color.isValid() \
                        else QColor(0, 255, 0)
        self._history = list(history or [])
        self._result  = None   # set on accept

        self._build_ui()
        self._apply_color(self._color)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Color Wheel ──────────────────────────────────────────────
        self.wheel = ColorWheelWidget()
        self.wheel.colorChanged.connect(self._on_wheel_changed)
        root.addWidget(self.wheel)

        # ── Value Slider ─────────────────────────────────────────────
        val_label = QLabel("BRIGHTNESS")
        val_label.setObjectName("sectionLabel")
        root.addWidget(val_label)
        self.val_slider = ValueSlider()
        self.val_slider.valueChanged.connect(self._on_value_changed)
        root.addWidget(self.val_slider)

        # ── Preview + Hex ─────────────────────────────────────────────
        hex_row = QHBoxLayout()
        hex_row.setSpacing(8)

        # "Before" and "after" preview patches
        patches = QHBoxLayout()
        patches.setSpacing(0)

        self._before_patch = QLabel()
        self._before_patch.setFixedSize(40, 36)
        self._before_patch.setAutoFillBackground(True)
        self._before_patch.setToolTip("Original color")

        self._after_patch = QLabel()
        self._after_patch.setFixedSize(40, 36)
        self._after_patch.setAutoFillBackground(True)
        self._after_patch.setToolTip("New color")

        # Set both to the initial colour; _after_patch updates as user picks
        pal = self._before_patch.palette()
        pal.setColor(self._before_patch.backgroundRole(), self._color)
        self._before_patch.setPalette(pal)
        self._after_patch.setPalette(pal)

        patches.addWidget(self._before_patch)
        patches.addWidget(self._after_patch)
        hex_row.addLayout(patches)

        hex_row.addSpacing(6)
        hex_label = QLabel("#")
        hex_label.setStyleSheet("color:#6c8ff0; font-size:15px; font-weight:bold;")
        hex_row.addWidget(hex_label)
        self.hex_input = QLineEdit()
        self.hex_input.setMaxLength(6)
        self.hex_input.setFixedWidth(84)
        self.hex_input.setPlaceholderText("RRGGBB")
        self.hex_input.editingFinished.connect(self._on_hex_changed)
        hex_row.addWidget(self.hex_input)
        hex_row.addStretch()
        root.addLayout(hex_row)

        # ── Recent Colors ─────────────────────────────────────────────
        if self._history:
            hist_label = QLabel("RECENT")
            hist_label.setObjectName("sectionLabel")
            root.addWidget(hist_label)

            swatch_wrap = QHBoxLayout()
            swatch_wrap.setSpacing(4)
            self._swatches: list[ColorSwatch] = []
            for color in self._history[:16]:
                sw = ColorSwatch(color)
                sw.clicked.connect(self._apply_color)
                swatch_wrap.addWidget(sw)
                self._swatches.append(sw)
            swatch_wrap.addStretch()
            root.addLayout(swatch_wrap)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("okButton")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------ colour sync

    def _apply_color(self, color: QColor):
        """Master update: one colour in, all widgets updated."""
        self._color = QColor(color)
        h, s, v, _ = self._color.getHsvF()
        if h < 0:
            h = 0.0  # achromatic (grey)

        # Wheel
        self.wheel.blockSignals(True)
        self.wheel.set_hsv(h, s, v)
        self.wheel.blockSignals(False)

        # Value slider
        self.val_slider.blockSignals(True)
        self.val_slider.set_hue_sat(h, s)
        self.val_slider.set_value(v)
        self.val_slider.blockSignals(False)

        # Hex input
        self.hex_input.blockSignals(True)
        self.hex_input.setText(self._color.name()[1:].upper())  # strip '#'
        self.hex_input.blockSignals(False)

        # After-patch preview
        pal = self._after_patch.palette()
        pal.setColor(self._after_patch.backgroundRole(), self._color)
        self._after_patch.setPalette(pal)

    # ------------------------------------------------------------------ slots

    def _on_wheel_changed(self, h, s):
        """Wheel changed h+s; keep current v."""
        v = self.val_slider._value
        new_color = QColor.fromHsvF(h, s, v)
        # Update slider gradient without triggering feedback
        self.val_slider.blockSignals(True)
        self.val_slider.set_hue_sat(h, s)
        self.val_slider.blockSignals(False)
        # Update hex + preview only
        self._color = new_color
        self.hex_input.blockSignals(True)
        self.hex_input.setText(new_color.name()[1:].upper())
        self.hex_input.blockSignals(False)
        pal = self._after_patch.palette()
        pal.setColor(self._after_patch.backgroundRole(), new_color)
        self._after_patch.setPalette(pal)

    def _on_value_changed(self, v):
        """Slider changed v; keep current h+s from _color."""
        h, s, _, _ = self._color.getHsvF()
        if h < 0:
            h = 0.0
        new_color = QColor.fromHsvF(h, s, v)
        # Tell wheel to re-render at new brightness
        self.wheel.blockSignals(True)
        self.wheel.set_value(v)
        self.wheel.blockSignals(False)
        self._color = new_color
        self.hex_input.blockSignals(True)
        self.hex_input.setText(new_color.name()[1:].upper())
        self.hex_input.blockSignals(False)
        pal = self._after_patch.palette()
        pal.setColor(self._after_patch.backgroundRole(), new_color)
        self._after_patch.setPalette(pal)

    def _on_hex_changed(self):
        text = self.hex_input.text().strip()
        # Accept with or without leading '#'
        if not text.startswith('#'):
            text = '#' + text
        color = QColor(text)
        if color.isValid():
            self._apply_color(color)
        else:
            # Revert hex field to current valid colour
            self.hex_input.setText(self._color.name()[1:].upper())

    # ------------------------------------------------------------------ result

    def accept(self):
        self._result = QColor(self._color)
        super().accept()

    def selected_color(self) -> QColor | None:
        return self._result

    # ------------------------------------------------------------------ static helper

    @staticmethod
    def pick(initial_color: QColor = None, history: list = None, parent=None) -> QColor | None:
        """
        Open the dialog and return the chosen QColor,
        or None if cancelled.
        """
        dlg = ColorPickerDialog(initial_color, history, parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.selected_color()
        return None
