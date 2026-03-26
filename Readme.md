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