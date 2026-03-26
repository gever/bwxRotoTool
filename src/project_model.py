import json
import os

class RotoProject:
    def __init__(self):
        self.video_path = None
        # frames is a dict mapping frame_idx (int) to a list of polygons.
        # A polygon is a list of points: [[x1, y1], [x2, y2], ...]
        self.frames = {}

    def to_dict(self):
        return {
            "video_path": self.video_path,
            "frames": self.frames
        }

    def from_dict(self, data):
        self.video_path = data.get("video_path", None)
        raw_frames = data.get("frames", {})
        # JSON dictionary keys are serialized as strings, so convert them back to integers
        self.frames = {int(k): v for k, v in raw_frames.items()}

    def save(self, filepath):
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)

    def load(self, filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Project file not found: {filepath}")
        with open(filepath, 'r') as f:
            data = json.load(f)
            self.from_dict(data)

    def add_polygon(self, frame_idx, polygon):
        """Adds a new polygon to a given frame."""
        if frame_idx not in self.frames:
            self.frames[frame_idx] = []
        self.frames[frame_idx].append(polygon)

    def set_polygons(self, frame_idx, polygons):
        """Replaces all polygons for a given frame."""
        self.frames[frame_idx] = polygons

    def get_polygons(self, frame_idx):
        """Returns all polygons for a given frame."""
        return self.frames.get(frame_idx, [])

    def clear_frame(self, frame_idx):
        """Clears all polygons on a frame."""
        if frame_idx in self.frames:
            del self.frames[frame_idx]

    def export_bwxbasic(self, filepath):
        """Exports the project in a format digestible by bwxBASIC (e.g. DATA statements)"""
        with open(filepath, 'w') as f:
            f.write("' bwxBASIC Polygon Export\n")
            f.write("' Format: DATA <frame_idx>, <polygon_idx>, <num_points>, <x1>, <y1>, <x2>, <y2>, ...\n")
            for frame_idx in sorted(self.frames.keys()):
                for poly_idx, poly in enumerate(self.frames[frame_idx]):
                    if not poly:
                        continue
                    # Flatten points: x1, y1, x2, y2, ...
                    points_flat = []
                    for pt in poly:
                        # Convert to int for cleaner basic arrays if necessary
                        points_flat.append(str(int(pt[0])))
                        points_flat.append(str(int(pt[1])))
                    
                    points_str = ", ".join(points_flat)
                    f.write(f"DATA {frame_idx}, {poly_idx}, {len(poly)}, {points_str}\n")
