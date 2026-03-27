# Antigravity Roto-Tool 🕺✨

A custom, open-source rotoscoping utility designed to capture student dance 
performances and convert them into low-fidelity polygonal animations for 
retro-style games.

## The 15 FPS Philosophy
To achieve a "crunchy" retro aesthetic, this tool forces a 15 fps workflow 
regardless of the source video's frame rate. By editing at the target 
game-speed, we ensure that every vertex move is intentional and visible 
in the final engine.

## Features
* **Frame Stepping:** Automatically skips frames to maintain a 15 fps cadence.
* **Polygon Mapping:** Click-to-draw vertex points over video frames.
* **JSON Export:** Saves animation data as lightweight coordinate sets.
* **Onion Skinning:** (Planned) See the previous frame's pose to maintain flow.

## Project Structure
* `/src`: The Python source code.
* `/data`: JSON exports of the rotoscoped paths.
* `/video`: Source footage (Use Git LFS for these!).

## Quick Start
1. Build the venv and install dependencies: `make setup`
2. Run the tool: `make run`
3. Load your iPhone footage and start "tinkering."

> `make clean` removes the `.venv` if you need a fresh install.

## Documentation & Controls

We've evolved the tool beyond a simple viewer into a fully interactive rotoscoping suite.

### Video Management
When you open an iPhone clip (or any variable framerate video), the tool automatically leverages `ffmpeg` to process and transcode a `_15fps.mp4` caching file directly beside it. Next time you open the same clip, it instantly loads the cached version to save time.

### Rotoscope Drawing
- **Add Points:** Left-click anywhere on the video frame to drop a vertex.
- **Close Polygon:** Right-click (or press `Enter`) to seal the polygon and commit it.
- **Delete Polygon:** Press `Backspace` to clear all polygons on the current frame.

### Project Saving & Export
- **Save Projects:** Save your progress natively into `.bwxroto` JSON files, preserving exactly what polygons sit on which frames.
- **bwxBASIC Export:** Export the rotoscoped coordinates into a pure `.bas` file consisting of sequentially formatted `DATA` statements ready to be pasted into older retro systems! 

### View & Canvas Navigation
The canvas supports seamless zooming and panning over high-definition details:
- **Zoom In:** `Ctrl + =` or Scroll Mouse Wheel Up.
- **Zoom Out:** `Ctrl + -` or Scroll Mouse Wheel Down.
- **Reset Zoom (100%):** `Ctrl + 0`
- **Zoom to Fit:** `Ctrl + F`
- **Pan Image:** Hold `Shift` and Left-Click Drag. *Note: Holding shift will temporarily disable polygon point placement to protect your drawings while you pan!*

### Registration Point
Each frame has a draggable **⊕ yellow crosshair** that marks the character's anchor (e.g. the ball of the foot). All exported coordinates are relative to this point, so the game engine can place the character independently of its position in the source video.
- **Move Anchor:** Drag the ⊕ crosshair to the desired body landmark.
- **Copy from Previous Frame:** `Shift+R` — snaps the current frame's anchor to the same position as the previous frame's anchor (great for thumbnails with minimal movement).
- **Toggle Visibility:** `View → Show Registration Point` (`Ctrl+Shift+R`)

### Playback Preview
Open a non-modal animation preview window via **`Window → Open Playback Preview`** (`Ctrl+Shift+P`). The window plays back all rotoscoped frames at 15 FPS using registration-normalized coordinates (character centred at origin), independent of the background video.
- **Play/Pause:** ⏸ / ▶ button
- **Loop:** ⟳ Loop toggle
- **Background Color:** Click the BG Color swatch to change the preview background.

### Onion Skinning
Ghost frames are automatically **registration-aligned** — the previous/next frame's pose is shifted so the character body overlaps the current frame, not the raw screen position.
- **Previous frame only:** `O`
- **Previous + next frames:** `Shift+O`

### Timeline Controls
- **Next Frame:** `D`
- **Previous Frame:** `A`