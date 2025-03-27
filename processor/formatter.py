import os
import ffmpeg
from typing import Optional, List, Union

def format_video(
    video_path: str, 
    resize: bool = False, 
    vertical_crop: bool = False, 
    mirror: bool = False, 
    speed_ramp: Optional[float] = None,
    output_path: Optional[str] = None
) -> str:
    """
    Applies multiple video formatting operations using FFmpeg.

    Args:
        video_path (str): Path to the input video file.
        resize (bool, optional): Resize video to vertical format (1080x1920). Defaults to False.
        vertical_crop (bool, optional): Crop video to vertical aspect ratio. Defaults to False.
        mirror (bool, optional): Horizontally flip the video. Defaults to False.
        speed_ramp (float, optional): Speed multiplier for video. Defaults to None.
        output_path (str, optional): Custom output file path.

    Returns:
        str: Path to the formatted video file.

    Raises:
        FileNotFoundError: If the input video file does not exist.
        ValueError: If multiple size-altering operations are requested.
    """
    # Validate input video file
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Prepare filters
    filters: List[str] = []

    # Size and crop handling
    if resize and vertical_crop:
        raise ValueError("Cannot apply both resize and crop simultaneously.")
    
    if resize:
        filters.append("scale=1080:1920")
    elif vertical_crop:
        filters.append("crop=1080:1920")

    # Mirror operation
    if mirror:
        filters.append("hflip")

    # Speed ramping
    if speed_ramp is not None:
        if speed_ramp <= 0:
            raise ValueError("Speed multiplier must be a positive number.")
        filters.append(f"setpts={1/speed_ramp}*PTS")

    # Determine output path
    if output_path is None:
        base, ext = os.path.splitext(video_path)
        output_path = f"{base}_formatted{ext}"

    try:
        # Apply video formatting
        (
            ffmpeg
            .input(video_path)
            .filter(','.join(filters) if filters else None)
            .output(output_path)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        print(f"Error during video formatting: {e.stderr.decode()}")
        raise

    return output_path

# Predefined formatting presets
FORMATTING_PRESETS = {
    'vertical_tiktok': {
        'resize': True,
        'mirror': False,
        'speed_ramp': 1.25
    },
    'instagram_reels': {
        'vertical_crop': True,
        'mirror': False,
        'speed_ramp': 1.0
    },
    'quick_edit': {
        'speed_ramp': 1.5,
        'mirror': True
    }
}

def format_video_with_preset(
    video_path: str, 
    preset: str = 'vertical_tiktok'
) -> str:
    """
    Format video using predefined preset configurations.

    Args:
        video_path (str): Path to the input video file.
        preset (str, optional): Formatting preset. 
                                Choices: 'vertical_tiktok', 'instagram_reels', 'quick_edit'. 
                                Defaults to 'vertical_tiktok'.

    Returns:
        str: Path to the formatted video file.
    """
    if preset not in FORMATTING_PRESETS:
        raise ValueError(f"Invalid preset. Choose from {list(FORMATTING_PRESETS.keys())}")
    
    preset_params = FORMATTING_PRESETS[preset]
    return format_video(video_path, **preset_params)