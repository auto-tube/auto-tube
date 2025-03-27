import ffmpeg
import os

def extract_audio(video_path):
    """
    Extracts audio from a video file.
    
    Args:
        video_path (str): Path to the input video file.
    
    Returns:
        str: Path to the extracted audio file.
    """
    # Ensure the input video file exists
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # Generate audio output filename
    audio_output = video_path.replace(".mp4", ".mp3")
    
    try:
        # Extract audio using ffmpeg
        (
            ffmpeg
            .input(video_path)
            .output(audio_output, format="mp3")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        print(f"An error occurred: {e.stderr.decode()}")
        raise
    
    return audio_output