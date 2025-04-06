# core/processing_manager.py
import threading
import time
import os
import traceback
from typing import Callable, List, Dict, Any, Optional
import random # For temp filenames
import logging # Ensure logging is imported early for fallback

# --- Import utility functions and classes ---
# Use try-except for robustness, especially during development/setup
utils_loaded = False
video_processor_available = False
tts_available = False
sub_utils_available = False
helpers_available = False
ai_utils_available = False
logger_available = False
file_manager_available = False

try:
    # Attempt to import logger first
    from utils.logger_config import setup_logging
    logger = setup_logging() # Initialize logger early
    logger_available = True

    # Import other utilities
    from utils.video_processor import VideoProcessor, FFmpegNotFoundError, VideoProcessingError
    video_processor_available = True
    from utils.subtitle_utils import generate_ass_file_with_style
    sub_utils_available = True
    from utils.tts_utils import generate_polly_tts_and_marks
    tts_available = True
    # Import the new finder function and refactored helpers from helpers.py
    from utils.helpers import (find_ffmpeg_executables, get_media_duration,
                               prepare_background_video, combine_ai_short_elements)
    helpers_available = True
    from utils.ai_utils import (generate_script_with_gemini,
                                generate_hashtags_with_gemini,
                                generate_tags_with_gemini,
                                generate_titles_with_gemini,
                                GeminiError)
    ai_utils_available = True
    from utils.file_manager import FileOrganizer # Import organizer
    file_manager_available = True


    # Check if all core utilities loaded successfully
    utils_loaded = (video_processor_available and tts_available and
                    sub_utils_available and helpers_available and ai_utils_available and
                    logger_available and file_manager_available)
    if utils_loaded:
        logger.info("ProcessingManager: All required utility modules loaded.")
    else:
        missing = []
        if not video_processor_available: missing.append("video_processor")
        if not tts_available: missing.append("tts_utils")
        if not sub_utils_available: missing.append("subtitle_utils")
        if not helpers_available: missing.append("helpers")
        if not ai_utils_available: missing.append("ai_utils")
        if not file_manager_available: missing.append("file_manager")
        if not logger_available: missing.append("logger_config")
        logger.warning(f"ProcessingManager Warning: Not all utility modules loaded. Missing: {', '.join(missing)}")


except ImportError as import_error:
    err_msg = f"ERROR [ProcessingManager]: Failed to import one or more utility modules: {import_error}"
    # Use logger if available, otherwise print
    # Ensure logger exists even if import failed above
    if 'logger' not in globals() or not isinstance(logger, logging.Logger):
        # Basic fallback logger configuration if the main one failed
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logger = logging.getLogger('autotube_fallback')
        logger.critical(err_msg, exc_info=True) # Log the original error
    else:
        logger.critical(err_msg, exc_info=True)

    print("Processing functions might fail. Ensure utils package and contents are correct.")
    # --- Define dummy placeholders if imports fail ---

    if not video_processor_available:
        class VideoProcessor: pass
        class FFmpegNotFoundError(Exception): pass
        class VideoProcessingError(Exception): pass
    if not sub_utils_available:
        def generate_ass_file_with_style(*a, **kw): logger.error("subtitle_utils not loaded"); return False
    if not tts_available:
        def generate_polly_tts_and_marks(*a, **kw): logger.error("tts_utils not loaded"); return None, None
    if not helpers_available:
        def find_ffmpeg_executables(*a, **kw): logger.error("helpers not loaded"); return None, None
        def get_media_duration(*a, **kw): logger.error("helpers not loaded"); return 0.0
        def prepare_background_video(*a, **kw): logger.error("helpers not loaded"); return False
        def combine_ai_short_elements(*a, **kw): logger.error("helpers not loaded"); return False
    if not ai_utils_available:
        def generate_script_with_gemini(*a, **kw): logger.error("ai_utils not loaded"); raise ImportError("AI Utils not loaded")
        def generate_hashtags_with_gemini(*a, **kw): logger.error("ai_utils not loaded"); return None
        def generate_tags_with_gemini(*a, **kw): logger.error("ai_utils not loaded"); return None
        def generate_titles_with_gemini(*a, **kw): logger.error("ai_utils not loaded"); return None
        class GeminiError(Exception): pass
    if not file_manager_available:
        class FileOrganizer:
             def __init__(self, *args, **kwargs): pass # Fix dummy init signature
             def organize_output(self, *args, **kwargs): logger.error("FileOrganizer not loaded")
    # --- End Dummies ---
# --- End Imports ---


# Define Callback Types (Keep as before)
ProgressCallback = Callable[[int, int, float], None]
StatusCallback = Callable[[str], None]
ProcessingCompletionCallback = Callable[[str, int, int, int, Dict], None]
ScriptCompletionCallback = Callable[[Optional[str], Optional[Exception]], None]
MetadataCompletionCallback = Callable[[str, Optional[List[str]], Optional[Exception]], None]


# --- Clipping Queue Processing Function (MODIFIED WITH FIX) ---
def run_clipping_queue(video_queue: List[str], output_path: str, options: Dict[str, Any],
                       progress_callback: ProgressCallback, status_callback: StatusCallback,
                       completion_callback: ProcessingCompletionCallback, processing_state: Dict[str, bool]):
    """
    Processes videos in the queue for clipping. Runs in a thread.
    Uses callbacks for GUI updates and checks processing_state['active'] for stops.
    Finds FFmpeg/FFprobe paths, passes them to VideoProcessor, and organizes output.
    """
    logger.info("--- Starting Clipping Queue Processing Thread ---")
    start_time = time.time() # Define start time early
    # --- Find FFmpeg/FFprobe FIRST ---
    ffmpeg_exec, ffprobe_exec = None, None
    # Check dependencies required for this function
    if not video_processor_available or not helpers_available:
         missing_deps = []
         if not video_processor_available: missing_deps.append("VideoProcessor")
         if not helpers_available: missing_deps.append("Helpers (FFmpeg finder)")
         err_msg = f"Error: Cannot start clipping. Missing dependencies: {', '.join(missing_deps)}"
         logger.critical(err_msg)
         status_callback(err_msg)
         completion_callback("Clipping", 0, len(video_queue), len(video_queue), processing_state)
         processing_state['active'] = False
         return

    # Dependencies seem loaded, try finding executables
    try:
        # Pass config paths from options if provided (though GUI now handles this)
        ffmpeg_exec, ffprobe_exec = find_ffmpeg_executables() # Call without arguments
        if not ffmpeg_exec or not ffprobe_exec:
            # find_ffmpeg_executables logs details, raise specific error here
            raise FFmpegNotFoundError("FFmpeg or FFprobe executable not found. Check system PATH, FFMPEG_PATH/FFPROBE_PATH env vars, or configure paths in Settings.")
    except FFmpegNotFoundError as e:
         logger.critical(f"FFmpeg/FFprobe Check Failed: {e}")
         status_callback(f"Error: {e}")
         completion_callback("Clipping", 0, len(video_queue), len(video_queue), processing_state)
         processing_state['active'] = False
         return
    except Exception as e:
         logger.critical(f"Unexpected error finding FFmpeg/FFprobe: {e}", exc_info=True)
         status_callback("Error: Unexpected error finding FFmpeg/FFprobe.")
         completion_callback("Clipping", 0, len(video_queue), len(video_queue), processing_state)
         processing_state['active'] = False
         return
    logger.info(f"Clipping Queue: Using FFmpeg='{ffmpeg_exec}', FFprobe='{ffprobe_exec}'")
    # --- End FFmpeg Find ---

    total_videos = len(video_queue)
    processed_count = 0
    error_count = 0
    video_processor: Optional[VideoProcessor] = None
    final_clip_list_all_videos = [] # Store all final paths for organizer
    current_video_index = -1 # Keep track of last attempted index

    # --- Get options NOT meant for video_processor.process_video ---
    # Identify options used only by the manager or other parts of the workflow
    manager_specific_options = ['organize_output']
    # Retrieve the value now for clarity, will be used later
    organize_files = options.get("organize_output", False)

    # Create a filtered dictionary containing only the arguments
    # intended for the video_processor.process_video method.
    video_processing_args = {
        key: value for key, value in options.items()
        if key not in manager_specific_options
    }
    logger.debug(f"CORE CLIP: Filtered options for process_video: {video_processing_args}")

    status_callback("Status: Initializing clipping process...")
    try:
        # Initialize VideoProcessor - PASS THE FOUND PATHS
        logger.info(f"CORE CLIP: Initializing VideoProcessor (Output: {output_path})")
        video_processor = VideoProcessor(output_path, ffmpeg_path=ffmpeg_exec, ffprobe_path=ffprobe_exec, logger=logger) # Pass logger
        logger.info("CORE CLIP: VideoProcessor Initialized successfully.")

    except (FFmpegNotFoundError, ValueError) as e: # Catch init errors
         logger.critical(f"Failed to initialize VideoProcessor: {e}")
         status_callback(f"Error: {e}")
         completion_callback("Clipping", 0, total_videos, total_videos, processing_state)
         processing_state['active'] = False
         return
    except Exception as e: # Catch unexpected init errors
        logger.critical(f"Unexpected error initializing VideoProcessor: {e}", exc_info=True)
        status_callback(f"Error: Could not initialize Video Processor: {e}")
        completion_callback("Clipping", 0, total_videos, total_videos, processing_state)
        processing_state['active'] = False
        return

    # --- Main Clipping Loop ---
    for index, file_path in enumerate(video_queue):
        current_video_index = index # Update index before processing
        # Check stop flag
        if not processing_state.get('active', True):
             logger.info("CORE CLIP: Stop signal received during queue processing.")
             status_callback("Status: Stopping clipping process...")
             break

        current_video_basename = os.path.basename(file_path)
        try:
            status_text = f"Clipping {index + 1}/{total_videos}: {current_video_basename}"
            status_callback(status_text)
            logger.info(f"CORE CLIP: Processing video {index + 1}/{total_videos}: {file_path}")

            if not video_processor: raise RuntimeError("VideoProcessor instance became invalid.")

            # --- MODIFIED CALL ---
            # Call VP which uses internal paths, passing only relevant args
            processed_clips_for_this_video = video_processor.process_video(
                file_path,
                **video_processing_args # Use the filtered dictionary
            )
            # --- END MODIFIED CALL ---

            if isinstance(processed_clips_for_this_video, list) and processed_clips_for_this_video:
                processed_count += 1
                final_clip_list_all_videos.extend(processed_clips_for_this_video) # Collect final paths
                logger.info(f"CORE CLIP: Successfully processed {current_video_basename}.")
            elif isinstance(processed_clips_for_this_video, list) and not processed_clips_for_this_video:
                 logger.warning(f"CORE CLIP: No valid clips generated for {current_video_basename}.")
                 # Don't count this as an error unless process_video indicates one
            else:
                # This case might indicate an internal error in process_video that didn't raise an exception
                # but also didn't return a list. Log it as an error.
                error_count += 1
                logger.error(f"CORE CLIP: Processing failed for {current_video_basename} (unexpected return type or value from process_video).")
                status_callback(f"Error during clipping: {current_video_basename} (unexpected result)")

            progress_callback(index + 1, total_videos, start_time) # Update progress (use index+1 for completed count)

        except (VideoProcessingError, FileNotFoundError, ValueError) as e:
             error_count += 1
             logger.error(f"ERROR clipping {current_video_basename}: {type(e).__name__} - {e}")
             status_callback(f"Error on: {current_video_basename} - {type(e).__name__}")
             progress_callback(index + 1, total_videos, start_time) # Ensure progress updates even on error
        except RuntimeError as e:
             error_count +=1
             logger.critical(f"Runtime error during clipping: {e}", exc_info=True)
             status_callback(f"Critical Error: {e}")
             progress_callback(index + 1, total_videos, start_time)
        except Exception as e: # Catch any other unexpected error
            error_count += 1
            # Log the full traceback for unexpected errors
            logger.critical(f"CRITICAL UNEXPECTED ERROR clipping {current_video_basename}", exc_info=True)
            status_callback(f"Critical Error processing {current_video_basename}! Check logs.")
            progress_callback(index + 1, total_videos, start_time)
    # --- End Clipping Loop ---

    was_stopped = not processing_state.get('active', True)
    processing_state['active'] = False # Ensure state is inactive after loop/break

    # Calculate attempted count based on where loop finished/stopped
    attempted_count = current_video_index + 1 if current_video_index >= 0 else 0

    # --- File Organization (AFTER loop, before completion callback) ---
    # Use the 'organize_files' variable extracted earlier from options
    if organize_files and processed_count > 0 and not was_stopped and file_manager_available:
        logger.info(f"CORE CLIP: Organizing {len(final_clip_list_all_videos)} output files into date folders...")
        status_callback("Status: Organizing output files...")
        try:
            # Organizer works on the base output directory
            if os.path.isdir(output_path): # Ensure output path exists
                 organizer = FileOrganizer(output_path)
                 # This assumes FileOrganizer correctly handles files in the base dir
                 # Adapt file extensions if VideoProcessor generates other types (e.g., .mp3)
                 organizer.organize_output(file_extensions=[".mp4"]) # Example: only organize videos
                 logger.info("CORE CLIP: File organization complete.")
            else:
                 logger.warning(f"CORE CLIP: Cannot organize files, output directory not found: {output_path}")
        except Exception as org_e:
            logger.error(f"CORE CLIP: Error during file organization: {org_e}", exc_info=True)
            status_callback("Warning: Error organizing output files.") # Inform user via status
    elif organize_files and processed_count == 0:
         logger.info("CORE CLIP: Skipping file organization as no clips were successfully processed.")
    elif organize_files and was_stopped:
         logger.info("CORE CLIP: Skipping file organization as process was stopped.")
    elif not file_manager_available:
         logger.warning("CORE CLIP: FileOrganizer module not loaded, skipping organization.")
    # --- End File Organization ---

    logger.info(f"--- Clipping Queue Processing Finished. Success: {processed_count}, Errors: {error_count}, Total Attempted: {attempted_count}, Total Videos in Queue: {total_videos}, Stopped by user: {was_stopped} ---")
    completion_callback("Clipping", processed_count, error_count, total_videos, processing_state)


# --- Gemini Script Generation Function ---
def run_gemini_script_generation(prompt: str, completion_callback: ScriptCompletionCallback):
    """Generates a script using Gemini in a background thread."""
    logger.info("--- Starting Gemini Script Generation Thread ---")
    if not utils_loaded or not ai_utils_available:
         err = ImportError("AI utility module (ai_utils) not loaded.")
         logger.error(f"Cannot generate script: {err}")
         completion_callback(None, err)
         return

    logger.info(f"CORE AI SCRIPT: Starting generation for prompt: '{prompt[:50]}...'")
    generated_script: Optional[str] = None
    error: Optional[Exception] = None

    try:
        # Call the actual Gemini generation function from utils.ai_utils
        generated_script = generate_script_with_gemini(prompt) # Max length default used

        if generated_script:
             logger.info("CORE AI SCRIPT: Generation successful.")
        else:
             # Handle case where function returns None or empty string without explicit error
             error = GeminiError("Gemini returned no script content.")
             logger.warning("CORE AI SCRIPT: Generation returned empty script or None.")

    except GeminiError as ge: # Catch specific errors from ai_utils
        logger.error(f"CORE AI SCRIPT: Gemini API Error: {ge}")
        error = ge
    except ValueError as ve: # Catch input errors like empty prompt
         logger.error(f"CORE AI SCRIPT: Input error: {ve}")
         error = ve
    except Exception as e: # Catch unexpected errors
        logger.critical("CORE AI SCRIPT: Unexpected error during generation:", exc_info=True)
        error = e
    finally:
        logger.info("--- Gemini Script Generation Thread Finished ---")
        # Call the GUI callback (which uses root.after)
        completion_callback(generated_script, error)


# --- Gemini Metadata Generation Function ---
def run_gemini_metadata_generation(metadata_type: str, context: str, count: int,
                                   completion_callback: MetadataCompletionCallback):
    """Generates hashtags, tags, or titles using Gemini in a background thread."""
    logger.info(f"--- Starting Gemini Metadata Generation Thread ({metadata_type}) ---")
    valid_types = ['hashtags', 'tags', 'titles']
    if metadata_type not in valid_types:
        err = ValueError(f"Invalid metadata_type requested: {metadata_type}")
        logger.error(err)
        completion_callback(metadata_type, None, err)
        return

    if not utils_loaded or not ai_utils_available:
         err = ImportError("AI utility module (ai_utils) not loaded.")
         logger.error(f"Cannot generate {metadata_type}: {err}")
         completion_callback(metadata_type, None, err)
         return

    logger.info(f"CORE AI META: Starting '{metadata_type}' generation for context: '{context[:50]}...' (Count: {count})")
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

        if result_list is not None: # Check specifically for None, empty list is valid success
             logger.info(f"CORE AI META: '{metadata_type}' generation successful (Count: {len(result_list)}).")
        else:
             # Generation function returned None, likely indicating an error within it
             error = GeminiError(f"Gemini failed to generate {metadata_type} (check ai_utils logs).")
             logger.warning(f"CORE AI META: Generation function returned None for {metadata_type}.")

    except GeminiError as ge: # Catch errors raised directly if API fails badly
        logger.error(f"CORE AI META: Gemini API Error ({metadata_type}): {ge}")
        error = ge
    except ValueError as ve: # Catch invalid input errors (e.g., empty context)
         logger.error(f"CORE AI META: Input error for {metadata_type}: {ve}")
         error = ve
    except Exception as e: # Catch unexpected errors
        logger.critical(f"CORE AI META: Unexpected error during {metadata_type} generation:", exc_info=True)
        error = e
    finally:
        logger.info(f"--- Gemini Metadata Generation Thread Finished ({metadata_type}) ---")
        # Call the GUI callback with type, result (list or None), and any error
        completion_callback(metadata_type, result_list, error)


# --- AI Short Generation Processing Function (MODIFIED) ---
def run_ai_short_generation(script_text: str, background_video_path: str, final_output_path: str,
                            temp_dir: str, ai_options: Dict[str, Any],
                            progress_callback: ProgressCallback, status_callback: StatusCallback,
                            completion_callback: ProcessingCompletionCallback, processing_state: Dict[str, bool]):
    """
    Orchestrates the AI Short Generation process. Runs in a thread.
    Finds FFmpeg/FFprobe paths, passes them to helper functions, and organizes output.
    """
    logger.info("--- Starting AI Short Generation Thread ---")
    start_time = time.time() # Define start time early
    # --- Find FFmpeg/FFprobe FIRST ---
    ffmpeg_exec, ffprobe_exec = None, None
    # Check required dependencies
    required_utils = {"TTS": tts_available, "Subtitles": sub_utils_available, "Helpers": helpers_available, "Logger": logger_available}
    missing_deps = [name for name, loaded in required_utils.items() if not loaded]
    if missing_deps:
        err_msg = f"Error: Cannot start AI Short Gen. Missing dependencies: {', '.join(missing_deps)}"
        logger.critical(err_msg)
        status_callback(err_msg)
        completion_callback("AI Short Generation", 0, 1, 1, processing_state)
        processing_state['active'] = False
        return

    # Dependencies loaded, try finding executables
    try:
        # Get specific paths from AI options if provided
        conf_ffmpeg = ai_options.get("config_ffmpeg_path", None)
        conf_ffprobe = ai_options.get("config_ffprobe_path", None)
        ffmpeg_exec, ffprobe_exec = find_ffmpeg_executables(conf_ffmpeg, conf_ffprobe)
        if not ffmpeg_exec or not ffprobe_exec:
            raise FFmpegNotFoundError("FFmpeg or FFprobe executable not found for AI Short Gen. Check Settings or environment variables.")
    except FFmpegNotFoundError as e:
         logger.critical(f"FFmpeg/FFprobe Check Failed for AI Short Gen: {e}")
         status_callback(f"Error: {e}")
         completion_callback("AI Short Generation", 0, 1, 1, processing_state)
         processing_state['active'] = False
         return
    except Exception as e:
         logger.critical(f"Unexpected error finding FFmpeg/FFprobe for AI Short Gen: {e}", exc_info=True)
         status_callback("Error: Unexpected error finding FFmpeg/FFprobe.")
         completion_callback("AI Short Generation", 0, 1, 1, processing_state)
         processing_state['active'] = False
         return
    logger.info(f"AI Short Gen: Using FFmpeg='{ffmpeg_exec}', FFprobe='{ffprobe_exec}'")
    # --- End FFmpeg Find ---

    processed_count = 0; error_count = 1; total_steps = 5 # Assuming 5 main steps
    voice_audio_path: Optional[str] = None; temp_ass_file: Optional[str] = None; prepared_video_path: Optional[str] = None
    timestamp = int(time.time()); random_id = random.randint(1000,9999)

    try:
        # Check stop flag function
        def check_stop():
            if not processing_state.get('active', True):
                raise InterruptedError("Stop requested by user during AI short generation.")

        # Ensure temp_dir exists
        if not os.path.isdir(temp_dir):
            try:
                logger.info(f"CORE AI: Creating temporary directory: {temp_dir}")
                os.makedirs(temp_dir, exist_ok=True)
            except OSError as e:
                raise ValueError(f"Could not create temporary directory: {temp_dir} - {e}")

        # --- Step 1: TTS (Polly) ---
        check_stop()
        status_callback("Status: 1/5 Generating voiceover...")
        logger.info("CORE AI: Calling Polly TTS...")
        # Pass relevant TTS options
        polly_voice = ai_options.get('polly_voice', 'Joanna') # Example: get voice from options
        tts_result = generate_polly_tts_and_marks(script_text, temp_dir, polly_voice)
        # Check if TTS succeeded and returned valid data
        if tts_result is None or tts_result[0] is None or tts_result[1] is None:
            # Error should have been logged in tts_utils, raise specific error here
            raise ValueError("TTS generation failed or returned invalid data (check logs/AWS setup).")
        voice_audio_path, parsed_speech_marks = tts_result
        if not os.path.exists(voice_audio_path):
            raise FileNotFoundError(f"TTS audio file not found: {voice_audio_path}")
        logger.info(f"CORE AI: Generated voiceover: {voice_audio_path}")
        progress_callback(1, total_steps, start_time) # Step 1 done = 1 step completed

        # --- Step 2: Get Audio Duration ---
        check_stop()
        status_callback("Status: 2/5 Getting audio duration...")
        logger.info("CORE AI: Getting audio duration...")
        audio_duration = get_media_duration(voice_audio_path, ffprobe_exec=ffprobe_exec) # Pass ffprobe path
        if audio_duration <= 0:
            raise ValueError(f"Could not determine valid voiceover duration ({audio_duration:.2f}s).")
        logger.info(f"CORE AI: Voiceover duration: {audio_duration:.3f}s")
        progress_callback(2, total_steps, start_time) # Step 2 done = 2 steps completed

        # --- Step 3: Generate ASS File ---
        check_stop()
        status_callback("Status: 3/5 Generating subtitle file...")
        temp_ass_filename = f"temp_subs_{timestamp}_{random_id}.ass"
        temp_ass_file = os.path.join(temp_dir, temp_ass_filename)
        logger.info(f"CORE AI: Creating temporary ASS file: {temp_ass_file}")
        # Pass relevant subtitle options
        font_size = ai_options.get('font_size', 48) # Example: get font size from options
        ass_success = generate_ass_file_with_style(
            parsed_speech_marks=parsed_speech_marks,
            output_ass_path=temp_ass_file,
            font_size=font_size
        )
        if not ass_success:
            raise ValueError("Failed to generate ASS subtitle file (check logs).")
        logger.info("CORE AI: Temp ASS file created.")
        progress_callback(3, total_steps, start_time) # Step 3 done = 3 steps completed

        # --- Step 4: Prepare Background Video ---
        check_stop()
        status_callback("Status: 4/5 Preparing background video...")
        prepared_video_filename = f"prep_video_{timestamp}_{random_id}.mp4"
        prepared_video_path = os.path.join(temp_dir, prepared_video_filename)
        logger.info(f"CORE AI: Preparing background video -> {prepared_video_path}")
        prep_success = prepare_background_video(
            background_video_path,
            prepared_video_path,
            audio_duration,
            ffmpeg_exec=ffmpeg_exec, # Pass ffmpeg path
            ffprobe_exec=ffprobe_exec # Pass ffprobe path
        )
        if not prep_success:
            raise ValueError("Failed to prepare background video (check logs).")
        logger.info("CORE AI: Background video prepared.")
        progress_callback(4, total_steps, start_time) # Step 4 done = 4 steps completed

        # --- Step 5: Final FFmpeg Composition ---
        check_stop()
        status_callback("Status: 5/5 Combining final video...")
        logger.info("CORE AI: Combining final elements...")
        # Get relevant composition options
        bg_music = ai_options.get('background_music_path', None)
        music_vol = ai_options.get('music_volume', 0.1)
        combine_success = combine_ai_short_elements(
            video_path=prepared_video_path,
            audio_path=voice_audio_path,
            ass_path=temp_ass_file,
            output_path=final_output_path,
            ffmpeg_exec=ffmpeg_exec, # Pass ffmpeg path
            bg_music_path=bg_music,
            music_volume=music_vol
        )
        if not combine_success:
            raise ValueError("Final FFmpeg composition failed (check logs).")
        logger.info("CORE AI: Final combination successful.")
        progress_callback(5, total_steps, start_time) # Step 5 done = 5 steps completed

        # If all steps succeeded
        processed_count = 1
        error_count = 0
        status_callback("Status: AI Short Generation Successful!")
        logger.info("CORE AI: AI Short Generation process completed successfully.")

        # --- File Organization (AFTER successful combination) ---
        organize_ai_files = ai_options.get("organize_output", False) # Get flag from options
        if organize_ai_files and file_manager_available: # Check module loaded
            logger.info("CORE AI: Organizing final AI short output file...")
            status_callback("Status: Organizing output file...")
            try:
                ai_output_dir = os.path.dirname(final_output_path)
                if os.path.isdir(ai_output_dir): # Ensure output dir exists
                    organizer = FileOrganizer(ai_output_dir)
                    # Only organize the final MP4 for AI shorts
                    organizer.organize_output(file_extensions=[".mp4"])
                    logger.info("CORE AI: AI short file organization complete.")
                else:
                    logger.warning(f"CORE AI: Cannot organize AI short, output directory not found: {ai_output_dir}")
            except Exception as org_e:
                logger.error(f"CORE AI: Error during AI short file organization: {org_e}", exc_info=True)
                status_callback("Warning: Error organizing AI short output file.")
        elif organize_ai_files and not file_manager_available: # Check flag but module missing
             logger.warning("CORE AI: FileOrganizer module not loaded, skipping organization.")
        # --- End File Organization ---

    except InterruptedError as e:
         logger.info(f"CORE AI: Stop signal received: {e}")
         status_callback("Status: AI Short Generation Stopped.")
         # error_count remains 1 (default), processed_count remains 0
    except (FFmpegNotFoundError, ValueError, FileNotFoundError, ConnectionError, GeminiError) as e: # Added GeminiError just in case
         error_msg = f"ERROR generating AI Short: {type(e).__name__} - {e}"
         logger.error(error_msg, exc_info=False) # Log specific error without full trace usually
         logger.debug(f"Traceback for AI Short Error:", exc_info=True) # Add full trace at debug level
         status_callback(f"Error: {e}")
         # error_count remains 1 (default), processed_count remains 0
    except Exception as e:
        error_msg = "CRITICAL UNEXPECTED ERROR generating AI Short"
        logger.critical(error_msg, exc_info=True) # Log full trace for unexpected
        status_callback("Critical Error generating AI Short! Check logs.")
        # error_count remains 1 (default), processed_count remains 0
    finally:
        # --- Cleanup Intermediate Files ---
        files_to_clean = [temp_ass_file, voice_audio_path, prepared_video_path]
        logger.info(f"CORE AI: Cleaning up temporary files...")
        for f_path in files_to_clean:
            if f_path and os.path.exists(f_path):
                try:
                    os.remove(f_path)
                    logger.info(f"CORE AI: Removed temp file: {os.path.basename(f_path)}")
                except OSError as e_clean:
                    logger.warning(f"CORE AI: Error removing temp file {f_path}: {e_clean}")
            elif f_path:
                logger.debug(f"CORE AI: Temp file path not found or already cleaned up: {f_path}")
        # --- Signal Completion ---
        was_stopped = not processing_state.get('active', True)
        processing_state['active'] = False # Ensure inactive state
        logger.info(f"--- AI Short Generation Thread Finished. Success: {processed_count}, Errors: {error_count}, Stopped by user: {was_stopped} ---")
        # For AI short, total is always 1 attempt
        completion_callback("AI Short Generation", processed_count, error_count, 1, processing_state)