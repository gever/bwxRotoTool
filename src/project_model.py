import json
import os

class RotoProject:
    def __init__(self):
        self.video_path = None
        self.last_frame = 0
        # frames is a dict mapping frame_idx (int) to a list of polygons.
        # A polygon is a dict: {"points": [[x1, y1], [x2, y2], ...], "color": "#00ff00", "z_index": 0}
        self.frames = {}
        # registrations is a dict mapping frame_idx (int) to [x, y] in video pixels.
        # This is the per-frame reference point all exported coordinates are relative to.
        self.registrations = {}

    def to_dict(self):
        return {
            "video_path": self.video_path,
            "last_frame": self.last_frame,
            "frames": self.frames,
            "registrations": self.registrations,
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

        # Load registration points — keys stored as strings in JSON
        raw_regs = data.get("registrations", {})
        self.registrations = {int(k): v for k, v in raw_regs.items()}

    def save(self, filepath):
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)

    def load(self, filepath):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Project file not found: {filepath}")
        with open(filepath, 'r') as f:
            data = json.load(f)
            self.from_dict(data)

    # ── Polygon helpers ──────────────────────────────────────────────────────

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
        """Returns all polygons for a given frame."""
        return self.frames.get(frame_idx, [])

    def clear_frame(self, frame_idx):
        """Clears all polygons on a frame."""
        if frame_idx in self.frames:
            del self.frames[frame_idx]

    # ── Registration helpers ─────────────────────────────────────────────────

    def set_registration(self, frame_idx, x, y):
        """Sets the registration point for a frame."""
        self.registrations[frame_idx] = [x, y]

    def get_registration(self, frame_idx):
        """Returns [x, y] for a frame's registration point, defaulting to [0, 0]."""
        return self.registrations.get(frame_idx, [0.0, 0.0])

    def copy_registration_from_prev(self, frame_idx):
        """Copies the registration point from frame_idx-1 to frame_idx.
        Returns True if a previous registration was found, False otherwise."""
        if frame_idx <= 0:
            return False
        prev_reg = self.registrations.get(frame_idx - 1)
        if prev_reg is not None:
            self.registrations[frame_idx] = list(prev_reg)
            return True
        return False

    # ── Export ───────────────────────────────────────────────────────────────

    def export_bwxbasic(self, filepath):
        """Exports the project in a format digestible by bwxBASIC (DATA statements).
        All coordinates are relative to the per-frame registration point."""
        with open(filepath, 'w') as f:
            f.write("' bwxBASIC Polygon Export\n")
            f.write("' Format: DATA <frame_idx>, <polygon_idx>, <num_points>, <color>, <x1>, <y1>, <x2>, <y2>, ...\n")
            f.write("' Coordinates are registration-relative (subtract reg point from raw video coords)\n")

            # Sort by Z-index before exporting so bwxBASIC draws them correctly!
            for frame_idx in sorted(self.frames.keys()):
                reg = self.get_registration(frame_idx)
                reg_x, reg_y = reg[0], reg[1]

                # Write a registration comment so the game engine can reconstruct world-space paths
                f.write(f"' Frame {frame_idx} registration: {int(reg_x)}, {int(reg_y)}\n")

                # Sort the polygons in this frame by z_index
                sorted_polys = sorted(self.frames[frame_idx], key=lambda p: p.get("z_index", 0))

                for poly_idx, poly_dict in enumerate(sorted_polys):
                    points = poly_dict.get("points", [])
                    color = poly_dict.get("color", "#00ff00")
                    if not points:
                        continue

                    points_flat = []
                    for pt in points:
                        # Subtract the registration point, convert to int
                        points_flat.append(str(int(pt[0] - reg_x)))
                        points_flat.append(str(int(pt[1] - reg_y)))

                    points_str = ", ".join(points_flat)
                    f.write(f"DATA {frame_idx}, {poly_idx}, {len(points)}, \"{color}\", {points_str}\n")
