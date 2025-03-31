# core/processing_manager.py
import threading
import time
import os
import traceback
from typing import Callable, List, Dict, Any, Optional

# --- Import utility functions and classes ---
# Use try-except for robust startup, especially if utils are complex
utils_loaded = False
video_processor_available = False
tts_available = False
sub_utils_available = False
helpers_available = False

try:
    from utils.video_processor import VideoProcessor, FFmpegNotFoundError, VideoProcessingError
    video_processor_available = True
    from utils.subtitle_utils import generate_ass_file_with_style
    sub_utils_available = True
    from utils.tts_utils import generate_polly_tts_and_marks
    tts_available = True
    from utils.helpers import get_media_duration, prepare_background_video, combine_ai_short_elements
    helpers_available = True
    utils_loaded = video_processor_available and tts_available and sub_utils_available and helpers_available
    print("ProcessingManager: All required utility modules loaded successfully.")
except ImportError as import_error:
    print(f"ERROR [ProcessingManager]: Failed to import one or more utility modules: {import_error}")
    print("Processing functions might fail. Ensure utils package and contents are correct.")
    # Define dummy placeholders if imports fail to prevent immediate crashes on load
    if not video_processor_available:
        class VideoProcessor: pass
        class FFmpegNotFoundError(Exception): pass
        class VideoProcessingError(Exception): pass
    if not sub_utils_available:
        def generate_ass_file_with_style(*args, **kwargs): print("ERROR: subtitle_utils not loaded"); return False
    if not tts_available:
        def generate_polly_tts_and_marks(*args, **kwargs): print("ERROR: tts_utils not loaded"); return None, None
    if not helpers_available:
        def get_media_duration(*args, **kwargs): print("ERROR: helpers not loaded"); return 0.0
        def prepare_background_video(*args, **kwargs): print("ERROR: helpers not loaded"); return False
        def combine_ai_short_elements(*args, **kwargs): print("ERROR: helpers not loaded"); return False
# --- End Imports ---


# Define Callback Types (for type hinting)
ProgressCallback = Callable[[int, int, float], None] # index, total, start_time
StatusCallback = Callable[[str], None]
CompletionCallback = Callable[[str, int, int, int, Dict], None] # process_type, processed, errors, total, processing_state_dict


# --- Clipping Queue Processing Function ---

def run_clipping_queue(video_queue: List[str], output_path: str, options: Dict[str, Any],
                       progress_callback: ProgressCallback, status_callback: StatusCallback,
                       completion_callback: CompletionCallback, processing_state: Dict[str, bool]):
    """
    Processes videos in the queue for clipping. Runs in a thread.
    Uses callbacks for GUI updates and checks processing_state['active'] for stops.
    """
    if not utils_loaded or not video_processor_available: # Check specific dependency
        status_callback("Error: Video processing module failed to load.")
        completion_callback("Clipping", 0, len(video_queue), len(video_queue), processing_state)
        processing_state['active'] = False
        return

    total_videos = len(video_queue)
    start_time = time.time()
    processed_count = 0
    error_count = 0
    video_processor: Optional[VideoProcessor] = None

    status_callback("Status: Initializing clipping process...")
    try:
        print(f"CORE CLIP: Initializing VP (Output: {output_path})")
        video_processor = VideoProcessor(output_path) # Initializes and checks FFmpeg
        print("CORE CLIP: VideoProcessor Initialized.")
    except (FFmpegNotFoundError, ValueError) as e:
         status_callback(f"Error: {e}")
         completion_callback("Clipping", 0, total_videos, total_videos, processing_state)
         processing_state['active'] = False
         return
    except Exception as e:
        status_callback(f"Error: Could not initialize Video Processor: {e}")
        traceback.print_exc()
        completion_callback("Clipping", 0, total_videos, total_videos, processing_state)
        processing_state['active'] = False
        return

    # --- Main Clipping Loop ---
    for index, file_path in enumerate(video_queue):
        if not processing_state.get('active', True):
             print("CORE CLIP: Stop signal received.")
             break # Exit loop if stop requested

        current_video_basename = os.path.basename(file_path)
        try:
            status_text = f"Clipping {index + 1}/{total_videos}: {current_video_basename}"
            status_callback(status_text)
            print(f"CORE CLIP: Processing: {file_path}")

            if not video_processor: raise RuntimeError("VideoProcessor instance invalid.")

            # Delegate actual processing to the VideoProcessor instance
            processed_clips = video_processor.process_video(file_path, **options)

            if isinstance(processed_clips, list) and processed_clips:
                processed_count += 1
                print(f"CORE CLIP: Successfully processed {current_video_basename}.")
            else:
                error_count += 1
                print(f"CORE CLIP: Processing failed or no clips generated for {current_video_basename}.")
                status_callback(f"Error during clipping: {current_video_basename}")

            progress_callback(index, total_videos, start_time) # Update progress

        except (VideoProcessingError, FileNotFoundError, ValueError) as e:
             error_count += 1
             print(f"ERROR clipping {current_video_basename}: {type(e).__name__} - {e}")
             status_callback(f"Error on: {current_video_basename} - {type(e).__name__}")
        except Exception as e:
            error_count += 1
            print(f"CRITICAL UNEXPECTED ERROR clipping {current_video_basename}:")
            traceback.print_exc()
            status_callback(f"Critical Error on: {current_video_basename}! Check console.")

    # --- Loop Finished or Stopped ---
    was_stopped = not processing_state.get('active', True)
    processing_state['active'] = False # Ensure flag is off
    completion_callback("Clipping", processed_count, error_count, total_videos, processing_state)
    print(f"CORE CLIP: Clipping queue finished. Was stopped: {was_stopped}")


# --- AI Short Generation Processing Function ---

def run_ai_short_generation(script_text: str, background_video_path: str, final_output_path: str,
                            temp_dir: str, ai_options: Dict[str, Any],
                            progress_callback: ProgressCallback, status_callback: StatusCallback,
                            completion_callback: CompletionCallback, processing_state: Dict[str, bool]):
    """
    Orchestrates the AI Short Generation process. Runs in a thread.
    Uses callbacks for GUI updates and checks processing_state['active'] for stops.
    """
    if not utils_loaded: # Check if all necessary utils loaded
        status_callback("Error: Core processing or utility modules failed to load.")
        completion_callback("AI Short Generation", 0, 1, 1, processing_state)
        processing_state['active'] = False
        return

    start_time = time.time()
    processed_count = 0
    error_count = 1 # Start assuming failure
    total_steps = 5 # TTS, Duration, ASS Gen, Video Prep, Combine

    # Intermediate file paths
    voice_audio_path: Optional[str] = None
    temp_ass_file: Optional[str] = None
    prepared_video_path: Optional[str] = None

    try:
        # Check stop flag function
        def check_stop():
            if not processing_state.get('active', True):
                raise InterruptedError("Stop requested by user.")

        # Ensure temp_dir exists
        if not os.path.isdir(temp_dir): os.makedirs(temp_dir, exist_ok=True)

        # --- Step 1: TTS (Polly) ---
        check_stop()
        status_callback("Status: 1/5 Generating voiceover (AWS Polly)...")
        print("CORE AI: Calling Polly TTS function...")
        tts_result = generate_polly_tts_and_marks( # From utils.tts_utils
            script_text, temp_dir, ai_options.get('polly_voice', 'Joanna')
        )
        if tts_result is None or tts_result[0] is None or tts_result[1] is None:
            raise ValueError("TTS generation failed or returned invalid data.")
        voice_audio_path, parsed_speech_marks = tts_result
        print(f"CORE AI: Generated voiceover: {voice_audio_path}")
        progress_callback(0, total_steps, start_time)

        # --- Step 2: Get Audio Duration ---
        check_stop()
        status_callback("Status: 2/5 Getting audio duration...")
        print("CORE AI: Getting audio duration...")
        audio_duration = get_media_duration(voice_audio_path) # From utils.helpers
        if audio_duration <= 0:
            raise ValueError(f"Could not determine valid voiceover duration ({audio_duration:.2f}s).")
        print(f"CORE AI: Voiceover duration: {audio_duration:.3f}s")
        progress_callback(1, total_steps, start_time)

        # --- Step 3: Generate ASS File ---
        check_stop()
        status_callback("Status: 3/5 Generating subtitle file...")
        timestamp = int(time.time())
        temp_ass_filename = f"temp_subs_{timestamp}.ass"
        temp_ass_file = os.path.join(temp_dir, temp_ass_filename)
        print(f"CORE AI: Creating temp ASS: {temp_ass_file}")
        ass_success = generate_ass_file_with_style( # From utils.subtitle_utils
            parsed_speech_marks=parsed_speech_marks,
            output_ass_path=temp_ass_file,
            font_size=ai_options.get('font_size', 24)
        )
        if not ass_success: raise ValueError("Failed to generate ASS subtitle file.")
        print("CORE AI: Temp ASS file created.")
        progress_callback(2, total_steps, start_time)

        # --- Step 4: Prepare Background Video ---
        check_stop()
        status_callback("Status: 4/5 Preparing background video...")
        prepared_video_path = os.path.join(temp_dir, f"prep_video_{timestamp}.mp4")
        print(f"CORE AI: Preparing background video -> {prepared_video_path}")
        prep_success = prepare_background_video(background_video_path, prepared_video_path, audio_duration) # From utils.helpers
        if not prep_success: raise ValueError("Failed to prepare background video.")
        print("CORE AI: Background video prepared.")
        progress_callback(3, total_steps, start_time)

        # --- Step 5: Final FFmpeg Composition ---
        check_stop()
        status_callback("Status: 5/5 Combining final video...")
        print("CORE AI: Combining final elements...")
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
        if not combine_success: raise ValueError("Final FFmpeg composition failed.")
        print("CORE AI: Final combination successful.")
        progress_callback(4, total_steps, start_time) # Step 5 complete

        # If all steps succeeded
        processed_count = 1
        error_count = 0
        status_callback("Status: AI Short Generation Successful!")
        print("CORE AI: Process completed successfully.")

    except InterruptedError: # Catch explicit stop request
         print("CORE AI: Stop signal received during AI short generation.")
         status_callback("Status: AI Short Generation Stopped.")
         # error_count remains 1, processed_count remains 0
    except (FFmpegNotFoundError, ValueError, FileNotFoundError, ConnectionError) as e: # Catch specific expected errors
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
        # --- Cleanup Intermediate Files ---
        files_to_clean = [temp_ass_file, voice_audio_path, prepared_video_path]
        print(f"CORE AI: Cleaning up temporary files: {files_to_clean}")
        for f_path in files_to_clean:
            if f_path and os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    print(f"CORE AI: Removed temporary file: {os.path.basename(f_path)}")
                except OSError as e_clean:
                    print(f"CORE AI: Error removing temp file {f_path}: {e_clean}")
        # --- Signal Completion via Callback ---
        was_stopped = not processing_state.get('active', True)
        processing_state['active'] = False # Ensure flag is off
        # Use process_type="AI Short Generation", total items = 1 short
        completion_callback("AI Short Generation", processed_count, error_count, 1, processing_state)
        print(f"CORE AI: AI Short generation finished. Was stopped: {was_stopped}")