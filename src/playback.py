"""playback.py — Non-modal playback preview window for bwxRotoTool.

Shows the rotoscoped animation at 15 FPS on a plain background,
with all coordinates normalized to each frame's registration point.
The window is non-blocking so the artist can keep editing in the main view.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSizePolicy, QColorDialog, QFrame
)
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF, QFont
from PyQt6.QtCore import Qt, QTimer, QPointF, QSizeF, QRectF


class _Canvas(QFrame):
    """Internal widget that renders the animation frames."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.current_frame = 0
        self.total_frames = 0
        self.video_size = QSizeF(640, 480)       # native video dimensions
        self.bg_color = QColor(0, 0, 0)           # playback background
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Background ──────────────────────────────────────────────────────
        painter.fillRect(self.rect(), self.bg_color)

        if not self.project or self.total_frames == 0:
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No project loaded")
            return

        # ── Compute scale-to-fit transform ──────────────────────────────────
        w, h = self.width(), self.height()
        vw, vh = self.video_size.width(), self.video_size.height()
        scale = min(w / vw, h / vh)
        draw_w, draw_h = vw * scale, vh * scale
        ox = (w - draw_w) / 2       # centering offsets
        oy = (h - draw_h) / 2

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

            # Normalize to registration-relative, then scale to canvas
            qpts = QPolygonF()
            for px, py in raw_pts:
                cx = ox + (px - reg_x) * scale
                cy = oy + (py - reg_y) * scale
                qpts.append(QPointF(cx, cy))

            painter.setPen(QPen(color, max(1, scale)))
            painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 180)))
            painter.drawPolygon(qpts)

        # ── Frame counter ────────────────────────────────────────────────────
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

        self._frame_label = QLabel("Frame 0")
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(self._play_btn)
        ctrl_layout.addWidget(self._loop_btn)
        ctrl_layout.addWidget(self._bg_btn)
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
