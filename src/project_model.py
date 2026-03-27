import json
import os

class RotoProject:
    def __init__(self):
        self.video_path = None
        self.last_frame = 0
        # frames is a dict mapping frame_idx (int) to a list of polygons.
        # A polygon is a dict: {"points": [[x1, y1], [x2, y2], ...], "color": "#00ff00", "z_index": 0}
        self.frames = {}

    def to_dict(self):
        return {
            "video_path": self.video_path,
            "last_frame": self.last_frame,
            "frames": self.frames
        }

    def from_dict(self, data):
        self.video_path = data.get("video_path", None)
        self.last_frame = data.get("last_frame", 0)
        raw_frames = data.get("frames", {})
        self.frames = {}
        for k, v in raw_frames.items():
            migrated_polys = []
            for poly in v:
                # Migrate older v1 projects which stored simple lists
                if isinstance(poly, list):
                    migrated_polys.append({
                        "points": poly,
                        "color": "#00ff00",
                        "z_index": 0
                    })
                else:
                    migrated_polys.append(poly)
            self.frames[int(k)] = migrated_polys

    def save(self, filepath):
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)

    def load(self, filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Project file not found: {filepath}")
        with open(filepath, 'r') as f:
            data = json.load(f)
            self.from_dict(data)

    def add_polygon(self, frame_idx, polygon_data):
        """Adds a new polygon to a given frame. polygon_data should be a dict."""
        if frame_idx not in self.frames:
            self.frames[frame_idx] = []
        # Wrapper fallback just in case
        if isinstance(polygon_data, list):
            polygon_data = {"points": polygon_data, "color": "#00ff00", "z_index": 0}
        self.frames[frame_idx].append(polygon_data)

    def set_polygons(self, frame_idx, polygons):
        """Replaces all polygons for a given frame."""
        self.frames[frame_idx] = polygons

    def get_polygons(self, frame_idx):
        """Returns all polygons for a given frame. Returns shallow copies so edits don't bypass set_polygons natively, or references so edits take implicitly."""
        return self.frames.get(frame_idx, [])

    def clear_frame(self, frame_idx):
        """Clears all polygons on a frame."""
        if frame_idx in self.frames:
            del self.frames[frame_idx]

    def export_bwxbasic(self, filepath):
        """Exports the project in a format digestible by bwxBASIC (e.g. DATA statements)"""
        with open(filepath, 'w') as f:
            f.write("' bwxBASIC Polygon Export\n")
            f.write("' Format: DATA <frame_idx>, <polygon_idx>, <num_points>, <color>, <x1>, <y1>, <x2>, <y2>, ...\n")
            # Sort by Z-index before exporting so bwxBASIC draws them correctly!
            for frame_idx in sorted(self.frames.keys()):
                
                # Sort the polygons in this frame by z_index
                sorted_polys = sorted(self.frames[frame_idx], key=lambda p: p.get("z_index", 0))
                
                for poly_idx, poly_dict in enumerate(sorted_polys):
                    points = poly_dict.get("points", [])
                    color = poly_dict.get("color", "#00ff00")
                    if not points:
                        continue
                    
                    points_flat = []
                    for pt in points:
                        # Convert to int for cleaner basic arrays
                        points_flat.append(str(int(pt[0])))
                        points_flat.append(str(int(pt[1])))
                    
                    points_str = ", ".join(points_flat)
                    f.write(f"DATA {frame_idx}, {poly_idx}, {len(points)}, \"{color}\", {points_str}\n")
