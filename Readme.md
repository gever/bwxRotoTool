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
1. Install dependencies: `pip install -r requirements.txt`
2. Run the tool: `python src/main.py`
3. Load your iPhone footage and start "tinkering."

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

### Timeline Controls
- **Next Frame:** `D`
- **Previous Frame:** `A`