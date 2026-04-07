import cv2
import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
                             QGraphicsPixmapItem, QFileDialog, QMessageBox, QProgressDialog,
                             QVBoxLayout, QHBoxLayout, QWidget, QLabel, QToolBar,
                             QGraphicsPolygonItem, QGraphicsEllipseItem, QGraphicsItem,
                             QGraphicsLineItem, QPushButton, QSizePolicy, QFrame,
                             QDialog, QDialogButtonBox, QRadioButton)

from PyQt6.QtGui import (QImage, QPixmap, QAction, QPolygonF, QPen, QBrush, QColor,
                         QKeySequence, QPainterPath, QPainter)
from PyQt6.QtCore import Qt, QPointF, QSizeF, QRectF, pyqtSignal

from color_picker import ColorPickerDialog
from video_processor import convert_to_15fps, flip_video
from project_model import RotoProject
from playback import PlaybackWindow

# ── Timeline bar ─────────────────────────────────────────────────────────────

class TimelineBar(QWidget):
    """
    A compact scrub bar showing:
      • A dark track spanning frame 0..N-1
      • A highlighted in→out region
      • Draggable in-point  (yellow left triangle)
      • Draggable out-point (yellow right triangle)
      • A playhead needle   (white vertical line + top dot)
      • Subtle tick marks for frames that have polygon data

    Signals
    -------
    frame_changed(int)   – user clicked/dragged the track → jump to frame
    in_changed(int)      – user dragged the in-point handle
    out_changed(int)     – user dragged the out-point handle
    """

    frame_changed = pyqtSignal(int)
    in_changed    = pyqtSignal(int)
    out_changed   = pyqtSignal(int)

    _HEIGHT      = 32
    _TRACK_H     = 10          # height of the coloured track band
    _HANDLE_W    = 10          # half-width of the triangle handle base
    _HIT_RADIUS  = 10          # px either side for handle hit-testing

    # colours
    _C_BG        = QColor(0x0e, 0x0f, 0x1e)
    _C_TRACK     = QColor(0x25, 0x26, 0x40)
    _C_RANGE     = QColor(0x2e, 0x50, 0x8a, 180)
    _C_TICK      = QColor(0x4c, 0xd9, 0x6e, 180)   # light green for drawn frames
    _C_IN        = QColor(0xf5, 0xc5, 0x18)   # yellow
    _C_OUT       = QColor(0xf5, 0xc5, 0x18)
    _C_PLAYHEAD  = QColor(0xff, 0xff, 0xff)
    _C_LABEL     = QColor(0x9a, 0xa5, 0xc4)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self._HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        self._total   = 0     # total_frames (0 = no video loaded)
        self._current = 0     # current playhead frame
        self._in      = 0     # in-point frame
        self._out     = 0     # out-point frame  (≡ total-1 when unset)
        self._has_data: set[int] = set()   # frames with polygon data for ticks

        self._drag: str | None = None   # "in" | "out" | "playhead" | "track"

    # ── public setters (called by RotoTool whenever state changes) ─────────

    def set_total(self, total: int):
        self._total = max(1, total)
        self.update()

    def set_current(self, frame: int):
        self._current = frame
        self.update()

    def set_in_out(self, in_f: int, out_f: int):
        self._in  = in_f
        self._out = out_f
        self.update()

    def set_data_frames(self, frames: set[int]):
        self._has_data = set(frames)
        self.update()

    # ── geometry helpers ────────────────────────────────────────────────────

    def _margin(self):
        return self._HANDLE_W + 4

    def _track_rect(self):
        m  = self._margin()
        cy = self._HEIGHT // 2
        return QRectF(m, cy - self._TRACK_H // 2,
                      self.width() - 2 * m, self._TRACK_H)

    def _frame_to_x(self, frame: int) -> float:
        tr = self._track_rect()
        if self._total <= 1:
            return tr.left()
        return tr.left() + (frame / (self._total - 1)) * tr.width()

    def _x_to_frame(self, x: float) -> int:
        tr = self._track_rect()
        if tr.width() <= 0:
            return 0
        t = (x - tr.left()) / tr.width()
        return int(round(max(0.0, min(1.0, t)) * (self._total - 1)))

    # ── hit testing ────────────────────────────────────────────────────────

    def _hit(self, x: float) -> str | None:
        if self._total <= 0:
            return None
        ix = self._frame_to_x(self._in)
        ox = self._frame_to_x(self._out)
        px = self._frame_to_x(self._current)
        if abs(x - px) <= self._HIT_RADIUS:
            return "playhead"
        if abs(x - ix) <= self._HIT_RADIUS:
            return "in"
        if abs(x - ox) <= self._HIT_RADIUS:
            return "out"
        tr = self._track_rect()
        if tr.left() - self._HANDLE_W <= x <= tr.right() + self._HANDLE_W:
            return "track"
        return None

    # ── painting ────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        if self._total <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._C_BG)

        tr  = self._track_rect()
        m   = self._margin()
        cy  = self._HEIGHT // 2

        # ── track background ──
        path = QPainterPath()
        path.addRoundedRect(tr, 3, 3)
        p.fillPath(path, self._C_TRACK)

        # ── in→out highlight ──
        ix = self._frame_to_x(self._in)
        ox = self._frame_to_x(self._out)
        rng = QRectF(ix, tr.top(), ox - ix, tr.height())
        if rng.width() > 0:
            rng_path = QPainterPath()
            rng_path.addRoundedRect(rng, 2, 2)
            p.fillPath(rng_path, self._C_RANGE)

        # ── per-frame data rectangles (light-green filled blocks) ──
        if self._total > 1 and self._has_data:
            px_per_frame = tr.width() / (self._total - 1)
            block_w = max(2.0, px_per_frame - 0.5)  # at least 2 px wide
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self._C_TICK))
            for f in self._has_data:
                fx = self._frame_to_x(f)
                rect = QRectF(fx - block_w / 2, tr.top() + 1, block_w, tr.height() - 2)
                p.drawRect(rect)

        # ── track border ──
        p.setPen(QPen(QColor(255, 255, 255, 25), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # ── in-point handle (left-pointing filled triangle) ──
        self._draw_in_handle(p, ix, cy)

        # ── out-point handle (right-pointing filled triangle) ──
        self._draw_out_handle(p, ox, cy)

        # ── playhead needle ──
        px = self._frame_to_x(self._current)
        p.setPen(QPen(self._C_PLAYHEAD, 1.5))
        p.drawLine(QPointF(px, tr.top() - 2), QPointF(px, tr.bottom() + 2))
        # top dot
        p.setBrush(QBrush(self._C_PLAYHEAD))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(px, tr.top() - 5), 4, 4)

    def _draw_in_handle(self, p: QPainter, x: float, cy: int):
        hw = self._HANDLE_W
        hh = self._TRACK_H + 4
        # Right-facing triangle (points right into the track)
        tri = QPolygonF([
            QPointF(x - hw, cy - hh // 2),
            QPointF(x,      cy),
            QPointF(x - hw, cy + hh // 2),
        ])
        p.setBrush(QBrush(self._C_IN))
        p.setPen(QPen(QColor(0, 0, 0, 80), 1))
        p.drawPolygon(tri)

    def _draw_out_handle(self, p: QPainter, x: float, cy: int):
        hw = self._HANDLE_W
        hh = self._TRACK_H + 4
        # Left-facing triangle (points left into the track)
        tri = QPolygonF([
            QPointF(x + hw, cy - hh // 2),
            QPointF(x,      cy),
            QPointF(x + hw, cy + hh // 2),
        ])
        p.setBrush(QBrush(self._C_OUT))
        p.setPen(QPen(QColor(0, 0, 0, 80), 1))
        p.drawPolygon(tri)

    # ── mouse interaction ───────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._total <= 0:
            return
        x = event.position().x()
        self._drag = self._hit(x)
        if self._drag in ("in", "playhead"):
            # Clicking the in-handle also jumps to that frame
            f = self._in if self._drag == "in" else self._current
            self.frame_changed.emit(f)
        elif self._drag == "out":
            self.frame_changed.emit(self._out)
        elif self._drag == "track":
            f = self._x_to_frame(x)
            self._current = f
            self.frame_changed.emit(f)
            self.update()

    def mouseMoveEvent(self, event):
        if self._drag is None or self._total <= 0:
            return
        f = self._x_to_frame(event.position().x())
        if self._drag == "in":
            f = max(0, min(f, self._out))
            self._in = f
            self.in_changed.emit(f)
            self.frame_changed.emit(f)
            self.update()
        elif self._drag == "out":
            f = max(self._in, min(f, self._total - 1))
            self._out = f
            self.out_changed.emit(f)
            self.frame_changed.emit(f)
            self.update()
        elif self._drag in ("playhead", "track"):
            f = max(0, min(f, self._total - 1))
            self._current = f
            self.frame_changed.emit(f)
            self.update()

    def mouseReleaseEvent(self, _event):
        self._drag = None


# ── Persistent colour palette bar ───────────────────────────────────────────

class PaletteSwatchButton(QWidget):
    """A single clickable colour swatch for the palette bar."""
    clicked = pyqtSignal(QColor)

    _SWATCH_SIZE = 28

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._active = False
        self.setFixedSize(self._SWATCH_SIZE + 4, self._SWATCH_SIZE + 4)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(color.name().upper())

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.setToolTip(color.name().upper())
        self.update()

    def set_active(self, active: bool):
        self._active = active
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._SWATCH_SIZE
        x = (self.width() - s) // 2
        y = (self.height() - s) // 2
        rect = QRectF(x, y, s, s)
        path = QPainterPath()
        path.addRoundedRect(rect, 5, 5)
        p.fillPath(path, QBrush(self._color))
        if self._active:
            p.setPen(QPen(QColor(255, 255, 255, 230), 2.5))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawPath(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._color)


class ColorPaletteBar(QWidget):
    """
    Persistent horizontal strip that lives below the menu bar.
    Shows the current active colour + up to 16 history swatches.
    Emits color_selected(QColor) when the user clicks a swatch.
    """
    color_selected = pyqtSignal(QColor)

    _MAX_HISTORY = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet(
            "ColorPaletteBar { background: #1a1b2e; border-bottom: 1px solid #2e3050; }"
        )
        self._history: list[QColor] = []
        self._active_color: QColor = QColor(0, 255, 0)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # "Active" swatch (current color) — slightly larger with a label
        active_label = QLabel("Color:")
        active_label.setStyleSheet("color: #6e7a9a; font-size: 10px; letter-spacing: 1px;")
        layout.addWidget(active_label)

        self._active_swatch = PaletteSwatchButton(self._active_color)
        self._active_swatch.set_active(True)
        self._active_swatch.clicked.connect(self.color_selected)
        layout.addWidget(self._active_swatch)

        # Thin separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #2e3050;")
        layout.addWidget(sep)

        # History swatches container (populated dynamically)
        self._history_swatches: list[PaletteSwatchButton] = []
        self._swatch_container = QWidget()
        self._swatch_layout = QHBoxLayout(self._swatch_container)
        self._swatch_layout.setContentsMargins(0, 0, 0, 0)
        self._swatch_layout.setSpacing(4)
        layout.addWidget(self._swatch_container)

        layout.addStretch()

        # "…" button to open the full picker
        self._more_btn = QPushButton("…")
        self._more_btn.setFixedSize(28, 28)
        self._more_btn.setToolTip("Open full color picker  (Ctrl+P)")
        self._more_btn.setStyleSheet(
            "QPushButton { background: #252638; color: #9aa5c4; border: 1px solid #383a5c;"
            "  border-radius: 6px; font-size: 14px; padding: 0; }"
            "QPushButton:hover { background: #353859; border-color: #4f6ed4; }"
        )
        layout.addWidget(self._more_btn)

    # ------------------------------------------------------------------ public

    @property
    def more_button(self) -> QPushButton:
        return self._more_btn

    def set_active_color(self, color: QColor):
        """Update the prominent active-color swatch."""
        self._active_color = QColor(color)
        self._active_swatch.set_color(color)

    def set_history(self, history: list[QColor]):
        """Rebuild the history swatches from the given list."""
        self._history = list(history[: self._MAX_HISTORY])

        # Remove old widgets
        for sw in self._history_swatches:
            self._swatch_layout.removeWidget(sw)
            sw.deleteLater()
        self._history_swatches.clear()

        for color in self._history:
            sw = PaletteSwatchButton(color)
            sw.clicked.connect(self.color_selected)
            self._swatch_layout.addWidget(sw)
            self._history_swatches.append(sw)


# ── Registration crosshair marker ────────────────────────────────────────────

class RegistrationMarkerItem(QGraphicsItem):
    """Draggable ⊕ crosshair that marks the per-frame registration point.
    Always rendered at a fixed screen size regardless of zoom level."""

    RADIUS = 12
    # Store as plain tuple — QColor must NOT be created before QApplication exists
    _COLOR_RGB = (255, 220, 0)   # bright yellow

    def __init__(self, on_moved=None):
        super().__init__()
        self._on_moved = on_moved   # callback(x, y) in scene coordinates
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
            QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        )
        self.setZValue(9999)   # always on top
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip("Registration Point — drag to set the character anchor for this frame")

    def boundingRect(self):
        r = self.RADIUS + 2
        from PyQt6.QtCore import QRectF
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter, _option, _widget=None):
        r = self.RADIUS
        color = QColor(*self._COLOR_RGB)
        pen_outer = QPen(QColor(0, 0, 0, 160), 3)
        pen_inner = QPen(color, 2)

        # Shadow ring
        painter.setPen(pen_outer)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), r, r)
        painter.drawLine(QPointF(-r - 4, 0), QPointF(r + 4, 0))
        painter.drawLine(QPointF(0, -r - 4), QPointF(0, r + 4))

        # Bright crosshair
        painter.setPen(pen_inner)
        painter.drawEllipse(QPointF(0, 0), r, r)
        painter.drawLine(QPointF(-r - 4, 0), QPointF(r + 4, 0))
        painter.drawLine(QPointF(0, -r - 4), QPointF(0, r + 4))

        # Centre dot
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(0, 0), 3, 3)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self._on_moved:
                self._on_moved(value.x(), value.y())
        return super().itemChange(change, value)



# ── Vertex / polygon items ────────────────────────────────────────────────────

class VertexHandleItem(QGraphicsEllipseItem):
    def __init__(self, x, y, w, h, parent_poly, index):
        super().__init__(x, y, w, h, parent_poly)
        self.parent_poly = parent_poly
        self.index = index
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges |
                      QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setBrush(QBrush(QColor(255, 0, 0)))
        self.setPen(QPen(Qt.GlobalColor.black))

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # When dragged, tell parent polygon to adjust the point behind the scenes
            self.parent_poly.update_handle_pos(self.index, value)
        return super().itemChange(change, value)

class RotoPolygonItem(QGraphicsPolygonItem):
    def __init__(self, poly_dict, parent=None, fill_alpha=100):
        super().__init__(parent)
        self.poly_dict = poly_dict.copy()
        
        points = [QPointF(x, y) for x, y in self.poly_dict.get("points", [])]
        self.setPolygon(QPolygonF(points))
        
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.color = QColor(self.poly_dict.get("color", "#00ff00"))
        
        self.setBrush(QBrush(QColor(self.color.red(), self.color.green(), self.color.blue(), fill_alpha)))
        self.setPen(QPen(self.color, 2))
        
        self.z_val = max(1, self.poly_dict.get("z_index", 1))
        self.setZValue(self.z_val)
        
        self.handles = []

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            is_selected = value
            if is_selected:
                if self.scene() and hasattr(self.scene(), "main_window"):
                    if self.scene().main_window.active_edit_item != self:
                        self.scene().main_window.enter_edit_mode(self)
        return super().itemChange(change, value)

    def show_handles(self):
        poly = self.polygon()
        for i in range(poly.count()):
            pt = poly.at(i)
            r = 8
            # The rect is drawn around 0,0 locally, placed at pt
            handle = VertexHandleItem(-r/2, -r/2, r, r, self, i)
            handle.setPos(pt)
            self.handles.append(handle)

    def hide_handles(self):
        scene = self.scene()
        for h in self.handles:
            if scene:
                scene.removeItem(h)
            elif h.scene():
                h.scene().removeItem(h)
        self.handles.clear()

    def update_handle_pos(self, index, new_pos):
        poly = self.polygon()
        poly.replace(index, new_pos)
        self.setPolygon(poly)

    def get_dict(self):
        poly = self.polygon()
        # Use mapToScene so coordinates are correct even after the item has been
        # dragged (moving the item changes pos(), not the raw polygon points).
        points = [[self.mapToScene(poly.at(i)).x(), self.mapToScene(poly.at(i)).y()]
                  for i in range(poly.count())]
        self.poly_dict["points"] = points
        self.poly_dict["color"] = self.color.name()
        self.poly_dict["z_index"] = self.z_val
        return self.poly_dict

class RotoScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None

    def mousePressEvent(self, event):
        # Prevent picking/dropping points if the user is panning (shift)
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            super().mousePressEvent(event)
            return

        if self.main_window:
            # If we are in the middle of drawing a polygon, ignore existing item selection
            if self.main_window.mode == "DRAW" and len(self.main_window.current_points) > 0:
                self.main_window.scene_mousePressEvent(event)
                event.accept()
                return

            if self.main_window.mode == "EDIT":
                # Ctrl+click → insert a vertex on the nearest edge (FEAT16)
                if (event.button() == Qt.MouseButton.LeftButton
                        and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                    self.main_window._try_insert_vertex(event.scenePos())
                    event.accept()
                    return

                # Plain click on the background → leave edit mode
                item = self.itemAt(event.scenePos(), self.main_window.view.transform())
                if item == self.main_window.bg_item:
                    self.main_window.leave_edit_mode(save=True)
                    event.accept()
                    return

            super().mousePressEvent(event)
            self.main_window.scene_mousePressEvent(event)
        else:
            super().mousePressEvent(event)



class RotoGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(self.renderHints() | self.renderHints().Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._is_panning = False
        self._zoom_factor = 1.1

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.scale(self._zoom_factor, self._zoom_factor)
        else:
            self.scale(1 / self._zoom_factor, 1 / self._zoom_factor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self._is_panning = True
            super().mousePressEvent(event)
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_panning:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self._is_panning = False
            super().mouseReleaseEvent(event)
        else:
            super().mouseReleaseEvent(event)
            
    def zoom_in(self):
        self.scale(self._zoom_factor, self._zoom_factor)

    def zoom_out(self):
        self.scale(1 / self._zoom_factor, 1 / self._zoom_factor)

    def reset_zoom(self):
        self.resetTransform()

    def zoom_to_fit(self):
        if self.scene():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

class RotoTool(QMainWindow):
    def __init__(self, initial_video=None):
        super().__init__()
        self.setWindowTitle("Antigravity Roto-Tool [15 FPS]")
        self.resize(1024, 768)

        self.project = RotoProject()
        self.cap = None
        self.current_game_frame = 0
        self.total_frames = 0
        self.current_project_file = None

        # Draw vs Edit state
        self.mode = "DRAW"
        self.active_edit_item = None

        # UI Setup
        self.scene = RotoScene()
        self.scene.main_window = self
        
        self.view = RotoGraphicsView(self.scene)
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.setCentralWidget(self.view)
        
        self.bg_item = QGraphicsPixmapItem()
        self.bg_item.setZValue(-1)
        self.scene.addItem(self.bg_item)

        # ── Palette bar (persistent, lives between menu and canvas) ──────────
        self.palette_bar = ColorPaletteBar()
        self.palette_bar.color_selected.connect(self._on_palette_color_selected)
        self.palette_bar.more_button.clicked.connect(self._open_picker_from_bar)

        # ── Timeline bar (below palette, above canvas) ────────────────────────
        self.timeline_bar = TimelineBar()
        self.timeline_bar.frame_changed.connect(self._on_timeline_frame)
        self.timeline_bar.in_changed.connect(self._on_timeline_in)
        self.timeline_bar.out_changed.connect(self._on_timeline_out)

        # Wrap the view + palette bar in a container so the palette sits above
        # the canvas without going into the status bar.
        _central = QWidget()
        _vbox = QVBoxLayout(_central)
        _vbox.setContentsMargins(0, 0, 0, 0)
        _vbox.setSpacing(0)
        _vbox.addWidget(self.palette_bar)
        _vbox.addWidget(self.timeline_bar)
        _vbox.addWidget(self.view)
        self.setCentralWidget(_central)

        # Status Label
        self.status_label = QLabel("Frame: 0 / 0 | DRAW MODE")
        self.statusBar().addWidget(self.status_label)

        # Drawing state
        self.current_points = []
        self.temp_polygon_item = None
        self.temp_dots = []
        self.current_polygon_color = QColor(0, 255, 0)
        self.opaque_fill = False   # Space toggles transparent ↔ opaque fill
        self.palette_bar.set_active_color(self.current_polygon_color)

        # Copy buffer: holds a polygon dict ready to paste
        self.copy_buffer: dict | None = None

        # Onion-skin mode: None | "prev" | "both"
        self.onion_mode: str | None = None

        # Color history (up to 16, most recent first)
        self.color_history: list[QColor] = []

        # Registration marker state
        self.reg_marker: RegistrationMarkerItem | None = None
        self.show_registration = True   # toggled via View menu
        self._placing_reg_marker = False   # guard against setPos → itemChange → redraw loop

        # Playback window (keeps a reference so it isn't garbage-collected)
        self._playback_window: PlaybackWindow | None = None

        # Unsaved-changes flag
        self._dirty = False

        self._create_actions()
        self._create_menu()
        
        if initial_video and os.path.exists(initial_video):
            self.load_video(initial_video)
        else:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, self.check_last_project)

    def check_last_project(self):
        settings_path = os.path.expanduser("~/.bwxrototool")
        if os.path.exists(settings_path):
            try:
                import json
                with open(settings_path, "r") as f:
                    data = json.load(f)
                # Restore colour history
                for hex_str in data.get("color_history", []):
                    c = QColor(hex_str)
                    if c.isValid():
                        self.color_history.append(c)
                # Sync palette bar with restored history
                self.palette_bar.set_history(self.color_history)
                last_proj = data.get("last_project")
                if last_proj and os.path.exists(last_proj):
                    reply = QMessageBox.question(self, "Resume Last Project", f"Would you like to resume your last project?\n\n{last_proj}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if reply == QMessageBox.StandardButton.Yes:
                        self.load_project_file(last_proj)
            except Exception:
                pass

    def save_settings(self):
        settings_path = os.path.expanduser("~/.bwxrototool")
        try:
            import json
            data = {}
            if self.current_project_file:
                data["last_project"] = self.current_project_file
            data["color_history"] = [c.name() for c in self.color_history[:16]]
            with open(settings_path, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _create_actions(self):
        self.open_video_action = QAction("Open Video...", self)
        self.open_video_action.triggered.connect(self.open_video)
        
        self.open_project_action = QAction("Open Project...", self)
        self.open_project_action.triggered.connect(self.open_project)
        
        self.save_project_action = QAction("Save Project", self)
        self.save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_project_action.triggered.connect(self.save_project)

        self.save_project_as_action = QAction("Save Project As...", self)
        self.save_project_as_action.triggered.connect(self.save_project_as)
        
        self.export_bwx_action = QAction("Export to bwxBASIC ARRAY...", self)
        self.export_bwx_action.triggered.connect(self.export_bwxbasic)

        self.export_json_action = QAction("Export Polygon Data as JSON...", self)
        self.export_json_action.setToolTip("Export all frames as a clean JSON file (for p5.js or other tools)")
        self.export_json_action.triggered.connect(self.export_json)

        self.import_json_action = QAction("Import Polygon Data from JSON...", self)
        self.import_json_action.setToolTip("Import polygon data from a bwxRotoTool JSON export")
        self.import_json_action.triggered.connect(self.import_json_data)
        
        self.clear_frame_action = QAction("Clear Current Frame", self)
        self.clear_frame_action.triggered.connect(self.clear_current_frame)

        self.zoom_in_action = QAction("Zoom In", self)
        self.zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.zoom_in_action.triggered.connect(self.view.zoom_in)

        self.zoom_out_action = QAction("Zoom Out", self)
        self.zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.zoom_out_action.triggered.connect(self.view.zoom_out)

        self.zoom_reset_action = QAction("Reset Zoom", self)
        self.zoom_reset_action.setShortcut("Ctrl+0")
        self.zoom_reset_action.triggered.connect(self.view.reset_zoom)
        
        self.zoom_fit_action = QAction("Zoom to Fit", self)
        self.zoom_fit_action.setShortcut("Ctrl+F")
        self.zoom_fit_action.triggered.connect(self.view.zoom_to_fit)

        # Registration visibility toggle
        self.show_reg_action = QAction("Show Registration Point", self)
        self.show_reg_action.setCheckable(True)
        self.show_reg_action.setChecked(True)
        self.show_reg_action.setShortcut("Ctrl+Shift+R")
        self.show_reg_action.triggered.connect(self._toggle_reg_visibility)

        # Playback window
        self.open_playback_action = QAction("Open Playback Preview", self)
        self.open_playback_action.setShortcut("Ctrl+Shift+P")
        self.open_playback_action.triggered.connect(self._open_playback_window)

        # Tools
        self.estimate_registration_action = QAction("Estimate Registration", self)
        self.estimate_registration_action.setShortcut("Ctrl+Shift+E")
        self.estimate_registration_action.setToolTip(
            "Set the registration point to the centroid of the currently drawn vertices"
        )
        self.estimate_registration_action.triggered.connect(self.estimate_registration)

        self.set_in_point_action = QAction("Set In-point", self)
        self.set_in_point_action.setShortcut("I")
        self.set_in_point_action.setToolTip("Set the In-point to the current frame")
        self.set_in_point_action.triggered.connect(self._set_in_point)

        self.set_out_point_action = QAction("Set Out-point", self)
        self.set_out_point_action.setShortcut("E")
        self.set_out_point_action.setToolTip("Set the Out-point to the current frame")
        self.set_out_point_action.triggered.connect(self._set_out_point)

        # Video transforms
        self.flip_h_action = QAction("Flip Horizontally", self)
        self.flip_h_action.setToolTip(
            "Mirror the video left-to-right and update all polygon/registration data"
        )
        self.flip_h_action.triggered.connect(self.flip_horizontal)

    def _create_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        file_menu.addAction(self.open_video_action)
        file_menu.addSeparator()
        file_menu.addAction(self.open_project_action)
        file_menu.addAction(self.save_project_action)
        file_menu.addAction(self.save_project_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_bwx_action)
        file_menu.addAction(self.export_json_action)
        file_menu.addSeparator()
        file_menu.addAction(self.import_json_action)
        
        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction(self.clear_frame_action)

        view_menu = menubar.addMenu("View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.zoom_reset_action)
        view_menu.addAction(self.zoom_fit_action)
        view_menu.addSeparator()
        view_menu.addAction(self.show_reg_action)

        tools_menu = menubar.addMenu("Tools")
        tools_menu.addAction(self.estimate_registration_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.set_in_point_action)
        tools_menu.addAction(self.set_out_point_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.flip_h_action)

        window_menu = menubar.addMenu("Window")
        window_menu.addAction(self.open_playback_action)

    def open_video(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Video Files (*.mp4 *.MP4 *.mov *.MOV *.avi *.AVI *.mkv *.MKV *.webm *.WEBM)")
        if filepath:
            progress = QProgressDialog("Processing video to 15 FPS...", "Cancel", 0, 0, self)
            progress.setWindowTitle("Processing")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()
            QApplication.processEvents()
            
            out_file, err = convert_to_15fps(filepath)
            progress.close()
            
            if out_file:
                self.project = RotoProject()
                self.project.video_path = out_file
                self.load_video(out_file)
            else:
                QMessageBox.critical(self, "Video Load Failed", err or "Unknown error during video conversion.")

    def load_video(self, filepath):
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(filepath)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.current_game_frame = 0
        self.project.video_path = filepath
        self.setWindowTitle(f"Antigravity Roto-Tool - {os.path.basename(filepath)}")
        self.current_points = []
        self.view.resetTransform()
        self._update_timeline()
        self.update_frame()
        
    def open_project(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Roto Files (*.bwxroto *.json)")
        if filepath:
            self.load_project_file(filepath)

    def load_project_file(self, filepath):
        self.project = RotoProject()
        try:
            self.project.load(filepath)
            self.current_project_file = filepath
            self._dirty = False   # freshly loaded project has no unsaved changes
            
            if self.project.video_path and os.path.exists(self.project.video_path):
                self.load_video(self.project.video_path)
                # Restore the saved frame position
                saved_frame = max(0, min(self.project.last_frame, self.total_frames - 1))
                if saved_frame != 0:
                    self.current_game_frame = saved_frame
                    self.update_frame()
            self.save_settings()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load project: {e}")

    def save_project(self):
        if self.current_project_file:
            self.project.last_frame = self.current_game_frame
            self.project.save(self.current_project_file)
            self._dirty = False
            self.set_status("Saved")
            self.save_settings()
        else:
            self.save_project_as()
            
    def save_project_as(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "Roto Files (*.bwxroto)")
        if filepath:
            if not filepath.endswith('.bwxroto'):
                filepath += '.bwxroto'
            self.project.last_frame = self.current_game_frame
            self.project.save(filepath)
            self.current_project_file = filepath
            self._dirty = False
            self.set_status("Saved")
            self.save_settings()

    def export_bwxbasic(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Export bwxBASIC", "", "Text Files (*.bas *.txt)")
        if filepath:
            if not filepath.endswith('.bas') and not filepath.endswith('.txt'):
                filepath += '.bas'
            self.project.export_bwxbasic(filepath)

    def export_json(self):
        """Export all polygon + registration data to a clean JSON file."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Polygon Data as JSON", "", "JSON Files (*.json)"
        )
        if not filepath:
            return
        if not filepath.endswith('.json'):
            filepath += '.json'
        try:
            self.project.export_json(filepath)
            n_frames = len(self.project.frames)
            self.set_status(f"Exported {n_frames} frame(s) to {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not write JSON:\n{e}")

    def import_json_data(self):
        """Import polygon data from a JSON file, prompting the user to choose a merge strategy."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Polygon Data from JSON", "", "JSON Files (*.json)"
        )
        if not filepath:
            return

        # Ask how to merge
        dialog = QDialog(self)
        dialog.setWindowTitle("Import — Choose Merge Strategy")
        layout = QVBoxLayout(dialog)

        info = QLabel(
            "How should the imported data be merged with the current project?\n"
            f"File: {os.path.basename(filepath)}"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        rb_replace = QRadioButton("Replace all  — discard current polygon data and replace entirely")
        rb_merge   = QRadioButton("Merge        — keep existing frames; only add frames not yet present")
        rb_overwrite = QRadioButton("Overwrite    — add all frames, overwriting any that already exist")
        rb_replace.setChecked(True)
        layout.addWidget(rb_replace)
        layout.addWidget(rb_merge)
        layout.addWidget(rb_overwrite)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if rb_replace.isChecked():
            strategy = "replace"
        elif rb_merge.isChecked():
            strategy = "merge"
        else:
            strategy = "overwrite"

        try:
            imported, skipped = self.project.import_json(filepath, merge=strategy)
            self._dirty = True
            self.redraw_polygons()
            self._update_timeline()
            detail = f"{imported} frame(s) imported"
            if skipped:
                detail += f", {skipped} frame(s) {'overwritten' if strategy == 'overwrite' else 'skipped (already present)'}"
            self.set_status(f"JSON import complete — {detail}")
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"Could not import JSON:\n{e}")

    def update_frame(self):
        if not self.cap or self.total_frames == 0:
            return
            
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_game_frame)
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            img = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
            self.bg_item.setPixmap(QPixmap.fromImage(img))
            self.scene.setSceneRect(0, 0, w, h)
            self._video_size = QSizeF(w, h)   # remember for playback window

            # Auto-seed registration from the nearest previous frame so the
            # crosshair doesn't jump back to (0,0) when advancing to an unset frame.
            if self.current_game_frame not in self.project.registrations:
                inherited = self.project.get_nearest_registration(self.current_game_frame)
                if inherited != [0.0, 0.0]:
                    self.project.set_registration(self.current_game_frame, inherited[0], inherited[1])

            self.leave_edit_mode(save=False) # Safely drop unsaved drawing or editing when scrubbing frames
            self.redraw_polygons()
            self.timeline_bar.set_current(self.current_game_frame)

            
    def clear_current_frame(self):
        self.project.clear_frame(self.current_game_frame)
        self._dirty = True
        self.current_points = []
        self.redraw_polygons()
            
    def _draw_onion_skins(self):
        """Render ghost polygons from neighbouring frames, aligned by registration point."""
        if not self.onion_mode:
            return
        frames_to_show = []
        if self.onion_mode in ("prev", "both") and self.current_game_frame > 0:
            frames_to_show.append((self.current_game_frame - 1, QColor(255, 80, 80)))   # red-tinted
        if self.onion_mode == "both" and self.current_game_frame < self.total_frames - 1:
            frames_to_show.append((self.current_game_frame + 1, QColor(80, 80, 255)))   # blue-tinted

        cur_reg = self.project.get_registration(self.current_game_frame)
        cur_rx, cur_ry = cur_reg[0], cur_reg[1]

        for frame_idx, tint in frames_to_show:
            ghost_reg = self.project.get_registration(frame_idx)
            # Compute shift so the ghost character's anchor aligns to the current anchor
            dx = cur_rx - ghost_reg[0]
            dy = cur_ry - ghost_reg[1]

            for poly_dict in self.project.get_polygons(frame_idx):
                pts = poly_dict.get("points", [])
                if len(pts) > 2:
                    qpoly = QPolygonF([QPointF(x + dx, y + dy) for x, y in pts])
                    ghost = self.scene.addPolygon(
                        qpoly,
                        QPen(tint, 1, Qt.PenStyle.DashLine),
                        QBrush(QColor(tint.red(), tint.green(), tint.blue(), 40))
                    )
                    # Ghost polygons must not intercept any mouse events (BUG03)
                    ghost.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                    ghost.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)


    def _place_registration_marker(self):
        """Remove any existing reg marker and add a fresh one at the current frame's registration."""
        # Remove old marker if present
        if self.reg_marker is not None:
            if self.reg_marker.scene():
                self.scene.removeItem(self.reg_marker)
            self.reg_marker = None

        if not self.show_registration or not self.cap:
            return

        reg = self.project.get_registration(self.current_game_frame)
        marker = RegistrationMarkerItem(on_moved=self._on_registration_moved)
        # Guard: setPos fires itemChange → _on_registration_moved; we must not
        # treat this programmatic move as a user drag (would cause infinite recursion
        # when onion-skinning is active).
        self._placing_reg_marker = True
        try:
            marker.setPos(QPointF(reg[0], reg[1]))
        finally:
            self._placing_reg_marker = False
        self.scene.addItem(marker)
        self.reg_marker = marker

    def _on_registration_moved(self, x: float, y: float):
        """Called when the user drags the registration marker."""
        # Ignore position changes that originate from our own setPos call inside
        # _place_registration_marker — those are not user drags.
        if self._placing_reg_marker:
            return
        self.project.set_registration(self.current_game_frame, x, y)
        self._dirty = True
        # Update onion skins live so the alignment shifts in real time.
        # IMPORTANT: defer via singleShot so we do NOT call redraw_polygons()
        # synchronously while a drag is in progress — redraw removes all scene
        # items including the marker currently being dragged, which causes Qt to
        # segfault when it tries to continue the drag on the deleted item.
        if self.onion_mode:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self.redraw_polygons)

    def _toggle_reg_visibility(self):
        self.show_registration = self.show_reg_action.isChecked()
        self._place_registration_marker()

    def estimate_registration(self):
        """Set the current frame's registration point to the centroid of all
        visible vertices on the current frame: committed polygons + any
        in-progress drawn points.  Does nothing if there are no vertices."""
        all_points: list[list[float]] = []

        # 1. Vertices from committed polygons on this frame
        for poly_dict in self.project.get_polygons(self.current_game_frame):
            all_points.extend(poly_dict.get("points", []))

        # 2. In-progress (not yet committed) drawn vertices
        all_points.extend(self.current_points)

        if not all_points:
            self.set_status("Estimate Registration: no vertices on this frame — registration unchanged")
            return

        avg_x = sum(p[0] for p in all_points) / len(all_points)
        avg_y = sum(p[1] for p in all_points) / len(all_points)

        self.project.set_registration(self.current_game_frame, avg_x, avg_y)
        self._dirty = True

        # Move the on-screen marker to match
        if self.reg_marker is not None:
            self.reg_marker.setPos(QPointF(avg_x, avg_y))
        else:
            self._place_registration_marker()

        self.set_status(
            f"Registration estimated at ({avg_x:.1f}, {avg_y:.1f}) "
            f"from {len(all_points)} vertices"
        )

    def _set_in_point(self):
        """Set the In-point to the current frame."""
        if not self.cap:
            return
        self.project.start_frame = self.current_game_frame
        end = self.project.end_frame if self.project.end_frame is not None else self.total_frames - 1
        if end < self.project.start_frame:
            self.project.end_frame = self.project.start_frame
        out_f = self.project.end_frame if self.project.end_frame is not None else self.total_frames - 1
        self.timeline_bar.set_in_out(self.project.start_frame, out_f)
        self.set_status(f"In-point set: frame {self.project.start_frame}")

    def _set_out_point(self):
        """Set the Out-point to the current frame."""
        if not self.cap:
            return
        self.project.end_frame = self.current_game_frame
        if self.project.start_frame > self.project.end_frame:
            self.project.start_frame = self.project.end_frame
        self.timeline_bar.set_in_out(self.project.start_frame, self.project.end_frame)
        self.set_status(f"Out-point set: frame {self.project.end_frame}")

    def flip_horizontal(self):
        """Flip the current video horizontally and mirror all polygon/registration data."""
        if not self.cap:
            QMessageBox.information(self, "No Video", "Please open a video project first.")
            return

        reply = QMessageBox.question(
            self,
            "Flip Horizontally",
            "This will re-encode the video file and mirror all polygon data.\n"
            "The original video file will be preserved with its current name.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Capture video width before we tear down the capture
        video_width = self.scene.sceneRect().width()

        src_path = self.project.video_path

        progress = QProgressDialog("Flipping video horizontally…", None, 0, 0, self)
        progress.setWindowTitle("Processing")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        out_path, err = flip_video(src_path, direction="hflip")
        progress.close()

        if not out_path:
            QMessageBox.critical(self, "Flip Failed", err or "Unknown error during flip.")
            return

        # Mirror all stored polygon and registration coordinates
        self.project.flip_horizontal(video_width)

        # Point the project to the new (flipped) video and reload
        self.project.video_path = out_path
        self.load_video(out_path)
        self._dirty = True
        self.set_status("Video flipped horizontally — remember to save your project")

    def _open_playback_window(self):
        if not self.cap:
            QMessageBox.information(self, "No Video", "Please open a video project first.")
            return
        video_size = getattr(self, "_video_size", QSizeF(640, 480))
        if self._playback_window is None or not self._playback_window.isVisible():
            self._playback_window = PlaybackWindow(
                self.project, self.total_frames, video_size, parent=self
            )
        else:
            # Refresh in case the project changed
            self._playback_window.update_project(self.project, self.total_frames, video_size)
        self._playback_window.show()
        self._playback_window.raise_()

    def closeEvent(self, event):
        if self._dirty:
            name = os.path.basename(self.current_project_file) if self.current_project_file else "Untitled"
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                f"'{name}' has unsaved changes.\n\nSave before closing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                self.save_project()
                # If still dirty after save attempt (e.g. Save As was cancelled), abort close
                if self._dirty:
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        event.accept()

    def redraw_polygons(self):
        for item in self.scene.items():
            if item != self.bg_item:
                self.scene.removeItem(item)
        self.reg_marker = None  # we just removed it; _place_registration_marker will recreate

        # Onion skins first (sit below live polys)
        self._draw_onion_skins()
                
        # Draw committed polygons via our new smart objects
        polys_dict_list = self.project.get_polygons(self.current_game_frame)
        fill_alpha = 255 if self.opaque_fill else 100
        for poly_dict in polys_dict_list:
            if len(poly_dict.get("points", [])) > 2:
                poly_item = RotoPolygonItem(poly_dict, fill_alpha=fill_alpha)
                self.scene.addItem(poly_item)
            
        # Draw current points (in-progress drawing mode)
        self.temp_polygon_item = None
        self.temp_dots = []
        if self.current_points:
            pen = QPen(self.current_polygon_color, 2)
            brush = QBrush(self.current_polygon_color)
            for x, y in self.current_points:
                dot = self.scene.addEllipse(x-3, y-3, 6, 6, pen, brush)
                self.temp_dots.append(dot)
            if len(self.current_points) > 1:
                qf = QPolygonF([QPointF(x, y) for x, y in self.current_points])
                self.temp_polygon_item = self.scene.addPolygon(qf, pen, QBrush(Qt.BrushStyle.NoBrush))

        # Registration marker always on top
        self._place_registration_marker()

        # Refresh timeline data ticks (which frames have polygon data may have changed)
        if self.cap:
            frames_with_data = {f for f in self.project.frames if self.project.frames[f]}
            self.timeline_bar.set_data_frames(frames_with_data)

    def scene_mousePressEvent(self, event):
        if not self.cap or event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            return
            
        pos = event.scenePos()
        clicked_item = self.scene.itemAt(pos, self.view.transform())
        
        if self.mode == "DRAW":
            if event.button() == Qt.MouseButton.LeftButton:
                # Only live interactive items block first-point placement.
                # Onion-skin ghosts are plain QGraphicsPolygonItems (not subclassed)
                # so itemAt() still finds them even though they don't accept mouse
                # buttons — we must not let them block drawing (BUG03 follow-up).
                is_blocking = isinstance(
                    clicked_item,
                    (RotoPolygonItem, VertexHandleItem, RegistrationMarkerItem)
                )
                if not is_blocking or len(self.current_points) > 0:
                    self.current_points.append([pos.x(), pos.y()])
                    self.redraw_polygons()

        # In edit mode, selection handles interaction, we don't drop points.

    def enter_edit_mode(self, poly_item):
        if self.active_edit_item and self.active_edit_item != poly_item:
            # Cleanly save the old item without throwing us out of EDIT mode or destroying the scene
            self.active_edit_item.hide_handles()
            self.active_edit_item.setPen(QPen(self.active_edit_item.color, 2))
            new_polys = []
            items = sorted([it for it in self.scene.items() if isinstance(it, RotoPolygonItem)], key=lambda x: x.z_val)
            for item in items:
                new_polys.append(item.get_dict())
            self.project.set_polygons(self.current_game_frame, new_polys)
            self.active_edit_item = None
            
        self.mode = "EDIT"
        self.active_edit_item = poly_item
        self.active_edit_item.setPen(QPen(Qt.GlobalColor.white, 3, Qt.PenStyle.DashLine))
        self.active_edit_item.show_handles()
        self.view.setCursor(Qt.CursorShape.ArrowCursor)
        # Reflect the selected polygon's colour in the palette bar
        self.palette_bar.set_active_color(self.active_edit_item.color)
        self.set_status("EDIT MODE - [Esc] to cancel, [Enter] to save")

    def leave_edit_mode(self, save=True):
        if self.mode == "EDIT" and self.active_edit_item:
            self.active_edit_item.hide_handles()
            self.active_edit_item.setPen(QPen(self.active_edit_item.color, 2))
            
            if save:
                # Compile all current shapes back to json dict framework
                new_polys = []
                items = sorted([it for it in self.scene.items() if isinstance(it, RotoPolygonItem)], key=lambda x: x.z_val)
                for item in items:
                    new_polys.append(item.get_dict())
                self.project.set_polygons(self.current_game_frame, new_polys)
                self._dirty = True

        self.mode = "DRAW"
        self.active_edit_item = None
        self.scene.clearSelection()
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        # Restore palette to show the current draw colour
        self.palette_bar.set_active_color(self.current_polygon_color)
        self.set_status("DRAW MODE")
        
        if not save:
            self.redraw_polygons()

    def set_status(self, msg):
        fill_tag = "OPAQUE" if self.opaque_fill else "TRANSPARENT"
        end_tag = self.project.end_frame if self.project.end_frame is not None else (self.total_frames - 1)
        range_tag = f"In:{self.project.start_frame}  Out:{end_tag}"
        self.status_label.setText(
            f"Frame: {self.current_game_frame} / {self.total_frames - 1}  [{range_tag}] | {msg} | Fill: {fill_tag}"
        )

    def _fill_brush(self, color: QColor) -> QBrush:
        """Return a fill brush using the current opaque/transparent setting."""
        alpha = 255 if self.opaque_fill else 100
        return QBrush(QColor(color.red(), color.green(), color.blue(), alpha))

    def _pick_color(self, initial: QColor) -> QColor | None:
        """Open the custom color picker and return the chosen color (or None).
        Adds the chosen color to the LEFT of history only if it is new;
        existing colors stay in their current position."""
        color = ColorPickerDialog.pick(initial, self.color_history, self)
        if color and color.isValid():
            self._add_to_history(color)
            self.save_settings()
            # Sync the palette bar
            self.palette_bar.set_active_color(color)
            self.palette_bar.set_history(self.color_history)
            return color
        return None

    def _add_to_history(self, color: QColor):
        """Add *color* to the left of the history list only if it is not already
        present.  Existing colours keep their position (BUG02 fix).
        The list is capped at 16 entries."""
        if not any(c.name() == color.name() for c in self.color_history):
            self.color_history.insert(0, color)
            self.color_history = self.color_history[:16]


    # ------------------------------------------------------------------ palette bar handlers

    def _on_palette_color_selected(self, color: QColor):
        """Called when the user clicks a swatch in the persistent palette bar."""
        if self.mode == "EDIT" and self.active_edit_item:
            # Apply to the currently selected polygon
            self.active_edit_item.color = color
            self.active_edit_item.setBrush(self._fill_brush(color))
            self.active_edit_item.setPen(QPen(Qt.GlobalColor.white, 3, Qt.PenStyle.DashLine))
            self._dirty = True
        # Always update the draw color and the active swatch
        self.current_polygon_color = color
        self.palette_bar.set_active_color(color)
        # Add to history only if new — existing colours stay in place (BUG02)
        self._add_to_history(color)
        self.palette_bar.set_history(self.color_history)
        self.save_settings()

    def _open_picker_from_bar(self):
        """Open the full color picker (same as Ctrl+P) from the palette bar '…' button."""
        if self.mode == "EDIT" and self.active_edit_item:
            color = self._pick_color(self.active_edit_item.color)
            if color:
                self.active_edit_item.color = color
                self.current_polygon_color = color
                self.active_edit_item.setBrush(self._fill_brush(color))
                self.active_edit_item.setPen(QPen(Qt.GlobalColor.white, 3, Qt.PenStyle.DashLine))
        else:
            color = self._pick_color(self.current_polygon_color)
            if color:
                self.current_polygon_color = color

    # ------------------------------------------------------------------ timeline helpers

    def _update_timeline(self):
        """Push all current state to the TimelineBar in one call."""
        if not self.cap:
            return
        out_f = self.project.end_frame if self.project.end_frame is not None \
                else self.total_frames - 1
        self.timeline_bar.set_total(self.total_frames)
        self.timeline_bar.set_current(self.current_game_frame)
        self.timeline_bar.set_in_out(self.project.start_frame, out_f)
        # Collect frames that have polygon data for tick marks
        frames_with_data = {f for f in self.project.frames if self.project.frames[f]}
        self.timeline_bar.set_data_frames(frames_with_data)

    def _on_timeline_frame(self, frame: int):
        """User clicked/dragged the timeline playhead → jump to that frame."""
        if not self.cap:
            return
        self.current_game_frame = max(0, min(frame, self.total_frames - 1))
        self.update_frame()

    def _on_timeline_in(self, frame: int):
        """User dragged the in-point handle."""
        if not self.cap:
            return
        self.project.start_frame = frame
        out_f = self.project.end_frame if self.project.end_frame is not None \
                else self.total_frames - 1
        if out_f < frame:
            self.project.end_frame = frame
        self.set_status(f"In-point: frame {frame}")
        self._dirty = True

    def _on_timeline_out(self, frame: int):
        """User dragged the out-point handle."""
        if not self.cap:
            return
        self.project.end_frame = frame
        if self.project.start_frame > frame:
            self.project.start_frame = frame
        self.set_status(f"Out-point: frame {frame}")
        self._dirty = True

    def _try_insert_vertex(self, scene_pos: QPointF):
        """Ctrl+click in EDIT mode: insert a new vertex on the nearest polygon edge.

        Works in item-local coordinates so it remains correct after the polygon
        has been panned/dragged.  Tolerance is expressed in screen pixels and
        converted to local units via the current view zoom.
        """
        poly_item = self.active_edit_item
        if not poly_item:
            self.set_status("Ctrl+click: no polygon selected")
            return

        poly = poly_item.polygon()
        n = poly.count()
        if n < 2:
            return

        # Map the click from scene → item-local space
        local_pos = poly_item.mapFromScene(scene_pos)

        # Tolerance: 12 screen pixels, converted to scene units via view zoom,
        # then to item-local units (for unscaled items scene ≡ local).
        view_scale = self.view.transform().m11()
        tol_local  = 12.0 / view_scale
        tol_sq     = tol_local ** 2

        best_dist_sq = tol_sq
        best_edge    = -1
        best_pt      = QPointF()

        for i in range(n):
            a = poly.at(i)
            b = poly.at((i + 1) % n)
            dx = b.x() - a.x()
            dy = b.y() - a.y()
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1e-10:
                continue

            # Nearest point on segment a→b
            t = ((local_pos.x() - a.x()) * dx + (local_pos.y() - a.y()) * dy) / seg_len_sq
            t = max(0.0, min(1.0, t))
            nx = a.x() + t * dx
            ny = a.y() + t * dy
            dist_sq = (nx - local_pos.x()) ** 2 + (ny - local_pos.y()) ** 2

            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_edge    = i
                best_pt      = QPointF(nx, ny)

        if best_edge == -1:
            self.set_status("Ctrl+click: click closer to a polygon edge to insert a vertex")
            return

        # Rebuild polygon with new vertex inserted after vertex best_edge
        poly_item.hide_handles()
        new_poly = QPolygonF()
        for i in range(n):
            new_poly.append(poly.at(i))
            if i == best_edge:
                new_poly.append(best_pt)
        poly_item.setPolygon(new_poly)
        poly_item.show_handles()
        self._dirty = True
        self.set_status(
            f"Vertex inserted on edge {best_edge}\u2192{(best_edge + 1) % n}  "
            f"(polygon now has {new_poly.count()} vertices)"
        )

    # ------------------------------------------------------------------ z-order helpers

    def _get_ordered_poly_items(self) -> list:
        """Return all RotoPolygonItems in the scene sorted by z_val (lowest first = back of stack)."""
        return sorted(
            [it for it in self.scene.items() if isinstance(it, RotoPolygonItem)],
            key=lambda it: it.z_val
        )

    def _apply_z_order(self, ordered_items: list):
        """Assign contiguous ranks 1..N to *ordered_items* (index 0 = back) and
        update both the item's z_val and the Qt scene Z-value.  Marks the frame dirty."""
        for rank, item in enumerate(ordered_items, start=1):
            item.z_val = rank
            item.setZValue(rank)
        self._dirty = True

    def keyPressEvent(self, event):
        if not self.cap: return
        key = event.key()

        
        # Opaque / transparent fill toggle (Space)
        if key == Qt.Key.Key_Space:
            self.opaque_fill = not self.opaque_fill
            for item in self.scene.items():
                if isinstance(item, RotoPolygonItem):
                    item.setBrush(self._fill_brush(item.color))
                    if item == self.active_edit_item:
                        item.setPen(QPen(Qt.GlobalColor.white, 3, Qt.PenStyle.DashLine))
            self.set_status("EDIT MODE" if self.mode == "EDIT" else "DRAW MODE")
            return

        # Set In-point  (I)
        if key == Qt.Key.Key_I and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._set_in_point()
            return

        # Set End/Out-point  (E)
        if key == Qt.Key.Key_E and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._set_out_point()
            return

        # Copy registration from previous frame (Shift+R)
        if key == Qt.Key.Key_R and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            if self.cap:
                copied = self.project.copy_registration_from_prev(self.current_game_frame)
                if copied:
                    reg = self.project.get_registration(self.current_game_frame)
                    if self.reg_marker:
                        self.reg_marker.setPos(QPointF(reg[0], reg[1]))
                    self.set_status(f"Registration copied from frame {self.current_game_frame - 1}")
                else:
                    self.set_status("No previous registration point to copy")
            return

        # Onion skin toggle  (o = prev only, Shift+O = prev+next)
        if key == Qt.Key.Key_O:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+O: toggle both-direction onion skin
                self.onion_mode = None if self.onion_mode == "both" else "both"
            else:
                # o: toggle previous-frame onion skin
                self.onion_mode = None if self.onion_mode == "prev" else "prev"
            self.redraw_polygons()
            onion_label = {None: "OFF", "prev": "PREV", "both": "PREV+NEXT"}.get(self.onion_mode, "")
            self.set_status(f"Onion skin: {onion_label}")
            return

        # Copy polygon  (Ctrl+C)
        if key == Qt.Key.Key_C and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if self.mode == "EDIT" and self.active_edit_item:
                import copy
                self.copy_buffer = copy.deepcopy(self.active_edit_item.get_dict())
                self.set_status(f"Copied polygon ({len(self.copy_buffer.get('points',[]))} pts)")
            return

        # Paste polygon  (Ctrl+V)
        if key == Qt.Key.Key_V and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if self.copy_buffer:
                import copy
                new_dict = copy.deepcopy(self.copy_buffer)
                self.project.add_polygon(self.current_game_frame, new_dict)
                self._dirty = True
                self.redraw_polygons()
                self.set_status(f"Pasted polygon to frame {self.current_game_frame}")
            return

        # Color Dialog (Ctrl+P)
        if key == Qt.Key.Key_P and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if self.mode == "EDIT" and self.active_edit_item:
                color = self._pick_color(self.active_edit_item.color)
                if color:
                    self.active_edit_item.color = color
                    self.current_polygon_color = color
                    self.active_edit_item.setBrush(self._fill_brush(color))
                    self.active_edit_item.setPen(QPen(Qt.GlobalColor.white, 3, Qt.PenStyle.DashLine))
                    self.palette_bar.set_active_color(color)
            else:
                # No polygon selected — pick the default draw color for new polygons
                color = self._pick_color(self.current_polygon_color)
                if color:
                    self.current_polygon_color = color
                    self.palette_bar.set_active_color(color)
            return
            
        if self.mode == "DRAW":
            if key == Qt.Key.Key_D:
                self.current_game_frame = min(self.total_frames - 1, self.current_game_frame + 1)
                self.current_points = []
                self.update_frame()
            elif key == Qt.Key.Key_A:
                self.current_game_frame = max(0, self.current_game_frame - 1)
                self.current_points = []
                self.update_frame()
            elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                if len(self.current_points) > 2:
                    # New polygon gets rank N+1 (on top of the current stack)
                    n = len(self.project.get_polygons(self.current_game_frame))
                    poly_dict = {"points": self.current_points, "color": self.current_polygon_color.name(), "z_index": n + 1}
                    self.project.add_polygon(self.current_game_frame, poly_dict)
                    self._dirty = True
                self.current_points = []
                self.redraw_polygons()
            elif key == Qt.Key.Key_Escape:
                self.current_points = []
                self.redraw_polygons()
                
        elif self.mode == "EDIT":
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self.leave_edit_mode(save=True)
            elif key == Qt.Key.Key_Escape:
                self.leave_edit_mode(save=False)
            elif key == Qt.Key.Key_Backspace or key == Qt.Key.Key_Delete:
                for item in self.scene.selectedItems():
                    if isinstance(item, VertexHandleItem):
                        poly = item.parent_poly.polygon()
                        if poly.count() > 3:
                            poly.remove(item.index)
                            item.parent_poly.setPolygon(poly)
                            item.parent_poly.hide_handles()
                            item.parent_poly.show_handles()
                        else:
                            self.scene.removeItem(item.parent_poly)
                        self._dirty = True
                    elif isinstance(item, RotoPolygonItem):
                        self.scene.removeItem(item)
                        self._dirty = True
                        self.leave_edit_mode(save=True)
            elif key == Qt.Key.Key_BracketRight:   # ] raise by one
                if self.active_edit_item:
                    items = self._get_ordered_poly_items()
                    idx = items.index(self.active_edit_item)
                    if idx < len(items) - 1:
                        items[idx], items[idx + 1] = items[idx + 1], items[idx]
                    self._apply_z_order(items)
            elif key == Qt.Key.Key_BracketLeft:    # [ lower by one
                if self.active_edit_item:
                    items = self._get_ordered_poly_items()
                    idx = items.index(self.active_edit_item)
                    if idx > 0:
                        items[idx], items[idx - 1] = items[idx - 1], items[idx]
                    self._apply_z_order(items)
            elif key == Qt.Key.Key_BraceRight:     # } bring to front
                if self.active_edit_item:
                    items = self._get_ordered_poly_items()
                    items.remove(self.active_edit_item)
                    items.append(self.active_edit_item)
                    self._apply_z_order(items)
            elif key == Qt.Key.Key_BraceLeft:      # { send to back
                if self.active_edit_item:
                    items = self._get_ordered_poly_items()
                    items.remove(self.active_edit_item)
                    items.insert(0, self.active_edit_item)
                    self._apply_z_order(items)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RotoTool()
    window.show()
    sys.exit(app.exec())