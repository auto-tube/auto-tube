import ffmpeg
import cv2
import numpy as np
import os
import random
from typing import List, Optional
from utils.video_processor import setup_logging

logger = setup_logging()

def extract_clips(
    video_path: str, 
    clip_count: str = "all", 
    clip_length: str = "30-45", 
    overlap: bool = False, 
    scene_detect: bool = False, 
    output_folder: Optional[str] = None
) -> List[str]:
    """
    Extracts clips from a video file with optional scene detection and overlapping.
    
    Args:
        video_path (str): Path to the input video file.
        clip_count (str): Number of clips to extract. 'all' or a specific number.
        clip_length (str): Predefined range for clip length.
        overlap (bool): Whether to allow clip overlap.
        scene_detect (bool): Whether to use scene detection.
        output_folder (str, optional): Folder to save extracted clips.
    
    Returns:
        List[str]: Paths to extracted clip files.
    """
    # Validate input video
    if not os.path.exists(video_path):
        logger.error(f"Video file not found: {video_path}")
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Create output folder if not specified
    if output_folder is None:
        output_folder = os.path.join(os.path.dirname(video_path), "extracted_clips")
    os.makedirs(output_folder, exist_ok=True)

    # Define clip length ranges
    clip_length_range = {
        "30-45": (30, 45), 
        "60-105": (60, 105), 
        "120-180": (120, 180)
    }

    # Validate clip length input
    if clip_length not in clip_length_range:
        logger.error(f"Invalid clip length range: {clip_length}")
        raise ValueError(f"Invalid clip length range. Choose from {list(clip_length_range.keys())}")

    # Probe video duration
    try:
        probe = ffmpeg.probe(video_path)
        duration = int(float(probe["format"]["duration"]))
    except ffmpeg.Error as e:
        logger.error(f"Error probing video: {e}")
        raise

    # Determine number of clips
    min_length, max_length = clip_length_range[clip_length]
    num_clips = (duration // ((min_length + max_length) // 2)) if clip_count == "all" else int(clip_count)

    # Extract clips
    clips = []
    start_time = 0

    for _ in range(num_clips):
        # Determine clip duration
        clip_duration = random.randint(min_length, max_length)
        
        # Check if we've exceeded video duration
        if start_time + clip_duration > duration:
            break

        # Scene detection if enabled
        if scene_detect:
            start_time = detect_scenes(video_path, start_time)

        # Generate output filename
        output_file = os.path.join(
            output_folder, 
            f"{os.path.splitext(os.path.basename(video_path))[0]}_clip_{len(clips) + 1}.mp4"
        )

        # Extract clip using ffmpeg
        try:
            (
                ffmpeg
                .input(video_path, ss=start_time, t=clip_duration)
                .output(output_file)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            clips.append(output_file)
        except ffmpeg.Error as e:
            logger.error(f"Error extracting clip: {e.stderr.decode()}")
            continue

        # Update start time with optional overlap
        start_time += (clip_duration - 5) if overlap else (clip_duration + 5)

    logger.info(f"Extracted {len(clips)} clips from {video_path}")
    return clips

def detect_scenes(video_path: str, start_time: float, threshold: float = 5e6) -> float:
    """
    Detects the next scene transition using OpenCV.
    
    Args:
        video_path (str): Path to the video file.
        start_time (float): Starting time for scene detection.
        threshold (float): Threshold for scene change detection.
    
    Returns:
        float: Timestamp of detected scene change.
    """
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)

    prev_frame = None
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_frame is not None:
            diff = np.sum((gray - prev_frame) ** 2)
            if diff > threshold:
                scene_time = int(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000)
                cap.release()
                return scene_time

        prev_frame = gray

    cap.release()
    return start_time

# Type hints added
# Error handling improved
# Logging integrated
# More robust input validation
# Improved scene detection function