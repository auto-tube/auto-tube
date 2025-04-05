# utils/ai_utils.py
import google.generativeai as genai
import os
import traceback
from typing import Optional, List
import re # For cleaning output

print("Loading ai_utils.py")

# --- Custom Error ---
class GeminiError(Exception):
    """Custom exception for errors during Gemini API interaction."""
    pass

# --- Module Level Variables (Initialized to None) ---
gemini_model = None
GEMINI_CONFIGURED = False
_google_api_key_used = None # Store the key used for configuration

# --- NEW: Function to configure API ---
def configure_google_api(api_key: Optional[str]):
    """Configures the Google Gemini API using the provided key."""
    global gemini_model, GEMINI_CONFIGURED, _google_api_key_used

    if not api_key:
        print("AI Utils WARN: No Google API Key provided for configuration. Gemini features disabled.")
        gemini_model = None
        GEMINI_CONFIGURED = False
        _google_api_key_used = None
        return # Cannot configure without a key

    # Only reconfigure if the key is different or not configured yet
    if api_key == _google_api_key_used and GEMINI_CONFIGURED:
        print("AI Utils: Google API already configured with the provided key.")
        return

    try:
        print(f"AI Utils: Configuring Google Gemini API with provided key...")
        genai.configure(api_key=api_key)
        # Ensure the model name is suitable and available
        MODEL_NAME = 'gemini-1.5-flash-latest' # Or 'gemini-1.0-pro' etc.
        # Test model instantiation
        gemini_model = genai.GenerativeModel(MODEL_NAME)
        # Optional: Perform a small test call like list_models to be sure
        # genai.list_models() # This might require specific permissions
        print(f"AI Utils: Google Gemini API configured successfully with model '{MODEL_NAME}'.")
        GEMINI_CONFIGURED = True
        _google_api_key_used = api_key # Store the key used
    except Exception as e:
        print(f"AI Utils ERROR: Failed to configure Google Gemini API: {e}")
        gemini_model = None
        GEMINI_CONFIGURED = False
        _google_api_key_used = None
        # Optionally raise the error to be caught by the GUI
        # raise GeminiError(f"Failed to configure Gemini: {e}") from e

# --- REMOVED Initial Configuration Attempt ---

# --- Generation Config & Safety --- (FIXED PLACEHOLDERS)
DEFAULT_GENERATION_CONFIG = genai.types.GenerationConfig(
    max_output_tokens=800, # Allow more tokens for lists/scripts
    temperature=0.7,       # Balance creativity and predictability
    # top_p=0.9,           # Optional: Nucleus sampling
    # top_k=40,            # Optional: Top-k sampling
)
DEFAULT_SAFETY_SETTINGS = {
    # Adjust levels as needed - e.g., 'block_only_high' for less strict filtering
    'HARM_CATEGORY_HARASSMENT': 'block_medium_and_above',
    'HARM_CATEGORY_HATE_SPEECH': 'block_medium_and_above',
    'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'block_medium_and_above',
    'HARM_CATEGORY_DANGEROUS_CONTENT': 'block_medium_and_above',
}

# --- Helper to Run Generation (MODIFIED Check) ---
def _run_gemini_generation(prompt: str, context: str = "Generating metadata") -> Optional[str]:
    """Internal helper to run the Gemini API call and handle basic errors."""
    # Check if configured NOW, before making the call
    if not GEMINI_CONFIGURED or not gemini_model:
        print("AI Utils ERROR: Gemini API model not configured or initialized. Cannot run generation.")
        raise GeminiError("Gemini API model not configured. Please check API key in Settings.")

    try:
        print(f"AI Utils ({context}): Sending prompt (first 100 chars): '{prompt[:100]}...'")
        # Use the globally configured gemini_model
        response = gemini_model.generate_content(
            prompt,
            generation_config=DEFAULT_GENERATION_CONFIG,
            safety_settings=DEFAULT_SAFETY_SETTINGS
        )
        print(f"AI Utils ({context}): Received response.")

        # Check safety feedback before accessing candidates/text
        if response.prompt_feedback and response.prompt_feedback.block_reason:
             block_reason = response.prompt_feedback.block_reason.name # Get enum name
             safety_ratings = response.prompt_feedback.safety_ratings # Log details
             print(f"AI Utils WARN ({context}): Generation blocked by safety settings. Reason: {block_reason}")
             print(f"Safety Ratings: {safety_ratings}")
             raise GeminiError(f"Generation blocked by safety settings. Reason: {block_reason}")

        # Check candidates exist before accessing parts/text
        if not response.candidates:
             print(f"AI Utils WARN ({context}): No candidates returned in response.")
             raise GeminiError("Generation failed: No candidates returned in response.")

        # Process candidates for text (handle potential variations in response structure)
        try:
             # Standard way to get text
             if response.text:
                  return response.text.strip()
             # Fallback check on parts
             elif response.candidates[0].content and response.candidates[0].content.parts:
                  print(f"AI Utils ({context}): Using parts fallback to get text.")
                  return "".join(part.text for part in response.candidates[0].content.parts).strip()
             else:
                  # No text, no parts, check finish reason for clues
                  finish_reason = response.candidates[0].finish_reason.name
                  print(f"AI Utils WARN ({context}): Generation finished but returned no text content. Finish Reason: {finish_reason}")
                  # Raise error based on finish reason if it indicates a problem
                  if finish_reason not in ['STOP', 'MAX_TOKENS']:
                        raise GeminiError(f"Generation returned no text content. Finish Reason: {finish_reason}")
                  else:
                       return "" # Return empty string if finished normally but no text
        except (AttributeError, IndexError, ValueError) as e:
             print(f"AI Utils ERROR ({context}): Could not parse text from Gemini response object: {e}")
             raise GeminiError("Failed to parse text from Gemini response.") from e

    except Exception as e:
        # Catch API call errors (network, auth etc.) or response processing errors
        error_type = type(e).__name__
        # Avoid logging API key if it's part of the error message
        error_message = str(e).replace(_google_api_key_used or "DUMMY_KEY", "********") if _google_api_key_used else str(e)
        print(f"AI Utils ERROR ({context}): Error during Gemini API call: {error_type} - {error_message}")
        # Re-raise as specific error type for caller to handle
        raise GeminiError(f"Failed during {context}: {e}") from e


# --- Script Generation Function ---
def generate_script_with_gemini(prompt: str) -> Optional[str]:
    """Generates a short video script using Gemini."""
    if not prompt: raise ValueError("Prompt cannot be empty.")
    full_prompt = f"""Generate a concise script suitable for a short vertical video (like YouTube Shorts) based on the following idea/niche.
The script should be engaging and easy to speak naturally.
Format the output with short paragraphs or sentences, each on a NEW LINE. Do not use markdown formatting like bold or italics. Start the script directly without any preamble.

Idea/Niche: "{prompt}"

SCRIPT:
"""
    try:
        return _run_gemini_generation(full_prompt, context="Script Generation")
    except GeminiError as e:
        print(f"Script generation failed: {e}")
        raise # Let processing_manager handle the callback with the error


# --- NEW Metadata Generation Functions ---

def generate_hashtags_with_gemini(context: str, count: int) -> Optional[List[str]]:
    """Generates relevant hashtags using Gemini."""
    if not context: raise ValueError("Context (topic/description) cannot be empty.")
    if count <= 0: return []

    prompt = f"""Generate a list of exactly {count} relevant and effective hashtags for a short vertical video (like YouTube Shorts/TikTok) about the following topic/description.
Format the output ONLY as a comma-separated list of hashtags, each starting with '#'. Do not include any other text, introduction, numbering, or explanation. Example: #hashtag1,#hashtag2,#hashtag3

Topic/Description: "{context}"

Hashtags:
"""
    try:
        response_text = _run_gemini_generation(prompt, context="Hashtag Generation")
        if response_text:
            # More robust parsing: handle extra spaces, ensure '#' prefix
            hashtags = [tag.strip() for tag in response_text.split(',') if tag.strip().startswith('#')]
            return hashtags[:count] # Return only the requested count
        else:
            return [] # Return empty list if response was empty but no error
    except GeminiError as e:
        print(f"Hashtag generation failed: {e}")
        raise # Let processing_manager handle the callback with the error

def generate_tags_with_gemini(context: str, count: int) -> Optional[List[str]]:
    """Generates relevant YouTube video tags (keywords) using Gemini."""
    if not context: raise ValueError("Context (topic/description) cannot be empty.")
    if count <= 0: return []

    prompt = f"""Generate a list of exactly {count} relevant YouTube video tags (keywords or short phrases) for a short video about the following topic/description.
These tags help YouTube categorize the video. They should be specific and descriptive. Lowercase is preferred.
Format the output ONLY as a comma-separated list of tags. Do not include hashtags (#) or any other text, introduction, numbering, or explanation. Example: keyword one,keyword two,short phrase

Topic/Description: "{context}"

Tags:
"""
    try:
        response_text = _run_gemini_generation(prompt, context="Tag Generation")
        if response_text:
            # Parse comma-separated list, remove empty strings, strip whitespace, lowercase
            tags = [tag.strip().lower() for tag in response_text.split(',') if tag.strip()]
            return tags[:count]
        else:
            return [] # Return empty list if response was empty but no error
    except GeminiError as e:
        print(f"Tag generation failed: {e}")
        raise # Let processing_manager handle the callback with the error

def generate_titles_with_gemini(context: str, count: int) -> Optional[List[str]]:
    """Generates potential YouTube video title ideas using Gemini."""
    if not context: raise ValueError("Context (topic/description) cannot be empty.")
    if count <= 0: return []

    prompt = f"""Generate exactly {count} engaging and click-worthy YouTube video title ideas for a short vertical video about the following topic/description.
The titles should be concise and suitable for platforms like YouTube Shorts.
Format the output ONLY as a numbered list, with each title on a new line. Do not include any other text, introduction, or explanation. Example:
1. Title Idea One
2. Another Great Title

Topic/Description: "{context}"

Titles:
"""
    try:
        response_text = _run_gemini_generation(prompt, context="Title Generation")
        if response_text:
            # Parse numbered list (handle variations), strip whitespace
            titles = []
            for line in response_text.splitlines():
                 # Remove leading numbers/punctuation/spaces more robustly
                 cleaned_line = re.sub(r"^\s*\d+[\.\)\-:]?\s*", "", line).strip()
                 if cleaned_line:
                     titles.append(cleaned_line)
            # If parsing failed to find enough lines, maybe the format was wrong?
            if not titles: print(f"AI Utils WARN (Titles): Could not parse titles from response:\n{response_text}")
            return titles[:count] # Return requested count
        else:
            return [] # Return empty list if response was empty but no error
    except GeminiError as e:
        print(f"Title generation failed: {e}")
        raise # Let processing_manager handle the callback with the error