# utils/video_processor.py
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
import subprocess # For direct ffmpeg/ffprobe check in _check_ffmpeg only
import shutil # Added for shutil.which

logger = setup_logging() # Initialize logger for this module

class VideoProcessingError(Exception):
    """Custom exception for video processing errors."""
    pass

class FFmpegNotFoundError(Exception):
    """Exception raised when FFmpeg is not found or configured correctly."""
    pass

class VideoProcessor:
    """
    Handles low-level video processing tasks using FFmpeg and Scenedetect
    for individual video files. Focused on clipping and basic transformations.
    Requires valid paths to ffmpeg and ffprobe executables upon initialization.
    """

    def __init__(self, output_folder: str, ffmpeg_path: Optional[str], ffprobe_path: Optional[str]): # Added paths to init
        """
        Initialize the VideoProcessor. Checks output folder and FFmpeg availability.

        Args:
            output_folder (str): The base directory where output files will be saved.
            ffmpeg_path (Optional[str]): Full path to the FFmpeg executable.
            ffprobe_path (Optional[str]): Full path to the FFprobe executable.

        Raises:
            ValueError: If the output folder is invalid or cannot be created.
            FFmpegNotFoundError: If the provided FFmpeg/FFprobe paths are invalid or executables cannot be verified.
        """
        if not output_folder or not isinstance(output_folder, str):
             raise ValueError("VP Init: Invalid output folder path provided.")
        try:
            # Ensure output folder exists
            if not os.path.isdir(output_folder):
                logger.info(f"VP Init: Output folder '{output_folder}' not found. Creating.")
                os.makedirs(output_folder, exist_ok=True)
            self.output_folder = output_folder
            logger.debug(f"VP Init: Output folder set to: {self.output_folder}")
        except OSError as e:
            # Wrap OS error in a more specific ValueError
            raise ValueError(f"VP Init: Output folder '{output_folder}' could not be created: {e}")

        # Store paths and perform the check during initialization
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self._check_ffmpeg() # This will raise FFmpegNotFoundError if paths are invalid

    def _check_ffmpeg(self):
        """Checks if FFprobe/FFmpeg are accessible via stored paths using subprocess."""
        # Use self.ffprobe_path and self.ffmpeg_path now
        for exe_path, name in [(self.ffprobe_path, "FFprobe"), (self.ffmpeg_path, "FFmpeg")]:
            logger.debug(f"VP Check: Verifying {name} at provided path: {exe_path}")
            if not exe_path or not os.path.isfile(exe_path):
                 # Log if not found via PATH either for context
                 path_check = shutil.which(name.lower())
                 if path_check:
                     logger.warning(f"VP Check: {name} found via PATH at '{path_check}', but provided path '{exe_path}' is invalid or missing.")
                 else:
                     logger.error(f"VP Check: {name} not found via PATH either.")
                 # Raise error based on the invalid provided path
                 raise FFmpegNotFoundError(f"{name} executable path provided ('{exe_path}') is invalid or the file was not found.")

            # Run the executable with -version flag to verify it runs
            try:
                cmd = [exe_path, "-version"]
                # Use CREATE_NO_WINDOW on Windows to prevent flashing console
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                # Run the command, capture output, don't check return code immediately
                result = subprocess.run(cmd, capture_output=True, text=True, check=False,
                                        encoding='utf-8', errors='replace', creationflags=creationflags)

                # Combine stdout and stderr for version check (sometimes in stderr)
                version_info = (result.stdout or "") + (result.stderr or "")
                version_info = version_info.strip()

                # Check if expected version string fragment exists
                if f"{name.lower()} version" not in version_info.lower():
                     # If the command failed AND version info is missing, it's definitely an error
                     if result.returncode != 0:
                          error_detail = f"Exit code {result.returncode}. Output: {version_info[:500]}{'...' if len(version_info)>500 else ''}"
                          logger.error(f"VP Check: Failed to execute {name} at '{exe_path}'. {error_detail}")
                          raise FFmpegNotFoundError(f"Failed to execute {name} at '{exe_path}'. {error_detail}")
                     else:
                          # Command ran successfully (exit code 0) but output didn't contain "version"?
                          # This is unusual but might happen with custom builds. Log a warning but proceed.
                          logger.warning(f"VP Check: {name} ran successfully at '{exe_path}' but expected version string was not found in output. Assuming OK.")
                else:
                    # Found version string, log success
                    logger.info(f"VP Check: {name} check successful using provided path: {exe_path}")

            except (FileNotFoundError, PermissionError) as e:
                # These errors typically mean the path is wrong or permissions are denied
                logger.error(f"VP Check: Failed to find or execute {name} due to OS error at '{exe_path}': {e}")
                raise FFmpegNotFoundError(f"Failed to find or execute {name} at '{exe_path}': {e}")
            except Exception as e:
                # Catch any other unexpected exceptions during the check
                logger.error(f"VP Check: Unexpected error during {name} check using path '{exe_path}': {e}")
                traceback.print_exc()
                raise FFmpegNotFoundError(f"Unexpected error during {name} check ('{exe_path}'): {e}")

    # --- Duration ---
    def get_video_duration(self, video_path: str) -> float:
        """Gets video duration in seconds using FFprobe via ffmpeg-python."""
        clean_path = str(video_path).strip('"')
        if not os.path.isfile(clean_path):
            logger.error(f"VP Get Duration: File not found: {clean_path}")
            return 0.0
        # Use the stored ffprobe path
        if not self.ffprobe_path:
             logger.error("VP Get Duration: FFprobe path not configured in VideoProcessor.")
             # Raise error as this is required
             raise FFmpegNotFoundError("FFprobe path is required but not configured.")
             # return 0.0
        try:
            logger.debug(f"VP Get Duration: Probing: {clean_path} using {self.ffprobe_path}")
            # Use self.ffprobe_path here
            probe_result = ffmpeg.probe(clean_path, cmd=self.ffprobe_path)
            duration = float(probe_result["format"]["duration"])
            logger.debug(f"VP Get Duration: Duration found: {duration:.3f}s")
            return duration
        except ffmpeg.Error as e:
            stderr = e.stderr.decode('utf-8', errors='replace') if e.stderr else "N/A"
            logger.error(f"VP Get Duration: FFprobe error for {clean_path}: {stderr}")
            return 0.0 # Return 0.0 on probe error, could be invalid file
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"VP Get Duration: Error parsing duration from FFprobe output for {clean_path}: {e}")
            return 0.0 # Return 0.0 on parsing error
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
        if duration <= 0:
            logger.warning("Video duration is zero or negative, cannot determine clip count.")
            return 0
        if duration < min_length:
            logger.info(f"Video duration ({duration:.2f}s) is less than minimum clip length ({min_length}s). No clips possible.")
            return 0
        # Return at least 1, but don't exceed the requested count
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
                 return start_time # Return original start time if file missing

            # --- Initialize Scenedetect Components ---
            # Consider passing ffprobe path if VideoManager can use it
            video_manager = VideoManager([clean_path])
            scene_manager = SceneManager()
            # Add ContentDetector with the specified threshold
            scene_manager.add_detector(ContentDetector(threshold=threshold))

            # Improve performance by downscaling before analysis
            video_manager.set_downscale_factor(integer=True) # Auto-downscale
            # Start the video manager (opens the video file)
            video_manager.start()
            # Get the base timecode (required for accurate timestamp conversion)
            base_timecode = video_manager.get_base_timecode()
            if not base_timecode:
                 raise VideoProcessingError("Could not get base timecode from video manager.")

            # Set the start time for detection
            start_frame = base_timecode.get_frames() + int(start_time * base_timecode.get_framerate())
            video_manager.seek(start_frame) # Seek to the frame corresponding to start_time

            # Perform scene detection
            # show_progress=False prevents console output from scenedetect
            scene_manager.detect_scenes(frame_source=video_manager, show_progress=False)

            # Get the list of scenes detected (tuples of start/end FrameTimecode objects)
            # Only get scenes *after* the seek point
            scene_list = scene_manager.get_scene_list(base_timecode, start_time=start_time) # Use start_time filter

            # Find the first scene transition *after* the given start_time
            if scene_list:
                logger.debug(f"VP SceneDetect: Found {len(scene_list)} potential scenes after {start_time:.2f}s.")
                # scene_list is sorted; the first element's start is the earliest transition
                first_transition_timecode, _ = scene_list[0]
                scene_start_sec = first_transition_timecode.get_seconds()

                # Ensure the detected transition is actually *after* the requested start time (with a small buffer)
                if scene_start_sec > (start_time + 0.1):
                    logger.info(f"VP SceneDetect: Next transition found at {scene_start_sec:.2f}s")
                    return scene_start_sec
                else:
                    # Detected scene might start exactly at or before our start_time due to seeking/timing
                    logger.info("VP SceneDetect: Detected scene starts too close to current start time. No suitable *next* transition found.")
            else:
                logger.info("VP SceneDetect: No scenes detected after the specified start time.")

        except scenedetect.stats_manager.StatsFileCorruptError as e:
             # Handle potential error if using stats files (not default here)
             logger.warning(f"VP SceneDetect: Stats file error (if used): {e}.")
        except Exception as e:
            logger.error(f"VP SceneDetect: Error processing {os.path.basename(clean_path)}: {e}")
            traceback.print_exc()
        finally:
            # Ensure the video file is released
            if video_manager:
                video_manager.release()

        # Fallback: return the original start time if no suitable transition found
        return start_time

    # --- FFmpeg Command Runner ---
    def _run_ffmpeg_command(self, stream, operation_name="FFmpeg operation") -> bool:
        """Helper to run ffmpeg-python command using configured FFMPEG_PATH."""
        # Use the stored ffmpeg path
        if not self.ffmpeg_path:
             logger.error(f"VP Execute: FFmpeg path not configured for {operation_name}.")
             return False
        try:
            # Compile the command using the stored self.ffmpeg_path
            cmd_list = stream.compile(cmd=self.ffmpeg_path, overwrite_output=True)
            logger.debug(f"VP Execute: Running for {operation_name}: {' '.join(cmd_list)}")

            # Execute the command using stored self.ffmpeg_path
            # Pass cmd= here to ensure the correct executable is used by stream.run()
            stdout, stderr = stream.run(cmd=self.ffmpeg_path, capture_stdout=True, capture_stderr=True, overwrite_output=True)

            stderr_str = stderr.decode('utf-8', errors='replace').strip()
            if stderr_str:
                 # Crude check for 'warning' vs 'error' vs informational output
                 log_level_func = logger.debug # Default to debug for general output
                 if "error" in stderr_str.lower(): log_level_func = logger.error
                 elif "warning" in stderr_str.lower(): log_level_func = logger.warning
                 log_level_func(f"{operation_name} FFmpeg output:\n{stderr_str[:1000]}{'...' if len(stderr_str)>1000 else ''}")

            return True # Indicate command executed without ffmpeg.Error exception

        except ffmpeg.Error as e:
            # ffmpeg-python raises this if FFmpeg returns a non-zero exit code
            stderr_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else "No stderr available"
            logger.error(f"VP Execute: FFmpeg error during {operation_name}:\n{stderr_output}")
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
        scene_detect: bool = False,
        scene_threshold: float = 30.0,
        remove_audio: bool = False,
        extract_audio: bool = False,
        vertical_crop: bool = False,
        mirror: bool = False,
        enhance: bool = False,
    ) -> List[str]:
        """
        Clips video based on parameters, applies selected post-processing.
        Returns a list of paths to the final processed clip files.
        """
        logger.info(f"--- VP ProcessVideo Start: {os.path.basename(video_path)} ---")
        opts_str = (f"clips={clip_count}, len={min_clip_length}-{max_clip_length}s, "
                    f"scene={scene_detect}({scene_threshold}), crop={vertical_crop}, "
                    f"mirror={mirror}, enhance={enhance}, rm_audio={remove_audio}, "
                    f"ext_audio={extract_audio}")
        logger.info(f"VP Options: {opts_str}")

        clean_video_path = str(video_path).strip('"')
        initial_clip_paths = [] # Store paths of initially clipped files
        final_output_paths = [] # Store paths of final files after post-processing
        intermediate_files = set() # Keep track of files created during post-processing

        try:
            # Use the instance method to get duration (which uses configured ffprobe path)
            duration = self.get_video_duration(clean_video_path)
            if duration <= 0:
                 # get_video_duration logs errors, just raise specific error here
                 raise VideoProcessingError(f"Could not get valid duration ({duration:.2f}s) for {os.path.basename(video_path)}")

            # Validate clip length and determine number of clips
            min_len, max_len = self._validate_clip_length_range(min_clip_length, max_clip_length)
            num_clips_to_make = self._determine_clip_count(clip_count, duration, min_len, max_len)

            if num_clips_to_make == 0:
                logger.info(f"VP Clip: No clips possible based on duration and settings for {os.path.basename(video_path)}.")
                return [] # Return empty list if no clips can be made

            logger.info(f"VP Details: Duration={duration:.2f}s, Target clips={num_clips_to_make}")

            start_time_sec = 0.0 # Start time for the next potential clip
            clip_success_count = 0 # Number of clips successfully created so far

            # --- Clipping Loop ---
            # Continue until we have the desired number of successful clips
            while clip_success_count < num_clips_to_make:
                current_attempt_index = len(initial_clip_paths) # Track total attempts
                logger.info(f"--- VP Clip Attempt {current_attempt_index + 1} (Target {clip_success_count + 1}/{num_clips_to_make}) ---")

                # Check if remaining duration is too short for even the minimum clip length
                min_time_needed = 1.0 # Need at least a small buffer
                if start_time_sec >= duration - min_time_needed:
                    logger.info(f"VP Clip: Remaining duration ({duration - start_time_sec:.2f}s) too short. Stopping clip generation.")
                    break # Exit the loop if not enough time left

                # Determine Actual Start Time (Adjust if scene detection enabled)
                actual_start_time = start_time_sec
                if scene_detect:
                    # Find the next scene transition *after* the current start_time_sec
                    detected_start = self.detect_scene_transition(clean_video_path, start_time_sec, scene_threshold)
                    # Use the detected start only if it's significantly after the current start
                    # and leaves enough time for a minimum length clip
                    if detected_start > (start_time_sec + 0.1) and detected_start < duration - min_time_needed:
                        logger.info(f"VP Clip: Scene Detect adjusted start from {start_time_sec:.2f}s to {detected_start:.2f}s")
                        actual_start_time = detected_start
                    else:
                        logger.info(f"VP Clip: Scene Detect did not find a suitable later start point near {start_time_sec:.2f}s.")

                # Final check if adjusted start time is still valid
                if actual_start_time >= duration - min_time_needed:
                    logger.warning(f"VP Clip: Adjusted start time {actual_start_time:.2f}s is too close to video end. Stopping clip generation.")
                    break

                # Determine Clip Duration for this attempt
                max_possible_duration = duration - actual_start_time
                # Clip length cannot exceed max_len or the remaining video duration
                current_max_len = min(max_len, int(max_possible_duration))
                # Min length cannot be less than 1 or more than the adjusted max
                current_min_len = max(1, min(min_len, current_max_len))

                # Check if a valid duration range exists
                if current_min_len > current_max_len :
                     logger.warning(f"VP Clip: Invalid calculated length range ({current_min_len}-{current_max_len}s) at start {actual_start_time:.2f}s. Advancing start time.")
                     start_time_sec = actual_start_time + 1.0 # Advance slightly to avoid getting stuck
                     continue # Skip to the next attempt

                # Choose a random duration within the valid range
                clip_duration_sec = random.randint(current_min_len, current_max_len)
                logger.info(f"VP Clip {clip_success_count + 1}: Start={actual_start_time:.2f}s, Duration={clip_duration_sec:.2f}s")

                # --- Define Output Path for this specific clip ---
                base_name = os.path.basename(clean_video_path)
                name, _ = os.path.splitext(base_name)
                # Use a temporary suffix initially? Or just the final name pattern?
                # Using the final pattern seems okay if cleanup handles intermediates.
                clip_output_filename = f"{name}_clip_{clip_success_count + 1}.mp4"
                clip_output_path = os.path.join(self.output_folder, clip_output_filename)

                # --- FFmpeg Clipping Command using ffmpeg-python ---
                try:
                    logger.debug("VP Clip: Building ffmpeg clipping command...")
                    # Input stream with start time (ss) and duration (t)
                    # Using -ss before -i is faster for keyframe seeking but less precise.
                    # Using -ss after -i (in input()) is precise but slower. Let's prioritize precision.
                    input_stream = ffmpeg.input(clean_video_path, ss=actual_start_time, t=clip_duration_sec)

                    # Output parameters: Copy codecs initially for speed, handle audio removal
                    output_params = {
                        'c:v': 'copy',          # Copy video codec (fastest)
                        'c:a': 'copy',          # Copy audio codec
                        'map_metadata': '-1',   # Remove global metadata
                        'map_chapters': -1,     # Remove chapters
                        'avoid_negative_ts': 'make_zero' # Handle potential timestamp issues
                    }
                    if remove_audio:
                        logger.debug("VP Clip: Audio removal requested for initial clip.")
                        del output_params['c:a'] # Remove audio copy
                        output_params['an'] = None # Add flag to disable audio

                    # Create the output node
                    stream = ffmpeg.output(input_stream, clip_output_path, **output_params)

                    logger.debug("VP Clip: Executing ffmpeg clipping command...")
                    # Run the command using the helper which uses configured ffmpeg path
                    if self._run_ffmpeg_command(stream, f"Clip {clip_success_count + 1}"):
                        # Verify the output file was created and has content
                        if os.path.exists(clip_output_path) and os.path.getsize(clip_output_path) > 100: # Basic size check
                             initial_clip_paths.append(clip_output_path)
                             logger.info(f"VP Clip: Successfully created initial clip: {clip_output_filename}")
                             clip_success_count += 1 # Increment success count ONLY if clip is valid
                        else:
                             logger.error(f"VP Clip: FFmpeg reported success but output missing/empty: {clip_output_path}")
                             if os.path.exists(clip_output_path):
                                 try: os.remove(clip_output_path) # Clean up empty file
                                 except OSError: pass
                             # Do not increment success count, try again from next position
                    else:
                         logger.error(f"VP Clip: FFmpeg failed for clip {clip_success_count + 1}.")
                         # Do not increment success count, try again from next position

                except Exception as clip_e:
                    logger.error(f"VP Clip: Error during clip {clip_success_count + 1} setup/run: {clip_e}")
                    traceback.print_exc()
                    # Do not increment success count, try again from next position

                # --- Update Start Time for Next Clip Attempt ---
                # Advance start time based on the end of the *attempted* clip,
                # regardless of success/failure, to avoid retrying the same segment.
                # Add a small buffer (e.g., 1 second) to prevent potential overlap issues.
                start_time_sec = actual_start_time + clip_duration_sec + 1.0
            # --- End Clipping Loop ---

            # --- Post-Processing Loop ---
            if not initial_clip_paths:
                 logger.warning(f"VP Post: No initial clips were successfully created for {os.path.basename(video_path)}. Skipping post-processing.")
                 return [] # Return empty if clipping failed entirely

            logger.info(f"--- VP Post-Processing {len(initial_clip_paths)} initial clips ---")
            for clip_path in initial_clip_paths:
                 if not os.path.exists(clip_path):
                     logger.warning(f"VP Post: Initial clip path missing, skipping: {clip_path}")
                     continue

                 logger.debug(f"VP Post: Processing '{os.path.basename(clip_path)}'")
                 current_input_path = clip_path # Start with the initial clip
                 final_output_for_this_clip = clip_path # Assume initial clip is final unless changed
                 needs_re_encoding = False # Flag if any filter requires re-encoding

                 try:
                    # --- Audio Extraction (Optional) ---
                    if extract_audio and not remove_audio: # Only if audio wasn't removed initially
                        # This runs as a separate FFmpeg command
                        audio_file = self._extract_audio(current_input_path)
                        if audio_file:
                            logger.debug(f"VP Post: Extracted audio for {os.path.basename(clip_path)}")
                        # Audio extraction doesn't change the video path being processed

                    # --- Prepare filters for combined re-encoding run ---
                    video_filters = []
                    audio_filters = [] # Currently unused, but could be added
                    output_suffix_parts = [] # To build a descriptive filename

                    # Vertical Crop / Format Filter
                    if vertical_crop:
                        # Define crop/scale/pad filters
                        video_filters.extend([
                            "crop=w=min(iw\\,ih*9/16):h=min(ih\\,iw*16/9)",
                            "scale=w=1080:h=1920:force_original_aspect_ratio=decrease",
                            "pad=w=1080:h=1920:x=(ow-iw)/2:y=(oh-ih)/2:color=black",
                            "setsar=1" # Ensure square pixels
                        ])
                        output_suffix_parts.append("crop")
                        needs_re_encoding = True

                    # Mirror Filter
                    if mirror:
                        video_filters.append("hflip")
                        output_suffix_parts.append("mir")
                        needs_re_encoding = True

                    # Enhancement Filter
                    if enhance:
                        # Define enhancement filters (adjust values as needed)
                        video_filters.append("eq=contrast=1.1:brightness=0.01:saturation=1.1:gamma=1.05")
                        output_suffix_parts.append("enh")
                        needs_re_encoding = True

                    # --- Execute Combined Re-encoding (if needed) ---
                    if needs_re_encoding:
                        # Construct unique output path for the processed version
                        base, ext = os.path.splitext(clip_path) # Use original clip path base
                        # Remove existing suffixes to avoid doubling up
                        known_suffixes = ["_noaudio", "_enhanced", "_formatted", "_crop", "_mir"]
                        for suffix in known_suffixes:
                             if base.endswith(suffix): base = base[:-len(suffix)]; break
                        output_suffix = "_" + "_".join(output_suffix_parts) + ext
                        processed_output_path = base + output_suffix
                        operation_desc = "+".join(output_suffix_parts)

                        logger.info(f"VP Post ({operation_desc}): -> {os.path.basename(processed_output_path)}")

                        # Build ffmpeg-python command for combined filters
                        input_stream = ffmpeg.input(current_input_path)
                        filtered_video = input_stream['v'].filter_multi_output('split')[0] # Start chain
                        if video_filters:
                            filtered_video = filtered_video.filter("vf", ",".join(video_filters))

                        # Handle audio: copy if present and not removed, otherwise disable
                        output_params_post = {'c:v': 'libx264', 'preset': 'medium', 'crf': 23}
                        has_audio = False
                        if not remove_audio:
                             try:
                                 # Probe the *current input* for audio before filtering
                                 probe = ffmpeg.probe(current_input_path, cmd=self.ffprobe_path)
                                 has_audio = any(s.get('codec_type') == 'audio' for s in probe.get('streams', []))
                             except Exception: pass

                        if has_audio:
                            # If filtering video, we MUST re-encode audio or copy it carefully. Copy is preferred.
                            output_params_post['c:a'] = 'copy'
                            stream = ffmpeg.output(filtered_video, input_stream['a'], processed_output_path, **output_params_post)
                        else:
                            output_params_post['an'] = None
                            stream = ffmpeg.output(filtered_video, processed_output_path, **output_params_post)

                        # Run the combined post-processing command
                        if self._run_ffmpeg_command(stream, f"Post-Process ({operation_desc})"):
                             # If successful, update the final path for this clip
                             final_output_for_this_clip = processed_output_path
                             # Mark the original clip path as intermediate if it's different
                             if clip_path != final_output_for_this_clip:
                                 intermediate_files.add(clip_path)
                             logger.info(f"VP Post: Successfully processed -> {os.path.basename(final_output_for_this_clip)}")
                        else:
                             logger.error(f"VP Post: Failed to apply post-processing filters ({operation_desc}) to {os.path.basename(clip_path)}. Using original clip.")
                             # Keep final_output_for_this_clip as the original clip_path

                    # Add the final path (either original or processed) to the list
                    final_output_paths.append(final_output_for_this_clip)

                 except Exception as post_e:
                     logger.error(f"VP Post: Error during post-processing loop for '{os.path.basename(clip_path)}': {post_e}")
                     traceback.print_exc()
                     # If an error occurred, ensure the *original* clip path is added if it wasn't already
                     # And if it still exists
                     if os.path.exists(clip_path) and clip_path not in final_output_paths:
                         final_output_paths.append(clip_path)
            # --- End Post-Processing Loop ---

            # --- Cleanup Intermediate Files (Optional) ---
            # If you want to delete the initial clips after processing:
            # logger.debug(f"VP Cleanup: Intermediate files marked: {intermediate_files}")
            # for int_file in intermediate_files:
            #     if int_file in final_output_paths: continue # Don't delete if it's also a final output
            #     if os.path.exists(int_file):
            #         try:
            #             os.remove(int_file)
            #             logger.info(f"VP Cleanup: Removed intermediate file: {os.path.basename(int_file)}")
            #         except OSError as e:
            #             logger.warning(f"VP Cleanup: Failed to remove intermediate file {int_file}: {e}")

            logger.info(f"--- VP ProcessVideo Finish: {os.path.basename(video_path)}. Final clips: {len(final_output_paths)} ---")
            return final_output_paths

        except (FFmpegNotFoundError, VideoProcessingError, FileNotFoundError, ValueError, TypeError) as e:
             # Catch errors occurring before or during the main processing loops
             logger.error(f"VP ProcessVideo: Failed for {os.path.basename(video_path)}: {e}")
             # No traceback here unless debugging, as the error type is known
             return [] # Return empty list on failure
        except Exception as e:
            # Catch unexpected critical errors
            logger.error(f"VP ProcessVideo: Unexpected critical error for {os.path.basename(video_path)}: {e}")
            traceback.print_exc()
            return [] # Return empty list on failure


    # --- Individual Post-Processing Steps (Refactored for internal use in combined step) ---
    # These are kept for reference or potential future use, but the main process_video
    # now combines filters where possible for efficiency.

    def _extract_audio(self, clip_path: str) -> Optional[str]:
        """Extracts audio to an MP3 file. Returns output path or None."""
        clean_clip_path = str(clip_path).strip('"')
        if not os.path.isfile(clean_clip_path):
             logger.warning(f"VP ExtractAudio: Input file not found: {clean_clip_path}")
             return None
        base, ext = os.path.splitext(clean_clip_path)
        audio_output = base + ".mp3"

        # Check if paths are configured
        if not self.ffmpeg_path or not self.ffprobe_path:
             logger.error("VP ExtractAudio: FFmpeg/FFprobe paths not configured in VideoProcessor.")
             return None
        logger.info(f"VP ExtractAudio: -> {os.path.basename(audio_output)}")
        try:
            # Check for audio stream first
            probe = ffmpeg.probe(clean_clip_path, cmd=self.ffprobe_path)
            if not any(s.get('codec_type') == 'audio' for s in probe.get('streams', [])):
                 logger.warning(f"VP ExtractAudio: No audio stream found in '{os.path.basename(clean_clip_path)}'.")
                 return None # No audio to extract

            # Build ffmpeg-python command
            input_stream = ffmpeg.input(clean_clip_path)
            # Select only the audio stream ('a')
            stream = ffmpeg.output(input_stream['a'], audio_output, format="mp3", acodec='libmp3lame', q='2') # Good quality VBR

            # Run using helper
            if self._run_ffmpeg_command(stream, "Extract Audio"):
                 if os.path.exists(audio_output): return audio_output
                 else: logger.error("VP ExtractAudio: Command success but output file missing."); return None
            else:
                 return None # _run_ffmpeg_command already logged error
        except ffmpeg.Error as e:
             stderr = e.stderr.decode('utf-8', errors='replace') if e.stderr else "N/A"
             logger.error(f"VP ExtractAudio: ffmpeg.Error for {os.path.basename(clip_path)}: {stderr}")
             return None
        except Exception as e:
             logger.error(f"VP ExtractAudio: Unexpected error for {os.path.basename(clip_path)}: {e}")
             traceback.print_exc()
             return None

    # Note: _enhance_video and _format_video logic is now primarily handled
    # within the combined post-processing section of process_video for efficiency.
    # These separate methods could be kept for standalone use cases if needed,
    # but ensure they use self.ffmpeg_path and self.ffprobe_path correctly if kept.
    # For clarity, I'll comment them out here as the main flow doesn't use them separately anymore.

    # def _enhance_video(self, clip_path: str) -> Optional[str]: ...
    # def _format_video(self, clip_path: str, vertical_crop: bool, mirror: bool) -> Optional[str]: ...

    # --- Context Manager (Keep if needed for OpenCV later) ---
    # @contextmanager
    # def _video_capture(self, video_path: str, start_time: float): ...