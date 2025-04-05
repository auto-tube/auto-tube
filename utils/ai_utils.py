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

# --- Configure Gemini API ---
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
gemini_model = None
GEMINI_CONFIGURED = False

if GOOGLE_API_KEY:
    try:
        print("AI Utils: Configuring Google Gemini API...")
        genai.configure(api_key=GOOGLE_API_KEY)
        MODEL_NAME = 'gemini-1.5-flash-latest' # Use a capable text generation model
        gemini_model = genai.GenerativeModel(MODEL_NAME)
        print(f"AI Utils: Google Gemini API configured successfully with model '{MODEL_NAME}'.")
        GEMINI_CONFIGURED = True
    except Exception as e:
        print(f"AI Utils ERROR: Failed to configure Google Gemini API: {e}")
        gemini_model = None
        GEMINI_CONFIGURED = False
else:
    print("AI Utils WARNING: GOOGLE_API_KEY environment variable not set. AI features will fail.")
    gemini_model = None
    GEMINI_CONFIGURED = False

# --- Generation Config & Safety --- (Can be shared)
DEFAULT_GENERATION_CONFIG = genai.types.GenerationConfig(
    max_output_tokens=800, # Allow more tokens for lists
    temperature=0.7,
)
DEFAULT_SAFETY_SETTINGS={
    'HARM_CATEGORY_HARASSMENT': 'block_medium_and_above',
    'HARM_CATEGORY_HATE_SPEECH': 'block_medium_and_above',
    'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'block_medium_and_above',
    'HARM_CATEGORY_DANGEROUS_CONTENT': 'block_medium_and_above',
}

# --- Helper to Run Generation ---
def _run_gemini_generation(prompt: str, context: str = "Generating metadata") -> Optional[str]:
    """Internal helper to run the Gemini API call and handle basic errors."""
    if not GEMINI_CONFIGURED or not gemini_model:
        raise GeminiError("Gemini API model not initialized.")

    try:
        print(f"AI Utils ({context}): Sending prompt (first 100 chars): '{prompt[:100]}...'")
        response = gemini_model.generate_content(
            prompt,
            generation_config=DEFAULT_GENERATION_CONFIG,
            safety_settings=DEFAULT_SAFETY_SETTINGS
        )
        print(f"AI Utils ({context}): Received response.")

        if not response.candidates:
             block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else "Unknown"
             raise GeminiError(f"Generation blocked by safety settings. Reason: {block_reason}")

        if response.text:
             return response.text.strip()
        else:
             # Check parts as fallback
             if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                 return "".join(part.text for part in response.candidates[0].content.parts).strip()
             else:
                 finish_reason = response.candidates[0].finish_reason.name if response.candidates else "UNKNOWN"
                 raise GeminiError(f"Generation finished but returned no text content. Finish Reason: {finish_reason}")

    except Exception as e:
        print(f"AI Utils ERROR ({context}): Error during Gemini API call: {type(e).__name__} - {e}")
        # Don't print full traceback here, let the caller handle it if needed
        # traceback.print_exc()
        # Re-raise as specific error type
        raise GeminiError(f"Failed during {context}: {e}") from e


# --- Script Generation Function ---
def generate_script_with_gemini(prompt: str) -> Optional[str]:
    """Generates a short video script using Gemini."""
    if not prompt: raise ValueError("Prompt cannot be empty.")
    full_prompt = f"""Generate a concise script suitable for a short vertical video (like YouTube Shorts) based on the following idea/niche.
The script should be engaging and easy to speak naturally.
Format the output with short paragraphs or sentences, each on a NEW LINE.

Idea/Niche: "{prompt}"

SCRIPT:
"""
    return _run_gemini_generation(full_prompt, context="Script Generation")


# --- NEW Metadata Generation Functions ---

def generate_hashtags_with_gemini(context: str, count: int) -> Optional[List[str]]:
    """Generates relevant hashtags using Gemini."""
    if not context: raise ValueError("Context (topic/description) cannot be empty.")
    if count <= 0: return []

    prompt = f"""Generate a list of exactly {count} relevant and effective hashtags for a short vertical video (like YouTube Shorts/TikTok) about the following topic/description.
Format the output as a comma-separated list of hashtags, each starting with '#'. Do not include any other text, introduction, or explanation.

Topic/Description: "{context}"

Hashtags:
"""
    try:
        response_text = _run_gemini_generation(prompt, context="Hashtag Generation")
        if response_text:
            # Parse the comma-separated list, remove empty strings, strip whitespace
            hashtags = [tag.strip() for tag in response_text.split(',') if tag.strip().startswith('#')]
            # Return only the requested count, even if API gave more/less
            return hashtags[:count]
        else:
            return None
    except GeminiError as e:
        print(f"Hashtag generation failed: {e}")
        return None # Return None on API error

def generate_tags_with_gemini(context: str, count: int) -> Optional[List[str]]:
    """Generates relevant YouTube video tags (keywords) using Gemini."""
    if not context: raise ValueError("Context (topic/description) cannot be empty.")
    if count <= 0: return []

    prompt = f"""Generate a list of exactly {count} relevant YouTube video tags (keywords or short phrases) for a short video about the following topic/description.
These tags help YouTube categorize the video. They should be specific and descriptive.
Format the output as a comma-separated list of tags. Do not include hashtags (#) or any other text, introduction, or explanation.

Topic/Description: "{context}"

Tags:
"""
    try:
        response_text = _run_gemini_generation(prompt, context="Tag Generation")
        if response_text:
            # Parse comma-separated list, remove empty strings, strip whitespace
            tags = [tag.strip() for tag in response_text.split(',') if tag.strip()]
            return tags[:count]
        else:
            return None
    except GeminiError as e:
        print(f"Tag generation failed: {e}")
        return None

def generate_titles_with_gemini(context: str, count: int) -> Optional[List[str]]:
    """Generates potential YouTube video title ideas using Gemini."""
    if not context: raise ValueError("Context (topic/description) cannot be empty.")
    if count <= 0: return []

    prompt = f"""Generate exactly {count} engaging and click-worthy YouTube video title ideas for a short vertical video about the following topic/description.
The titles should be concise and suitable for platforms like YouTube Shorts.
Format the output as a numbered list, with each title on a new line. Do not include any other text, introduction, or explanation.

Topic/Description: "{context}"

Titles:
"""
    try:
        response_text = _run_gemini_generation(prompt, context="Title Generation")
        if response_text:
            # Parse numbered list (handle potential variations like "1.", "1)", "1 - ")
            # Split by newline, remove numbering and whitespace
            titles = []
            for line in response_text.splitlines():
                 cleaned_line = re.sub(r"^\s*\d+[\.\)-]?\s*", "", line).strip() # Remove numbering
                 if cleaned_line:
                     titles.append(cleaned_line)
            return titles[:count] # Return requested count
        else:
            return None
    except GeminiError as e:
        print(f"Title generation failed: {e}")
        return None