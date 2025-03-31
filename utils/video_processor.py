# utils/video_processor.py
from asyncio import streams
import os
import random
# import cv2 # Only needed if using _video_capture context manager
# import numpy as np # Only needed if using _video_capture context manager
import ffmpeg
from typing import List, Optional, Tuple
from contextlib import contextmanager
from .logger_config import setup_logging # Relative import within package
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
    # --- Define Paths Here ---
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
        """Checks if FFprobe/FFmpeg are accessible via specified paths using subprocess."""
        for exe_path, name in [(self.FFPROBE_PATH, "FFprobe"), (self.FFMPEG_PATH, "FFmpeg")]:
            logger.debug(f"VP Check: Verifying {name} at: {exe_path}")
            try:
                if not os.path.isfile(exe_path):
                    # Try finding in PATH as a fallback check for logging purposes
                    path_check_cmd = ["where", name.lower()] if sys.platform == 'win32' else ["which", name.lower()]
                    try:
                        # Hide console window for where/which check
                        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                        path_result = subprocess.run(path_check_cmd, capture_output=True, text=True, check=True,
                                                     creationflags=creationflags, encoding='utf-8', errors='replace')
                        logger.warning(f"VP Check: {name} found in PATH at: {path_result.stdout.strip()}, but explicit path check failed for: {exe_path}")
                    except (FileNotFoundError, subprocess.CalledProcessError):
                        logger.warning(f"VP Check: {name} not found in PATH either.")
                    # Still raise error based on the explicit path check failure
                    raise FileNotFoundError(f"{name} executable not found at specified path: {exe_path}")

                # Run the executable with -version flag
                cmd = [exe_path, "-version"]
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                result = subprocess.run(cmd, capture_output=True, text=True, check=False, # Allow non-zero exit for -version quirk
                                        encoding='utf-8', errors='replace', creationflags=creationflags)

                version_info = result.stdout or result.stderr # Version info might be in stderr
                # Check if output contains expected version string fragment
                if f"{name.lower()} version" not in version_info.lower():
                     # If it failed AND version info isn't present, raise error
                     if result.returncode != 0:
                          raise FFmpegNotFoundError(f"Failed to execute {name} at '{exe_path}'. Exit code {result.returncode}. Output: {version_info[:500]}...")
                     else:
                          # Ran successfully but output didn't contain version? Strange, but proceed.
                          logger.warning(f"VP Check: {name} ran but version string not found in output. Assuming OK.")

                logger.info(f"VP Check: {name} check successful using path: {exe_path}")

            except (FileNotFoundError, PermissionError) as e:
                logger.error(f"VP Check: Failed to find or execute {name} at '{exe_path}': {e}")
                raise FFmpegNotFoundError(f"Failed to find or execute {name} at '{exe_path}': {e}") # Re-raise as specific type
            except Exception as e:
                logger.error(f"VP Check: Unexpected error during {name} check using path '{exe_path}'")
                traceback.print_exc()
                raise FFmpegNotFoundError(f"Unexpected error during {name} check ('{exe_path}'): {e}") # Re-raise

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

            video_manager.set_downscale_factor(integer=True) # Auto-downscale
            video_manager.start()
            base_timecode = video_manager.get_base_timecode()
            if not base_timecode:
                 raise VideoProcessingError("Could not get base timecode from video manager.")

            scene_manager.detect_scenes(frame_source=video_manager, show_progress=False)
            scene_list = scene_manager.get_scene_list(base_timecode)

            if scene_list:
                logger.debug(f"VP SceneDetect: Found {len(scene_list)} scenes.")
                for scene_start, _ in scene_list:
                    scene_start_sec = scene_start.get_seconds()
                    if scene_start_sec > (start_time + 0.1): # Find first scene *after* current start + buffer
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
        """Helper to run ffmpeg-python command using configured FFMPEG_PATH."""
        try:
            # Compile the command using the class FFMPEG_PATH
            cmd_list = stream.compile(cmd=self.FFMPEG_PATH, overwrite_output=True)
            logger.debug(f"VP Execute: Running for {operation_name}: {' '.join(cmd_list)}")

            # Execute the command
            stdout, stderr = stream.run(capture_stdout=True, capture_stderr=True)

            stderr_str = stderr.decode('utf-8', errors='replace')
            if stderr_str:
                 log_level = logger.warning if "warning" in stderr_str.lower() else logger.debug
                 log_level(f"{operation_name} stderr: {stderr_str[:1000]}" + ("..." if len(stderr_str)>1000 else ""))

            return True # Indicate command executed without ffmpeg.Error

        except ffmpeg.Error as e:
            stderr_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else "No stderr available"
            logger.error(f"VP Execute: FFmpeg error during {operation_name}: {stderr_output}")
            return False # Indicate failure
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
        # overlap: bool = False, # Removed
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
        initial_clip_paths = []
        final_output_paths = []
        intermediate_files = set()

        try:
            duration = self.get_video_duration(clean_video_path)
            if duration <= 0: raise VideoProcessingError(f"Invalid duration {duration:.2f}s for {video_path}")

            min_len, max_len = self._validate_clip_length_range(min_clip_length, max_clip_length)
            num_clips_to_make = self._determine_clip_count(clip_count, duration, min_len, max_len)
            if num_clips_to_make == 0: return []

            logger.info(f"VP Details: Duration={duration:.2f}s, Target clips={num_clips_to_make}")

            start_time_sec = 0.0
            clip_success_count = 0

            # --- Clipping Loop ---
            while clip_success_count < num_clips_to_make:
                current_attempt_index = len(initial_clip_paths)
                logger.info(f"--- VP Clip Attempt {current_attempt_index + 1} (Target {clip_success_count + 1}/{num_clips_to_make}) ---")

                min_time_needed = 1.0
                if start_time_sec >= duration - min_time_needed:
                    logger.info(f"VP Clip: Remaining duration too short. Stopping.")
                    break

                actual_start_time = start_time_sec
                if scene_detect:
                    detected_start = self.detect_scene_transition(clean_video_path, start_time_sec, scene_threshold)
                    if detected_start > (start_time_sec + 0.1) and detected_start < duration - min_time_needed:
                        logger.info(f"VP Clip: Scene Detect adjusted start: {detected_start:.2f}s")
                        actual_start_time = detected_start

                if actual_start_time >= duration - min_time_needed:
                    logger.warning(f"VP Clip: Adjusted start {actual_start_time:.2f}s too close to end. Stopping.")
                    break

                # Determine Clip Duration
                max_possible_duration = duration - actual_start_time
                current_max_len = min(max_len, int(max_possible_duration))
                current_min_len = min(min_len, current_max_len)

                if current_min_len <= 0 or current_min_len > current_max_len :
                     logger.warning(f"VP Clip: Invalid length range ({current_min_len}-{current_max_len}) at start {actual_start_time:.2f}s. Advancing.")
                     start_time_sec = actual_start_time + 1.0
                     continue

                clip_duration_sec = random.randint(current_min_len, current_max_len)
                logger.info(f"VP Clip {clip_success_count + 1}: Start={actual_start_time:.2f}s, Duration={clip_duration_sec:.2f}s")

                # Define Output Path
                base_name = os.path.basename(clean_video_path)
                name, _ = os.path.splitext(base_name)
                clip_output_filename = f"{name}_clip_{clip_success_count + 1}.mp4"
                clip_output_path = os.path.join(self.output_folder, clip_output_filename)

                # --- FFmpeg Clipping Command ---
                try:
                    logger.debug("VP Clip: Building ffmpeg command...")
                    # *** FIX: Remove accurate_seek=True ***
                    input_stream = ffmpeg.input(clean_video_path, ss=actual_start_time, t=clip_duration_sec) # Removed accurate_seek

                    # Parameters for initial clip
                    output_params = {'c:v': 'copy', 'c:a': 'copy', 'map_metadata': '-1', 'map_chapters': -1, 'avoid_negative_ts': 'make_zero'}
                    if remove_audio:
                        logger.debug("VP Clip: Audio removal requested.")
                        output_params = {'c:v': 'copy', 'an': None, 'map_metadata': '-1', 'map_chapters': -1, 'avoid_negative_ts': 'make_zero'}

                    stream = ffmpeg.output(input_stream, clip_output_path, **output_params)

                    logger.debug("VP Clip: Executing ffmpeg command...")
                    if self._run_ffmpeg_command(stream, f"Clip {clip_success_count + 1}"):
                        if os.path.exists(clip_output_path) and os.path.getsize(clip_output_path) > 100:
                             initial_clip_paths.append(clip_output_path)
                             logger.info(f"VP Clip: Successfully created: {clip_output_filename}")
                             clip_success_count += 1
                        else:
                             logger.error(f"VP Clip: FFmpeg success but output missing/empty: {clip_output_path}")
                             if os.path.exists(clip_output_path): os.remove(clip_output_path)
                    else:
                         logger.error(f"VP Clip: FFmpeg failed for clip {clip_success_count + 1}.")
                         # Advance start time even on failure to avoid getting stuck repeating the same failed clip
                         # start_time_sec = actual_start_time + 1.0 # Option: advance minimally
                         # Or just let the default advancement below happen

                except Exception as clip_e:
                    logger.error(f"VP Clip: Error during clip {clip_success_count + 1} setup/run: {clip_e}")
                    traceback.print_exc()
                    # Advance start time to avoid getting stuck
                    # start_time_sec = actual_start_time + 1.0 # Option: advance minimally

                # --- Update Start Time for Next Attempt ---
                # Always advance based on the *attempted* clip's end time
                start_time_sec = actual_start_time + clip_duration_sec
                # Add overlap logic here if desired

            # --- Post-Processing ---
            logger.info(f"--- VP Post-Processing {len(initial_clip_paths)} initial clips ---")
            # ... (rest of post-processing loop remains the same as previous version) ...
            for clip_path in initial_clip_paths:
                 if not os.path.exists(clip_path): continue
                 logger.debug(f"VP Post: Processing '{os.path.basename(clip_path)}'")
                 current_path = clip_path
                 final_path = clip_path

                 try:
                    if extract_audio:
                        audio_file = self._extract_audio(current_path)
                        if audio_file: logger.debug(f"VP Post: Extracted audio for {os.path.basename(clip_path)}")

                    formatted_path = None
                    if vertical_crop or mirror:
                         formatted_path = self._format_video(current_path, vertical_crop, mirror)
                         if formatted_path:
                             logger.info(f"VP Post: Formatted -> {os.path.basename(formatted_path)}")
                             if current_path != clip_path: intermediate_files.add(current_path)
                             current_path = formatted_path
                             final_path = formatted_path
                         # else: Log handled in _format_video

                    enhanced_path = None
                    if enhance:
                        enhanced_path = self._enhance_video(current_path)
                        if enhanced_path:
                            logger.info(f"VP Post: Enhanced -> {os.path.basename(enhanced_path)}")
                            if current_path != clip_path and current_path != formatted_path: intermediate_files.add(current_path)
                            final_path = enhanced_path
                        # else: Log handled in _enhance_video

                    final_output_paths.append(final_path)

                 except Exception as post_e:
                     logger.error(f"VP Post: Error post-processing '{os.path.basename(clip_path)}': {post_e}")
                     traceback.print_exc()
                     if os.path.exists(clip_path) and clip_path not in final_output_paths:
                         final_output_paths.append(clip_path)

            # --- Cleanup (Optional) ---
            # logger.debug(f"VP Cleanup: Intermediate files: {intermediate_files}")
            # for int_file in intermediate_files: ...

            logger.info(f"--- VP ProcessVideo Finish: {os.path.basename(video_path)}. Final clips: {len(final_output_paths)} ---")
            return final_output_paths

        except (FFmpegNotFoundError, VideoProcessingError, FileNotFoundError, ValueError, TypeError) as e:
             logger.error(f"VP ProcessVideo: Pre-processing or setup error for {video_path}: {e}")
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
        base, ext = os.path.splitext(clean_clip_path)
        audio_output = base + ".mp3"
        logger.info(f"VP ExtractAudio: -> {os.path.basename(audio_output)}")
        try:
            probe = ffmpeg.probe(clean_clip_path, cmd=self.FFPROBE_PATH)
            if not any(s.get('codec_type') == 'audio' for s in probe.get('streams', [])):
                 logger.warning(f"VP ExtractAudio: No audio stream found in '{os.path.basename(clean_clip_path)}'.")
                 return None

            if self._run_ffmpeg_command(streams, "Extract Audio"): return audio_output
        except Exception as e: logger.error(f"VP ExtractAudio: Failed for {clip_path}: {e}")
        return None

    def _enhance_video(self, clip_path: str) -> Optional[str]:
        """Applies enhancement filters. Returns output path or None."""
        clean_clip_path = str(clip_path).strip('"')
        if not os.path.isfile(clean_clip_path): return None
        base, ext = os.path.splitext(clean_clip_path)
        # Avoid double suffix
        if base.endswith("_enhanced"): return clip_path
        for suffix in ["_formatted", "_crop", "_mir", "_noaudio"]: # Check other suffixes too
             if base.endswith(suffix): base = base[:-len(suffix)]; break
        output_path = base + "_enhanced" + ext

        logger.info(f"VP Enhance: -> {os.path.basename(output_path)}")
        try:
            vf_filter = "eq=contrast=1.1:brightness=0.01:saturation=1.1:gamma=1.05"
            output_params = {'vf': vf_filter, 'c:v': 'libx264', 'preset': 'medium', 'crf': 23}
            has_audio = False
            try:
                 probe = ffmpeg.probe(clean_clip_path, cmd=self.FFPROBE_PATH)
                 has_audio = any(s.get('codec_type') == 'audio' for s in probe.get('streams', []))
            except Exception: pass

            if has_audio: output_params['c:a'] = 'copy'
            else: output_params['an'] = None

            stream = ffmpeg.input(clean_clip_path).output(output_path, **output_params)

            if self._run_ffmpeg_command(stream, "Enhance Video"): return output_path
            elif has_audio: # Retry with audio re-encode
                 logger.warning("VP Enhance: Retrying with audio re-encode...")
                 output_params['c:a'] = 'aac'; output_params['b:a'] = '192k'
                 stream = ffmpeg.input(clean_clip_path).output(output_path, **output_params)
                 if self._run_ffmpeg_command(stream, "Enhance Video (Audio Re-encode)"): return output_path
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
            # Crop/Scale/Pad filter chain
            filters.extend([
                "crop=w=min(iw\\,ih*9/16):h=min(ih\\,iw*16/9)",
                "scale=w=1080:h=1920:force_original_aspect_ratio=decrease",
                "pad=w=1080:h=1920:x=(ow-iw)/2:y=(oh-ih)/2:color=black",
                "setsar=1" # Ensure square pixels after scaling/padding
            ])
            op_name_parts.append("Crop9x16")
            output_suffix_parts.append("crop")
        if mirror:
            filters.append("hflip")
            op_name_parts.append("Mirror")
            output_suffix_parts.append("mir")

        if not filters: return None

        # Construct unique output path
        base, ext = os.path.splitext(clean_clip_path)
        known_suffixes = ["_noaudio", "_enhanced", "_formatted", "_crop", "_mir"]
        for suffix in known_suffixes:
             if base.endswith(suffix): base = base[:-len(suffix)]; break
        output_suffix = "_" + "_".join(output_suffix_parts) + ext
        output_path = base + output_suffix

        operation_desc = "+".join(op_name_parts)
        logger.info(f"VP Format ({operation_desc}): -> {os.path.basename(output_path)}")
        try:
            output_params = {'vf': ",".join(filters), 'c:v': 'libx264', 'preset': 'medium', 'crf': 23}
            has_audio = False
            try:
                 probe = ffmpeg.probe(clean_clip_path, cmd=self.FFPROBE_PATH)
                 has_audio = any(s.get('codec_type') == 'audio' for s in probe.get('streams', []))
            except Exception: pass

            if has_audio: output_params['c:a'] = 'copy'
            else: output_params['an'] = None

            stream = ffmpeg.input(clean_clip_path).output(output_path, **output_params)

            if self._run_ffmpeg_command(stream, f"Format Video ({operation_desc})"): return output_path
            elif has_audio: # Retry with audio re-encode
                 logger.warning("VP Format: Retrying with audio re-encode...")
                 output_params['c:a'] = 'aac'; output_params['b:a'] = '192k'
                 stream = ffmpeg.input(clean_clip_path).output(output_path, **output_params)
                 if self._run_ffmpeg_command(stream, f"Format Video ({operation_desc} - Audio Re-encode)"): return output_path
        except Exception as e: logger.error(f"VP Format: Failed for {clip_path}: {e}")
        return None

    # --- Context Manager (Currently Unused, keep if needed for OpenCV later) ---
    # @contextmanager
    # def _video_capture(self, video_path: str, start_time: float):
    #     """Context manager for OpenCV video capture."""
    #     cap = None
    #     clean_path = str(video_path).strip('"')
    #     try:
    #         if not os.path.isfile(clean_path): raise FileNotFoundError(f"File not found: {clean_path}")
    #         import cv2 # Import here if only used here
    #         cap = cv2.VideoCapture(clean_path)
    #         if not cap.isOpened(): raise IOError(f"Could not open video with OpenCV: {clean_path}")
    #         cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
    #         yield cap
    #     finally:
    #         if cap: cap.release()