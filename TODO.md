# TODO

- [x] FEAT: convert variable framerate video clips on import to constant framerate using ffmpeg using something like: ```ffmpeg -i iphone_video.mov -r 15 -c:v libx264 -crf 18 -preset slow output_15fps.mp4```
- [x] FEAT: save progress/work as json file (format as needed to support resuming work), and we'll call it a project-name.bwxroto file.
- [x] FEAT: export polygons as json or bwxBASIC ARRAY format.
- [x] FEAT: import polygons from json or bwxBASIC ARRAY format.