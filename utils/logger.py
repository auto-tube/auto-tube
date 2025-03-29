# utils/logger.py
import os
import random
import cv2
import numpy as np
import ffmpeg
from typing import List, Optional, Tuple
from contextlib import contextmanager
from utils.logger_config import setup_logging # Assuming logger_config.py is in the same directory
import scenedetect
# These imports are only needed if detect_scene_transition uses them directly, which it does
from scenedetect.video_manager import VideoManager
from scenedetect.detectors import ContentDetector
from scenedetect.scene_manager import SceneManager

logger = setup_logging()

class VideoProcessingError(Exception):
    """Custom exception for video processing errors."""
    pass

class FFmpegNotFoundError(Exception):
    """Exception raised when FFmpeg is not found."""
    pass

class VideoProcessor:
    """A comprehensive video processing utility class."""

    # CLIP_LENGTH_RANGES is likely not needed anymore if min/max are passed directly
    # CLIP_LENGTH_RANGES = {
    #     "30-45": (30, 45),
    #     "60-105": (60, 105),
    #     "120-180": (120, 180)
    # }

    def __init__(self, output_folder: str):
        """
        Initialize the VideoProcessor with output configuration.

        Args:
            output_folder (str): Directory where processed videos will be saved.
        """
        if not os.path.isdir(output_folder):
             # Attempt to create if it doesn't exist
             try:
                 print(f"Output folder '{output_folder}' not found. Attempting to create.")
                 os.makedirs(output_folder, exist_ok=True)
             except OSError as e:
                 raise ValueError(f"Output folder '{output_folder}' is not a valid directory and could not be created: {e}")

        self.output_folder = output_folder
        # os.makedirs(output_folder, exist_ok=True) # Already checked/created above
        self._check_ffmpeg() # Ensure FFmpeg is available

    def _check_ffmpeg(self):
        """Check if FFmpeg (specifically ffprobe for probe) is installed and accessible."""
        # --- Use the specific path provided by the user ---
        # !! IMPORTANT: Replace this path if your FFmpeg location is different !!
        ffprobe_path = r"C:\Users\V0iD\Downloads\ffmpeg-2025-03-27-git-114fccc4a5-full_build\bin\ffprobe.exe"
        # --- End specific path ---
        try:
            # Check if the explicit path exists and is a file
            if not os.path.isfile(ffprobe_path):
                raise FileNotFoundError(f"The specified ffprobe executable does not exist at: {ffprobe_path}")

            # Pass the explicit path for ffprobe to the probe command's 'cmd' argument
            print(f"Attempting probe using explicit ffprobe path: {ffprobe_path}") # Debug print
            # Using a dummy file that doesn't exist is fine for just checking if ffprobe runs
            ffmpeg.probe("dummy_nonexistent_file.mp4", cmd=ffprobe_path)
            # If probe raises an ffmpeg.Error because the file doesn't exist,
            # BUT NOT a FileNotFoundError for ffprobe itself, that's still success!
            print("FFmpeg ffprobe check seems successful (ffprobe executable was likely found and run).")
            # We can proceed assuming ffprobe works.

        except ffmpeg.Error as e:
            # Check if the error is specifically about the dummy file, which means ffprobe ran!
            stderr_str = e.stderr.decode('utf-8', errors='replace') if e.stderr else ""
            if "dummy_nonexistent_file.mp4: No such file or directory" in stderr_str:
                print("FFmpeg ffprobe check successful (ffprobe ran, dummy file error expected).")
                # This means ffprobe executable was found and executed. We're good.
            else:
                # ffprobe ran but failed for a different reason (e.g., permissions, corrupted build)
                raise FFmpegNotFoundError(f"ffmpeg.probe error using explicit path {ffprobe_path}: {stderr_str}")
        except FileNotFoundError:
            # This error means the *explicit ffprobe_path itself* couldn't be found/executed by the OS
            # This is different from ffmpeg.Error if the dummy file isn't found
            raise FFmpegNotFoundError(f"Explicit FFprobe path not found or invalid. Please verify the path. Checked: {ffprobe_path}")
        except PermissionError:
            # Catch permission errors specifically
             raise FFmpegNotFoundError(f"Permission denied when trying to execute ffprobe at: {ffprobe_path}. Check file permissions.")
        except Exception as e:
            # Catch other unexpected errors during the probe call
            import traceback
            traceback.print_exc() # Print full traceback for debugging
            raise FFmpegNotFoundError(f"Unexpected error during FFmpeg check using explicit path {ffprobe_path}: {e}")


    @staticmethod
    def format_time(seconds: int) -> str:
        """
        Convert seconds to formatted time string (hh:mm:ss). DEPRECATED by _seconds_to_srt_time?
        Keep for now if used elsewhere, but SRT formatting is different.
        Args:
            seconds (int): Total seconds to format.

        Returns:
            str: Formatted time string.
        """
        if not isinstance(seconds, (int, float)) or seconds < 0:
            return "00:00:00" # Handle invalid input
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{secs:02}"

    def get_video_duration(self, video_path: str) -> float: # Return float for potentially more precision
        """
        Retrieve the duration of a video in seconds.

        Args:
            video_path (str): Path to the video file.

        Returns:
            float: Video duration in seconds. Returns 0.0 if duration cannot be determined.
        """
        clean_path = video_path.strip('"') # Remove quotes if present
        if not os.path.isfile(clean_path):
             logger.error(f"Video file not found at path: {clean_path}")
             raise FileNotFoundError(f"Video file not found: {clean_path}")

        try:
             # Explicitly define ffprobe path for probe, reusing from check or defining again
             ffprobe_path = r"C:\Users\V0iD\Downloads\ffmpeg-2025-03-27-git-114fccc4a5-full_build\bin\ffprobe.exe"
             if not os.path.isfile(ffprobe_path): # Check again just in case
                  raise FFmpegNotFoundError(f"FFprobe executable not found at specified path: {ffprobe_path}")

             logger.info(f"Probing video duration for: {clean_path} using ffprobe: {ffprobe_path}")
             probe = ffmpeg.probe(clean_path, cmd=ffprobe_path)
             duration = float(probe["format"]["duration"])
             logger.info(f"Determined duration: {duration} seconds")
             return duration
        except ffmpeg.Error as e:
            stderr_str = e.stderr.decode('utf-8', errors='replace') if e.stderr else "N/A"
            logger.error(f"FFmpeg/FFprobe error probing video duration for {clean_path}: {stderr_str}")
            # Don't raise VideoProcessingError here, allow calling code to handle maybe
            return 0.0 # Return 0 or None to indicate failure? Returning 0 for now.
        except KeyError:
             logger.error(f"Could not find 'duration' key in FFprobe output format section for {clean_path}.")
             return 0.0
        except Exception as e:
            logger.error(f"Unexpected error probing video duration for {clean_path}: {e}")
            import traceback
            traceback.print_exc()
            return 0.0 # Return 0 on unexpected errors

    def _get_clip_length_range(self, min_length: int, max_length: int) -> Tuple[int, int]:
        """
        Validates and returns the clip length range.

        Args:
            min_length (int): Minimum clip length.
            max_length (int): Maximum clip lengths.

        Returns:
            Tuple[int, int]: Minimum and maximum clip lengths.
        Raises:
            ValueError: If min_length > max_length or lengths are non-positive.
        """
        if not isinstance(min_length, int) or not isinstance(max_length, int):
             raise TypeError("Clip lengths must be integers.")
        if min_length <= 0 or max_length <= 0:
             raise ValueError("Clip lengths must be positive.")
        if min_length > max_length:
            raise ValueError("Minimum clip length cannot be greater than maximum clip length.")
        return (min_length, max_length)

    def _determine_clip_count(self, clip_count: int, duration: float,
                               min_length: int, max_length: int) -> int:
        """
        Calculates the number of clips, ensuring it's reasonable.

        Args:
            clip_count (int): Desired number of clips.
            duration (float): Total video duration.
            min_length (int): Minimum clip length.
            max_length (int): Maximum clip length.

        Returns:
            int: Number of clips to extract (at least 1 if possible).
        """
        if not isinstance(clip_count, int) or clip_count <= 0:
            logger.warning(f"Invalid clip_count '{clip_count}', defaulting to 1.")
            clip_count = 1
        if duration <= 0:
             logger.warning("Video duration is zero or negative, cannot determine clip count.")
             return 0 # Cannot make clips from zero duration video

        # Ensure at least one clip can theoretically fit
        if duration < min_length:
             logger.warning(f"Video duration ({duration}s) is less than minimum clip length ({min_length}s). Cannot extract clips.")
             return 0

        # Optional: Add a check to prevent excessively large number of clips
        # avg_length = (min_length + max_length) / 2
        # max_possible_clips = int(duration // min_length) # Absolute max non-overlapping
        # if clip_count > max_possible_clips * 2: # Allow some overlap/flexibility
        #    logger.warning(f"Requested clip count ({clip_count}) seems high for video duration ({duration}s). Adjusting to {max_possible_clips}.")
        #    clip_count = max_possible_clips

        return max(1, clip_count) # Ensure at least 1 clip is requested if possible


    def detect_scene_transition(self, video_path: str, start_time: float, threshold: float) -> float:
        """
        Detect scene transitions using scenedetect library.

        Args:
            video_path (str): Path to the video file.
            start_time (float): Starting time for scene detection (in seconds).
            threshold (float): Scene detection threshold (content detector specific).

        Returns:
            float: Timestamp (seconds) of the start of the *next* detected scene
                   occurring *after* start_time. Returns start_time if no suitable
                   scene transition is found or an error occurs.
        """
        clean_path = video_path.strip('"')
        logger.info(f"Detecting scenes for '{os.path.basename(clean_path)}' starting after {start_time:.2f}s with threshold {threshold}")
        video_manager = None # Ensure variable exists for finally block
        try:
            # Note: VideoManager might require paths without spaces or special chars depending on backend.
            # Consider using a temporary copy with a safe name if issues arise.
            video_manager = VideoManager([clean_path])
            scene_manager = SceneManager()
            # Using ContentDetector - sensitive to changes in content/color/motion
            scene_manager.add_detector(ContentDetector(threshold=threshold))

            base_timecode = video_manager.get_base_timecode()

            # Set downscale factor for performance, if desired (e.g., 2 means process at half resolution)
            # video_manager.set_downscale_factor(2)

            # Start video decoding. Crucial for accurate scene detection timecodes.
            video_manager.start() # Start from beginning to process duration/frame rate info

            # Set the start time for detection *after* starting the video_manager
            start_frame = base_timecode + start_time # Convert seconds to FrameTimecode
            end_frame = base_timecode + self.get_video_duration(clean_path) # Detect until the end

            logger.debug(f"Detecting scenes between {start_frame} and {end_frame}")

            # Detect scenes within the specified range (or whole video if range not needed)
            scene_manager.detect_scenes(frame_source=video_manager) # Detect all scenes first

            # Get list of scenes relative to the video start (00:00:00.000)
            scene_list = scene_manager.get_scene_list(base_timecode) # List of tuples: (start_timecode, end_timecode)

            if scene_list:
                logger.debug(f"Detected {len(scene_list)} scenes: {[(s[0].get_timecode(), s[1].get_timecode()) for s in scene_list]}")
                # Find the first scene START time that is strictly greater than the requested start_time
                for scene_start, scene_end in scene_list:
                    scene_start_sec = scene_start.get_seconds()
                    # Add a small buffer (e.g., 0.1s) to avoid re-detecting the same transition immediately
                    if scene_start_sec > (start_time + 0.1):
                        logger.info(f"Next scene found starting at {scene_start_sec:.2f}s")
                        return scene_start_sec # Return the start time of that scene

                logger.info("No subsequent scene transitions found after the specified start time.")
            else:
                logger.info("No scenes detected in the video.")

        except scenedetect.stats_manager.StatsFileCorruptError as e:
             logger.error(f"Scene detection stats file error for {clean_path}: {e}. Try deleting any '.stats' file near the video.")
        except Exception as e:
            logger.error(f"Error during scene detection for {clean_path}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if video_manager:
                video_manager.release() # Ensure video file handle is released

        return start_time # Return original start_time if no suitable scene found or error


    @contextmanager
    def _video_capture(self, video_path: str, start_time: float):
        """
        Context manager for OpenCV video capture (Less used now with FFmpeg/Scenedetect).
        """
        cap = None
        clean_path = video_path.strip('"')
        try:
            if not os.path.isfile(clean_path):
                 raise FileNotFoundError(f"Video file not found for OpenCV capture: {clean_path}")
            cap = cv2.VideoCapture(clean_path) # Use clean path for OpenCV
            if not cap.isOpened():
                 raise IOError(f"Could not open video file with OpenCV: {clean_path}")
            cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
            yield cap
        finally:
            if cap:
                cap.release()

    def _quote_path(self, path: str) -> str:
        """DEPRECATED. Path quoting for direct shell commands. Not needed for list args."""
        # ffmpeg-python library handles quoting internally when needed.
        # Using explicit quotes can sometimes cause issues with the library.
        return path # Return unchanged path

    # --- Main Processing Method ---
    def process_video(
        self,
        video_path: str,
        clip_count: int = 3,
        min_clip_length: int = 15, # Default min
        max_clip_length: int = 45, # Default max
        overlap: bool = False, # Keep overlap option? Needs logic adjustment if used
        scene_detect: bool = False,
        scene_threshold: float = 30.0,
        remove_audio: bool = False,
        extract_audio: bool = False,
        vertical_crop: bool = False,
        mirror: bool = False,
        enhance: bool = False,
    ) -> List[str]:
        """
        Clips video based on parameters, optionally using scene detection.
        Handles audio removal/extraction and basic formatting.
        """
        logger.info(f"--- Starting processing for: {os.path.basename(video_path)} ---")
        logger.info(f"Options: clips={clip_count}, len={min_clip_length}-{max_clip_length}s, scene_detect={scene_detect}, threshold={scene_threshold}, crop={vertical_crop}, mirror={mirror}, enhance={enhance}, remove_audio={remove_audio}, extract_audio={extract_audio}")

        processed_clips_paths = []
        clean_video_path = video_path.strip('"')

        try:
            # Validate inputs early
            duration = self.get_video_duration(clean_video_path)
            if duration <= 0:
                logger.error(f"Cannot process video with duration {duration}s.")
                return [] # Return empty list if no duration

            min_len, max_len = self._get_clip_length_range(min_clip_length, max_clip_length)
            num_clips_to_make = self._determine_clip_count(clip_count, duration, min_len, max_len)
            if num_clips_to_make == 0:
                 logger.warning("Could not determine a valid number of clips to create.")
                 return []

            logger.info(f"Video Duration: {duration:.2f}s. Target clips: {num_clips_to_make}")

            start_time_sec = 0.0
            clip_index = 0 # Use index for filename

            while clip_index < num_clips_to_make:
                # Check if remaining duration is sufficient for a minimal clip
                if start_time_sec + min_len > duration:
                    logger.info(f"Remaining duration ({duration - start_time_sec:.2f}s) less than min clip length ({min_len}s). Stopping clip generation.")
                    break

                # --- Scene Detection Logic ---
                actual_start_time = start_time_sec
                if scene_detect:
                    logger.debug(f"Running scene detection starting after {start_time_sec:.2f}s")
                    detected_start = self.detect_scene_transition(clean_video_path, start_time_sec, scene_threshold)
                    # Only use detected start if it's valid and different from current start
                    if detected_start > start_time_sec and detected_start < duration:
                        logger.info(f"Scene detection adjusted start time from {start_time_sec:.2f}s to {detected_start:.2f}s")
                        actual_start_time = detected_start
                    else:
                         logger.info("Scene detection did not find a suitable later start time.")
                         # Optional: If no scene found, maybe just advance by a fixed amount or stop?
                         # For now, proceed from the original start_time_sec if no scene found.


                # Ensure start time is not beyond duration after potential scene detect adjustment
                if actual_start_time >= duration:
                     logger.warning(f"Calculated start time {actual_start_time:.2f}s is beyond video duration {duration:.2f}s. Stopping.")
                     break

                # --- Determine Clip Duration ---
                # Ensure max possible duration doesn't exceed remaining video
                max_possible_duration = duration - actual_start_time
                current_max_len = min(max_len, int(max_possible_duration)) # Clip can't be longer than remaining video
                # Ensure min_len isn't greater than the adjusted current_max_len
                current_min_len = min(min_len, current_max_len)

                if current_min_len >= current_max_len:
                    # If remaining time is very short, just take what's left if it meets min_len, otherwise use min_len if possible
                    clip_duration_sec = current_min_len if current_min_len > 0 else 1 # Ensure positive duration
                else:
                    # Generate random duration within the valid current range
                     clip_duration_sec = random.randint(current_min_len, current_max_len)

                # Final check to prevent tiny clips if logic above fails
                if clip_duration_sec <= 0:
                     logger.warning(f"Calculated clip duration {clip_duration_sec} is zero or negative. Skipping clip.")
                     start_time_sec += 1 # Advance slightly to avoid infinite loop
                     continue


                logger.info(f"Clip {clip_index + 1}: Start={actual_start_time:.2f}s, Duration={clip_duration_sec:.2f}s")

                # --- Define Output Path ---
                base_name = os.path.basename(clean_video_path)
                name, ext = os.path.splitext(base_name)
                output_filename = f"{name}_clip_{clip_index + 1}.mp4" # Use standard mp4 extension
                output_path = os.path.join(self.output_folder, output_filename)

                # --- FFmpeg Processing for Clipping ---
                try:
                    input_stream = ffmpeg.input(clean_video_path, ss=actual_start_time, t=clip_duration_sec)
                    output_params = {'c:v': 'libx264', 'crf': 23, 'preset': 'medium'} # Basic encoding params

                    # Handle Audio Options during clipping if possible
                    if remove_audio:
                        output_params['an'] = None # Disable audio
                        audio_stream = None
                    else:
                        # Include audio by default
                         audio_stream = input_stream.audio
                         output_params['c:a'] = 'aac' # Specify audio codec
                         output_params['b:a'] = '192k' # Specify audio bitrate


                    # Combine streams for output
                    if audio_stream:
                        stream = ffmpeg.output(input_stream.video, audio_stream, output_path, **output_params)
                    else:
                        stream = ffmpeg.output(input_stream.video, output_path, **output_params)


                    logger.debug(f"Running FFmpeg command for clipping: {stream.compile()}")
                    stream.run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
                    logger.info(f"Successfully created clip: {output_filename}")
                    processed_clips_paths.append(output_path)
                    clip_index += 1 # Increment only on successful clip creation

                except ffmpeg.Error as e:
                    stderr_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else "No stderr"
                    logger.error(f"FFmpeg error during clipping for {output_filename}: {stderr_output}")
                    # Decide whether to stop or continue on error
                    # break # Option 1: Stop processing this video entirely on error
                    # Option 2: Skip this clip and try the next one (might need start_time adjustment)
                    # For now, let's just log and continue the loop to try and get *some* clips
                    pass # Continue to next iteration

                # --- Update Start Time for Next Clip ---
                # Simple non-overlapping advance:
                start_time_sec = actual_start_time + clip_duration_sec
                # Add logic for 'overlap' if needed here, e.g.:
                # if overlap:
                #     overlap_amount = 5 # seconds
                #     start_time_sec = actual_start_time + clip_duration_sec - overlap_amount
                #     start_time_sec = max(0, start_time_sec) # Ensure non-negative
                # else:
                #     start_time_sec = actual_start_time + clip_duration_sec


            # --- Post-Processing Loop (Audio Extraction, Formatting, Enhance) ---
            final_clip_paths = []
            for clip_path in processed_clips_paths:
                 current_path = clip_path # Start with the clipped path
                 path_to_use_for_next_step = current_path # Path to input for next filter

                 try:
                    # --- Audio Extraction ---
                    if extract_audio:
                        extracted_audio_path = self._extract_audio(path_to_use_for_next_step)
                        if extracted_audio_path: logger.info(f"Extracted audio for {os.path.basename(clip_path)}")
                        # Note: Extraction doesn't change the video path for subsequent steps

                    # --- Formatting (Crop/Mirror) ---
                    formatted_path = None
                    if vertical_crop or mirror:
                         formatted_path = self._format_video(path_to_use_for_next_step, vertical_crop, mirror)
                         if formatted_path:
                             logger.info(f"Formatted video: {os.path.basename(formatted_path)}")
                             path_to_use_for_next_step = formatted_path # Use formatted output for enhance
                         else:
                             logger.warning(f"Formatting failed for {os.path.basename(current_path)}")


                    # --- Enhancement ---
                    enhanced_path = None
                    if enhance:
                        enhanced_path = self._enhance_video(path_to_use_for_next_step)
                        if enhanced_path:
                            logger.info(f"Enhanced video: {os.path.basename(enhanced_path)}")
                            # Decide final path: if enhanced, use it, otherwise use formatted or original clip
                            current_path = enhanced_path
                        else:
                            logger.warning(f"Enhancement failed for {os.path.basename(path_to_use_for_next_step)}")
                            # If enhance failed, use the previously processed path (formatted or original clip)
                            current_path = path_to_use_for_next_step
                    elif formatted_path: # If no enhance but formatting was done
                         current_path = formatted_path


                    # --- Add the final resulting path ---
                    final_clip_paths.append(current_path)

                    # --- Optional Cleanup: Delete intermediate files ---
                    # Be careful with this! Only delete if you're sure.
                    # files_to_delete = [clip_path, formatted_path, path_to_use_for_next_step]
                    # for f_path in files_to_delete:
                    #     if f_path and f_path != current_path and os.path.exists(f_path):
                    #         try:
                    #             os.remove(f_path)
                    #             logger.debug(f"Deleted intermediate file: {f_path}")
                    #         except OSError as e:
                    #             logger.warning(f"Could not delete intermediate file {f_path}: {e}")


                 except Exception as post_e:
                     logger.error(f"Error during post-processing for {os.path.basename(clip_path)}: {post_e}")
                     # Decide whether to keep the original clip path if post-processing fails
                     if os.path.exists(clip_path):
                          final_clip_paths.append(clip_path) # Keep original if post-processing fails catastrophically

            logger.info(f"--- Finished processing for: {os.path.basename(video_path)}. Final clips: {len(final_clip_paths)} ---")
            return final_clip_paths


        except FFmpegNotFoundError as e:
             logger.error(f"FFmpeg not found during processing: {e}")
             raise # Re-raise critical error
        except FileNotFoundError as e:
             logger.error(f"Input video file not found: {e}")
             return [] # Return empty if input file not found
        except ValueError as e: # Catch validation errors
             logger.error(f"Input validation error: {e}")
             return []
        except Exception as e:
            logger.error(f"Unexpected error processing {video_path}: {e}")
            import traceback
            traceback.print_exc() # Log full traceback
            # Decide if VideoProcessingError should be raised for unexpected errors
            # raise VideoProcessingError(f"Video processing failed unexpectedly: {e}")
            return [] # Return empty list on failure


    def _run_ffmpeg_command(self, stream, operation_name="FFmpeg operation"):
        """Helper to run FFmpeg command and log stderr on error."""
        try:
            logger.debug(f"Running command for {operation_name}: {stream.compile()}")
            stdout, stderr = stream.run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
            # Log stdout/stderr even on success if needed for debugging
            # logger.debug(f"{operation_name} stdout: {stdout.decode('utf-8', errors='replace')}")
            # logger.debug(f"{operation_name} stderr: {stderr.decode('utf-8', errors='replace')}")
            return True # Indicate success
        except ffmpeg.Error as e:
            stderr_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else "No stderr"
            logger.error(f"FFmpeg error during {operation_name}: {stderr_output}")
            return False # Indicate failure

    def _remove_audio(self, clip_path: str):
        """Removes audio from a video clip, creating a new file."""
        if not os.path.isfile(clip_path): return None
        output_path = clip_path.replace(".mp4", "_no_audio.mp4")
        logger.info(f"Removing audio from {os.path.basename(clip_path)} -> {os.path.basename(output_path)}")
        stream = ffmpeg.input(clip_path).output(output_path, an=None, c='copy') # Copy video stream
        if self._run_ffmpeg_command(stream, "Remove Audio"):
            return output_path
        return None

    def _extract_audio(self, clip_path: str):
        """Extracts audio from a video clip to an MP3 file."""
        if not os.path.isfile(clip_path): return None
        audio_output = clip_path.replace(".mp4", ".mp3")
        logger.info(f"Extracting audio from {os.path.basename(clip_path)} -> {os.path.basename(audio_output)}")
        stream = ffmpeg.input(clip_path).output(audio_output, format="mp3", acodec='libmp3lame', q='a:2') # Good quality MP3
        if self._run_ffmpeg_command(stream, "Extract Audio"):
             return audio_output
        return None

    def _enhance_video(self, clip_path: str):
        """Applies basic enhancement filters to a video clip."""
        if not os.path.isfile(clip_path): return None
        output_path = clip_path.replace(".mp4", "_enhanced.mp4")
        logger.info(f"Enhancing {os.path.basename(clip_path)} -> {os.path.basename(output_path)}")
        stream = ffmpeg.input(clip_path).output(
            output_path,
            vf="eq=contrast=1.1:brightness=0.02:saturation=1.1", # Adjusted values slightly
            c='copy', # Copy audio stream if present
            preset='medium', crf=23 # Re-encode video with enhancement
        )
        if self._run_ffmpeg_command(stream, "Enhance Video"):
            return output_path
        return None


    def _format_video(self, clip_path: str, vertical_crop: bool, mirror: bool):
        """Applies crop and/or mirror filters to a video clip."""
        if not os.path.isfile(clip_path): return None

        filters = []
        op_name = [] # Build operation name for logging
        if vertical_crop:
            filters.append("crop=ih*9/16:ih") # Crop to 9:16 based on input height
            op_name.append("Crop")
        if mirror:
            filters.append("hflip")
            op_name.append("Mirror")

        if not filters: # No formatting needed
            return None # Return None, indicating no new file was created

        output_suffix = "_formatted.mp4" # Consistent suffix
        output_path = clip_path.replace(".mp4", output_suffix)
        operation_desc = "+".join(op_name)
        logger.info(f"Formatting ({operation_desc}) {os.path.basename(clip_path)} -> {os.path.basename(output_path)}")

        stream = ffmpeg.input(clip_path).output(
            output_path,
            vf=",".join(filters),
            c='copy', # Copy audio stream if present
            preset='medium', crf=23 # Re-encode video with filter
        )
        if self._run_ffmpeg_command(stream, f"Format Video ({operation_desc})"):
            return output_path
        return None