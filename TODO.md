# TODO

- [x] FEAT: convert variable framerate video clips on import to constant framerate using ffmpeg using something like: ```ffmpeg -i iphone_video.mov -r 15 -c:v libx264 -crf 18 -preset slow output_15fps.mp4```
- [ ] FEAT: save progress/work as json file (format as needed to support resuming work), and we'll call it a project-name.bwxroto file.
- [ ] FEAT: export polygons as json or bwxBASIC ARRAY format.
- [ ] FEAT: import polygons from json or bwxBASIC ARRAY format.
- [ ] FEAT: add keyboard shortcuts for common operations (space to play/pause, arrow keys to step through frames, etc.)
- [ ] FEAT: add support for multiple polygons per frame.
- [ ] FEAT: add support for changing the color of polygons, and the color of the polygon outline, and the drawing order (stacking).
- [x] FEAT: add View menu to set a specific zoom on the workspace, and support shift-drag to pan the workspace. Support zoom in/out with mouse wheel (by 10% increments).
