# TODO

- [x] FEAT01: convert variable framerate video clips on import to constant framerate using ffmpeg using something like: ```ffmpeg -i iphone_video.mov -r 15 -c:v libx264 -crf 18 -preset slow output_15fps.mp4```
- [X] FEAT02: save progress/work as json file (format as needed to support resuming work), and we'll call it a project-name.bwxroto file.
- [X] FEAT03: export polygons as json or bwxBASIC ARRAY format.
- [ ] FEAT04: import polygons from json or bwxBASIC ARRAY format.
- [X] FEAT05 add keyboard shortcuts for common operations (space to play/pause, arrow keys to step through frames, etc.)
- [X] FEAT06: add support for multiple polygons per frame.
- [X] FEAT07: add support for editing polygons; changing the fill color, and the drawing order (stacking). <ctrl-P> should pop up the color palette, clicking on the polygon should select it; the color palette should update to show the current fill color of the current polygon, vertex handles should appear, and the selected polygon should be highlighted. Clicking on a vertex handle should highlight it, dragging a vertex handle should move the vertex, and the selected polygon should be updated. Hitting delete or backspace when a polygon is selected should delete it, and hitting delete or backspace when a vertex handle is selected should delete it. 
- [x] FEAT08: add View menu to set a specific zoom on the workspace, and support shift-drag to pan the workspace. Support zoom in/out with mouse wheel (by 10% increments).
- [X] BUG01: polygons can be pushed back behind the background image. 
- [ ] FEAT09: add support for deleting a vertex on a polygon.
- [X] FEAT10: add support for deleting a polygon.
- [X] FEAT11: add command to file menu to export as JSON for use in p5.js based projects (add a sample p5.js project to the repo that illustrates how to load and draw the polygon data).
- [X] FEAT12: add command to file menu to import JSON polygon data.

- [X] FEAT13: add command to tools menu to flip video horizontally (and update the polygon data accordingly).

- [ ] FEAT14: add command to tools menu to flip video vertically.
- [ ] FEAT15: add command to tools menu to rotate video 90 degrees clockwise (multiple times to allow for 180 and 270 degree rotations).
- [X] BUG02: the order of colors in the color tiles changes when a color is selected. This is unexpected behabior for the users who expect the color to be in the same position. The fix is to just add colors in on left when new colors are created, pushing older colors to the right. To encourage minimal color usage, let's only keep the most recent 16 colors.

