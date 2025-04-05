# core/processing_manager.py
import threading
import time
import os
import traceback
from typing import Callable, List, Dict, Any, Optional
import random # Added for temp filenames in AI Short Gen

# --- Import utility functions and classes ---
# Use try-except for robustness, especially during development/setup
utils_loaded = False
video_processor_available = False
tts_available = False
sub_utils_available = False
helpers_available = False
ai_utils_available = False
try:
    from utils.video_processor import VideoProcessor, FFmpegNotFoundError, VideoProcessingError
    video_processor_available = True
    from utils.subtitle_utils import generate_ass_file_with_style
    sub_utils_available = True
    from utils.tts_utils import generate_polly_tts_and_marks
    tts_available = True
    from utils.helpers import get_media_duration, prepare_background_video, combine_ai_short_elements
    helpers_available = True
    from utils.ai_utils import (generate_script_with_gemini,
                                generate_hashtags_with_gemini,
                                generate_tags_with_gemini,
                                generate_titles_with_gemini,
                                GeminiError)
    ai_utils_available = True

    utils_loaded = (video_processor_available and tts_available and
                    sub_utils_available and helpers_available and ai_utils_available)
    if utils_loaded: print("ProcessingManager: All required utility modules loaded.")
    else: print("ProcessingManager Warning: Not all utility modules loaded.")

except ImportError as import_error:
    print(f"ERROR [ProcessingManager]: Failed to import one or more utility modules: {import_error}")
    print("Processing functions might fail. Ensure utils package and contents are correct.")
    # --- CORRECTED DUMMY DEFINITIONS ---
    # Define dummy placeholders if imports fail
    if not video_processor_available:
        class VideoProcessor: pass
        class FFmpegNotFoundError(Exception): pass
        class VideoProcessingError(Exception): pass
    if not sub_utils_available:
        def generate_ass_file_with_style(*args, **kwargs):
            print("ERROR: subtitle_utils not loaded"); return False
    if not tts_available:
        def generate_polly_tts_and_marks(*args, **kwargs):
            print("ERROR: tts_utils not loaded"); return None, None
    if not helpers_available:
        def get_media_duration(*args, **kwargs): print("ERROR: helpers not loaded"); return 0.0
        def prepare_background_video(*args, **kwargs): print("ERROR: helpers not loaded"); return False
        def combine_ai_short_elements(*args, **kwargs): print("ERROR: helpers not loaded"); return False
    if not ai_utils_available:
        def generate_script_with_gemini(*args, **kwargs):
            print("ERROR: ai_utils not loaded"); raise ImportError("AI Utils not loaded")
        def generate_hashtags_with_gemini(*args, **kwargs):
            print("ERR: AI Utils not loaded"); return None
        def generate_tags_with_gemini(*args, **kwargs):
            print("ERR: AI Utils not loaded"); return None
        def generate_titles_with_gemini(*args, **kwargs):
            print("ERR: AI Utils not loaded"); return None
        class GeminiError(Exception): pass
    # --- END CORRECTION ---
# --- End Imports ---


# Define Callback Types (for type hinting - helps readability)
ProgressCallback = Callable[[int, int, float], None] # index, total, start_time
StatusCallback = Callable[[str], None]
# Pass processing_state dict back in completion callback for state management
ProcessingCompletionCallback = Callable[[str, int, int, int, Dict], None] # process_type, processed, errors, total, processing_state_dict
ScriptCompletionCallback = Callable[[Optional[str], Optional[Exception]], None]
MetadataCompletionCallback = Callable[[str, Optional[List[str]], Optional[Exception]], None] # type, result_list, error


# --- Clipping Queue Processing Function ---
def run_clipping_queue(video_queue: List[str], output_path: str, options: Dict[str, Any],
                       progress_callback: ProgressCallback, status_callback: StatusCallback,
                       completion_callback: ProcessingCompletionCallback, processing_state: Dict[str, bool]):
    """
    Processes videos in the queue for clipping. Runs in a thread.
    Uses callbacks for GUI updates and checks processing_state['active'] for stops.
    """
    if not utils_loaded or not video_processor_available:
        status_callback("Error: Video processing module failed to load.")
        completion_callback("Clipping", 0, len(video_queue), len(video_queue), processing_state)
        processing_state['active'] = False # Ensure state is updated
        return

    total_videos = len(video_queue)
    start_time = time.time()
    processed_count = 0
    error_count = 0
    video_processor: Optional[VideoProcessor] = None # Type hint

    status_callback("Status: Initializing clipping process...")
    try:
        # Initialize VideoProcessor - may raise FFmpegNotFoundError or ValueError
        print(f"CORE CLIP: Initializing VP (Output: {output_path})")
        video_processor = VideoProcessor(output_path) # From utils.video_processor
        print("CORE CLIP: VideoProcessor Initialized.")
    except (FFmpegNotFoundError, ValueError) as e:
         status_callback(f"Error: {e}")
         completion_callback("Clipping", 0, total_videos, total_videos, processing_state)
         processing_state['active'] = False
         return
    except Exception as e: # Catch unexpected init errors
        status_callback(f"Error: Could not initialize Video Processor: {e}")
        traceback.print_exc()
        completion_callback("Clipping", 0, total_videos, total_videos, processing_state)
        processing_state['active'] = False
        return

    # --- Main Clipping Loop ---
    for index, file_path in enumerate(video_queue):
        # Check stop flag before processing each video
        # Needs to access the 'active' key within the mutable dict
        if not processing_state.get('active', True):
             print("CORE CLIP: Stop signal received during queue processing.")
             break # Exit the loop

        current_video_basename = os.path.basename(file_path)
        try:
            status_text = f"Clipping {index + 1}/{total_videos}: {current_video_basename}"
            status_callback(status_text) # Call GUI update function via callback
            print(f"CORE CLIP: Processing: {file_path}")

            # Ensure video_processor is valid (should be from above init)
            if not video_processor:
                 raise RuntimeError("VideoProcessor instance is not valid.")

            # Call the core video processing method from video_processor.py
            # This method should contain its own detailed logging and error handling
            processed_clips = video_processor.process_video(file_path, **options)

            if isinstance(processed_clips, list) and processed_clips:
                # Successfully processed this video (at least one clip was made)
                processed_count += 1
                print(f"CORE CLIP: Successfully processed {current_video_basename}.")
            else:
                # video_processor.process_video returned empty list or None, indicating failure
                error_count += 1
                print(f"CORE CLIP: Processing failed for {current_video_basename} (check video_processor logs).")
                # Update status to reflect error for this specific file
                status_callback(f"Error during clipping: {current_video_basename}")

            progress_callback(index, total_videos, start_time) # Update progress based on index

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
    # Call the completion callback (which uses root.after to update GUI)
    completion_callback("Clipping", processed_count, error_count, total_videos, processing_state)
    print(f"CORE CLIP: Clipping queue processing finished. Was stopped by user: {was_stopped}")


# --- Gemini Script Generation Function ---
def run_gemini_script_generation(prompt: str, completion_callback: ScriptCompletionCallback):
    """
    Generates a script using Gemini in a background thread.

    Args:
        prompt: The user's input prompt (niche/idea).
        completion_callback: Function to call with (generated_script, error) upon completion.
    """
    if not utils_loaded or not ai_utils_available:
         completion_callback(None, ImportError("AI utility module (ai_utils) not loaded."))
         return

    print(f"CORE AI SCRIPT: Starting generation for prompt: '{prompt[:50]}...'")
    generated_script: Optional[str] = None
    error: Optional[Exception] = None

    try:
        # Call the actual Gemini generation function from utils.ai_utils
        # This function handles API key config internally or raises GeminiError
        generated_script = generate_script_with_gemini(prompt) # Max length default used

        if generated_script:
             print("CORE AI SCRIPT: Generation successful.")
        else:
             # Handle case where function returns None without explicit error
             # Or Gemini might return empty string for safety/other reasons
             error = GeminiError("Gemini returned no script content.")
             print("CORE AI SCRIPT: Generation returned empty script.")

    except GeminiError as ge: # Catch specific errors from ai_utils
        print(f"CORE AI SCRIPT: Gemini API Error: {ge}")
        error = ge
    except Exception as e: # Catch unexpected errors
        print(f"CORE AI SCRIPT: Unexpected error during generation: {e}")
        error = e
        traceback.print_exc()
    finally:
        # Call the GUI callback (which uses root.after)
        completion_callback(generated_script, error)
        print("CORE AI SCRIPT: Generation thread finished.")


# --- NEW Gemini Metadata Generation Function ---
def run_gemini_metadata_generation(metadata_type: str, context: str, count: int,
                                   completion_callback: MetadataCompletionCallback):
    """
    Generates hashtags, tags, or titles using Gemini in a background thread.

    Args:
        metadata_type (str): 'hashtags', 'tags', or 'titles'.
        context (str): The video topic/description provided by the user.
        count (int): The desired number of items to generate.
        completion_callback: Function to call with (type, result_list, error).
    """
    if not utils_loaded or not ai_utils_available:
         completion_callback(metadata_type, None, ImportError("AI utility module (ai_utils) not loaded."))
         return

    print(f"CORE AI META: Starting '{metadata_type}' generation for context: '{context[:50]}...' (Count: {count})")
    result_list: Optional[List[str]] = None
    error: Optional[Exception] = None

    try:
        # Choose the correct generation function based on type
        if metadata_type == 'hashtags':
            result_list = generate_hashtags_with_gemini(context, count)
        elif metadata_type == 'tags':
            result_list = generate_tags_with_gemini(context, count)
        elif metadata_type == 'titles':
            result_list = generate_titles_with_gemini(context, count)
        else:
            # Should not happen if called correctly from GUI
            raise ValueError(f"Invalid metadata_type requested: {metadata_type}")

        if result_list is not None: # Check specifically for None, empty list is valid
             print(f"CORE AI META: '{metadata_type}' generation successful.")
        else:
             # Generation function returned None, likely indicating an error within it
             error = GeminiError(f"Gemini failed to generate {metadata_type} (check ai_utils logs).")
             print(f"CORE AI META: Generation failed for {metadata_type}.")

    except GeminiError as ge: # Catch specific errors from ai_utils
        print(f"CORE AI META: Gemini API Error ({metadata_type}): {ge}")
        error = ge
    except ValueError as ve: # Catch invalid input errors (e.g., empty context)
         print(f"CORE AI META: Input error for {metadata_type}: {ve}")
         error = ve
    except Exception as e: # Catch unexpected errors
        print(f"CORE AI META: Unexpected error during {metadata_type} generation: {e}")
        error = e
        traceback.print_exc()
    finally:
        # Call the GUI callback with type, result (list or None), and any error
        completion_callback(metadata_type, result_list, error)
        print(f"CORE AI META: '{metadata_type}' generation thread finished.")


# --- AI Short Generation Processing Function ---
def run_ai_short_generation(script_text: str, background_video_path: str, final_output_path: str,
                            temp_dir: str, ai_options: Dict[str, Any],
                            progress_callback: ProgressCallback, status_callback: StatusCallback,
                            completion_callback: ProcessingCompletionCallback, processing_state: Dict[str, bool]):
    """
    Orchestrates the AI Short Generation process. Runs in a thread.
    Uses callbacks for GUI updates and checks processing_state['active'] for stops.
    """
    if not utils_loaded: # Check if all needed utils loaded
        status_callback("Error: Core processing or utility modules failed to load.")
        completion_callback("AI Short Generation", 0, 1, 1, processing_state) # 1 total item (the short), 1 error
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
        # Check stop flag function (defined locally for this function)
        def check_stop():
            if not processing_state.get('active', True):
                raise InterruptedError("Stop requested by user.")

        # Ensure temp_dir exists
        if not os.path.isdir(temp_dir):
            try:
                os.makedirs(temp_dir, exist_ok=True)
            except OSError as e:
                raise ValueError(f"Could not create temporary directory: {temp_dir} - {e}")

        # --- Step 1: TTS (Polly) ---
        check_stop()
        status_callback("Status: 1/5 Generating voiceover (AWS Polly)...")
        print("CORE AI: Calling Polly TTS function...")
        # This function needs to exist in tts_utils.py and handle errors internally or raise them
        tts_result = generate_polly_tts_and_marks( # From utils.tts_utils
            script_text, temp_dir, ai_options.get('polly_voice', 'Joanna')
        )
        # Check if TTS succeeded and returned valid data
        if tts_result is None or tts_result[0] is None or tts_result[1] is None:
            raise ValueError("TTS generation failed or returned invalid data (check tts_utils logs/AWS setup).")
        voice_audio_path, parsed_speech_marks = tts_result
        if not os.path.exists(voice_audio_path): # Double check file exists
             raise FileNotFoundError(f"TTS audio file path returned but file not found: {voice_audio_path}")
        print(f"CORE AI: Generated voiceover: {voice_audio_path}")
        progress_callback(0, total_steps, start_time) # Step 1 complete (index 0)

        # --- Step 2: Get Audio Duration ---
        check_stop()
        status_callback("Status: 2/5 Getting audio duration...")
        print("CORE AI: Getting audio duration...")
        audio_duration = get_media_duration(voice_audio_path) # From utils.helpers
        if audio_duration <= 0:
            raise ValueError(f"Could not determine valid voiceover duration ({audio_duration:.2f}s).")
        print(f"CORE AI: Voiceover duration: {audio_duration:.3f}s")
        progress_callback(1, total_steps, start_time) # Step 2 complete (index 1)

        # --- Step 3: Generate ASS File ---
        check_stop()
        status_callback("Status: 3/5 Generating subtitle file...")
        # Create unique filename for ASS file
        timestamp = int(time.time())
        random_id = random.randint(100,999)
        temp_ass_filename = f"temp_subs_{timestamp}_{random_id}.ass"
        temp_ass_file = os.path.join(temp_dir, temp_ass_filename)
        print(f"CORE AI: Creating temp ASS: {temp_ass_file}")
        ass_success = generate_ass_file_with_style( # From utils.subtitle_utils
            parsed_speech_marks=parsed_speech_marks,
            output_ass_path=temp_ass_file,
            font_size=ai_options.get('font_size', 24)
            # Pass other style args here
        )
        if not ass_success:
            raise ValueError("Failed to generate ASS subtitle file (check subtitle_utils logs).")
        print("CORE AI: Temp ASS file created.")
        progress_callback(2, total_steps, start_time) # Step 3 complete (index 2)

        # --- Step 4: Prepare Background Video ---
        check_stop()
        status_callback("Status: 4/5 Preparing background video...")
        prepared_video_path = os.path.join(temp_dir, f"prep_video_{timestamp}_{random_id}.mp4")
        print(f"CORE AI: Preparing background video -> {prepared_video_path}")
        prep_success = prepare_background_video(background_video_path, prepared_video_path, audio_duration) # From utils.helpers
        if not prep_success:
             raise ValueError("Failed to prepare background video (check helpers logs).")
        print("CORE AI: Background video prepared.")
        progress_callback(3, total_steps, start_time) # Step 4 complete (index 3)

        # --- Step 5: Final FFmpeg Composition ---
        check_stop()
        status_callback("Status: 5/5 Combining final video...")
        print("CORE AI: Combining final elements...")
        bg_music = ai_options.get('background_music_path', None) # Get optional music path
        music_vol = ai_options.get('music_volume', 0.1)        # Get optional music volume
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
        progress_callback(4, total_steps, start_time) # Step 5 complete (index 4)

        # If all steps succeeded
        processed_count = 1
        error_count = 0 # Reset error count
        status_callback("Status: AI Short Generation Successful!")
        print("CORE AI: Process completed successfully.")

    except InterruptedError: # Catch explicit stop request
         print("CORE AI: Stop signal received during AI short generation.")
         status_callback("Status: AI Short Generation Stopped.")
         # Keep current processed/error counts (likely 0 processed, 1 error)
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
        print(f"CORE AI: Cleaning up: {files_to_clean}")
        for f_path in files_to_clean:
            if f_path and os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    print(f"CORE AI: Removed temporary file: {os.path.basename(f_path)}")
                except OSError as e_clean:
                    # Log warning but don't stop the completion callback
                    print(f"CORE AI: Error removing temporary file {f_path}: {e_clean}")
        # --- Signal Completion via Callback ---
        was_stopped = not processing_state.get('active', True) # Check flag state
        processing_state['active'] = False # Ensure flag is off
        # Use process_type="AI Short Generation", total items = 1 short
        completion_callback("AI Short Generation", processed_count, error_count, 1, processing_state)
        print(f"CORE AI: AI Short generation finished. Was stopped by user: {was_stopped}")