# Antigravity Roto-Tool Implementation Plan

Our goal is to evolve the current basic video frame viewer into a robust, streamlined python-based rotoscoping tool. Students will be able to select an iPhone video clip, convert it to a constant 15fps framerate via ffmpeg, map polygons over the frames, and save/export their progress.

## User Review Required

> [!IMPORTANT]
> - Do you want the `ffmpeg` output files to be placed in the same directory as the original videos (e.g., `video.mov` -> `video_15fps.mp4`), or should they go into a dedicated workspace/temp folder?
> - For drawing polygons, what is the preferred UX? (e.g., Click to add points, right-click/Enter to close the polygon)
> - Should we switch the `QLabel` video display to a `QGraphicsView`/`QGraphicsScene`? This is highly recommended for PyQt as it natively handles interactive shapes, coordinates, and points over the background image.

## Proposed Changes

---

### UI Architecture & Canvas Refactor

We will rebuild the main window to support interaction, dialogs, and tools.

#### [MODIFY] main.py (or break out into components)
- **Menu Bar & Actions**: Add `File -> Open Video`, `File -> Open Project`, `File -> Save Project`, `File -> Export bwxBASIC`.
- **Canvas Switch**: Replace `QLabel` with `QGraphicsView` and `QGraphicsScene`. 
  - The scene will have a background layer (the QPixmap of the current frame).
  - A foreground layer managing `QGraphicsPolygonItem` and `QGraphicsEllipseItem` (for drawing points).
- **Control Panel**: Add a timeline or status bar showing the current frame, total frames, and tool state.

---

### iPhone Video Processing (FFmpeg)

Address the variable frame rate issue directly on import.

#### [NEW] src/video_processor.py
- Implement a helper function `convert_to_15fps(input_path, output_path)` using `ffmpeg-python`.
- **Command equivalent**: `ffmpeg -i input.mov -r 15 -c:v libx264 -crf 18 -preset slow output.mp4`
- When opening a new video from the UI, a progress dialog will show while it synchronously (or asynchronously) transcodes the video before loading it into the `QGraphicsScene`.

---

### Project Data & Serialization (.bwxroto files)

Support resuming work and managing state.

#### [NEW] src/project_model.py
- Create a `RotoProject` class to maintain state:
  - Reference to the source/processed video path.
  - Dictionary mapping `frame_index` to a list of polygons. (e.g., `{ 0: [[ (x1,y1), (x2,y2) ], ...], 1: [...] }`)
- Methods for `save_to_json(filepath)` and `load_from_json(filepath)`.
- When exporting to bwxBASIC ARRAY format, format the data specifically as BASIC variable assignments or DATA lines.

## Next Steps Upon Approval
1. Add `QGraphicsView` support to `main.py` and implement basic polygon drawing with the mouse.
2. Integrate `ffmpeg-python` to process the clips upon selection.
3. Build the saving and loading architecture for `.bwxroto` and `.json` formats.
4. Check off the items in `TODO.md` as we complete each milestone.

## Open Questions

- Should we allow multiple polygons per frame, or just a single main character polygon?
- Do you have a specific format structure in mind for the `bwxBASIC ARRAY` export?

## Verification Plan

### Automated/Manual Tests
- **Import**: Pick a variable framerate `.mov` file from a test folder, verify `ffmpeg` transcodes it to exactly 15fps.
- **Roto**: Click points around a subject to form a polygon. Step to the next frame and ensure a clean canvas (or onion skin later). Step back and ensure the old polygon is there.
- **Serialization**: Save the project as `test.bwxroto`. Close the app, re-open, and load `test.bwxroto`. Verify polygons load onto their correct frames.
