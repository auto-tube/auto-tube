import os
import random
import cv2
import numpy as np
import ffmpeg
from typing import List, Optional, Tuple
from contextlib import contextmanager
from utils.logger_config import setup_logging
import scenedetect
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

    CLIP_LENGTH_RANGES = {
        "30-45": (30, 45),
        "60-105": (60, 105),
        "120-180": (120, 180)
    }

    def __init__(self, output_folder: str):
        """
        Initialize the VideoProcessor with output configuration.

        Args:
            output_folder (str): Directory where processed videos will be saved.
        """
        self.output_folder = output_folder
        os.makedirs(output_folder, exist_ok=True)
        self._check_ffmpeg()  # Ensure FFmpeg is available

    def _check_ffmpeg(self):
        """Check if FFmpeg is installed and accessible."""
        try:
            ffmpeg.probe("dummy.mp4")  # Probe a dummy file to check FFmpeg
        except FileNotFoundError:
            raise FFmpegNotFoundError("FFmpeg not found. Please ensure it's installed and in your system's PATH.")
        except Exception as e:
            raise FFmpegNotFoundError(f"FFmpeg check failed: {e}")

    @staticmethod
    def format_time(seconds: int) -> str:
        """
        Convert seconds to formatted time string (hh:mm:ss).

        Args:
            seconds (int): Total seconds to format.

        Returns:
            str: Formatted time string.
        """
        return f"{seconds // 3600:02}:{(seconds % 3600) // 60:02}:{seconds % 60:02}"

    def get_video_duration(self, video_path: str) -> int:
        """
        Retrieve the duration of a video in seconds.

        Args:
            video_path (str): Path to the video file.

        Returns:
            int: Video duration in seconds.
        """
        try:
            probe = ffmpeg.probe(self._quote_path(video_path))
            return int(float(probe["format"]["duration"]))
        except ffmpeg.Error as e:  # Catch ffmpeg.Error specifically
            logger.error(f"FFmpeg error probing video duration: {e}")
            raise VideoProcessingError(f"Could not determine video duration: {e}")
        except Exception as e:
            logger.error(f"Error probing video duration: {e}")
            raise VideoProcessingError(f"Could not determine video duration: {e}")

    def _get_clip_length_range(self, min_length: int, max_length: int) -> Tuple[int, int]:
        """
        Determine clip length range based on user input.

        Args:
            min_length (int): Minimum clip length.
            max_length (int): Maximum clip lengths.

        Returns:
            Tuple[int, int]: Minimum and maximum clip lengths.
        """
        return (min_length, max_length)

    def _determine_clip_count(self, clip_count: int, duration: int,
                               min_length: int, max_length: int) -> int:
        """
        Calculate number of clips based on video duration.

        Args:
            clip_count (int): Desired number of clips.
            duration (int): Total video duration.
            min_length (int): Minimum clip length.
            max_length (int): Maximum clip length.

        Returns:
            int: Number of clips to extract.
        """
        return clip_count

    def detect_scene_transition(self, video_path: str, start_time: float, threshold: float) -> float:
        """
        Detect scene transitions using scenedetect library.

        Args:
            video_path (str): Path to the video file.
            start_time (float): Starting time for scene detection (in seconds).
            threshold (float): Scene detection threshold.

        Returns:
            float: Timestamp of detected scene transition (in seconds), or start_time if no transition is found.
        """
        video_manager = VideoManager([video_path])
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))

        base_timecode = video_manager.get_base_timecode()

        try:
            video_manager.set_downscale_factor()
            video_manager.start(start_time=base_timecode + start_time) #start scene manager at appropriate timecode

            scene_manager.detect_scenes(frame_source=video_manager)

            scene_list = scene_manager.get_scene_list(base_timecode)

            if scene_list:
                # Return the start time of the *next* scene after the starting time.
                for scene in scene_list:
                  if scene[0].get_seconds() > start_time:
                    return scene[0].get_seconds()


        except Exception as e:
            logger.error(f"Error detecting scenes: {e}")

        finally:
            video_manager.release()

        return start_time  # Return original start_time if no scene is found


    @contextmanager
    def _video_capture(self, video_path: str, start_time: float):
        """
        Context manager for video capture to ensure proper resource handling.

        Args:
            video_path (str): Path to the video file.
            start_time (float): Starting time for video capture.

        Yields:
            cv2.VideoCapture: Video capture object.
        """
        cap = cv2.VideoCapture(self._quote_path(video_path))
        cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
        try:
            yield cap
        finally:
            cap.release()

    def _quote_path(self, path: str) -> str:
        """
        Safely quote file paths to handle special characters.

        Args:
            path (str): Original file path.

        Returns:
            str: Quoted file path.
        """
        return f'"{path}"'

    def process_video(
        self,
        video_path: str,
        clip_count: int = 3,
        min_clip_length: int = 30,
        max_clip_length: int = 45,
        overlap: bool = False,
        scene_detect: bool = False,
        scene_threshold: float = 30.0,
        remove_audio: bool = False,
        extract_audio: bool = False,
        vertical_crop: bool = False,
        mirror: bool = False,
        enhance: bool = False,
    ) -> List[str]:
        """
        Comprehensive video processing method.

        Args:
            video_path (str): Path to input video.
            clip_count (int): Number of clips to extract.
            min_clip_length (int): Min Length range for clips.
            max_clip_length (int): Max Length range for clips.
            overlap (bool): Whether clips should overlap.
            scene_detect (bool): Enable scene transition detection.
            scene_threshold (float): Threshold to use for scene detection.
            remove_audio (bool): Remove audio from clips.
            extract_audio (bool): Extract audio separately.
            vertical_crop (bool): Crop video vertically.
            mirror (bool): Mirror video horizontally.
            enhance (bool): Enhance video quality.

        Returns:
            List[str]: Paths to processed video clips.
        """
        try:
            duration = self.get_video_duration(video_path)
            min_length, max_length = self._get_clip_length_range(min_clip_length, max_clip_length)
            num_clips = self._determine_clip_count(clip_count, duration, min_length, max_length)

            processed_clips = []
            start_time = 0

            for _ in range(num_clips):
                clip_duration = random.randint(min_length, max_length)
                if start_time + clip_duration > duration:
                    break

                if scene_detect:
                    start_time = self.detect_scene_transition(video_path, start_time, scene_threshold) #Added scene_threshold

                output_filename = f"{os.path.basename(video_path).split('.')[0]}_clip_{len(processed_clips) + 1}.mp4"
                output_path = os.path.join(self.output_folder, output_filename)

                input_kwargs = {'ss': start_time, 't': clip_duration}
                output_kwargs = {}

                if remove_audio:
                    output_kwargs['an'] = None  # Remove audio

                video_stream = ffmpeg.input(self._quote_path(video_path), **input_kwargs)

                video_stream = video_stream.output(self._quote_path(output_path), **output_kwargs)

                try:
                    video_stream.run(overwrite_output=True)
                except ffmpeg.Error as e:
                    logger.error(f"FFmpeg error: {e.stderr.decode('utf8')}")
                    raise

                processed_clips.append(output_path)

                if overlap:
                  start_time += max(0, clip_duration - 5) # Ensure start_time is non-negative
                else:
                  start_time += clip_duration
            for clip in processed_clips:
                if remove_audio:
                    self._remove_audio(clip)
                if extract_audio:
                    self._extract_audio(clip)
                if enhance:
                    self._enhance_video(clip)
                if vertical_crop or mirror:
                    self._format_video(clip, vertical_crop, mirror, output_path)

            return processed_clips

        except Exception as e:
            logger.error(f"Error processing {video_path}: {e}")
            raise VideoProcessingError(f"Video processing failed: {e}")

    def _remove_audio(self, clip_path: str):
        """Remove audio from a video clip."""
        output_path = clip_path.replace(".mp4", "_no_audio.mp4")
        ffmpeg.input(self._quote_path(clip_path)).output(self._quote_path(output_path), an=None).run(overwrite_output=True)

    def _extract_audio(self, clip_path: str):
        """Extract audio from a video clip."""
        audio_output = clip_path.replace(".mp4", ".mp3")
        ffmpeg.input(self._quote_path(clip_path)).output(self._quote_path(audio_output), format="mp3").run(overwrite_output=True)

    def _enhance_video(self, clip_path: str):
        """Enhance video quality."""
        output_path = clip_path.replace(".mp4", "_enhanced.mp4")
        ffmpeg.input(self._quote_path(clip_path)).output(
            self._quote_path(output_path),
            vf="eq=contrast=1.2:brightness=0.03:sharpness=0.8"
        ).run(overwrite_output=True)

    def _format_video(self, clip_path: str, vertical_crop: bool, mirror: bool):
        """Apply video formatting."""
        filters = []
        if vertical_crop:
            filters.append("crop=1080:1920")
        if mirror:
            filters.append("hflip")

        output_path = clip_path.replace(".mp4", "_formatted.mp4")

        # Construct the filter string correctly
        if filters:
            ffmpeg.input(self._quote_path(clip_path)).output(
                self._quote_path(output_path),
                vf=",".join(filters)
            ).run(overwrite_output=True)
        else:
            # If no filters are needed, just copy the file
            ffmpeg.input(self._quote_path(clip_path)).output(self._quote_path(output_path),codec='copy').run(overwrite_output=True)