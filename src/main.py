import cv2
import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
                             QGraphicsPixmapItem, QFileDialog, QMessageBox, QProgressDialog,
                             QVBoxLayout, QWidget, QLabel, QToolBar, QGraphicsPolygonItem, 
                             QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem)
from PyQt6.QtGui import (QImage, QPixmap, QAction, QPolygonF, QPen, QBrush, QColor,
                         QKeySequence, QPainterPath)
from PyQt6.QtCore import Qt, QPointF, QSizeF

from color_picker import ColorPickerDialog
from video_processor import convert_to_15fps
from project_model import RotoProject
from playback import PlaybackWindow

# ── Registration crosshair marker ────────────────────────────────────────────

class RegistrationMarkerItem(QGraphicsItem):
    """Draggable ⊕ crosshair that marks the per-frame registration point.
    Always rendered at a fixed screen size regardless of zoom level."""

    RADIUS = 12   # screen-space radius in pixels
    COLOR  = QColor(255, 220, 0)   # bright yellow

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
        pen_outer = QPen(QColor(0, 0, 0, 160), 3)
        pen_inner = QPen(self.COLOR, 2)

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
        painter.setBrush(QBrush(self.COLOR))
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
        
        self.z_val = self.poly_dict.get("z_index", 0)
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
                # If they click the background, exit edit mode smoothly
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
        self.scene.addItem(self.bg_item)
        
        # Status Label
        self.status_label = QLabel("Frame: 0 / 0 | DRAW MODE")
        self.statusBar().addWidget(self.status_label)

        # Drawing state
        self.current_points = []
        self.temp_polygon_item = None
        self.temp_dots = []
        self.current_polygon_color = QColor(0, 255, 0)
        self.opaque_fill = False   # Space toggles transparent ↔ opaque fill

        # Copy buffer: holds a polygon dict ready to paste
        self.copy_buffer: dict | None = None

        # Onion-skin mode: None | "prev" | "both"
        self.onion_mode: str | None = None

        # Color history (up to 16, most recent first)
        self.color_history: list[QColor] = []

        # Registration marker state
        self.reg_marker: RegistrationMarkerItem | None = None
        self.show_registration = True   # toggled via View menu

        # Playback window (keeps a reference so it isn't garbage-collected)
        self._playback_window: PlaybackWindow | None = None

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
        
        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction(self.clear_frame_action)

        view_menu = menubar.addMenu("View")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.zoom_reset_action)
        view_menu.addAction(self.zoom_fit_action)
        view_menu.addSeparator()
        view_menu.addAction(self.show_reg_action)

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
            self.set_status("Saved")
            self.save_settings()

    def export_bwxbasic(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Export bwxBASIC", "", "Text Files (*.bas *.txt)")
        if filepath:
            if not filepath.endswith('.bas') and not filepath.endswith('.txt'):
                filepath += '.bas'
            self.project.export_bwxbasic(filepath)

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
            
            self.leave_edit_mode(save=False) # Safely drop unsaved drawing or editing when scrubbing frames
            self.redraw_polygons()
            
    def clear_current_frame(self):
        self.project.clear_frame(self.current_game_frame)
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
                    self.scene.addPolygon(
                        qpoly,
                        QPen(tint, 1, Qt.PenStyle.DashLine),
                        QBrush(QColor(tint.red(), tint.green(), tint.blue(), 40))
                    )

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
        marker.setPos(QPointF(reg[0], reg[1]))
        self.scene.addItem(marker)
        self.reg_marker = marker

    def _on_registration_moved(self, x: float, y: float):
        """Called when the user drags the registration marker."""
        self.project.set_registration(self.current_game_frame, x, y)
        # Update onion skins live so the alignment shifts in real time
        if self.onion_mode:
            self.redraw_polygons()

    def _toggle_reg_visibility(self):
        self.show_registration = self.show_reg_action.isChecked()
        self._place_registration_marker()

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

    def scene_mousePressEvent(self, event):
        if not self.cap or event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            return
            
        pos = event.scenePos()
        clicked_item = self.scene.itemAt(pos, self.view.transform())
        
        if self.mode == "DRAW":
            if event.button() == Qt.MouseButton.LeftButton:
                # If they clicked background, add point. If we already started a polygon, force add point ignoring items.
                if clicked_item == self.bg_item or len(self.current_points) > 0:
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

        self.mode = "DRAW"
        self.active_edit_item = None
        self.scene.clearSelection()
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.set_status("DRAW MODE")
        
        if not save:
            self.redraw_polygons()

    def set_status(self, msg):
        fill_tag = "OPAQUE" if self.opaque_fill else "TRANSPARENT"
        self.status_label.setText(f"Frame: {self.current_game_frame} / {self.total_frames} | {msg} | Fill: {fill_tag}")

    def _fill_brush(self, color: QColor) -> QBrush:
        """Return a fill brush using the current opaque/transparent setting."""
        alpha = 255 if self.opaque_fill else 100
        return QBrush(QColor(color.red(), color.green(), color.blue(), alpha))

    def _pick_color(self, initial: QColor) -> QColor | None:
        """Open the custom color picker and return the chosen color (or None).
        Automatically prepends the chosen color to self.color_history."""
        color = ColorPickerDialog.pick(initial, self.color_history, self)
        if color and color.isValid():
            # Add to front of history, deduplicate, cap at 16
            self.color_history = [c for c in self.color_history if c.name() != color.name()]
            self.color_history.insert(0, color)
            self.color_history = self.color_history[:16]
            self.save_settings()
            return color
        return None

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
            else:
                # No polygon selected — pick the default draw color for new polygons
                color = self._pick_color(self.current_polygon_color)
                if color:
                    self.current_polygon_color = color
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
                    poly_dict = {"points": self.current_points, "color": self.current_polygon_color.name(), "z_index": 0}
                    self.project.add_polygon(self.current_game_frame, poly_dict)
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
                    elif isinstance(item, RotoPolygonItem):
                        self.scene.removeItem(item)
                        self.leave_edit_mode(save=True)
            elif key == Qt.Key.Key_BracketRight:
                if self.active_edit_item:
                    inc = 100 if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1
                    self.active_edit_item.z_val += inc
                    self.active_edit_item.setZValue(self.active_edit_item.z_val)
            elif key == Qt.Key.Key_BracketLeft:
                if self.active_edit_item:
                    dec = 100 if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1
                    self.active_edit_item.z_val -= dec
                    self.active_edit_item.setZValue(self.active_edit_item.z_val)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RotoTool()
    window.show()
    sys.exit(app.exec())