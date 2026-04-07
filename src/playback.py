"""playback.py — Non-modal playback preview window for bwxRotoTool.

Shows the rotoscoped animation at 15 FPS on a plain background,
with all coordinates normalized to each frame's registration point.
The window is non-blocking so the artist can keep editing in the main view.

Zoom / pan controls
-------------------
  Mouse wheel          — zoom in / out (10 % increments, anchored to cursor)
  Shift + left drag    — pan
  Middle-button drag   — pan
  Double-click         — reset zoom & pan
  Reset View button    — same as double-click
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSizePolicy, QColorDialog, QFrame
)
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF, QFont, QTransform
from PyQt6.QtCore import Qt, QTimer, QPointF, QSizeF, QRectF


class _Canvas(QFrame):
    """Internal widget that renders the animation frames.

    Coordinate system
    -----------------
    The 'base' transform maps the video into the canvas with a scale-to-fit
    letterbox.  On top of that we layer a user-controlled pan/zoom
    (_user_zoom, _pan_x, _pan_y). The combined transform is:

        T_total = T_base · T_user

    where T_user = translate(pan) · scale(zoom) anchored at the cursor.
    """

    _ZOOM_STEP = 1.10   # 10 % per wheel tick

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.current_frame = 0
        self.total_frames = 0
        self.video_size = QSizeF(640, 480)       # native video dimensions
        self.bg_color = QColor(0, 0, 0)           # playback background

        # User zoom/pan state
        self._user_zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._panning = False
        self._pan_last = QPointF()

        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    # ── Reset ────────────────────────────────────────────────────────────────

    def reset_view(self):
        self._user_zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.update()

    # ── Base (scale-to-fit) helpers ──────────────────────────────────────────

    def _base_params(self):
        """Return (scale, ox, oy, cx_centre, cy_centre) for the current canvas size."""
        w, h = self.width(), self.height()
        vw, vh = self.video_size.width(), self.video_size.height()
        scale = min(w / vw, h / vh)
        draw_w, draw_h = vw * scale, vh * scale
        ox = (w - draw_w) / 2
        oy = (h - draw_h) / 2
        return scale, ox, oy, w / 2, h / 2

    def _combined_transform(self) -> QTransform:
        """Build the full painter transform: base scale-to-fit + user pan/zoom."""
        # User transform: zoom around canvas centre then pan
        cx, cy = self.width() / 2, self.height() / 2
        t = QTransform()
        t.translate(cx + self._pan_x, cy + self._pan_y)
        t.scale(self._user_zoom, self._user_zoom)
        t.translate(-cx, -cy)
        return t

    # ── Painting ─────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Background ──────────────────────────────────────────────────────
        painter.fillRect(self.rect(), self.bg_color)

        if not self.project or self.total_frames == 0:
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No project loaded")
            return

        # ── Apply combined transform (base + user pan/zoom) ─────────────────
        painter.setTransform(self._combined_transform())

        # ── Compute base scale params (after transform is set) ──────────────
        scale, ox, oy, cx_centre, cy_centre = self._base_params()

        # ── Registration-relative polygon drawing ───────────────────────────
        reg = self.project.get_registration(self.current_frame)
        reg_x, reg_y = reg[0], reg[1]

        polys = self.project.get_polygons(self.current_frame)
        sorted_polys = sorted(polys, key=lambda p: p.get("z_index", 0))

        for poly_dict in sorted_polys:
            raw_pts = poly_dict.get("points", [])
            if len(raw_pts) < 3:
                continue
            color = QColor(poly_dict.get("color", "#00ff00"))

            qpts = QPolygonF()
            for px, py in raw_pts:
                cx = cx_centre + (px - reg_x) * scale
                cy = cy_centre + (py - reg_y) * scale
                qpts.append(QPointF(cx, cy))

            painter.setPen(QPen(color, max(1, scale)))
            painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 180)))
            painter.drawPolygon(qpts)

        # ── Frame counter (drawn in screen space, not world space) ──────────
        painter.resetTransform()
        w, h = self.width(), self.height()
        counter_color = QColor(200, 200, 200, 160) if self.bg_color.lightness() < 128 else QColor(60, 60, 60, 160)
        painter.setPen(counter_color)
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(
            QRectF(4, 4, w, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            f"Frame {self.current_frame} / {self.total_frames - 1}"
        )

        # Zoom indicator (shown when not at 1×)
        if abs(self._user_zoom - 1.0) > 0.01:
            painter.drawText(
                QRectF(0, 4, w - 4, 20),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                f"{self._user_zoom:.1f}×"
            )

    # ── Mouse: zoom ──────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return

        factor = self._ZOOM_STEP if delta > 0 else 1.0 / self._ZOOM_STEP
        new_zoom = self._user_zoom * factor

        # Anchor zoom to cursor position so the point under the mouse stays fixed
        cursor = event.position()
        cx, cy = self.width() / 2, self.height() / 2

        # Current world position under cursor (before zoom change)
        wx = (cursor.x() - cx - self._pan_x) / self._user_zoom
        wy = (cursor.y() - cy - self._pan_y) / self._user_zoom

        self._user_zoom = new_zoom

        # Adjust pan so the world point stays under the cursor
        self._pan_x = cursor.x() - cx - wx * self._user_zoom
        self._pan_y = cursor.y() - cy - wy * self._user_zoom

        self.update()
        event.accept()

    # ── Mouse: pan ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        is_pan = (
            event.button() == Qt.MouseButton.MiddleButton
            or (event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        )
        if is_pan:
            self._panning = True
            self._pan_last = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_last
            self._pan_x += delta.x()
            self._pan_y += delta.y()
            self._pan_last = event.position()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()
            event.accept()


class PlaybackWindow(QDialog):
    """Non-modal window that plays back the registration-normalized animation."""

    FPS = 15

    def __init__(self, project, total_frames: int, video_size: QSizeF, parent=None):
        super().__init__(parent, Qt.WindowType.Window)   # Window flag: non-modal, own taskbar entry
        self.setWindowTitle("Playback Preview — Character Space")
        self.resize(480, 400)

        self._project = project
        self._total_frames = total_frames
        self._playing = True
        self._looping = True

        # ── Canvas ──────────────────────────────────────────────────────────
        self._canvas = _Canvas()
        self._canvas.project = project
        self._canvas.total_frames = total_frames
        self._canvas.video_size = video_size
        self._canvas.current_frame = project.start_frame if project else 0

        # ── Controls ────────────────────────────────────────────────────────
        self._play_btn = QPushButton("⏸ Pause")
        self._play_btn.setFixedWidth(90)
        self._play_btn.clicked.connect(self._toggle_play)

        self._loop_btn = QPushButton("⟳ Loop: ON")
        self._loop_btn.setFixedWidth(100)
        self._loop_btn.setCheckable(True)
        self._loop_btn.setChecked(True)
        self._loop_btn.clicked.connect(self._toggle_loop)

        self._bg_btn = QPushButton("⬛ BG Color")
        self._bg_btn.setFixedWidth(100)
        self._bg_btn.clicked.connect(self._pick_bg_color)
        self._update_bg_btn_style(self._canvas.bg_color)

        self._reset_btn = QPushButton("⤢ Reset View")
        self._reset_btn.setFixedWidth(100)
        self._reset_btn.setToolTip("Reset zoom and pan  (double-click canvas)")
        self._reset_btn.clicked.connect(self._canvas.reset_view)

        self._frame_label = QLabel("Frame 0")
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(self._play_btn)
        ctrl_layout.addWidget(self._loop_btn)
        ctrl_layout.addWidget(self._bg_btn)
        ctrl_layout.addWidget(self._reset_btn)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(self._frame_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addWidget(self._canvas)
        layout.addLayout(ctrl_layout)

        # ── Timer ────────────────────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // self.FPS)

    # ── Public ───────────────────────────────────────────────────────────────

    def update_project(self, project, total_frames: int, video_size: QSizeF):
        """Call this whenever the project reference or frame count changes."""
        self._project = project
        self._total_frames = total_frames
        self._canvas.project = project
        self._canvas.total_frames = total_frames
        self._canvas.video_size = video_size

    # ── Internals ─────────────────────────────────────────────────────────────

    def _tick(self):
        if not self._playing:
            return
        project = self._project
        start = project.start_frame if project else 0
        end = project.end_frame if (project and project.end_frame is not None) else (self._total_frames - 1)
        end = min(end, self._total_frames - 1)

        next_frame = self._canvas.current_frame + 1
        if next_frame < start:
            next_frame = start
        if next_frame > end:
            if self._looping:
                next_frame = start
            else:
                next_frame = end
                self._playing = False
                self._play_btn.setText("▶ Play")
        self._canvas.current_frame = next_frame
        self._canvas.update()
        self._frame_label.setText(f"Frame {next_frame}  [{start}–{end}]")

    def _toggle_play(self):
        self._playing = not self._playing
        self._play_btn.setText("⏸ Pause" if self._playing else "▶ Play")

    def _toggle_loop(self):
        self._looping = self._loop_btn.isChecked()
        self._loop_btn.setText("⟳ Loop: ON" if self._looping else "⟳ Loop: OFF")

    def _pick_bg_color(self):
        color = QColorDialog.getColor(self._canvas.bg_color, self, "Choose Background Color")
        if color.isValid():
            self._canvas.bg_color = color
            self._canvas.update()
            self._update_bg_btn_style(color)

    def _update_bg_btn_style(self, color: QColor):
        text_color = "#ffffff" if color.lightness() < 128 else "#000000"
        self._bg_btn.setStyleSheet(
            f"background-color: {color.name()}; color: {text_color}; border: 1px solid #555;"
        )

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
