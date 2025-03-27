import os
import ffmpeg
from typing import Optional, Union

def enhance_video(
    video_path: str, 
    contrast: float = 1.2, 
    brightness: float = 0.03, 
    sharpness: float = 0.8,
    output_path: Optional[str] = None
) -> str:
    """
    Automatically enhances video quality by adjusting contrast, brightness, and sharpness.

    Args:
        video_path (str): Path to the input video file.
        contrast (float, optional): Contrast enhancement factor. Defaults to 1.2.
        brightness (float, optional): Brightness adjustment. Defaults to 0.03.
        sharpness (float, optional): Sharpness enhancement factor. Defaults to 0.8.
        output_path (str, optional): Custom output file path. 
                                     If None, appends '_enhanced' to original filename.

    Returns:
        str: Path to the enhanced video file.

    Raises:
        FileNotFoundError: If the input video file does not exist.
        ffmpeg.Error: If there are issues with video processing.
    """
    # Validate input video file
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Determine output file path
    if output_path is None:
        base, ext = os.path.splitext(video_path)
        output_path = f"{base}_enhanced{ext}"

    try:
        # Apply video enhancement using FFmpeg
        (
            ffmpeg
            .input(video_path)
            .filter('eq', contrast=contrast, brightness=brightness, sharpness=sharpness)
            .output(output_path)
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        print(f"Error during video enhancement: {e.stderr.decode()}")
        raise

    return output_path

# Optional: Predefined enhancement presets
ENHANCEMENT_PRESETS = {
    'mild': {'contrast': 1.1, 'brightness': 0.02, 'sharpness': 0.5},
    'standard': {'contrast': 1.2, 'brightness': 0.03, 'sharpness': 0.8},
    'aggressive': {'contrast': 1.4, 'brightness': 0.05, 'sharpness': 1.0}
}

def enhance_video_with_preset(
    video_path: str, 
    preset: str = 'standard'
) -> str:
    """
    Enhance video using predefined enhancement presets.

    Args:
        video_path (str): Path to the input video file.
        preset (str, optional): Enhancement preset. 
                                Choices: 'mild', 'standard', 'aggressive'. 
                                Defaults to 'standard'.

    Returns:
        str: Path to the enhanced video file.
    """
    if preset not in ENHANCEMENT_PRESETS:
        raise ValueError(f"Invalid preset. Choose from {list(ENHANCEMENT_PRESETS.keys())}")
    
    preset_params = ENHANCEMENT_PRESETS[preset]
    return enhance_video(video_path, **preset_params)