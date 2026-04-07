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
        # In/out work-range. None means "use total_frames - 1" for end_frame.
        self.start_frame: int = 0
        self.end_frame: int | None = None

    def to_dict(self):
        return {
            "video_path": self.video_path,
            "last_frame": self.last_frame,
            "frames": self.frames,
            "registrations": self.registrations,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
        }

    def from_dict(self, data):
        self.video_path = data.get("video_path", None)
        self.last_frame = data.get("last_frame", 0)
        self.start_frame = data.get("start_frame", 0)
        self.end_frame = data.get("end_frame", None)
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

    def get_nearest_registration(self, frame_idx):
        """Returns the registration for frame_idx, or the nearest previous frame's
        registration if this frame has none set. Falls back to [0, 0]."""
        if frame_idx in self.registrations:
            return self.registrations[frame_idx]
        # Walk backwards to find the closest set registration
        for i in range(frame_idx - 1, -1, -1):
            if i in self.registrations:
                return self.registrations[i]
        return [0.0, 0.0]

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

    # ── Transforms ───────────────────────────────────────────────────────────

    def flip_horizontal(self, video_width: float):
        """Mirror all polygon points and registration coordinates horizontally.
        For a video of width W, each x becomes W - x.
        Call this AFTER the underlying video file has already been flipped."""
        # Flip polygon points
        for frame_idx, polys in self.frames.items():
            for poly in polys:
                flipped = []
                for pt in poly.get("points", []):
                    flipped.append([video_width - pt[0], pt[1]])
                poly["points"] = flipped

        # Flip registration points
        for frame_idx, reg in self.registrations.items():
            self.registrations[frame_idx] = [video_width - reg[0], reg[1]]

    # ── Export / Import ──────────────────────────────────────────────────────


    def export_json(self, filepath):
        """Export polygon + registration data as a clean JSON file.

        The format is intentionally video-agnostic so it can be loaded by
        external tools (e.g. p5.js) without knowing about the source video.

        Schema
        ------
        {
          "meta": {"tool": "bwxRotoTool", "version": 1},
          "frames": {
            "0": [
              {"color": "#00ff00", "z_index": 1,
               "points": [[x1, y1], [x2, y2], ...]},
              ...
            ],
            ...
          },
          "registrations": {
            "0": [rx, ry],
            ...
          }
        }

        All frame and registration keys are strings (JSON requirement).
        """
        data = {
            "meta": {"tool": "bwxRotoTool", "version": 1},
            "frames": {str(k): v for k, v in self.frames.items()},
            "registrations": {str(k): v for k, v in self.registrations.items()},
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def import_json(self, filepath, merge="replace"):
        """Import polygon + registration data from a JSON file produced by export_json().

        Parameters
        ----------
        merge : str
            "replace"  – discard ALL current frames/registrations and replace
                         with the imported data. (default)
            "merge"    – keep existing frames; only add frames that are NOT
                         already present in the project.
            "overwrite"– add all imported frames, overwriting any frame that
                         already exists in the project.

        Returns
        -------
        (int, int)  – (frames_imported, frames_skipped)

        Raises
        ------
        ValueError  – if the file cannot be parsed, or has an unexpected schema.
        """
        with open(filepath, "r") as f:
            data = json.load(f)

        # Support both the export_json format (has "meta" key) and raw
        # {frame_idx: [polys]} dicts for basic compatibility.
        if "frames" in data:
            raw_frames = data["frames"]
            raw_regs   = data.get("registrations", {})
        else:
            # Assume it's a bare {frame_idx: [polys]} mapping
            raw_frames = data
            raw_regs   = {}

        # Validate and migrate polygon entries (same logic as from_dict)
        imported_frames = {}
        for k, polys in raw_frames.items():
            if not isinstance(polys, list):
                raise ValueError(f"Frame '{k}' is not a list of polygons.")
            migrated = []
            for poly in polys:
                if isinstance(poly, list):
                    migrated.append({"points": poly, "color": "#00ff00", "z_index": 0})
                elif isinstance(poly, dict) and "points" in poly:
                    migrated.append(poly)
                else:
                    raise ValueError(f"Unexpected polygon entry in frame '{k}': {poly!r}")
            imported_frames[int(k)] = migrated

        imported_regs = {int(k): v for k, v in raw_regs.items()}

        imported = 0
        skipped  = 0

        if merge == "replace":
            self.frames        = imported_frames
            self.registrations = {**self.registrations, **imported_regs}
            imported = len(imported_frames)
        elif merge == "merge":
            for frame_idx, polys in imported_frames.items():
                if frame_idx in self.frames:
                    skipped += 1
                else:
                    self.frames[frame_idx] = polys
                    imported += 1
            for frame_idx, reg in imported_regs.items():
                if frame_idx not in self.registrations:
                    self.registrations[frame_idx] = reg
        elif merge == "overwrite":
            for frame_idx, polys in imported_frames.items():
                existed = frame_idx in self.frames
                self.frames[frame_idx] = polys
                if existed:
                    skipped += 1   # counted as 'overwritten' not skipped
                else:
                    imported += 1
            self.registrations.update(imported_regs)
        else:
            raise ValueError(f"Unknown merge strategy: {merge!r}")

        return imported, skipped

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
