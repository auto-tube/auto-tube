# utils/tts_utils.py
import boto3 # Requires pip install boto3
import os
import time
import traceback
import random # Only needed for placeholder & unique filenames
from typing import List, Dict, Any, Tuple, Optional
import json # For parsing speech marks

# --- AWS Polly Client Initialization ---
polly_client = None
try:
    print("TTS UTIL: Attempting to initialize AWS Polly client...")
    # Ensure AWS credentials (access key, secret key, region) are configured
    # via standard methods (e.g., ~/.aws/credentials, env vars, IAM role)
    polly_client = boto3.client('polly')
    # Optional quick check to verify client works (optional)
    # polly_client.list_voices(MaxResults=1)
    print("TTS UTIL: AWS Polly client initialized successfully.")
except Exception as e:
    print(f"TTS UTIL FATAL ERROR: Failed to initialize AWS Polly client: {e}")
    print("TTS UTIL: Ensure AWS credentials and region are configured correctly.")
    # Set client to None to indicate failure; calling functions should check this
    polly_client = None
# --- End Polly Client Init ---

def generate_polly_tts_and_marks(text: str, output_dir: str, voice_id: str = "Joanna",
                                engine: str = "neural") -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    Generates speech using Polly, saves MP3, requests word speech marks,
    and returns the audio path and parsed marks list.

    Args:
        text: The text script to synthesize. Needs to be plain text.
        output_dir: Directory to save the temporary MP3 file.
        voice_id: The Polly Voice ID (e.g., "Joanna", "Matthew").
        engine: Polly engine ('standard' or 'neural').

    Returns:
        Tuple (audio_file_path, speech_marks_list) on success,
        None on failure (logs error).
    """
    if not polly_client:
        print("TTS UTIL ERROR: Polly client not available.")
        # Optionally raise an error here instead of returning None
        raise ConnectionError("AWS Polly client failed to initialize. Cannot generate TTS.")
        # return None
    if not text:
        print("TTS UTIL ERROR: Input text for TTS is empty.")
        return None, None
    if not output_dir or not os.path.isdir(output_dir):
        print(f"TTS UTIL ERROR: Invalid output directory for TTS audio: {output_dir}")
        return None, None

    # Create a unique filename base
    timestamp = int(time.time())
    random_id = random.randint(1000, 9999)
    safe_filename_base = f"polly_voice_{timestamp}_{random_id}"
    audio_file_path = os.path.join(output_dir, f"{safe_filename_base}.mp3")
    marks_list = []

    try:
        # --- 1. Request Speech Marks (JSON format) ---
        # Polly has limits on text length per request (~3000 chars for sync synthesize)
        # Need to handle longer text by splitting if necessary (not implemented here)
        if len(text) > 2900: # Check limit (adjust if needed)
             print("TTS UTIL Warning: Text might be too long for single Polly request, may fail.")

        print(f"TTS UTIL: Requesting Polly speech marks (Voice: {voice_id})...")
        response_marks = polly_client.synthesize_speech(
            Text=text,
            OutputFormat='json',         # Request metadata format
            VoiceId=voice_id,
            Engine=engine,
            SpeechMarkTypes=['word']    # Request word boundaries
        )

        # --- Parse Speech Marks ---
        if 'AudioStream' not in response_marks:
            # For json output, marks are in the AudioStream
            raise ValueError("Polly speech mark response missing 'AudioStream'.")

        marks_content = response_marks['AudioStream'].read().decode('utf-8')
        raw_marks = []
        for line in marks_content.splitlines():
             line = line.strip()
             if line:
                 try:
                     mark_data = json.loads(line)
                     # Basic validation
                     if 'time' in mark_data and 'type' in mark_data and 'value' in mark_data:
                          raw_marks.append(mark_data)
                     # else: print(f"TTS UTIL Debug: Skipping non-word mark: {mark_data}")
                 except json.JSONDecodeError:
                     print(f"TTS UTIL Warning: Could not decode speech mark line: {line}")

        # Filter only for 'word' type marks
        marks_list = [mark for mark in raw_marks if mark.get('type') == 'word'] # Filter for words

        if not marks_list:
            # Log the raw content if parsing failed to get any words
            print(f"TTS UTIL ERROR: Failed to parse any valid 'word' speech marks from Polly response.")
            print(f"Raw marks content received:\n{marks_content[:1000]}...") # Log first part
            raise ValueError("No valid word speech marks found.")
        print(f"TTS UTIL: Parsed {len(marks_list)} word speech marks.")


        # --- 2. Request Audio Stream (MP3 format) ---
        print("TTS UTIL: Requesting Polly audio stream (MP3)...")
        response_audio = polly_client.synthesize_speech(
            Text=text,
            OutputFormat='mp3',
            VoiceId=voice_id,
            Engine=engine
            # Do NOT include SpeechMarkTypes when requesting audio format
        )

        # --- Save Audio Stream ---
        if 'AudioStream' in response_audio:
            with open(audio_file_path, 'wb') as f:
                audio_data = response_audio['AudioStream'].read()
                if not audio_data:
                     raise IOError("Polly returned empty audio stream.")
                f.write(audio_data)
            print(f"TTS UTIL: Saved Polly audio to {audio_file_path}")
            # Verify file size
            if os.path.getsize(audio_file_path) == 0:
                 os.remove(audio_file_path) # Clean up empty file
                 raise IOError(f"Polly audio file saved but is empty: {audio_file_path}")
        else:
            raise ValueError("Polly audio response did not contain 'AudioStream'.")

        return audio_file_path, marks_list

    except Exception as e: # Catch specific boto3 exceptions if needed (e.g., ClientError)
        print(f"TTS UTIL ERROR: Failed during Polly interaction: {e}")
        traceback.print_exc()
        # Clean up partial audio file if it exists
        if os.path.exists(audio_file_path):
            try: os.remove(audio_file_path)
            except OSError: pass
        return None, None # Indicate failure


# --- Placeholder Speech Mark Generator (Keep for testing without AWS) ---
def _get_placeholder_speech_marks_for_polly(text):
    """Generates fake speech marks similar to Polly word marks for testing."""
    print("TTS UTIL WARNING: Using PLACEHOLDER Polly speech mark data!")
    marks = []
    words = text.split()
    current_time_ms = 100 # Start at 100ms
    char_index = 0
    for i, word in enumerate(words):
         # Estimate duration based on word length (very basic)
         duration_ms = 150 + len(word) * 50 # Base + per char
         duration_ms = random.randint(int(duration_ms*0.8), int(duration_ms*1.2)) # Add randomness
         duration_ms = max(100, min(1000, duration_ms)) # Clamp duration

         start_char = text.find(word, char_index) # Simple find might fail on repetition
         if start_char == -1: start_char = char_index # fallback

         end_char = start_char + len(word)
         marks.append({'time': current_time_ms, 'type': 'word', 'start': start_char, 'end': end_char, 'value': word})

         current_time_ms += duration_ms + random.randint(50, 150) # Add gap
         char_index = end_char
    print(f"Generated {len(marks)} placeholder marks.")
    return marks