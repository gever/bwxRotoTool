import ffmpeg
import os
import shutil

def check_ffmpeg():
    """Returns True if the ffmpeg binary is available on PATH."""
    return shutil.which('ffmpeg') is not None

def convert_to_15fps(input_path, output_path=None):
    """
    Converts a variable framerate video (like from an iPhone) to 15 fps,
    stripping audio since we only need the visual frames.
    Equivalent to: ffmpeg -i input.mov -r 15 -an -c:v libx264 -crf 18 -preset slow output.mp4
    Returns (output_path, None) on success, or (None, error_message) on failure.
    """
    if not check_ffmpeg():
        return None, (
            "ffmpeg is not installed or not on PATH.\n\n"
            "Install it with:\n  sudo apt install ffmpeg"
        )

    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = f"{base}_15fps.mp4"

    # Skip conversion if the cached 15fps file is already up to date
    if os.path.exists(output_path) and os.path.exists(input_path):
        if os.path.getmtime(output_path) >= os.path.getmtime(input_path):
            return output_path, None

    try:
        stream = ffmpeg.input(input_path)
        # -an strips audio (not needed), -r 15 targets game frame rate
        stream = ffmpeg.output(stream, output_path, r=15, an=None, vcodec='libx264', crf=18, preset='slow')
        ffmpeg.run(stream, overwrite_output=True, quiet=True)
        return output_path, None
    except ffmpeg.Error as e:
        stderr_text = e.stderr.decode('utf8', errors='ignore') if e.stderr else str(e)
        print(f"ffmpeg error:\n{stderr_text}", flush=True)
        return None, f"ffmpeg conversion failed:\n\n{stderr_text[-800:]}"

