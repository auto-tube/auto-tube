# utils/helpers.py
import subprocess
import os
import sys
import traceback
import ffmpeg # Keep ffmpeg import if used by other helpers potentially
from typing import Optional

# --- Centralized FFmpeg/FFprobe Paths ---
# Reference these in other modules if needed, or pass them explicitly
# Ensure these paths are correct for your system
FFPROBE_PATH = r"C:\Users\V0iD\Downloads\ffmpeg-2025-03-27-git-114fccc4a5-full_build\bin\ffprobe.exe"
FFMPEG_PATH = r"C:\Users\V0iD\Downloads\ffmpeg-2025-03-27-git-114fccc4a5-full_build\bin\ffmpeg.exe"
# ---

def get_media_duration(media_path: str) -> float:
    """Gets media duration (video or audio) in seconds using FFprobe via subprocess."""
    clean_path = str(media_path).strip('"')
    if not os.path.isfile(clean_path):
        print(f"HELPER ERROR [get_duration]: File not found: {clean_path}")
        return 0.0

    if not os.path.isfile(FFPROBE_PATH):
        print(f"HELPER ERROR [get_duration]: FFprobe not found at: {FFPROBE_PATH}")
        raise FileNotFoundError(f"FFprobe not found at configured path: {FFPROBE_PATH}")

    ffprobe_cmd = [FFPROBE_PATH,
                   "-v", "error", # Only show errors
                   "-show_entries", "format=duration", # Get duration only
                   "-of", "default=noprint_wrappers=1:nokey=1", # Output only the value
                   clean_path]
    try:
        print(f"HELPER: Running ffprobe for duration: {' '.join(ffprobe_cmd)}")
        # Hide console window on Windows
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=True, # check=True raises error on failure
                                encoding='utf-8', errors='replace', creationflags=creationflags)
        duration = float(result.stdout.strip())
        print(f"HELPER: Detected duration: {duration:.3f}s")
        return duration
    except FileNotFoundError: # Should be caught by isfile check, but just in case
        print(f"HELPER ERROR [get_duration]: FFprobe command failed (FileNotFound).")
        raise # Re-raise critical error
    except subprocess.CalledProcessError as e:
        print(f"HELPER ERROR [get_duration]: ffprobe failed for {clean_path}: {e.stderr or e.stdout}")
        return 0.0 # Return 0 to indicate failure to get duration
    except ValueError:
        print(f"HELPER ERROR [get_duration]: Could not parse ffprobe duration output for {clean_path}.")
        return 0.0
    except Exception as e:
        print(f"HELPER ERROR [get_duration]: Unexpected error for {clean_path}: {e}")
        traceback.print_exc()
        return 0.0


def prepare_background_video(source_video_path: str, output_path: str, target_duration: float) -> bool:
    """Trims/Loops, crops to 9:16, scales, and removes audio using FFmpeg."""
    if not os.path.isfile(FFMPEG_PATH):
        print(f"HELPER ERROR [prepare_video]: FFmpeg not found at: {FFMPEG_PATH}")
        return False

    try:
        clean_source_path = str(source_video_path).strip('"')
        clean_output_path = str(output_path).strip('"')

        if not os.path.isfile(clean_source_path):
             raise FileNotFoundError(f"Source video not found: {clean_source_path}")

        source_duration = get_media_duration(clean_source_path)
        if source_duration <= 0:
            raise ValueError(f"Source video duration is invalid ({source_duration:.2f}s).")

        # --- FFmpeg Command Construction ---
        input_options = []
        output_options = [
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '25', # Reasonably fast encoding
            '-an' # Remove audio stream from background
        ]
        filter_complex_parts = []
        inputs = [] # Store input files/options

        # Input stream label
        input_v_stream = "[0:v]" # Assume video from first input initially

        # 1. Looping/Trimming Logic
        if source_duration < target_duration:
            # Use stream_loop for input option (simpler)
            num_loops = int(target_duration // source_duration) # Full loops *before* the last partial one
            inputs.extend(['-stream_loop', str(num_loops), "-i", clean_source_path])
            # Trim the looped stream to the exact target duration using -t output option
            output_options.extend(['-t', f"{target_duration:.4f}"]) # Use precise float for -t
            print(f"HELPER Prep: Looping video input {num_loops+1} times (duration {target_duration:.2f}s)")
        else:
            # Trim using -t input option
            inputs.extend(['-t', f"{target_duration:.4f}", "-i", clean_source_path])
            print(f"HELPER Prep: Trimming video input to {target_duration:.2f}s")

        # 2. Cropping and Scaling Filters
        # Crop first, then scale and pad if necessary to ensure 1080x1920
        crop_filter = "crop=w=min(iw\\,ih*9/16):h=min(ih\\,iw*16/9)" # Crop centered to 9:16 aspect
        scale_pad_filter = "scale=w=1080:h=1920:force_original_aspect_ratio=decrease,pad=w=1080:h=1920:x=(ow-iw)/2:y=(oh-ih)/2:color=black"
        vf_filters = [crop_filter, scale_pad_filter]
        output_options.extend(['-vf', ",".join(vf_filters)])


        # --- Assemble Command ---
        cmd = [FFMPEG_PATH, "-y"] # Overwrite output
        cmd.extend(inputs)      # Add input options and file
        cmd.extend(output_options) # Add filters and output options
        cmd.append(clean_output_path) # Add output file path


        # --- Run FFmpeg ---
        print(f"HELPER Prep: Running FFmpeg: {' '.join(cmd)}")
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                creationflags=creationflags) # check=True raises error on failure

        if result.returncode != 0:
            error_message = f"FFmpeg Prep Error (Code {result.returncode}):\n{result.stderr or result.stdout}"
            print(error_message)
            return False

        print(f"HELPER Prep: Background video preparation successful -> {output_path}")
        return True

    except Exception as e:
        print(f"HELPER Prep: Unexpected error preparing background video {os.path.basename(source_video_path)}: {e}")
        traceback.print_exc()
        return False


def combine_ai_short_elements(video_path: str, audio_path: str, ass_path: str, output_path: str,
                              bg_music_path: Optional[str] = None, music_volume: float = 0.1) -> bool:
    """Combines final video, voiceover, ASS subtitles, and optional music."""
    if not os.path.isfile(FFMPEG_PATH):
        print(f"HELPER ERROR [combine]: FFmpeg not found at: {FFMPEG_PATH}")
        return False

    try:
        # --- Validate Inputs ---
        clean_video_path = str(video_path).strip('"')
        clean_audio_path = str(audio_path).strip('"')
        clean_ass_path = str(ass_path).strip('"')
        clean_output_path = str(output_path).strip('"')
        clean_bg_music_path = str(bg_music_path).strip('"') if bg_music_path else None

        if not os.path.isfile(clean_video_path): raise FileNotFoundError(f"Prepared video not found: {clean_video_path}")
        if not os.path.isfile(clean_audio_path): raise FileNotFoundError(f"Voiceover audio not found: {clean_audio_path}")
        if not os.path.isfile(clean_ass_path): raise FileNotFoundError(f"ASS subtitle file not found: {clean_ass_path}")
        if clean_bg_music_path and not os.path.isfile(clean_bg_music_path):
            print(f"Warning: Background music file specified but not found: {clean_bg_music_path}")
            clean_bg_music_path = None

        # --- Build Command ---
        cmd = [FFMPEG_PATH, "-y"] # Overwrite

        # Inputs
        inputs = ["-i", clean_video_path, "-i", clean_audio_path]
        if clean_bg_music_path:
            inputs.extend(["-i", clean_bg_music_path])
        cmd.extend(inputs)

        # Filter Complex & Mapping
        filter_complex_parts = []
        video_input_label = "[0:v]" # Video from first input
        audio_input_label = "[1:a]" # Voiceover from second input
        final_video_label = "[v_out]" # Default label for final video output
        final_audio_label = "[a_out]" # Default label for final audio output

        # Subtitle Filter (Applied first to video input)
        if sys.platform == 'win32':
             # Need to escape backslashes and colons for filter syntax
             subtitle_filter_path = clean_ass_path.replace('\\', '\\\\').replace(':', '\\:')
        else:
             subtitle_filter_path = clean_ass_path
        # Apply ASS filter to video stream 0
        filter_complex_parts.append(f"{video_input_label}ass='{subtitle_filter_path}'{final_video_label}")

        # Audio Mixing Filter (if applicable)
        if clean_bg_music_path:
            music_input_label = f"[{len(inputs)-2}:a]" # Music is the last audio input (index 2 if present)
            # Adjust music volume first
            filter_complex_parts.append(f"{music_input_label}volume=volume={music_volume}[bg_vol]")
            # Mix voiceover and volume-adjusted background music
            filter_complex_parts.append(f"{audio_input_label}[bg_vol]amix=inputs=2:duration=first{final_audio_label}")
            print("HELPER Combine: Adding audio mixing filter.")
        else:
            # If no music, just label the voiceover as the final audio output
            filter_complex_parts.append(f"{audio_input_label}anull{final_audio_label}") # Use anull filter just to label the stream

        # Add filter_complex argument if filters were added
        if filter_complex_parts:
             cmd.extend(["-filter_complex", ";".join(filter_complex_parts)])

        # Mapping - map the final labeled streams
        cmd.extend(["-map", final_video_label])
        cmd.extend(["-map", final_audio_label])

        # Encoding Parameters
        cmd.extend([
            "-c:v", "libx264", "-preset", "medium", "-crf", "23", # Adjust CRF for quality
            "-c:a", "aac", "-b:a", "192k", # Re-encode audio (required for amix)
            "-shortest", # Finish when shortest input (audio) ends
            clean_output_path
        ])

        # --- Run Command ---
        print(f"HELPER Combine: Running FFmpeg: {' '.join(cmd)}")
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                creationflags=creationflags)

        if result.returncode != 0:
            error_message = f"Final FFmpeg Composition Error (Code {result.returncode}):\n{result.stderr or result.stdout}"
            print(error_message)
            return False

        print(f"HELPER Combine: Final composition successful -> {output_path}")
        return True

    except Exception as e:
        print(f"HELPER Combine: Unexpected error during final composition: {e}")
        traceback.print_exc()
        return False