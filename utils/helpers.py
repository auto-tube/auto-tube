# utils/helpers.py
import subprocess
import os
import sys
import traceback
import ffmpeg
from typing import Optional, Tuple
import shutil

# --- Helper function to determine resource path for bundled apps ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        # Not bundled, running in normal Python environment
        # Get the directory of the *current* script file (helpers.py)
        base_path = os.path.dirname(os.path.abspath(__file__))
        # Go one level up to reach the project root (assuming utils/ is directly in root)
        base_path = os.path.dirname(base_path)

    return os.path.join(base_path, relative_path)
# --- End resource_path helper ---


# --- Function to find executables (MODIFIED - Removed Config Path Check) ---
def find_ffmpeg_executables() -> Tuple[Optional[str], Optional[str]]:
    """
    Tries to find FFmpeg and FFprobe executables in a specific order.

    Checks order:
    1. Bundled path (using resource_path('bin/...')) - Handles both packaged EXE and dev script.
    2. Environment variables (FFMPEG_PATH, FFPROBE_PATH).
    3. System PATH using shutil.which().

    Returns:
        Tuple[Optional[str], Optional[str]]: (ffmpeg_path, ffprobe_path)
                                             Absolute paths if found, None otherwise.
    """
    ffmpeg_path = None
    ffprobe_path = None
    print("HELPER: Searching for FFmpeg/FFprobe executables...")

    # Determine potential executable names based on OS
    ffmpeg_exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    ffprobe_exe_name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"

    # --- Check Order ---
    # 1. Bundled/Local Path (using resource_path)
    bundled_ffmpeg_check = resource_path(os.path.join('bin', ffmpeg_exe_name))
    bundled_ffprobe_check = resource_path(os.path.join('bin', ffprobe_exe_name))

    print(f"HELPER: Checking bundled/local path: {bundled_ffmpeg_check}")
    if os.path.isfile(bundled_ffmpeg_check):
        print(f"HELPER: Found bundled/local ffmpeg: {bundled_ffmpeg_check}")
        ffmpeg_path = bundled_ffmpeg_check

    print(f"HELPER: Checking bundled/local path: {bundled_ffprobe_check}")
    if os.path.isfile(bundled_ffprobe_check):
        print(f"HELPER: Found bundled/local ffprobe: {bundled_ffprobe_check}")
        ffprobe_path = bundled_ffprobe_check

    # 2. Environment variables (if not found bundled/local)
    if not ffmpeg_path:
        ffmpeg_env = os.environ.get("FFMPEG_PATH")
        if ffmpeg_env and os.path.isfile(ffmpeg_env):
            print(f"HELPER: Found ffmpeg via FFMPEG_PATH env var: {ffmpeg_env}")
            ffmpeg_path = ffmpeg_env
    if not ffprobe_path:
        ffprobe_env = os.environ.get("FFPROBE_PATH")
        if ffprobe_env and os.path.isfile(ffprobe_env):
            print(f"HELPER: Found ffprobe via FFPROBE_PATH env var: {ffprobe_env}")
            ffprobe_path = ffprobe_env

    # 3. System PATH (if not found bundled/local or via env var)
    if not ffmpeg_path:
        ffmpeg_path_which = shutil.which("ffmpeg") # Finds ffmpeg or ffmpeg.exe
        if ffmpeg_path_which:
            print(f"HELPER: Found ffmpeg via system PATH: {ffmpeg_path_which}")
            ffmpeg_path = ffmpeg_path_which
        else:
            # Only warn if not found via any previous method
            if not os.environ.get("FFMPEG_PATH"):
                 print("HELPER WARN: ffmpeg not found in bundled/local/env/PATH.")

    if not ffprobe_path:
        ffprobe_path_which = shutil.which("ffprobe") # Finds ffprobe or ffprobe.exe
        if ffprobe_path_which:
            print(f"HELPER: Found ffprobe via system PATH: {ffprobe_path_which}")
            ffprobe_path = ffprobe_path_which
        else:
            # Only warn if not found via any previous method
            if not os.environ.get("FFPROBE_PATH"):
                 print("HELPER WARN: ffprobe not found in bundled/local/env/PATH.")


    # Final check and log outcome
    if not ffmpeg_path:
        print("HELPER ERROR: FFmpeg executable could NOT be located.")
    if not ffprobe_path:
        print("HELPER ERROR: FFprobe executable could NOT be located.")

    return ffmpeg_path, ffprobe_path
# --- End find_ffmpeg_executables ---


# --- REFACTORED get_media_duration ---
def get_media_duration(media_path: str, ffprobe_exec: Optional[str]) -> float:
    """Gets media duration (video or audio) in seconds using ffmpeg.probe."""
    clean_path = str(media_path).strip('"')
    if not os.path.isfile(clean_path):
        print(f"HELPER ERROR [get_duration]: File not found: {clean_path}")
        return 0.0

    if not ffprobe_exec or not os.path.isfile(ffprobe_exec):
        print(f"HELPER ERROR [get_duration]: Provided FFprobe path is invalid or not found: {ffprobe_exec}")
        raise FileNotFoundError(f"Invalid or missing FFprobe executable path provided: {ffprobe_exec}")

    try:
        print(f"HELPER: Probing duration for {os.path.basename(clean_path)} using {ffprobe_exec}")
        probe_result = ffmpeg.probe(clean_path, cmd=ffprobe_exec)
        duration = float(probe_result["format"]["duration"])
        print(f"HELPER: Detected duration: {duration:.3f}s")
        return duration
    except ffmpeg.Error as e:
        stderr = e.stderr.decode('utf-8', errors='replace') if e.stderr else "N/A"
        print(f"HELPER ERROR [get_duration]: FFprobe error for {os.path.basename(clean_path)}: {stderr}")
        return 0.0
    except (KeyError, ValueError, TypeError) as e:
        print(f"HELPER ERROR [get_duration]: Error parsing duration from FFprobe output for {os.path.basename(clean_path)}: {e}")
        return 0.0
    except Exception as e:
        print(f"HELPER ERROR [get_duration]: Unexpected error for {os.path.basename(clean_path)}: {e}")
        traceback.print_exc()
        return 0.0
# --- End REFACTORED get_media_duration ---


# --- REFACTORED prepare_background_video ---
def prepare_background_video(source_video_path: str, output_path: str, target_duration: float,
                              ffmpeg_exec: Optional[str], ffprobe_exec: Optional[str]) -> bool:
    """Trims/Loops, crops/scales/pads to 9:16, and removes audio using ffmpeg-python."""
    if not ffmpeg_exec or not os.path.isfile(ffmpeg_exec): print(f"HELPER ERROR [prepare_video]: Provided FFmpeg path is invalid or not found: {ffmpeg_exec}"); return False
    try:
        clean_source_path = str(source_video_path).strip('"'); clean_output_path = str(output_path).strip('"')
        if not os.path.isfile(clean_source_path): raise FileNotFoundError(f"Source video not found: {clean_source_path}")
        source_duration = get_media_duration(clean_source_path, ffprobe_exec)
        if source_duration <= 0: raise ValueError(f"Source video duration could not be determined or is invalid ({source_duration:.2f}s).")
        input_kwargs = {}; output_kwargs = {'c:v': 'libx264', 'preset': 'fast', 'crf': '25', 'an': None}
        if source_duration < target_duration: num_loops = int(target_duration // source_duration); input_kwargs['stream_loop'] = str(num_loops); output_kwargs['t'] = f"{target_duration:.4f}"; print(f"HELPER Prep: Looping video input {num_loops+1} times (target duration {target_duration:.2f}s)")
        else: input_kwargs['t'] = f"{target_duration:.4f}"; print(f"HELPER Prep: Trimming video input to {target_duration:.2f}s")
        input_stream = ffmpeg.input(clean_source_path, **input_kwargs); video_stream = input_stream['v']
        video_stream = video_stream.filter("crop", w="min(iw,ih*9/16)", h="min(ih,iw*16/9)")
        video_stream = video_stream.filter("scale", w="1080", h="1920", force_original_aspect_ratio="decrease")
        video_stream = video_stream.filter("pad", w="1080", h="1920", x="(ow-iw)/2", y="(oh-ih)/2", color="black")
        video_stream = video_stream.filter("setsar", sar="1")
        stream = ffmpeg.output(video_stream, clean_output_path, **output_kwargs)
        cmd_list_for_log = stream.compile(cmd=ffmpeg_exec, overwrite_output=True)
        print(f"HELPER Prep: Running FFmpeg command (via ffmpeg-python): {' '.join(cmd_list_for_log)}")
        try:
            stdout, stderr = stream.run(cmd=ffmpeg_exec, capture_stdout=True, capture_stderr=True, overwrite_output=True)
            stderr_str = stderr.decode('utf-8', errors='replace').strip();
            if stderr_str: print(f"HELPER Prep FFmpeg Info:\n{stderr_str[:1000]}{'...' if len(stderr_str)>1000 else ''}")
            if os.path.isfile(clean_output_path) and os.path.getsize(clean_output_path) > 0: print(f"HELPER Prep: Background video preparation successful -> {output_path}"); return True
            else: print(f"HELPER Prep ERROR: FFmpeg command finished but output file is missing or empty: {output_path}"); return False
        except ffmpeg.Error as e: stderr_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else "No stderr available"; print(f"HELPER Prep ERROR: FFmpeg failed (via ffmpeg-python):\n{stderr_output}"); return False
    except FileNotFoundError as e: print(f"HELPER Prep ERROR: Required file not found: {e}"); return False
    except ValueError as e: print(f"HELPER Prep ERROR: Invalid value encountered: {e}"); return False
    except Exception as e: print(f"HELPER Prep: Unexpected error preparing background video {os.path.basename(source_video_path)}: {e}"); traceback.print_exc(); return False
# --- End REFACTORED prepare_background_video ---


# --- REFACTORED combine_ai_short_elements ---
def combine_ai_short_elements(video_path: str, audio_path: str, ass_path: str, output_path: str,
                              ffmpeg_exec: Optional[str], bg_music_path: Optional[str] = None, music_volume: float = 0.1) -> bool:
    """Combines final video, voiceover, ASS subtitles, and optional music using ffmpeg-python."""
    if not ffmpeg_exec or not os.path.isfile(ffmpeg_exec): print(f"HELPER ERROR [combine]: Provided FFmpeg path is invalid or not found: {ffmpeg_exec}"); return False
    try:
        clean_video_path=str(video_path).strip('"'); clean_audio_path=str(audio_path).strip('"'); clean_ass_path=str(ass_path).strip('"'); clean_output_path=str(output_path).strip('"'); clean_bg_music_path = str(bg_music_path).strip('"') if bg_music_path else None
        if not os.path.isfile(clean_video_path): raise FileNotFoundError(f"Prepared video not found: {clean_video_path}")
        if not os.path.isfile(clean_audio_path): raise FileNotFoundError(f"Voiceover audio not found: {clean_audio_path}")
        if not os.path.isfile(clean_ass_path): raise FileNotFoundError(f"ASS subtitle file not found: {clean_ass_path}")
        if clean_bg_music_path and not os.path.isfile(clean_bg_music_path): print(f"Warning: Background music file specified but not found: {clean_bg_music_path}"); clean_bg_music_path = None
        input_video=ffmpeg.input(clean_video_path); input_audio=ffmpeg.input(clean_audio_path); input_music=None; streams_to_output=[]
        if sys.platform == 'win32': escaped_ass_path = clean_ass_path.replace('\\', '\\\\').replace(':', '\\:')
        else: escaped_ass_path = clean_ass_path.replace("'", "'\\''")
        video_stream=input_video['v'].filter('ass', filename=escaped_ass_path); streams_to_output.append(video_stream)
        voice_stream=input_audio['a']
        if clean_bg_music_path: input_music=ffmpeg.input(clean_bg_music_path); music_stream=input_music['a'].filter('volume', volume=f"{music_volume:.2f}"); mixed_audio=ffmpeg.filter([voice_stream, music_stream], 'amix', inputs=2, duration='first', dropout_transition=1); final_audio_stream=mixed_audio; print("HELPER Combine: Using amix filter for audio mixing.")
        else: final_audio_stream=voice_stream
        streams_to_output.append(final_audio_stream)
        output_kwargs={'c:v': 'libx264', 'preset': 'medium', 'crf': '23', 'c:a': 'aac', 'b:a': '192k', 'shortest': None}
        stream=ffmpeg.output(*streams_to_output, clean_output_path, **output_kwargs); cmd_list_for_log=stream.compile(cmd=ffmpeg_exec, overwrite_output=True)
        print(f"HELPER Combine: Running FFmpeg command (via ffmpeg-python): {' '.join(cmd_list_for_log)}")
        try:
            stdout, stderr = stream.run(cmd=ffmpeg_exec, capture_stdout=True, capture_stderr=True, overwrite_output=True)
            stderr_str = stderr.decode('utf-8', errors='replace').strip();
            if stderr_str: print(f"HELPER Combine FFmpeg Info:\n{stderr_str[:1000]}{'...' if len(stderr_str)>1000 else ''}")
            if os.path.isfile(clean_output_path) and os.path.getsize(clean_output_path) > 0: print(f"HELPER Combine: Final composition successful -> {output_path}"); return True
            else: print(f"HELPER Combine ERROR: FFmpeg command finished but output file is missing or empty: {output_path}"); return False
        except ffmpeg.Error as e: stderr_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else "No stderr available"; print(f"HELPER Combine ERROR: FFmpeg failed (via ffmpeg-python):\n{stderr_output}"); return False
    except FileNotFoundError as e: print(f"HELPER Combine ERROR: Required file not found: {e}"); return False
    except Exception as e: print(f"HELPER Combine: Unexpected error during final composition: {e}"); traceback.print_exc(); return False
# --- End REFACTORED combine_ai_short_elements ---