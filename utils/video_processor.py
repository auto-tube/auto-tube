# utils/video_processor.py
import os
import random
import cv2 # Only needed if _video_capture is kept (it's unused currently)
# import numpy as np # Only needed if _video_capture is kept
import ffmpeg
from typing import List, Optional, Tuple
from contextlib import contextmanager
from .logger_config import setup_logging # Relative import
import scenedetect
from scenedetect.video_manager import VideoManager
from scenedetect.detectors import ContentDetector
from scenedetect.scene_manager import SceneManager
from scenedetect import FrameTimecode # Import FrameTimecode
import traceback
import sys # For platform check
import subprocess # For direct ffmpeg/ffprobe check

logger = setup_logging() # Initialize logger for this module

class VideoProcessingError(Exception):
    """Custom exception for video processing errors."""
    pass

class FFmpegNotFoundError(Exception):
    """Exception raised when FFmpeg is not found."""
    pass

class VideoProcessor:
    """
    Handles low-level video processing tasks using FFmpeg and Scenedetect
    for individual video files. Focused on clipping and basic transformations.
    """
    # --- Define paths Here ---
    # Using explicit paths based on previous user confirmation
    # !! IMPORTANT: Update these paths if your install location changes !!
    FFPROBE_PATH = r"C:\Users\V0iD\Downloads\ffmpeg-2025-03-27-git-114fccc4a5-full_build\bin\ffprobe.exe"
    FFMPEG_PATH = r"C:\Users\V0iD\Downloads\ffmpeg-2025-03-27-git-114fccc4a5-full_build\bin\ffmpeg.exe"
    # --- End Paths ---

    def __init__(self, output_folder: str):
        """
        Initialize the VideoProcessor. Checks output folder and FFmpeg availability.
        """
        if not output_folder or not isinstance(output_folder, str):
             raise ValueError("VP Init: Invalid output folder path provided.")
        try:
            if not os.path.isdir(output_folder):
                logger.info(f"VP Init: Output folder '{output_folder}' not found. Creating.")
                os.makedirs(output_folder, exist_ok=True)
            self.output_folder = output_folder
            logger.debug(f"VP Init: Output folder set to: {self.output_folder}")
        except OSError as e:
            raise ValueError(f"VP Init: Output folder '{output_folder}' could not be created: {e}")

        self._check_ffmpeg() # Check FFmpeg/FFprobe during initialization

    def _check_ffmpeg(self):
        """Checks if FFprobe is accessible via the specified path using subprocess."""
        ffprobe_path = self.FFPROBE_PATH
        ffmpeg_path = self.FFMPEG_PATH
        logger.debug(f"VP Check: Verifying FFprobe at: {ffprobe_path}")
        logger.debug(f"VP Check: Verifying FFmpeg at: {ffmpeg_path}")

        for exe_path, name in [(ffprobe_path, "FFprobe"), (ffmpeg_path, "FFmpeg")]:
            try:
                if not os.path.isfile(exe_path):
                    # Try finding in PATH as a fallback check for logging purposes
                    path_check_cmd = ["where", name.lower()] if sys.platform == 'win32' else ["which", name.lower()]
                    try:
                        path_result = subprocess.run(path_check_cmd, capture_output=True, text=True, check=True,
                                                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                        logger.warning(f"{name} found in PATH at: {path_result.stdout.strip()}")
                    except (FileNotFoundError, subprocess.CalledProcessError):
                        logger.warning(f"{name} not found in PATH either.")
                    # Still raise error based on the explicit path check
                    raise FileNotFoundError(f"{name} executable not found at specified path: {exe_path}")

                # Run the executable with -version flag
                cmd = [exe_path, "-version"]
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                result = subprocess.run(cmd, capture_output=True, text=True, check=False, # Allow non-zero exit for -version quirk
                                        encoding='utf-8', errors='replace', creationflags=creationflags)

                version_info = result.stdout or result.stderr # Version info might be in stderr
                if f"{name.lower()} version" not in version_info.lower():
                     # If it failed AND version info isn't present, raise error
                     if result.returncode != 0:
                          raise FFmpegNotFoundError(f"Failed to execute {name} at '{exe_path}'. Exit code {result.returncode}. Output: {version_info[:500]}...")
                     else:
                          # Ran successfully but output didn't contain version? Strange, but proceed.
                          logger.warning(f"{name} ran but version string not found in output. Assuming OK.")

                logger.info(f"{name} check successful using path: {exe_path}")

            except (FileNotFoundError, PermissionError) as e:
                logger.error(f"VP Check: Failed to find or execute {name} at '{exe_path}': {e}")
                raise FFmpegNotFoundError(f"Failed to find or execute {name} at '{exe_path}': {e}")
            except Exception as e:
                logger.error(f"VP Check: Unexpected error during {name} check using path '{exe_path}'")
                traceback.print_exc()
                raise FFmpegNotFoundError(f"Unexpected error during {name} check ('{exe_path}'): {e}")

    # --- Duration ---
    def get_video_duration(self, video_path: str) -> float:
        """Gets video duration in seconds using FFprobe."""
        clean_path = str(video_path).strip('"')
        if not os.path.isfile(clean_path):
            logger.error(f"VP Get Duration: File not found: {clean_path}")
            return 0.0
        try:
            logger.debug(f"VP Get Duration: Probing: {clean_path} using {self.FFPROBE_PATH}")
            probe_result = ffmpeg.probe(clean_path, cmd=self.FFPROBE_PATH)
            duration = float(probe_result["format"]["duration"])
            logger.debug(f"VP Get Duration: Duration found: {duration:.3f}s")
            return duration
        except ffmpeg.Error as e:
            stderr = e.stderr.decode('utf-8', errors='replace') if e.stderr else "N/A"
            logger.error(f"VP Get Duration: FFprobe error for {clean_path}: {stderr}")
            return 0.0
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"VP Get Duration: Error parsing duration from FFprobe output for {clean_path}: {e}")
            return 0.0
        except Exception as e:
            logger.error(f"VP Get Duration: Unexpected error for {clean_path}: {e}")
            traceback.print_exc()
            return 0.0

    # --- Validation/Calculation Helpers ---
    def _validate_clip_length_range(self, min_length: int, max_length: int) -> Tuple[int, int]:
        """Validates and returns the clip length range."""
        if not isinstance(min_length, int) or not isinstance(max_length, int):
             raise TypeError("Clip lengths must be integers.")
        if min_length <= 0 or max_length <= 0:
             raise ValueError("Clip lengths must be positive.")
        if min_length > max_length:
            raise ValueError("Minimum clip length cannot be greater than maximum clip length.")
        return (min_length, max_length)

    def _determine_clip_count(self, clip_count: int, duration: float,
                               min_length: int, max_length: int) -> int:
        """Calculates the number of clips, ensuring it's reasonable."""
        if not isinstance(clip_count, int) or clip_count <= 0:
            logger.warning(f"Invalid clip_count '{clip_count}', defaulting to 1.")
            clip_count = 1
        if duration <= 0: return 0
        if duration < min_length: return 0
        return max(1, clip_count)

    # --- Scene Detection ---
    def detect_scene_transition(self, video_path: str, start_time: float, threshold: float) -> float:
        """Detects the next scene transition after start_time using Scenedetect."""
        clean_path = str(video_path).strip('"')
        logger.info(f"VP SceneDetect: Analyzing '{os.path.basename(clean_path)}' after {start_time:.2f}s (thr={threshold})")
        video_manager = None
        try:
            if not os.path.isfile(clean_path):
                 logger.error(f"VP SceneDetect: File not found: {clean_path}")
                 return start_time

            video_manager = VideoManager([clean_path])
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=threshold))

            video_manager.set_downscale_factor(integer=True)
            video_manager.start()
            base_timecode = video_manager.get_base_timecode()

            scene_manager.detect_scenes(frame_source=video_manager, show_progress=False)
            scene_list = scene_manager.get_scene_list(base_timecode)

            if scene_list:
                logger.debug(f"VP SceneDetect: Found {len(scene_list)} scenes.")
                for scene_start, _ in scene_list:
                    scene_start_sec = scene_start.get_seconds()
                    if scene_start_sec > (start_time + 0.1):
                        logger.info(f"VP SceneDetect: Next transition found at {scene_start_sec:.2f}s")
                        return scene_start_sec
                logger.info("VP SceneDetect: No subsequent transitions found.")
            else:
                logger.info("VP SceneDetect: No scenes detected.")

        except scenedetect.stats_manager.StatsFileCorruptError as e:
             logger.warning(f"VP SceneDetect: Stats file error: {e}.")
        except Exception as e:
            logger.error(f"VP SceneDetect: Error for {clean_path}: {e}")
            traceback.print_exc()
        finally:
            if video_manager:
                video_manager.release()

        return start_time # Fallback

    # --- FFmpeg Command Runner ---
    def _run_ffmpeg_command(self, stream, operation_name="FFmpeg operation") -> bool:
        """Helper to run ffmpeg-python command and log stderr on error."""
        try:
            cmd_list = stream.compile(cmd=self.FFMPEG_PATH) # Compile using explicit path
            logger.debug(f"VP Execute: Running for {operation_name}: {' '.join(cmd_list)}")
            # Run using the explicit FFMPEG_PATH passed via stream compilation
            stdout, stderr = stream.run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
            stderr_str = stderr.decode('utf-8', errors='replace')
            if stderr_str:
                 log_level = logger.warning if "warning" in stderr_str.lower() else logger.debug
                 log_level(f"{operation_name} stderr: {stderr_str[:1000]}" + ("..." if len(stderr_str)>1000 else ""))
            return True
        except ffmpeg.Error as e:
            stderr_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else "No stderr available"
            logger.error(f"VP Execute: FFmpeg error during {operation_name}: {stderr_output}")
            return False
        except Exception as e:
            logger.error(f"VP Execute: Unexpected error running {operation_name}: {e}")
            traceback.print_exc()
            return False

    # --- Core Clipping & Post-Processing ---
    def process_video(
        self,
        video_path: str,
        clip_count: int = 3,
        min_clip_length: int = 15,
        max_clip_length: int = 45,
        # overlap: bool = False, # Overlap logic removed
        scene_detect: bool = False,
        scene_threshold: float = 30.0,
        remove_audio: bool = False,
        extract_audio: bool = False,
        vertical_crop: bool = False,
        mirror: bool = False,
        enhance: bool = False,
    ) -> List[str]:
        """
        Clips video, applies selected post-processing. Returns final clip paths.
        """
        logger.info(f"--- VP ProcessVideo Start: {os.path.basename(video_path)} ---")
        opts_str = f"clips={clip_count}, len={min_clip_length}-{max_clip_length}s, scene={scene_detect}({scene_threshold}), crop={vertical_crop}, mirror={mirror}, enhance={enhance}, rm_audio={remove_audio}, ext_audio={extract_audio}"
        logger.info(f"VP Options: {opts_str}")

        clean_video_path = str(video_path).strip('"')
        initial_clip_paths = [] # Store paths of successfully clipped videos
        final_output_paths = [] # Store final paths after all processing
        intermediate_files = set() # Track intermediate files for cleanup

        try:
            duration = self.get_video_duration(clean_video_path)
            if duration <= 0: raise VideoProcessingError(f"Invalid duration {duration:.2f}s")

            min_len, max_len = self._validate_clip_length_range(min_clip_length, max_clip_length)
            num_clips_to_make = self._determine_clip_count(clip_count, duration, min_len, max_len)
            if num_clips_to_make == 0: return []

            logger.info(f"VP Details: Duration={duration:.2f}s, Target clips={num_clips_to_make}")

            start_time_sec = 0.0
            clip_index_success = 0 # Count successful clips made

            # --- Clipping Loop ---
            while clip_index_success < num_clips_to_make:
                current_attempt_index = len(initial_clip_paths) # Track total attempts
                logger.info(f"--- VP Clip Attempt {current_attempt_index + 1} (Target {clip_index_success + 1}/{num_clips_to_make}) ---")

                if start_time_sec >= duration - 1.0: # Need >= 1s remaining
                    logger.info(f"VP Clip: Remaining duration too short. Stopping.")
                    break

                actual_start_time = start_time_sec
                if scene_detect:
                    detected_start = self.detect_scene_transition(clean_video_path, start_time_sec, scene_threshold)
                    if detected_start > start_time_sec and detected_start < duration - 1.0: # Ensure detected start allows for min clip length
                        logger.info(f"VP Clip: Scene Detect adjusted start: {detected_start:.2f}s")
                        actual_start_time = detected_start

                if actual_start_time >= duration - 1.0:
                    logger.warning(f"VP Clip: Adjusted start time {actual_start_time:.2f}s too close to end. Stopping.")
                    break

                # Determine Clip Duration
                max_possible_duration = duration - actual_start_time
                current_max_len = min(max_len, int(max_possible_duration))
                current_min_len = min(min_len, current_max_len)

                if current_min_len <= 0 or current_min_len > current_max_len :
                     logger.warning(f"VP Clip: Invalid length range ({current_min_len}-{current_max_len}) at start {actual_start_time:.2f}s. Skipping.")
                     start_time_sec = actual_start_time + 1.0 # Advance slightly
                     continue # Skip this attempt

                clip_duration_sec = random.randint(current_min_len, current_max_len)
                logger.info(f"VP Clip {clip_index_success + 1}: Start={actual_start_time:.2f}s, Duration={clip_duration_sec:.2f}s")

                # Define Output Path
                base_name = os.path.basename(clean_video_path)
                name, _ = os.path.splitext(base_name)
                clip_output_filename = f"{name}_clip_{clip_index_success + 1}.mp4"
                clip_output_path = os.path.join(self.output_folder, clip_output_filename)

                # FFmpeg Clipping Command
                try:
                    input_stream = ffmpeg.input(clean_video_path, ss=actual_start_time, t=clip_duration_sec, accurate_seek=True) # Added accurate seek
                    # Try copying streams initially
                    output_params = {'c:v': 'copy', 'c:a': 'copy', 'map_metadata': '-1', 'map_chapters': -1, 'avoid_negative_ts': 'make_zero'} # Add avoid_negative_ts
                    if remove_audio:
                        output_params = {'c:v': 'copy', 'an': None, 'map_metadata': '-1', 'map_chapters': -1}

                    stream = ffmpeg.output(input_stream, clip_output_path, **output_params)

                    if self._run_ffmpeg_command(stream, f"Clip {clip_index_success + 1}"):
                        if os.path.exists(clip_output_path):
                             initial_clip_paths.append(clip_output_path)
                             logger.info(f"VP Clip: Successfully created: {clip_output_filename}")
                             clip_index_success += 1 # Increment SUCCESS counter
                        else:
                             logger.error(f"VP Clip: FFmpeg success but output missing: {clip_output_path}")
                    else:
                         logger.error(f"VP Clip: FFmpeg failed for clip {clip_index_success + 1}.")
                         # Don't increment success counter, try again from next possible start

                except Exception as clip_e:
                    logger.error(f"VP Clip: Error during clipping setup/run for clip {clip_index_success + 1}: {clip_e}")
                    traceback.print_exc()
                    # Don't increment success counter, try again from next possible start

                # Update Start Time for Next Attempt
                start_time_sec = actual_start_time + clip_duration_sec
                # Add overlap logic here if needed

            # --- Post-Processing ---
            logger.info(f"--- VP Post-Processing {len(initial_clip_paths)} clips ---")
            for clip_path in initial_clip_paths:
                 if not os.path.exists(clip_path): continue # Skip if missing
                 logger.debug(f"VP Post: Processing '{os.path.basename(clip_path)}'")
                 current_path = clip_path
                 final_path = clip_path # Assume original unless changed

                 try:
                    if extract_audio: self._extract_audio(current_path)

                    formatted_path = None
                    if vertical_crop or mirror:
                         formatted_path = self._format_video(current_path, vertical_crop, mirror)
                         if formatted_path:
                             logger.info(f"VP Post: Formatted -> {os.path.basename(formatted_path)}")
                             if current_path != clip_path: intermediate_files.add(current_path)
                             current_path = formatted_path
                             final_path = formatted_path
                         else: logger.warning(f"VP Post: Formatting failed for {os.path.basename(current_path)}")

                    enhanced_path = None
                    if enhance:
                        enhanced_path = self._enhance_video(current_path)
                        if enhanced_path:
                            logger.info(f"VP Post: Enhanced -> {os.path.basename(enhanced_path)}")
                            if current_path != clip_path and current_path != formatted_path: intermediate_files.add(current_path)
                            # current_path = enhanced_path # Not needed
                            final_path = enhanced_path
                        else: logger.warning(f"VP Post: Enhancement failed for {os.path.basename(current_path)}")

                    final_output_paths.append(final_path)

                 except Exception as post_e:
                     logger.error(f"VP Post: Error post-processing '{os.path.basename(clip_path)}': {post_e}")
                     traceback.print_exc()
                     if os.path.exists(clip_path) and clip_path not in final_output_paths:
                         final_output_paths.append(clip_path) # Keep original

            # --- Cleanup ---
            logger.debug(f"Intermediate files marked for cleanup: {intermediate_files}")
            for int_file in intermediate_files:
                 if int_file and os.path.exists(int_file):
                     try:
                         os.remove(int_file)
                         logger.info(f"VP Cleanup: Removed intermediate: {os.path.basename(int_file)}")
                     except OSError as e:
                         logger.warning(f"VP Cleanup: Could not delete intermediate file {int_file}: {e}")

            logger.info(f"--- VP ProcessVideo Finish: {os.path.basename(video_path)}. Final clips: {len(final_output_paths)} ---")
            return final_output_paths

        except (FFmpegNotFoundError, VideoProcessingError, FileNotFoundError, ValueError, TypeError) as e:
             logger.error(f"VP ProcessVideo: Pre-processing error for {video_path}: {e}")
             return []
        except Exception as e:
            logger.error(f"VP ProcessVideo: Unexpected critical error for {video_path}: {e}")
            traceback.print_exc()
            return []


    # --- Individual Post-Processing Steps ---
    # These return the output path on success, None on failure

    def _extract_audio(self, clip_path: str) -> Optional[str]:
        """Extracts audio to an MP3 file. Returns output path or None."""
        clean_clip_path = str(clip_path).strip('"')
        if not os.path.isfile(clean_clip_path): return None
        audio_output = clean_clip_path.replace(".mp4", ".mp3")
        logger.info(f"VP ExtractAudio: -> {os.path.basename(audio_output)}")
        try:
            probe = ffmpeg.probe(clean_clip_path, cmd=self.FFPROBE_PATH)
            if not any(s.get('codec_type') == 'audio' for s in probe.get('streams', [])):
                 logger.warning(f"VP ExtractAudio: No audio stream in '{os.path.basename(clean_clip_path)}'.")
                 return None
            stream = ffmpeg.input(clean_clip_path).output(audio_output, format="mp3", acodec='libmp3lame', q='a:2')
            if self._run_ffmpeg_command(stream, "Extract Audio"): return audio_output
        except Exception as e: logger.error(f"VP ExtractAudio: Failed for {clip_path}: {e}")
        return None

    def _enhance_video(self, clip_path: str) -> Optional[str]:
        """Applies enhancement filters. Returns output path or None."""
        clean_clip_path = str(clip_path).strip('"')
        if not os.path.isfile(clean_clip_path): return None
        # Use a more specific suffix, check if input already has it
        base, ext = os.path.splitext(clip_path)
        if base.endswith("_enhanced"): return clip_path # Avoid double enhancing
        output_path = base + "_enhanced" + ext

        logger.info(f"VP Enhance: -> {os.path.basename(output_path)}")
        try:
            vf_filter = "eq=contrast=1.1:brightness=0.01:saturation=1.1:gamma=1.05"
            output_params = {'vf': vf_filter, 'c:v': 'libx264', 'preset': 'medium', 'crf': 23}
            # Check for audio and copy/remove
            probe = ffmpeg.probe(clean_clip_path, cmd=self.FFPROBE_PATH)
            if any(s.get('codec_type') == 'audio' for s in probe.get('streams', [])):
                 output_params['c:a'] = 'copy'
            else:
                 output_params['an'] = None

            stream = ffmpeg.input(clean_clip_path).output(output_path, **output_params)

            if self._run_ffmpeg_command(stream, "Enhance Video"): return output_path
            else: # Retry with audio re-encode if copy might have failed
                if output_params.get('c:a') == 'copy':
                    logger.warning("VP Enhance: Retrying with audio re-encode...")
                    output_params['c:a'] = 'aac'; output_params['b:a'] = '192k'
                    stream = ffmpeg.input(clean_clip_path).output(output_path, **output_params)
                    if self._run_ffmpeg_command(stream, "Enhance Video (Audio Re-encode)"): return output_path
                return None # Failed even after retry or no audio
        except Exception as e: logger.error(f"VP Enhance: Failed for {clip_path}: {e}")
        return None


    def _format_video(self, clip_path: str, vertical_crop: bool, mirror: bool) -> Optional[str]:
        """Applies crop and/or mirror filters. Returns output path or None."""
        clean_clip_path = str(clip_path).strip('"')
        if not os.path.isfile(clean_clip_path): return None
        filters = []
        op_name_parts = []
        output_suffix_parts = []

        if vertical_crop:
            filters.append("crop=ih*9/16:ih") # Crop first
            filters.append("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black") # Scale and pad
            op_name_parts.append("Crop9:16")
            output_suffix_parts.append("crop")
        if mirror:
            filters.append("hflip")
            op_name_parts.append("Mirror")
            output_suffix_parts.append("mir")

        if not filters: return None

        # Construct output path carefully to avoid doubling suffixes
        base, ext = os.path.splitext(clip_path)
        current_suffixes = ["_noaudio", "_enhanced", "_formatted", "_crop", "_mir"] # Define known suffixes
        for suffix in current_suffixes:
             if base.endswith(suffix):
                 base = base[:-len(suffix)]
                 break
        output_suffix = "_" + "_".join(output_suffix_parts) + ext # Re-add original extension
        output_path = base + output_suffix

        operation_desc = "+".join(op_name_parts)
        logger.info(f"VP Format ({operation_desc}): -> {os.path.basename(output_path)}")
        try:
            output_params = {'vf': ",".join(filters), 'c:v': 'libx264', 'preset': 'medium', 'crf': 23}
            # Check audio
            probe = ffmpeg.probe(clean_clip_path, cmd=self.FFPROBE_PATH)
            if any(s.get('codec_type') == 'audio' for s in probe.get('streams', [])):
                 output_params['c:a'] = 'copy'
            else:
                 output_params['an'] = None

            stream = ffmpeg.input(clean_clip_path).output(output_path, **output_params)

            if self._run_ffmpeg_command(stream, f"Format Video ({operation_desc})"): return output_path
            else: # Retry with audio re-encode
                 if output_params.get('c:a') == 'copy':
                    logger.warning("VP Format: Retrying with audio re-encode...")
                    output_params['c:a'] = 'aac'; output_params['b:a'] = '192k'
                    stream = ffmpeg.input(clean_clip_path).output(output_path, **output_params)
                    if self._run_ffmpeg_command(stream, f"Format Video ({operation_desc} - Audio Re-encode)"): return output_path
                 return None
        except Exception as e: logger.error(f"VP Format: Failed for {clip_path}: {e}")
        return None

    # --- Context Manager (Currently Unused, keep if needed later) ---
    @contextmanager
    def _video_capture(self, video_path: str, start_time: float):
        """Context manager for OpenCV video capture."""
        cap = None
        clean_path = str(video_path).strip('"')
        try:
            if not os.path.isfile(clean_path): raise FileNotFoundError(f"File not found: {clean_path}")
            cap = cv2.VideoCapture(clean_path)
            if not cap.isOpened(): raise IOError(f"Could not open video with OpenCV: {clean_path}")
            cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
            yield cap
        finally:
            if cap: cap.release()