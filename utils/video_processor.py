# utils/video_processor.py

import os
import subprocess
import json
import logging
import time
import math
import sys # Needed for sys.platform
import traceback # Import traceback
from typing import Optional, Tuple, List, Dict, Any

# Try importing ffmpeg-python
FFMPEG_PYTHON_AVAILABLE = False
try:
    import ffmpeg
    FFMPEG_PYTHON_AVAILABLE = True
except ImportError:
    # Use print for immediate feedback if logger isn't set up yet during import
    print("ERROR [video_processor]: ffmpeg-python library not found. Install using: pip install ffmpeg-python")
    print("ERROR [video_processor]: Video filtering (including vertical cropping) will NOT work.")
    # Define dummy ffmpeg module if needed, although errors will likely occur later
    class FFmpegDummy:
        def input(self, *args, **kwargs): raise ImportError("ffmpeg-python not available")
        def output(self, *args, **kwargs): raise ImportError("ffmpeg-python not available")
        def probe(self, *args, **kwargs): raise ImportError("ffmpeg-python not available")
        # Define dummy Error class that subclasses Exception for broader catching
        class Error(Exception): pass
    ffmpeg = FFmpegDummy() # Assign dummy

# --- Scenedetect Imports ---
scenedetect_available = False
try:
    # Core components
    from scenedetect import open_video, SceneManager, StatsManager
    # Available detectors
    from scenedetect.detectors import ContentDetector # Most common
    # Corrected exception import (based on the error message)
    from scenedetect.stats_manager import StatsFileCorrupt
    # FrameTimecode for time calculations
    from scenedetect import FrameTimecode
    scenedetect_available = True
except ImportError:
    print("WARNING [video_processor]: PySceneDetect library not found. Scene detection features will be unavailable.")
    print("Install using: pip install scenedetect[opencv]")
    # Define dummy classes/exceptions if scenedetect is missing
    class FrameTimecode:
        def __init__(self, timecode, fps): pass
        def get_seconds(self): return 0.0
    class SceneManager: pass
    class StatsManager: pass
    class ContentDetector: pass
    class StatsFileCorrupt(Exception): pass # Define dummy exception
    def open_video(*args, **kwargs):
        raise ImportError("PySceneDetect not available")

# --- Custom Exceptions ---
class FFmpegNotFoundError(Exception):
    """Custom exception for when FFmpeg/FFprobe is not found or fails verification."""
    pass

class VideoProcessingError(Exception):
    """Custom exception for general errors during video processing."""
    pass

# --- VideoProcessor Class ---
class VideoProcessor:
    """Handles video processing tasks like clipping (with vertical formatting) and scene detection."""

    def __init__(self, output_dir: str, ffmpeg_path: str = 'ffmpeg', ffprobe_path: str = 'ffprobe', logger: Optional[logging.Logger] = None):
        """
        Initializes the VideoProcessor.

        Args:
            output_dir: The base directory where processed clips will be saved.
            ffmpeg_path: Path to the FFmpeg executable. Defaults to 'ffmpeg'.
            ffprobe_path: Path to the FFprobe executable. Defaults to 'ffprobe'.
            logger: An optional logger instance. If None, a default logger is created.

        Raises:
            FFmpegNotFoundError: If FFmpeg or FFprobe cannot be found or verified.
            ValueError: If the output directory cannot be created.
        """
        self.output_dir = output_dir
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path

        # Use provided logger or set up a basic one
        if logger:
            self.logger = logger
        else:
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            self.logger = logging.getLogger(__name__)

        self.logger.info(f"VideoProcessor initialized. Output Dir Target: '{self.output_dir}'")
        self.logger.info(f"Using potential FFmpeg path: '{self.ffmpeg_path}'")
        self.logger.info(f"Using potential FFprobe path: '{self.ffprobe_path}'")

        # Verify FFmpeg/FFprobe paths immediately
        self.logger.info(f"VideoProcessor attempting to verify FFmpeg: '{self.ffmpeg_path}'")
        if not self._verify_executable(self.ffmpeg_path):
            raise FFmpegNotFoundError(f"FFmpeg executable not found or verification failed at: {self.ffmpeg_path}")
        else:
             self.logger.info(f"Verification PASSED for FFmpeg.")

        self.logger.info(f"VideoProcessor attempting to verify FFprobe: '{self.ffprobe_path}'")
        if not self._verify_executable(self.ffprobe_path):
            raise FFmpegNotFoundError(f"FFprobe executable not found or verification failed at: {self.ffprobe_path}")
        else:
             self.logger.info(f"Verification PASSED for FFprobe.")

        # Ensure output directory exists
        try:
            if self.output_dir and self.output_dir != ".":
                os.makedirs(self.output_dir, exist_ok=True)
                self.logger.info(f"Output directory ensured: '{self.output_dir}'")
            else:
                self.logger.debug(f"Skipping output directory creation for placeholder: '{self.output_dir}'")
        except OSError as e:
            self.logger.error(f"Failed to create output directory '{self.output_dir}': {e}")
            raise ValueError(f"Could not create output directory: {e}")

    def _verify_executable(self, exec_path: str) -> bool:
        """Checks if the given path is an executable file using -version."""
        self.logger.debug(f"_verify_executable called for: {exec_path}")

        if not exec_path:
             self.logger.error("_verify_executable failed: exec_path is None or empty.")
             return False
        if not isinstance(exec_path, str):
             self.logger.error(f"_verify_executable failed: exec_path is not a string ({type(exec_path)}). Value: {exec_path}")
             return False
        if not os.path.isfile(exec_path):
            self.logger.error(f"_verify_executable failed: Path is not a file: {exec_path}")
            return False

        cmd = [exec_path, "-version"]
        self.logger.debug(f"_verify_executable running command: {' '.join(cmd)}")
        try:
            process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     check=False, text=True, encoding='utf-8', errors='ignore', timeout=10)
            output = process.stdout.lower() + process.stderr.lower()
            self.logger.debug(f"_verify_executable command finished. Return Code: {process.returncode}. Output length: {len(output)}")
            self.logger.debug(f"_verify_executable Output Snippet:\n{output[:500]}{'...' if len(output)>500 else ''}")

            is_ffmpeg = "ffmpeg version" in output
            is_ffprobe = "ffprobe version" in output

            if is_ffmpeg or is_ffprobe:
                self.logger.debug(f"_verify_executable PASSED (version string found): {exec_path}")
                return True
            else:
                if process.returncode == 0:
                     self.logger.warning(f"_verify_executable PASSED (return code 0, but version string missing): {exec_path}")
                     return True
                elif "usage:" in output or "option not found" in output:
                     self.logger.warning(f"_verify_executable PASSED (likely ran, showed usage/error message): {exec_path}")
                     return True
                else:
                     self.logger.error(f"_verify_executable FAILED (non-zero return code and no version/usage string): {exec_path}")
                     return False
        # Separate except blocks for different errors
        except FileNotFoundError:
            self.logger.error(f"_verify_executable FAILED: FileNotFoundError for {exec_path}")
            return False
        except subprocess.TimeoutExpired:
            self.logger.error(f"_verify_executable FAILED: Command timed out for {exec_path}.")
            return False
        except PermissionError:
            self.logger.error(f"_verify_executable FAILED: PermissionError executing {exec_path}.")
            return False
        except Exception as e:
            self.logger.error(f"_verify_executable FAILED: Unexpected error for {exec_path}: {e}", exc_info=True)
            return False

    def _run_command(self, cmd: List[str], purpose: str) -> Tuple[bool, str, str]:
        """Runs a basic subprocess command (FFmpeg/FFprobe) and handles errors."""
        self.logger.debug(f"Running Command ({purpose}): {' '.join(cmd)}")
        try:
            process = subprocess.run(cmd, capture_output=True, check=False, text=True, encoding='utf-8', errors='ignore')
            stdout = process.stdout
            stderr = process.stderr
            if stderr and stderr.strip():
                 self.logger.debug(f"Stderr from {purpose} (Return Code {process.returncode}): {stderr.strip()}")

            if process.returncode != 0:
                self.logger.error(f"Error during {purpose}. Return Code: {process.returncode}")
                self.logger.error(f"Command: {' '.join(cmd)}")
                error_summary = stderr.strip().splitlines()
                self.logger.error(f"Stderr Summary: {' | '.join(error_summary[:5])}{'...' if len(error_summary) > 5 else ''}")
                return False, stdout, stderr

            self.logger.debug(f"{purpose.capitalize()} command execution successful (Return Code 0).")
            return True, stdout, stderr
        # Separate except blocks
        except FileNotFoundError:
            self.logger.critical(f"Command failed: Executable not found for '{cmd[0]}'")
            raise FFmpegNotFoundError(f"Executable not found: {cmd[0]}")
        except Exception as e:
            self.logger.critical(f"Unexpected error running command '{' '.join(cmd)}': {e}", exc_info=True)
            raise VideoProcessingError(f"Unexpected error during {purpose}: {e}")

    def get_video_info(self, input_path: str) -> Optional[Dict[str, Any]]:
        """Gets video information using FFprobe."""
        if not os.path.exists(input_path):
            self.logger.error(f"Cannot get info: Input file not found: {input_path}")
            return None

        cmd = [
            self.ffprobe_path,
            '-v', 'error',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            input_path
        ]
        success, stdout, stderr = self._run_command(cmd, f"getting video info for {os.path.basename(input_path)}")

        if not success:
            self.logger.error(f"FFprobe failed to get info for: {input_path}")
            return None

        try:
            info = json.loads(stdout)
            video_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'video'), None)
            audio_stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'audio'), None)
            duration_str = info.get('format', {}).get('duration')
            duration = float(duration_str) if duration_str else 0.0

            if duration <= 0:
                self.logger.warning(f"FFprobe reported 0 or invalid duration for {input_path}. Trying video stream duration.")
                duration = float(video_stream.get('duration', 0)) if video_stream else 0.0
                if duration <= 0:
                    self.logger.error("Could not determine valid duration from format or video stream.")
                    return None

            width = video_stream.get('width') if video_stream else None
            height = video_stream.get('height') if video_stream else None
            avg_framerate_str = video_stream.get('avg_frame_rate', '0/0') if video_stream else '0/0'
            avg_framerate = 0.0 # Default
            if '/' in avg_framerate_str: # Basic check for valid format
                try:
                    num_str, den_str = avg_framerate_str.split('/')
                    num, den = int(num_str), int(den_str)
                    if den != 0: avg_framerate = num / den
                except (ValueError, ZeroDivisionError):
                     self.logger.warning(f"Could not parse frame rate: {avg_framerate_str}")

            result = {
                'duration': duration, 'width': width, 'height': height, 'avg_framerate': avg_framerate,
                'avg_framerate_str': avg_framerate_str, 'video_codec': video_stream.get('codec_name') if video_stream else None,
                'audio_codec': audio_stream.get('codec_name') if audio_stream else None,
                'size': info.get('format', {}).get('size'), 'raw_info': info
            }
            self.logger.info(f"Video Info for '{os.path.basename(input_path)}': Duration={result['duration']:.2f}s, Res={result['width']}x{result['height']}, FPS={result['avg_framerate']:.2f}")
            return result
        # Specific exceptions first
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
            self.logger.error(f"Error parsing FFprobe output for {input_path}: {e}", exc_info=True)
            self.logger.debug(f"FFprobe stdout was: {stdout}")
            return None
        except Exception as e: # General catch-all
            self.logger.error(f"Unexpected error processing FFprobe output for {input_path}: {e}", exc_info=True)
            return None

    def detect_scene_transition(self, video_path: str, target_start_sec: float, threshold: float = 30.0) -> float:
        """Detects scene transition near a target time using PySceneDetect."""
        if not scenedetect_available:
            self.logger.warning("Scene detection skipped: PySceneDetect not available.")
            return target_start_sec

        self.logger.info(f"Attempting scene detection near {target_start_sec:.2f}s for '{os.path.basename(video_path)}' (Threshold: {threshold})")
        video = None
        stats_manager = None # Initialize for finally block
        scene_manager = None # Initialize for finally block

        try:
            video = open_video(video_path)
            stats_file_path = f"{os.path.splitext(video_path)[0]}.stats.csv"
            stats_manager = StatsManager()
            scene_manager = SceneManager(stats_manager=stats_manager)
            scene_manager.add_detector(ContentDetector(threshold=threshold))

            if os.path.exists(stats_file_path):
                self.logger.debug(f"Attempting to load stats file: {stats_file_path}")
                try: # Nested try for loading stats
                    stats_manager.load_from_csv(stats_file_path)
                    self.logger.debug(f"Stats file loaded successfully.")
                except StatsFileCorrupt as e:
                    self.logger.warning(f"Scene detection stats file corrupt: {e}. Detecting scenes without stats. Deleting corrupt file.")
                    try: # Nested try for removing corrupt file
                         os.remove(stats_file_path)
                    except OSError as delete_err:
                         self.logger.error(f"Failed to delete corrupt stats file '{stats_file_path}': {delete_err}")
                    # Reset managers after corruption
                    stats_manager = StatsManager()
                    scene_manager = SceneManager(stats_manager=stats_manager)
                    scene_manager.add_detector(ContentDetector(threshold=threshold))
                except Exception as load_err: # Catch other loading errors
                    self.logger.error(f"Error loading stats file '{stats_file_path}': {load_err}. Proceeding without stats.")
                    stats_manager = StatsManager()
                    scene_manager = SceneManager(stats_manager=stats_manager)
                    scene_manager.add_detector(ContentDetector(threshold=threshold))
            # else: # Optional: log if no stats file found
            #     self.logger.debug(f"No stats file found at: {stats_file_path}")

            self.logger.debug("Starting scene detection process...")
            scene_manager.detect_scenes(video=video, show_progress=False)
            self.logger.debug("Scene detection process finished.")

            if stats_manager and stats_manager.is_save_required():
                 self.logger.debug(f"Saving updated stats file: {stats_file_path}")
                 try: # Nested try for saving stats
                     stats_manager.save_to_csv(stats_file_path)
                 except Exception as save_err:
                     self.logger.error(f"Failed to save stats file '{stats_file_path}': {save_err}")

            scene_list = scene_manager.get_scene_list()
            if not scene_list:
                self.logger.warning("Scene detection: No scenes found.")
                return target_start_sec

            best_scene_start_sec = -1.0
            for scene_start_tc, scene_end_tc in scene_list:
                scene_start_sec = scene_start_tc.get_seconds()
                if scene_start_sec >= target_start_sec - 0.1: # Allow slight tolerance
                    best_scene_start_sec = scene_start_sec
                    self.logger.info(f"Scene detection: Found scene boundary at {best_scene_start_sec:.3f}s (target was {target_start_sec:.3f}s)")
                    break # Use the first suitable scene found

            if best_scene_start_sec < 0:
                 # If no scene starts at or after the target
                 last_scene_start_tc, last_scene_end_tc = scene_list[-1]
                 last_scene_start_sec = last_scene_start_tc.get_seconds()
                 last_scene_end_sec = last_scene_end_tc.get_seconds()
                 # Check if target is within the last scene
                 if last_scene_start_sec <= target_start_sec < last_scene_end_sec:
                     self.logger.warning(f"Scene detection: Target time {target_start_sec:.3f}s falls within last scene. Using last scene start: {last_scene_start_sec:.3f}s.")
                     # Return start of the last scene instead? Or original target? Using last start.
                     return last_scene_start_sec
                 else:
                     # Target is before first scene or after last scene ends
                     self.logger.warning(f"Scene detection: No scene boundary found at or after {target_start_sec:.3f}s. Using original target time.")
                     return target_start_sec
            # else: # A suitable scene start was found
            #     return best_scene_start_sec
            return best_scene_start_sec # Return the found time

        except Exception as e: # Catch errors during main detection process
            self.logger.error(f"Error during scene detection for {os.path.basename(video_path)}: {type(e).__name__} - {e}", exc_info=True)
            return target_start_sec # Return original target on error
        finally: # Ensure video resource is always released
             if video:
                 try:
                     video.release()
                     self.logger.debug("Scene detection video resource released.")
                 except Exception as release_err:
                     self.logger.warning(f"Error releasing scene detection video resource: {release_err}")


    def _extract_clip(self, input_path: str, output_filename: str, start_sec: float, end_sec: float, use_copy: bool = True) -> Optional[str]:
        """
        Extracts a clip, ALWAYS applying vertical 9:16 formatting (crop/scale/pad).
        Requires re-encoding, so 'use_copy' argument is ignored.
        Requires the ffmpeg-python library.
        """
        output_path = os.path.join(self.output_dir, output_filename)
        duration = end_sec - start_sec

        if duration <= 0.01:
            self.logger.warning(f"Skipping clip extraction: Invalid or zero duration ({duration:.3f}s) for {output_filename}")
            return None

        if not FFMPEG_PYTHON_AVAILABLE:
            self.logger.error("Cannot extract clip with vertical formatting: ffmpeg-python library is required but not found.")
            raise VideoProcessingError("Cannot apply vertical formatting: ffmpeg-python library not installed.")

        log_prefix = "Extracting clip (re-encode, 9:16)"
        self.logger.info(f"{log_prefix}: {output_filename} [{start_sec:.3f}s -> {end_sec:.3f}s]")

        if os.path.exists(output_path):
            self.logger.warning(f"Output file {output_filename} already exists. Overwriting.")
            try:
                os.remove(output_path)
            except OSError as e:
                self.logger.error(f"Failed to remove existing file {output_path}: {e}. Extraction may fail.")
                return None

        # --- Main Try Block for ffmpeg-python operation ---
        try:
            input_stream = ffmpeg.input(input_path, ss=f"{start_sec:.6f}", to=f"{end_sec:.6f}")
            video = input_stream['v']
            # Use probe to check for audio before trying to map ['a?']
            has_audio = False
            try: # Inner try for probe
                probe_data = ffmpeg.probe(input_path, cmd=self.ffprobe_path)
                if any(stream.get('codec_type') == 'audio' for stream in probe_data.get('streams', [])):
                    has_audio = True
                    self.logger.debug(f"Probe detected audio stream in {os.path.basename(input_path)}.")
            except ffmpeg.Error as probe_err: # Specific ffmpeg probe error
                stderr_decode = probe_err.stderr.decode('utf-8', errors='replace') if probe_err.stderr else "N/A"
                self.logger.warning(f"Could not probe for audio stream in {input_path}: {stderr_decode}")
            except Exception as probe_err_generic: # Catch other potential probe errors
                 self.logger.warning(f"Unexpected error probing for audio stream in {input_path}: {probe_err_generic}", exc_info=True)

            # Apply filters
            self.logger.debug(f"Applying 9:16 filters to {output_filename}")
            video = video.filter("crop", w="min(iw,ih*9/16)", h="min(ih,iw*16/9)")
            video = video.filter("scale", w="1080", h="1920", force_original_aspect_ratio="decrease")
            video = video.filter("pad", w="1080", h="1920", x="(ow-iw)/2", y="(oh-ih)/2", color="black")
            video = video.filter("setsar", sar="1") # Ensure Square Pixels

            output_kwargs = {
                'c:v': 'libx264', 'preset': 'fast', 'crf': '23', 'movflags': '+faststart',
                'c:a': 'aac', 'b:a': '128k', 'ac': 2 # Defaults
            }

            streams_to_output = [video]
            if has_audio:
                audio = input_stream['a?'] # Map audio only if probe found it
                streams_to_output.append(audio)
                self.logger.debug("Audio stream mapped for output.")
            else:
                 self.logger.warning(f"No audio stream mapped for {output_filename}. Output will be video-only.")
                 output_kwargs.pop('c:a', None); output_kwargs.pop('b:a', None); output_kwargs.pop('ac', None)

            # Define and run the FFmpeg process
            stream = ffmpeg.output(*streams_to_output, output_path, **output_kwargs)
            cmd_list_for_log = stream.compile(cmd=self.ffmpeg_path, overwrite_output=True)
            self.logger.debug(f"Running FFmpeg command (via ffmpeg-python): {' '.join(cmd_list_for_log)}")

            # Execute FFmpeg - Errors from here are caught by the outer except ffmpeg.Error below
            stdout, stderr = stream.run(cmd=self.ffmpeg_path, capture_stdout=True, capture_stderr=True, overwrite_output=True)

            # Process stderr if run succeeded
            stderr_str = stderr.decode('utf-8', errors='replace').strip()
            if stderr_str:
                self.logger.debug(f"FFmpeg stderr for {output_filename}:\n{stderr_str[:1000]}{'...' if len(stderr_str)>1000 else ''}")

            # --- Verification ---
            if not os.path.exists(output_path):
                self.logger.error(f"Clip extraction command finished, but output file is missing: {output_path}")
                raise VideoProcessingError(f"Output file missing after FFmpeg run for {output_filename}") # Raise error

            # Check file size using nested try-except
            try:
                if os.path.getsize(output_path) == 0:
                    self.logger.error(f"Clip extraction command finished, but output file is empty (0 bytes): {output_path}")
                    # Try to remove the empty file
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass # Ignore error during cleanup
                    raise VideoProcessingError(f"Output file empty after FFmpeg run for {output_filename}") # Raise error
            except OSError as e: # Catch getsize error
                 self.logger.error(f"Could not get size of output file {output_path}: {e}")
                 raise VideoProcessingError(f"Could not verify output file size for {output_filename}") from e # Raise error

            # --- Success Case ---
            absolute_output_path = os.path.abspath(output_path)
            self.logger.info(f"Successfully extracted clip (9:16 formatted): {absolute_output_path}")
            return absolute_output_path

        # --- Exception Handling for the *main* try block ---
        # Catch specific ffmpeg-python errors first
        except ffmpeg.Error as e:
            stderr_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else "No stderr available"
            self.logger.error(f"Failed to extract clip {output_filename} (ffmpeg.Error):\n{stderr_output[:1500]}{'...' if len(stderr_output)>1500 else ''}")
            # Attempt cleanup using standard try/except
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError as remove_e:
                    self.logger.warning(f"Failed to remove incomplete output file {output_path} after ffmpeg.Error: {remove_e}")
            # Raise error to signal failure upstream
            raise VideoProcessingError(f"FFmpeg error during clip extraction for {output_filename}") from e

        # Catch other specific errors raised within the try block
        except (VideoProcessingError, FFmpegNotFoundError) as e:
             self.logger.error(f"Clip extraction failed for {output_filename}: {e}")
             if os.path.exists(output_path):
                 try:
                     os.remove(output_path)
                 except OSError as remove_e:
                     self.logger.warning(f"Failed to remove potentially incomplete output file {output_path} after error: {remove_e}")
             return None # Return None for these specific failures (or re-raise if needed)

        # Catch any other unexpected error
        except Exception as e:
            self.logger.error(f"Unexpected error during clip extraction for {output_filename}: {e}", exc_info=True)
            if os.path.exists(output_path):
                 try:
                     os.remove(output_path)
                 except OSError as remove_e:
                     self.logger.warning(f"Failed to remove potentially incomplete output file {output_path} after error: {remove_e}")
            # Raise error to signal failure upstream
            raise VideoProcessingError(f"Unexpected error during clip extraction for {output_filename}") from e
    # ***** END REFORMATTED _extract_clip *****


    def process_video(self, input_path: str, **kwargs) -> List[str]:
        """
        Processes a single video file to extract clips based on provided options.
        Clips will ALWAYS be vertically formatted (9:16) using ffmpeg-python.
        """
        self.logger.info(f"--- Processing video: {input_path} ---")
        if not os.path.exists(input_path):
            self.logger.error(f"Input video file not found: {input_path}")
            return []

        # --- Get Options ---
        try:
            min_clip_dur = float(kwargs.get('min_duration', 5.0))
            max_clip_dur = float(kwargs.get('max_duration', 60.0))
            use_scene_detection = bool(kwargs.get('use_scene_detection', False))
            scene_threshold = float(kwargs.get('scene_threshold', 30.0))
            num_clips_target = int(kwargs.get('num_clips', 1))
            if kwargs.get('use_codec_copy', False):
                 self.logger.warning("Vertical formatting requires re-encoding. 'Use Codec Copy' option will be ignored by _extract_clip.")
            use_copy = False # Force re-encoding
        except (ValueError, TypeError) as e:
            self.logger.error(f"Invalid processing option provided: {e}. Using defaults.")
            min_clip_dur = 5.0; max_clip_dur = 60.0; use_scene_detection = False
            scene_threshold = 30.0; num_clips_target = 1; use_copy = False

        # --- Get Video Info ---
        video_info = self.get_video_info(input_path)
        if not video_info or not video_info.get('duration'):
            self.logger.error(f"Could not get video info or duration for {input_path}. Aborting processing.")
            return []

        total_duration = video_info['duration']
        base_filename = os.path.splitext(os.path.basename(input_path))[0]
        processed_clips = [] # Store absolute paths
        clip_count = 0

        # --- Clipping Logic ---
        # Outer try-except for the whole process_video logic
        try:
            if use_scene_detection and scenedetect_available:
                # --- Scene Detection Based Clipping ---
                self.logger.info(f"Processing based on Scene Detection (Threshold: {scene_threshold}). Output will be 9:16.")
                video = None
                try: # Inner try-finally for scene detection resource release
                    video = open_video(input_path)
                    stats_file = f"{os.path.splitext(input_path)[0]}.stats.csv"
                    stats_manager = StatsManager()
                    scene_manager = SceneManager(stats_manager=stats_manager)
                    scene_manager.add_detector(ContentDetector(threshold=scene_threshold))

                    # *** CORRECTED if/try block structure ***
                    if os.path.exists(stats_file):
                        self.logger.debug(f"Attempting to load stats file: {stats_file}")
                        try: # Nested try for loading stats starts here
                            stats_manager.load_from_csv(stats_file)
                            self.logger.debug("Stats file loaded successfully.")
                        except StatsFileCorrupt as e:
                            self.logger.warning(f"Corrupt stats file {stats_file}, processing without. Deleting.")
                            try:
                                os.remove(stats_file)
                            except OSError as remove_e:
                                self.logger.error(f"Failed to remove corrupt stats file '{stats_file}': {remove_e}")
                            # Reset managers
                            stats_manager = StatsManager()
                            scene_manager = SceneManager(stats_manager=stats_manager)
                            scene_manager.add_detector(ContentDetector(threshold=scene_threshold))
                        except Exception as load_err:
                            self.logger.error(f"Error loading stats file {stats_file}: {load_err}. Proceeding without stats.")
                            # Reset managers
                            stats_manager = StatsManager()
                            scene_manager = SceneManager(stats_manager=stats_manager)
                            scene_manager.add_detector(ContentDetector(threshold=scene_threshold))
                    # *** END CORRECTION ***

                    scene_manager.detect_scenes(video=video); scene_list = scene_manager.get_scene_list()
                    if stats_manager and stats_manager.is_save_required():
                        try:
                            stats_manager.save_to_csv(stats_file)
                        except Exception as save_err:
                            self.logger.error(f"Failed to save stats file {stats_file}: {save_err}")
                    self.logger.info(f"Detected {len(scene_list)} potential scenes.")

                    for i, (start_tc, end_tc) in enumerate(scene_list):
                        start_sec = start_tc.get_seconds(); end_sec = end_tc.get_seconds(); duration = end_sec - start_sec
                        self.logger.info(f"Scene {i+1}: Start={start_sec:.3f}, End={end_sec:.3f}, Duration={duration:.3f}. Checking against Min={min_clip_dur}, Max={max_clip_dur}")
                        if min_clip_dur <= duration <= max_clip_dur:
                            self.logger.info(f"Scene {i+1} ACCEPTED for clipping.")
                            clip_count += 1
                            output_filename = f"{base_filename}_scene_{clip_count:03d}_9x16.mp4" # Add indicator
                            clip_path = self._extract_clip(input_path, output_filename, start_sec, end_sec, use_copy=False)
                            if clip_path: processed_clips.append(clip_path) # Store absolute path
                        elif duration > max_clip_dur: self.logger.info(f"Scene {i+1} duration ({duration:.2f}s) exceeds max_duration ({max_clip_dur:.2f}s). Skipping.")
                        else: self.logger.info(f"Scene {i+1} duration ({duration:.2f}s) is less than min_duration ({min_clip_dur:.2f}s). Skipping.")

                except Exception as e: # Catch errors from scene detection part
                    self.logger.error(f"Error during scene detection processing loop for {input_path}: {e}", exc_info=True)
                finally: # Ensure release even if errors occur within scene detection try
                    if video:
                        try: video.release()
                        except Exception: pass

            else:
                # --- Fixed Interval / Target Number Clipping ---
                self.logger.info("Processing based on fixed interval or target number. Output will be 9:16.")
                if total_duration <= 0: self.logger.error("Cannot perform fixed interval clipping: Total duration is zero or negative."); return []
                if num_clips_target <= 0: self.logger.warning("Number of clips target is zero or negative, no clips will be generated."); return []
                target_clip_dur = total_duration / num_clips_target; effective_clip_dur = max(min_clip_dur, min(max_clip_dur, target_clip_dur))
                self.logger.info(f"Targeting ~{num_clips_target} clips. Effective clip duration: {effective_clip_dur:.2f}s (Min: {min_clip_dur}, Max: {max_clip_dur})")
                start_sec = 0.0
                while start_sec < total_duration and clip_count < num_clips_target:
                    end_sec = min(start_sec + effective_clip_dur, total_duration); actual_duration = end_sec - start_sec
                    self.logger.info(f"Interval {clip_count+1}: Start={start_sec:.3f}, End={end_sec:.3f}, Duration={actual_duration:.3f}")
                    if actual_duration < min_clip_dur and (total_duration - start_sec) < min_clip_dur: self.logger.info(f"Remaining duration ({actual_duration:.2f}s) less than min clip duration. Stopping."); break
                    if actual_duration < min_clip_dur and end_sec < total_duration: end_sec = min(start_sec + min_clip_dur, total_duration); actual_duration = end_sec - start_sec
                    if actual_duration < 0.1: break # Avoid tiny clips
                    clip_count += 1
                    output_filename = f"{base_filename}_clip_{clip_count:03d}_9x16.mp4" # Add indicator
                    clip_path = self._extract_clip(input_path, output_filename, start_sec, end_sec, use_copy=False)
                    if clip_path: processed_clips.append(clip_path) # Store absolute path
                    start_sec = end_sec

        # Catch specific errors raised from _extract_clip or FFmpeg/FFprobe issues
        except (VideoProcessingError, FFmpegNotFoundError) as e:
            self.logger.error(f"Video processing run failed for {input_path}: {e}")
            # Don't return here, allow the final log and return of potentially partial list
        # Catch any other unexpected error during the main processing
        except Exception as e:
             self.logger.error(f"Unexpected error during video processing for {input_path}: {e}", exc_info=True)
             # On a totally unexpected error, probably safer to return empty list
             return []
        # This block executes regardless of exceptions in the main try

        # --- Final Log ---
        self.logger.info(f"--- Finished processing {input_path}. Generated {len(processed_clips)} vertically formatted clips. ---")
        return processed_clips

    # --- Optional: Add other methods ---