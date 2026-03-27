# TODO

- [x] FEAT: convert variable framerate video clips on import to constant framerate using ffmpeg using something like: ```ffmpeg -i iphone_video.mov -r 15 -c:v libx264 -crf 18 -preset slow output_15fps.mp4```
- [X] FEAT: save progress/work as json file (format as needed to support resuming work), and we'll call it a project-name.bwxroto file.
- [X] FEAT: export polygons as json or bwxBASIC ARRAY format.
- [ ] FEAT: import polygons from json or bwxBASIC ARRAY format.
- [X] FEAT: add keyboard shortcuts for common operations (space to play/pause, arrow keys to step through frames, etc.)
- [X] FEAT: add support for multiple polygons per frame.
- [x] FEAT: add support for editing polygons; changing the fill color, and the drawing order (stacking). <ctrl-P> should pop up the color palette, clicking on the polygon should select it; the color palette should update to show the current fill color of the current polygon, vertex handles should appear, and the selected polygon should be highlighted. Clicking on a vertex handle should highlight it, dragging a vertex handle should move the vertex, and the selected polygon should be updated. Hitting delete or backspace when a polygon is selected should delete it, and hitting delete or backspace when a vertex handle is selected should delete it. 
- [x] FEAT: add View menu to set a specific zoom on the workspace, and support shift-drag to pan the workspace. Support zoom in/out with mouse wheel (by 10% increments).
