import ffmpeg
import os

def convert_to_15fps(input_path, output_path=None):
    """
    Converts a variable framerate video (like from an iPhone) entirety to 15fps.
    Equivalent to: ffmpeg -i input.mov -r 15 -c:v libx264 -crf 18 -preset slow output.mp4
    Returns the path to the converted video.
    """
    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = f"{base}_15fps.mp4"

    # Skip conversion if the 15fps processed video is already up to date
    if os.path.exists(output_path) and os.path.exists(input_path):
        if os.path.getmtime(output_path) >= os.path.getmtime(input_path):
            return output_path

    try:
        stream = ffmpeg.input(input_path)
        # Apply the parameters from the TODO: -r 15 -c:v libx264 -crf 18 -preset slow
        stream = ffmpeg.output(stream, output_path, r=15, vcodec='libx264', crf=18, preset='slow')
        # We can capture stderr for debugging if needed, but we'll leave it quiet.
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
        return output_path
    except ffmpeg.Error as e:
        print(f"Error during ffmpeg conversion", flush=True)
        if e.stderr:
            print(e.stderr.decode('utf8', errors='ignore'), flush=True)
        return None
