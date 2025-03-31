# utils/tts_utils.py
import boto3 # Requires pip install boto3 and AWS credentials configured
import os
import time
import traceback
import random # For unique filenames
from typing import List, Dict, Any, Tuple, Optional
import json # For parsing speech marks

# --- AWS Polly Client Initialization ---
# Placed here so it's initialized when the module is imported
polly_client = None
try:
    print("TTS UTIL: Attempting to initialize AWS Polly client...")
    # Reads credentials/region from standard AWS locations
    # Specify region explicitly if needed: boto3.client('polly', region_name='us-east-1')
    polly_client = boto3.client('polly')
    # Quick check to verify client works (using describe_voices)
    polly_client.describe_voices() # Correct check - no MaxResults needed/allowed
    print("TTS UTIL: AWS Polly client initialized successfully.")
except Exception as e:
    print(f"TTS UTIL FATAL ERROR: Failed to initialize AWS Polly client: {e}")
    print("TTS UTIL: Ensure AWS credentials and region are configured correctly.")
    # Setting to None allows calling functions to check if init failed
    polly_client = None
# --- End Polly Client Init ---

def generate_polly_tts_and_marks(text: str, output_dir: str, voice_id: str = "Joanna",
                                engine: str = "neural") -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    Generates speech using Polly, saves MP3, requests word speech marks,
    and returns the audio path and parsed marks list.

    Args:
        text: The text script to synthesize. Plain text is expected.
        output_dir: Directory to save the temporary MP3 file.
        voice_id: The Polly Voice ID (e.g., "Joanna", "Matthew").
        engine: Polly engine ('standard' or 'neural'). Neural is usually higher quality.

    Returns:
        Tuple (audio_file_path, speech_marks_list) on success,
        None, None on failure (logs error).
    """
    if not polly_client:
        print("TTS UTIL ERROR: Polly client not available (failed initialization?).")
        # Raise an error to make the failure clearer to the calling code
        raise ConnectionError("AWS Polly client failed to initialize. Cannot generate TTS.")
        # return None, None # Alternative: return None to indicate failure

    if not text:
        print("TTS UTIL ERROR: Input text for TTS is empty.")
        return None, None # Return None tuple for invalid input
    if not output_dir or not os.path.isdir(output_dir):
        print(f"TTS UTIL ERROR: Invalid output directory for TTS audio: {output_dir}")
        return None, None # Return None tuple for invalid input

    # Create a unique filename base using timestamp and random number
    timestamp = int(time.time())
    random_id = random.randint(1000, 9999)
    safe_filename_base = f"polly_voice_{timestamp}_{random_id}"
    audio_file_path = os.path.join(output_dir, f"{safe_filename_base}.mp3")
    marks_list = []

    try:
        # --- Sanitize Text (Basic) ---
        text = " ".join(text.split()) # Consolidate whitespace

        # --- Check Text Length ---
        MAX_CHARS_POLLY = 2950 # Slightly conservative limit for synthesize_speech
        if len(text) > MAX_CHARS_POLLY:
            print(f"TTS UTIL WARNING: Text length ({len(text)}) exceeds recommended limit ({MAX_CHARS_POLLY}). Truncating.")
            text = text[:MAX_CHARS_POLLY]
            # Consider adding a warning back to the GUI user here if possible

        # --- 1. Request Speech Marks (JSON format) ---
        print(f"TTS UTIL: Requesting Polly speech marks (Voice: {voice_id}, Engine: {engine})...")
        response_marks = polly_client.synthesize_speech(
            Text=text,
            OutputFormat='json',
            VoiceId=voice_id,
            Engine=engine,
            SpeechMarkTypes=['word'] # Request word boundaries
        )

        # --- Parse Speech Marks ---
        if 'AudioStream' not in response_marks:
            raise ValueError("Polly speech mark response missing 'AudioStream' body.")

        marks_content = response_marks['AudioStream'].read().decode('utf-8')
        raw_marks = []
        for line in marks_content.splitlines():
             line = line.strip()
             if line:
                 try:
                     mark_data = json.loads(line)
                     # Validate expected keys for word marks
                     if all(k in mark_data for k in ['time', 'type', 'value']) and mark_data['type'] == 'word':
                          raw_marks.append(mark_data)
                     # else: print(f"TTS UTIL Debug: Skipping non-word mark: {mark_data}") # Optional
                 except json.JSONDecodeError:
                     print(f"TTS UTIL Warning: Could not decode speech mark JSON line: {line}")

        # Filter just in case non-word marks slipped through (shouldn't happen with type check)
        marks_list = [mark for mark in raw_marks if mark.get('type') == 'word']

        if not marks_list:
            print(f"TTS UTIL ERROR: Failed to parse any valid 'word' speech marks from Polly response.")
            print(f"Raw marks content received:\n{marks_content[:1000]}...") # Log part of raw marks
            raise ValueError("No valid word speech marks parsed.")
        print(f"TTS UTIL: Parsed {len(marks_list)} word speech marks.")


        # --- 2. Request Audio Stream (MP3 format) ---
        print("TTS UTIL: Requesting Polly audio stream (MP3)...")
        response_audio = polly_client.synthesize_speech(
            Text=text, # Synthesize the same text (potentially truncated)
            OutputFormat='mp3',
            VoiceId=voice_id,
            Engine=engine
            # DO NOT include SpeechMarkTypes when requesting 'mp3' format
        )

        # --- Save Audio Stream ---
        if 'AudioStream' in response_audio:
            with open(audio_file_path, 'wb') as f:
                audio_data = response_audio['AudioStream'].read()
                if not audio_data:
                     raise IOError("Polly returned empty audio stream.")
                f.write(audio_data)
            print(f"TTS UTIL: Saved Polly audio to {audio_file_path}")
            # Sanity check file size
            if os.path.getsize(audio_file_path) < 100:
                 os.remove(audio_file_path)
                 raise IOError(f"Polly audio file saved but is suspiciously small: {audio_file_path}")
        else:
            raise ValueError("Polly audio response did not contain 'AudioStream'.")

        # --- Success ---
        return audio_file_path, marks_list

    # --- Error Handling ---
    except polly_client.exceptions.TextLengthExceededException as e:
         # Catch specific Polly error for text length
         error_msg = f"Text length ({len(text)} chars) exceeds Polly's limit. Please shorten the script."
         print(f"TTS UTIL ERROR: {error_msg} - {e}")
         traceback.print_exc()
         return None, None # Return None tuple
    except boto3.exceptions.Boto3Error as e:
         # Catch general boto3/AWS errors (credentials, connection, etc.)
         error_msg = f"AWS/Boto3 Error during Polly interaction: {e}"
         print(f"TTS UTIL ERROR: {error_msg}")
         traceback.print_exc()
         return None, None
    except Exception as e:
        # Catch any other unexpected errors
        print(f"TTS UTIL ERROR: Unexpected failure during Polly interaction: {e}")
        traceback.print_exc()
        return None, None
    finally:
        # Clean up partial audio file if it exists AND we are returning None (error occurred)
        # This logic might need refinement depending on how errors are handled above
        # If an error occurred after audio was saved, but before returning successfully
        if 'audio_file_path' in locals() and os.path.exists(audio_file_path):
             # Check if we are about to return None,None - implies error
             # Need a flag or check return value if defined earlier
             # Simplified: Assume if exception happened, try cleanup
             # A better way is to set a success flag only at the end of try block
             try:
                  # This cleanup might run even on success if not careful,
                  # Only clean up if returning None, None
                  # Let's comment out the cleanup here for now, caller should handle temp files
                  # os.remove(audio_file_path)
                  # print(f"TTS UTIL: Cleaned up potentially partial audio file: {audio_file_path}")
                  pass
             except OSError: pass


# Note: Removed the placeholder generator function _get_placeholder_speech_marks_for_polly