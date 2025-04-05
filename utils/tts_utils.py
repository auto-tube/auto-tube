# utils/tts_utils.py
import boto3 # Requires pip install boto3
import botocore # For specific exceptions
import os
import time
import traceback
import random # For unique filenames
from typing import List, Dict, Any, Tuple, Optional
import json # For parsing speech marks

# --- Module Level Variables (Initialized to None) ---
polly_client = None
POLLY_CONFIGURED = False
_aws_config_used = {} # Store config used for comparison

# --- NEW: Function to configure Polly Client ---
def configure_polly_client(aws_access_key_id: Optional[str] = None,
                           aws_secret_access_key: Optional[str] = None,
                           aws_region_name: Optional[str] = None):
    """
    Configures the AWS Polly client using provided credentials and region.
    If credentials are None, it attempts to use default AWS SDK behavior
    (environment vars, shared credentials file, IAM role).
    """
    global polly_client, POLLY_CONFIGURED, _aws_config_used

    # Store current config attempt parameters for comparison
    current_config_attempt = {
        'aws_access_key_id': aws_access_key_id,
        'aws_secret_key_provided': bool(aws_secret_access_key), # Don't store the actual key
        'aws_region_name': aws_region_name
    }

    # Check if already configured with the exact same parameters
    # Note: If args are None, this won't detect changes in underlying default sources (env, ~/.aws)
    if POLLY_CONFIGURED and current_config_attempt == _aws_config_used:
         print("TTS UTIL: Polly client already configured with these parameters.")
         return True # Indicate success (already configured)

    print("TTS UTIL: Attempting to configure/reconfigure AWS Polly client...")
    # Reset state before attempting configuration
    polly_client = None
    POLLY_CONFIGURED = False
    _aws_config_used = {}

    try:
        # Create kwargs dict only with non-None values provided by user/settings
        boto_kwargs = {}
        config_info_parts = [] # For logging what was provided
        if aws_access_key_id:
             boto_kwargs['aws_access_key_id'] = aws_access_key_id
             config_info_parts.append("AccessKey(Provided)")
        if aws_secret_access_key:
             boto_kwargs['aws_secret_access_key'] = aws_secret_access_key
             config_info_parts.append("SecretKey(Provided)")
        if aws_region_name:
             boto_kwargs['region_name'] = aws_region_name
             config_info_parts.append(f"Region({aws_region_name})")

        config_info = ", ".join(config_info_parts) if config_info_parts else "Default AWS SDK Chain"
        print(f"TTS UTIL: Initializing boto3 client using configuration: [{config_info}]")

        # Initialize client - This is where Boto3 looks for credentials if not provided
        temp_client = boto3.client('polly', **boto_kwargs)

        # Test client with a simple, low-cost API call
        print("TTS UTIL: Testing Polly client connection with describe_voices...")
        temp_client.describe_voices(LanguageCode='en-US') # Specify language to potentially avoid region issues
        print("TTS UTIL: Polly client test successful.")

        # Update global client and state
        polly_client = temp_client
        POLLY_CONFIGURED = True
        _aws_config_used = current_config_attempt # Store successful config params
        print("TTS UTIL: AWS Polly client configured successfully.")
        return True # Indicate success

    except botocore.exceptions.NoCredentialsError:
        print("TTS UTIL FATAL ERROR: AWS credentials not found. Configure via Settings, env vars (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION), or shared file (~/.aws/credentials).")
        # Keep POLLY_CONFIGURED as False
        return False
    except botocore.exceptions.ClientError as e:
        # Catch specific boto errors like InvalidClientTokenId, SignatureDoesNotMatch, region issues
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        print(f"TTS UTIL FATAL ERROR: AWS ClientError during Polly configuration/test ({error_code}): {error_message}")
        # Keep POLLY_CONFIGURED as False
        return False
    except Exception as e:
        # Catch any other unexpected errors during init/test
        print(f"TTS UTIL FATAL ERROR: Unexpected failure during Polly client configuration/test: {e}")
        traceback.print_exc()
        # Keep POLLY_CONFIGURED as False
        return False

# --- REMOVED Initial Configuration Attempt ---

# --- generate_polly_tts_and_marks (MODIFIED Check) ---
def generate_polly_tts_and_marks(text: str, output_dir: str, voice_id: str = "Joanna",
                                engine: str = "neural") -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """
    Generates speech using Polly, saves MP3, requests word speech marks,
    and returns the audio path and parsed marks list.
    Requires configure_polly_client to be called successfully first.
    """
    # Check if configured NOW
    if not POLLY_CONFIGURED or not polly_client:
        print("TTS UTIL ERROR: Polly client not configured. Cannot generate TTS.")
        # Raise a specific error to be caught by the caller
        raise ConnectionError("AWS Polly client not configured. Please check credentials/region in Settings.")

    if not text:
        print("TTS UTIL ERROR: Input text for TTS is empty.")
        return None # Return None for invalid input, don't raise exception
    if not output_dir or not os.path.isdir(output_dir):
        print(f"TTS UTIL ERROR: Invalid output directory for TTS audio: {output_dir}")
        return None # Return None for invalid input

    # --- Create Unique Filename ---
    timestamp = int(time.time())
    random_id = random.randint(1000, 9999)
    safe_filename_base = f"polly_voice_{timestamp}_{random_id}"
    audio_file_path = os.path.join(output_dir, f"{safe_filename_base}.mp3")
    marks_list = []

    try:
        # --- Sanitize & Check Text Length ---
        text = " ".join(text.split()) # Consolidate whitespace
        MAX_CHARS_POLLY = 2950 # Conservative limit
        if len(text) > MAX_CHARS_POLLY:
            original_len = len(text)
            text = text[:MAX_CHARS_POLLY]
            print(f"TTS UTIL WARNING: Text length ({original_len}) exceeds recommended limit ({MAX_CHARS_POLLY}). Truncated.")
            # Maybe signal this back to the user via status bar? Requires callback modification.

        # --- 1. Request Speech Marks (JSON format) ---
        print(f"TTS UTIL: Requesting Polly speech marks (Voice: {voice_id}, Engine: {engine})...")
        response_marks = polly_client.synthesize_speech(
            Text=text,
            OutputFormat='json',
            VoiceId=voice_id,
            Engine=engine,
            SpeechMarkTypes=['word'] # Request word boundaries only
        )

        # --- Parse Speech Marks ---
        if 'AudioStream' not in response_marks:
            raise ValueError("Polly speech mark response missing 'AudioStream' body.")

        # Read the stream line by line and parse JSON
        marks_content = response_marks['AudioStream'].read().decode('utf-8')
        raw_marks = []
        for line in marks_content.splitlines():
             line = line.strip()
             if line:
                 try:
                     mark_data = json.loads(line)
                     # Validate expected keys for word marks more carefully
                     if (mark_data.get('type') == 'word' and
                         isinstance(mark_data.get('time'), int) and
                         isinstance(mark_data.get('value'), str)):
                          raw_marks.append(mark_data)
                     # else: print(f"TTS UTIL Debug: Skipping non-word/invalid mark: {mark_data}")
                 except json.JSONDecodeError:
                     print(f"TTS UTIL Warning: Could not decode speech mark JSON line: {line}")

        # Final list contains only valid word marks
        marks_list = raw_marks
        if not marks_list:
            # Log more context if parsing fails
            print(f"TTS UTIL ERROR: Failed to parse any valid 'word' speech marks from Polly response.")
            print(f"Raw marks content received (first 500 chars):\n{marks_content[:500]}...")
            raise ValueError("No valid word speech marks parsed from Polly.")
        print(f"TTS UTIL: Parsed {len(marks_list)} word speech marks.")


        # --- 2. Request Audio Stream (MP3 format) ---
        print("TTS UTIL: Requesting Polly audio stream (MP3)...")
        response_audio = polly_client.synthesize_speech(
            Text=text, # Use the same potentially truncated text
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
                     # Should not happen if API call succeeded, but check anyway
                     raise IOError("Polly returned empty audio stream despite successful API call.")
                f.write(audio_data)
            print(f"TTS UTIL: Saved Polly audio to {audio_file_path}")
            # Sanity check file size
            if os.path.getsize(audio_file_path) < 100: # Arbitrary small size check
                 # Clean up suspiciously small file
                 try: os.remove(audio_file_path)
                 except OSError: pass
                 raise IOError(f"Polly audio file saved but is suspiciously small (<100 bytes): {audio_file_path}")
        else:
            # Should not happen if API call succeeded
            raise ValueError("Polly audio response did not contain 'AudioStream'.")

        # --- Success ---
        return audio_file_path, marks_list

    # --- Error Handling ---
    except polly_client.exceptions.TextLengthExceededException as e:
         # Should be caught by manual check, but catch specific Polly error just in case
         error_msg = f"Text length ({len(text)} chars) exceeds Polly's limit. Please shorten the script."
         print(f"TTS UTIL ERROR: {error_msg} - {e}")
         return None # Return None tuple
    except botocore.exceptions.ClientError as e:
         # Catch specific boto errors like InvalidSampleRateError, ServiceFailureException etc.
         error_code = e.response.get('Error', {}).get('Code', 'Unknown')
         error_message = e.response.get('Error', {}).get('Message', str(e))
         print(f"TTS UTIL ERROR: AWS ClientError during Polly synthesis ({error_code}): {error_message}")
         traceback.print_exc() # Print traceback for boto errors
         return None
    except boto3.exceptions.Boto3Error as e: # Catch broader Boto3 issues
         error_msg = f"AWS/Boto3 Error during Polly synthesis: {e}"
         print(f"TTS UTIL ERROR: {error_msg}")
         traceback.print_exc()
         return None
    except (ValueError, IOError, FileNotFoundError) as e: # Catch specific errors raised above
        print(f"TTS UTIL ERROR: {e}")
        # Don't print traceback for these expected validation/IO errors
        return None
    except Exception as e:
        # Catch any other unexpected errors during synthesis/saving
        print(f"TTS UTIL ERROR: Unexpected failure during Polly interaction: {e}")
        traceback.print_exc()
        return None
    # No finally block needed for cleanup, handled by caller (temp dir removal)