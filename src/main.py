import cv2
import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
                             QGraphicsPixmapItem, QFileDialog, QMessageBox, QProgressDialog,
                             QVBoxLayout, QWidget, QLabel, QToolBar)
from PyQt6.QtGui import QImage, QPixmap, QAction, QPolygonF, QPen, QBrush, QColor, QKeySequence
from PyQt6.QtCore import Qt, QPointF

from video_processor import convert_to_15fps
from project_model import RotoProject

class RotoScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = None

    def mousePressEvent(self, event):
        if self.main_window:
            self.main_window.scene_mousePressEvent(event)
        super().mousePressEvent(event)

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

        # UI Setup
        self.scene = RotoScene()
        self.scene.main_window = self
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(self.view.renderHints() | self.view.renderHints().Antialiasing)
        
        # Disable scrollbars for a cleaner look if desired, but good to have if zoomed.
        
        self.setCentralWidget(self.view)
        
        self.bg_item = QGraphicsPixmapItem()
        self.scene.addItem(self.bg_item)
        
        # Status Label
        self.status_label = QLabel("Frame: 0 / 0 | Ready")
        self.statusBar().addWidget(self.status_label)

        # Drawing state
        self.current_points = []
        self.temp_polygon_item = None
        self.temp_dots = []

        self._create_actions()
        self._create_menu()
        
        if initial_video and os.path.exists(initial_video):
            self.load_video(initial_video)

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
        self.clear_frame_action.setShortcut(QKeySequence(Qt.Key.Key_Backspace))
        self.clear_frame_action.triggered.connect(self.clear_current_frame)
        
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

    def open_video(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Video", "", "Video Files (*.mp4 *.mov *.avi)")
        if filepath:
            # Show a busy dialog
            progress = QProgressDialog("Processing video to 15 FPS...", "Cancel", 0, 0, self)
            progress.setWindowTitle("Processing")
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()
            QApplication.processEvents()
            
            out_file = convert_to_15fps(filepath)
            progress.close()
            
            if out_file:
                self.project = RotoProject()
                self.project.video_path = out_file
                self.load_video(out_file)
            else:
                QMessageBox.critical(self, "Error", "Failed to convert video.")

    def load_video(self, filepath):
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(filepath)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.current_game_frame = 0
        self.project.video_path = filepath
        self.setWindowTitle(f"Antigravity Roto-Tool - {os.path.basename(filepath)}")
        self.current_points = []
        self.update_frame()
        
    def open_project(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Roto Files (*.bwxroto *.json)")
        if filepath:
            self.project = RotoProject()
            try:
                self.project.load(filepath)
                self.current_project_file = filepath
                
                if self.project.video_path and os.path.exists(self.project.video_path):
                    self.load_video(self.project.video_path)
                else:
                    QMessageBox.warning(self, "Warning", f"Video file not found at {self.project.video_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load project: {e}")

    def save_project(self):
        if self.current_project_file:
            self.project.save(self.current_project_file)
            self.status_label.setText(f"Frame: {self.current_game_frame} / {self.total_frames} | Saved")
        else:
            self.save_project_as()
            
    def save_project_as(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "Roto Files (*.bwxroto)")
        if filepath:
            if not filepath.endswith('.bwxroto'):
                filepath += '.bwxroto'
            self.project.save(filepath)
            self.current_project_file = filepath
            self.status_label.setText(f"Frame: {self.current_game_frame} / {self.total_frames} | Saved")

    def export_bwxbasic(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Export bwxBASIC", "", "Text Files (*.bas *.txt)")
        if filepath:
            if not filepath.endswith('.bas') and not filepath.endswith('.txt'):
                filepath += '.bas'
            self.project.export_bwxbasic(filepath)
            QMessageBox.information(self, "Exported", f"Successfully exported data to {os.path.basename(filepath)}")

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
            
            self.redraw_polygons()
            self.status_label.setText(f"Frame: {self.current_game_frame} / {self.total_frames} | Drawing")
            
    def clear_current_frame(self):
        self.project.clear_frame(self.current_game_frame)
        self.current_points = []
        self.redraw_polygons()
            
    def redraw_polygons(self):
        # Remove old interactable polygon visual elements, keeping bg item
        for item in self.scene.items():
            if item != self.bg_item:
                self.scene.removeItem(item)
                
        # Draw committed polygons
        polygons = self.project.get_polygons(self.current_game_frame)
        pen = QPen(QColor(0, 255, 0), 2)
        brush = QBrush(QColor(0, 255, 0, 50))
        for poly_points in polygons:
            if len(poly_points) > 2:
                qf = QPolygonF([QPointF(x, y) for x, y in poly_points])
                self.scene.addPolygon(qf, pen, brush)
            
        # Draw current points / in-progress polygon
        self.temp_polygon_item = None
        self.temp_dots = []
        if self.current_points:
            pen_blue = QPen(QColor(0, 0, 255), 2)
            brush_blue = QBrush(QColor(0, 0, 255))
            for x, y in self.current_points:
                dot = self.scene.addEllipse(x-3, y-3, 6, 6, pen_blue, brush_blue)
                self.temp_dots.append(dot)
            if len(self.current_points) > 1:
                qf = QPolygonF([QPointF(x, y) for x, y in self.current_points])
                self.temp_polygon_item = self.scene.addPolygon(qf, pen_blue, QBrush(Qt.BrushStyle.NoBrush))

    def scene_mousePressEvent(self, event):
        if not self.cap:
            return
            
        pos = event.scenePos()
        
        # We only accept clicks inside the bounds of the image
        if not self.bg_item.boundingRect().contains(pos):
            return
            
        if event.button() == Qt.MouseButton.LeftButton:
            self.current_points.append([pos.x(), pos.y()])
            self.redraw_polygons()
            
        elif event.button() == Qt.MouseButton.RightButton:
            if len(self.current_points) > 2:
                self.project.add_polygon(self.current_game_frame, self.current_points)
                self.current_points = []
                self.redraw_polygons()
            else:
                self.current_points = []
                self.redraw_polygons()

    def keyPressEvent(self, event):
        if not self.cap:
            return
            
        if event.key() == Qt.Key.Key_D:
            if self.current_game_frame < self.total_frames - 1:
                self.current_game_frame += 1
                self.current_points = []
                self.update_frame()
        elif event.key() == Qt.Key.Key_A:
            if self.current_game_frame > 0:
                self.current_game_frame -= 1
                self.current_points = []
                self.update_frame()
        # Right Click closes, but let's add Enter key as an alternative
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if len(self.current_points) > 2:
                self.project.add_polygon(self.current_game_frame, self.current_points)
                self.current_points = []
                self.redraw_polygons()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RotoTool()
    window.show()
    sys.exit(app.exec())