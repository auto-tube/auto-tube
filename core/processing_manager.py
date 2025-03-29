# core/processing_manager.py
import threading
import time
import os
import traceback
from typing import Callable, List, Dict, Any, Optional

# Import utility functions and classes - use try-except for robustness
try:
    from utils.video_processor import VideoProcessor, FFmpegNotFoundError, VideoProcessingError
    from utils.subtitle_utils import generate_ass_file_with_style # For AI Short ASS generation
    from utils.tts_utils import generate_polly_tts_and_marks      # For Polly TTS call
    from utils.helpers import get_media_duration, prepare_background_video, combine_ai_short_elements # General helpers
    UTILS_AVAILABLE = True
except ImportError as import_error:
    print(f"ERROR [ProcessingManager]: Failed to import utility modules: {import_error}")
    print("Processing functions will likely fail. Ensure utils package is correct.")
    UTILS_AVAILABLE = False
    # Define dummy classes/functions if imports fail, so manager itself doesn't crash on load
    class VideoProcessor: pass
    class FFmpegNotFoundError(Exception): pass
    class VideoProcessingError(Exception): pass
    def generate_ass_file_with_style(*args, **kwargs): print("ERROR: subtitle_utils not loaded"); return False
    def generate_polly_tts_and_marks(*args, **kwargs): print("ERROR: tts_utils not loaded"); return None, None
    def get_media_duration(*args, **kwargs): print("ERROR: helpers not loaded"); return 0.0
    def prepare_background_video(*args, **kwargs): print("ERROR: helpers not loaded"); return False
    def combine_ai_short_elements(*args, **kwargs): print("ERROR: helpers not loaded"); return False


# Define Callback Types (for type hinting - helps readability)
ProgressCallback = Callable[[int, int, float], None] # index, total, start_time
StatusCallback = Callable[[str], None]
CompletionCallback = Callable[[str, int, int, int], None] # process_type, processed, errors, total

# --- Clipping Queue Processing Function ---

def run_clipping_queue(video_queue: List[str], output_path: str, options: Dict[str, Any],
                       progress_callback: ProgressCallback, status_callback: StatusCallback,
                       completion_callback: CompletionCallback, processing_state: Dict[str, bool]):
    """
    Processes videos in the queue for clipping. Designed to run in a thread.

    Args:
        video_queue: List of video file paths to process.
        output_path: Directory where clipped videos will be saved.
        options: Dictionary containing processing parameters from the GUI.
        progress_callback: Function to update GUI progress bar.
        status_callback: Function to update GUI status label.
        completion_callback: Function to call when processing finishes or stops.
        processing_state: Mutable dictionary {'active': bool} to check for stop requests.
    """
    if not UTILS_AVAILABLE:
        status_callback("Error: Core processing utilities failed to load.")
        completion_callback("Clipping", 0, len(video_queue), len(video_queue))
        processing_state['active'] = False
        return

    total_videos = len(video_queue)
    start_time = time.time()
    processed_count = 0
    error_count = 0
    video_processor = None

    status_callback("Status: Initializing clipping process...")
    try:
        # Initialize VideoProcessor - raises FFmpegNotFoundError if ffmpeg is missing
        print(f"CORE CLIP: Initializing VideoProcessor (Output: {output_path})")
        video_processor = VideoProcessor(output_path) # From utils.video_processor
        print("CORE CLIP: VideoProcessor Initialized.")
    except (FFmpegNotFoundError, ValueError) as e: # Catch specific init errors
         status_callback(f"Error: {e}")
         completion_callback("Clipping", 0, total_videos, total_videos) # All failed
         processing_state['active'] = False # Update shared state
         return
    except Exception as e: # Catch unexpected init errors
        status_callback(f"Error: Could not initialize Video Processor: {e}")
        traceback.print_exc()
        completion_callback("Clipping", 0, total_videos, total_videos) # All failed
        processing_state['active'] = False # Update shared state
        return

    # --- Main Processing Loop ---
    for index, file_path in enumerate(video_queue):
        # Check stop flag before processing each video
        if not processing_state.get('active', True):
             print("CORE CLIP: Stop signal received during queue processing.")
             break # Exit the loop

        current_video_basename = os.path.basename(file_path)
        try:
            status_text = f"Clipping {index + 1}/{total_videos}: {current_video_basename}"
            status_callback(status_text) # Call GUI update function via callback
            print(f"CORE CLIP: Processing: {file_path}")

            # Ensure video_processor is valid (should be from above)
            if not video_processor:
                 raise RuntimeError("VideoProcessor instance is not valid.")

            # Call the core video processing method from video_processor.py
            processed_clips = video_processor.process_video(file_path, **options)

            if isinstance(processed_clips, list) and processed_clips:
                # Successfully processed this video (at least one clip was made)
                processed_count += 1
                print(f"CORE CLIP: Successfully processed {current_video_basename}.")
            else:
                # video_processor.process_video returned empty list or None, indicating failure for this video
                error_count += 1
                print(f"CORE CLIP: Processing failed for {current_video_basename} (check video_processor logs).")
                status_callback(f"Error during clipping: {current_video_basename}") # Update status

            progress_callback(index, total_videos, start_time) # Call GUI progress update

        except (VideoProcessingError, FileNotFoundError, ValueError) as e:
             # Catch specific, potentially recoverable errors for this video
             error_count += 1
             error_msg = f"ERROR clipping {current_video_basename}"
             print(error_msg + f": {type(e).__name__} - {e}")
             status_callback(f"Error on: {current_video_basename} - {type(e).__name__}")
             # Continue to the next video in the queue
        except Exception as e:
            # Catch unexpected errors during a specific video's processing
            error_count += 1
            error_msg = f"CRITICAL UNEXPECTED ERROR clipping {current_video_basename}"
            print(error_msg + ":")
            traceback.print_exc() # Print full stack trace
            status_callback(f"Critical Error on: {current_video_basename}! Check console.")
            # Continue to the next video

    # --- Loop Finished or Stopped ---
    was_stopped = not processing_state.get('active', True) # Check if stop was the reason loop ended
    processing_state['active'] = False # Ensure flag is off after loop/break
    completion_callback("Clipping", processed_count, error_count, total_videos) # Call completion callback
    print(f"CORE CLIP: Clipping queue processing finished. Was stopped by user: {was_stopped}")


# --- AI Short Generation Processing Function ---

def run_ai_short_generation(script_text: str, background_video_path: str, final_output_path: str,
                            temp_dir: str, ai_options: Dict[str, Any],
                            progress_callback: ProgressCallback, status_callback: StatusCallback,
                            completion_callback: CompletionCallback, processing_state: Dict[str, bool]):
    """
    Orchestrates the AI Short Generation process. Runs in a thread.

    Args:
        script_text: The text script for voiceover/subtitles.
        background_video_path: Path to the source video for visuals.
        final_output_path: Full path where the final .mp4 short should be saved.
        temp_dir: Directory to store intermediate files (voiceover, ASS, prepared video).
        ai_options: Dictionary containing AI parameters (voice, font size, etc.).
        progress_callback: Function to update GUI progress.
        status_callback: Function to update GUI status label.
        completion_callback: Function to call when finished.
        processing_state: Mutable dictionary {'active': bool} for stop checks.
    """
    if not UTILS_AVAILABLE:
        status_callback("Error: Core processing utilities failed to load.")
        completion_callback("AI Short Generation", 0, 1, 1) # 1 total item (the short), 1 error
        processing_state['active'] = False
        return

    start_time = time.time()
    processed_count = 0 # Will be 1 on full success
    error_count = 1 # Start assuming failure
    total_steps = 5 # Define number of major steps for progress reporting

    # Paths for intermediate files - ensure they are cleaned up
    voice_audio_path: Optional[str] = None
    temp_ass_file: Optional[str] = None
    prepared_video_path: Optional[str] = None

    try:
        # Ensure temp_dir exists
        if not os.path.isdir(temp_dir):
            try:
                os.makedirs(temp_dir, exist_ok=True)
            except OSError as e:
                raise ValueError(f"Could not create temporary directory: {temp_dir} - {e}")


        # Check for stop signal before starting each major step
        def check_stop():
            if not processing_state.get('active', True):
                raise InterruptedError("Stop requested by user.")

        # --- Step 1: TTS (Polly) ---
        check_stop()
        status_callback("Status: 1/5 Generating voiceover (AWS Polly)...")
        print("CORE AI: Calling Polly TTS function...")
        tts_result = generate_polly_tts_and_marks( # From utils.tts_utils
            script_text, temp_dir, ai_options.get('polly_voice', 'Joanna')
        )
        if tts_result is None:
            raise ValueError("TTS generation failed (check tts_utils logs/AWS setup).")
        voice_audio_path, parsed_speech_marks = tts_result
        if not voice_audio_path or not os.path.exists(voice_audio_path) or not parsed_speech_marks:
             raise ValueError("TTS generation succeeded but produced invalid output (missing audio or marks).")
        print(f"CORE AI: Generated voiceover: {voice_audio_path}")
        progress_callback(0, total_steps, start_time)

        # --- Step 2: Get Audio Duration ---
        check_stop()
        status_callback("Status: 2/5 Getting audio duration...")
        print("CORE AI: Getting audio duration...")
        audio_duration = get_media_duration(voice_audio_path) # From utils.helpers
        if audio_duration <= 0:
            raise ValueError(f"Could not determine valid voiceover duration for {voice_audio_path}.")
        print(f"CORE AI: Voiceover duration: {audio_duration:.3f}s")
        progress_callback(1, total_steps, start_time)

        # --- Step 3: Generate ASS File ---
        check_stop()
        status_callback("Status: 3/5 Generating subtitle file...")
        temp_ass_filename = f"temp_subs_{int(time.time())}_{random.randint(100,999)}.ass"
        temp_ass_file = os.path.join(temp_dir, temp_ass_filename)
        print(f"CORE AI: Creating temp ASS: {temp_ass_file}")
        ass_success = generate_ass_file_with_style( # From utils.subtitle_utils
            parsed_speech_marks=parsed_speech_marks,
            output_ass_path=temp_ass_file,
            font_size=ai_options.get('font_size', 24),
            # Pass other style args from ai_options here if implemented
        )
        if not ass_success:
            raise ValueError("Failed to generate ASS subtitle file (check subtitle_utils logs).")
        print("CORE AI: Temp ASS file created.")
        progress_callback(2, total_steps, start_time)

        # --- Step 4: Prepare Background Video ---
        check_stop()
        status_callback("Status: 4/5 Preparing background video...")
        prepared_video_path = os.path.join(temp_dir, f"prep_video_{int(time.time())}.mp4")
        print(f"CORE AI: Preparing background video -> {prepared_video_path}")
        prep_success = prepare_background_video(background_video_path, prepared_video_path, audio_duration) # From utils.helpers
        if not prep_success:
             raise ValueError("Failed to prepare background video (check helpers logs).")
        print("CORE AI: Background video prepared.")
        progress_callback(3, total_steps, start_time)

        # --- Step 5: Final FFmpeg Composition ---
        check_stop()
        status_callback("Status: 5/5 Combining final video...")
        print("CORE AI: Combining final elements...")
        # Pass optional background music path if added to ai_options
        bg_music = ai_options.get('background_music_path', None)
        music_vol = ai_options.get('music_volume', 0.1)
        combine_success = combine_ai_short_elements( # From utils.helpers
            video_path=prepared_video_path,
            audio_path=voice_audio_path,
            ass_path=temp_ass_file,
            output_path=final_output_path, # The final desired output path
            bg_music_path=bg_music,
            music_volume=music_vol
        )
        if not combine_success:
             raise ValueError("Final FFmpeg composition failed (check helpers logs).")
        print("CORE AI: Final combination successful.")
        progress_callback(4, total_steps, start_time) # Step 5 complete

        # If all steps succeeded
        processed_count = 1
        error_count = 0 # Reset error count
        status_callback("Status: AI Short Generation Successful!")
        print("CORE AI: Process completed successfully.")

    except InterruptedError:
         print("CORE AI: Stop signal received during AI short generation.")
         status_callback("Status: AI Short Generation Stopped.")
         # Keep current processed/error counts (likely 0 processed, 1 error)
    except (FFmpegNotFoundError, ValueError, FileNotFoundError) as e:
         error_msg = f"ERROR generating AI Short: {type(e).__name__} - {e}"
         print(error_msg)
         status_callback(f"Error: {e}")
         traceback.print_exc()
         # error_count remains 1
    except Exception as e:
        error_msg = f"CRITICAL UNEXPECTED ERROR generating AI Short"
        print(error_msg + ":")
        traceback.print_exc()
        status_callback("Critical Error! Check console.")
        # error_count remains 1
    finally:
        # --- Cleanup ---
        files_to_clean = [temp_ass_file, voice_audio_path, prepared_video_path]
        for f_path in files_to_clean:
            if f_path and os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    print(f"CORE AI: Removed temporary file: {f_path}")
                except OSError as e_clean:
                    print(f"CORE AI: Error removing temporary file {f_path}: {e_clean}")
        # --- Signal Completion ---
        was_stopped = not processing_state.get('active', True)
        processing_state['active'] = False # Ensure flag is off
        # Use process_type="AI Short Generation" for the callback
        completion_callback("AI Short Generation", processed_count, error_count, 1) # Total items = 1 short
        print(f"CORE AI: AI Short generation finished. Was stopped by user: {was_stopped}")