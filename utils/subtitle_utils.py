# utils/subtitle_utils.py
import os
import traceback
import sys
import time
import random
from typing import List, Dict, Any, Optional

print("Loading subtitle_utils.py") # Debug print

# --- Time Formatting Helpers ---
# (Keep _seconds_to_srt_time and _ms_to_ass_time as they were)
def _seconds_to_srt_time(total_seconds: float) -> str:
    """Converts seconds to HH:MM:SS,mmm format for SRT."""
    if total_seconds < 0: total_seconds = 0
    try:
        milliseconds = int(round((total_seconds - int(total_seconds)) * 1000))
        if milliseconds >= 1000:
             total_seconds += 1
             milliseconds = 0
        hours, remainder = divmod(int(total_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"
    except Exception as e:
        print(f"Error formatting SRT time for {total_seconds}: {e}")
        return "00:00:00,000" # Fallback

def _ms_to_ass_time(total_milliseconds: int) -> str:
    """Converts milliseconds to H:MM:SS.cs format for ASS."""
    if total_milliseconds < 0: total_milliseconds = 0
    try:
        total_seconds = total_milliseconds / 1000.0
        centiseconds = int(round((total_seconds - int(total_seconds)) * 100))
        if centiseconds >= 100:
             total_seconds += 1
             centiseconds = 0
        hours, remainder = divmod(int(total_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02}:{seconds:02}.{centiseconds:02}"
    except Exception as e:
        print(f"Error formatting ASS time for {total_milliseconds}: {e}")
        return "0:00:00.00" # Fallback

# --- Helper for Formatting Lines ---
def _format_words_into_lines(words: List[str], max_chars: int) -> str:
    """
    Groups words into visual lines using ASS line break tag {\\N},
    respecting max character length per line.
    """
    if not words: return ""
    lines = []
    current_line_parts = []
    for word in words:
        test_line = " ".join(current_line_parts + [word])
        # Check if adding the word exceeds the character limit FOR THIS VISUAL LINE
        if current_line_parts and len(test_line) > max_chars:
            # Current visual line is full, add it to the list of lines
            lines.append(" ".join(current_line_parts))
            # Start a new visual line with the current word
            current_line_parts = [word]
        else:
            # Add word to the current visual line
            current_line_parts.append(word)
    # Add the last remaining line
    if current_line_parts:
        lines.append(" ".join(current_line_parts))

    # Join the visual lines with the ASS newline tag
    return "{\\N}".join(lines) # Use double backslash for literal \N in final string

# --- ASS Generation (from Polly marks) ---
def generate_ass_file_with_style(parsed_speech_marks: List[Dict[str, Any]],
                                 output_ass_path: str,
                                 # --- Style Arguments ---
                                 font_size: int = 48,        # << INCREASED DEFAULT SIZE
                                 font_name: str = "Arial", # Default Font
                                 primary_color: str = "&H00FFFFFF&", # White (AABBGGRR)
                                 outline_color: str = "&H00000000&", # Black
                                 outline_width: float = 2.0, # Slightly thicker outline
                                 shadow: float = 1.0,        # Slightly more shadow
                                 alignment: int = 5,         # << CHANGED DEFAULT TO 5 (MiddleCenter)
                                 margin_v: int = 40,         # Vertical margin (pixels from edge relative to alignment)
                                 # --- Grouping/Timing Arguments ---
                                 max_chars_per_visual_line: int = 30, # << REDUCED for center alignment
                                 max_duration_sec: float = 5.0,     # << REDUCED max duration slightly
                                 min_duration_ms: int = 500,        # Min time even a short sub is shown
                                 pause_threshold_ms: int = 400      # Force new sub after pause > this
                                 ) -> bool:
    """
    Generates an ASS subtitle file from Polly word speech marks with styling
    and improved word grouping logic. Default style is larger, centered text.

    Args:
        parsed_speech_marks: List of dicts from Polly {'time': ms, 'type': 'word', 'value': 'word'}
        output_ass_path: Path to save the .ass file.
        font_size, font_name, ... : Styling parameters for ASS.
        alignment: ASS alignment value (5=MiddleCenter).
        margin_v: Vertical margin (pixels from edge/center depending on Alignment).
        max_chars_per_visual_line: Approx max chars before forcing a new visual line using {\\N}.
        max_duration_sec: Max duration (seconds) for a single ASS subtitle event.
        min_duration_ms: Minimum display time (milliseconds) for any subtitle event.
        pause_threshold_ms: Gap between words (milliseconds) that forces a new subtitle event.

    Returns:
        True if successful, False otherwise.
    """
    print(f"SUB UTIL: Generating ASS from {len(parsed_speech_marks)} marks -> {output_ass_path}")
    if not parsed_speech_marks:
        print("SUB UTIL ERROR: No speech marks provided.")
        return False

    try:
        # --- ASS Header and Style Definition ---
        primary_color = primary_color if primary_color.startswith("&H") else "&H00FFFFFF&"
        outline_color = outline_color if outline_color.startswith("&H") else "&H00000000&"

        # Using alignment=5 (MiddleCenter) and increased FontSize
        ass_header = f"""[Script Info]
Title: Generated by AutoTube AI Short
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,&{outline_color},&H6A000000,0,0,0,0,100,100,0,0,1,{outline_width:.1f},{shadow:.1f},{alignment},25,25,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        ass_lines = [ass_header.strip()]

        # --- Pre-process marks (estimate end times) ---
        marks_with_ends = []
        word_marks = [m for m in parsed_speech_marks if m.get('type') == 'word' and m.get('value')]
        if not word_marks: return False

        for i, mark in enumerate(word_marks):
             start_ms = mark.get('time', 0)
             word_value = mark.get('value', '')
             end_ms = start_ms + 750 # Default
             for j in range(i + 1, len(word_marks)):
                 if word_marks[j].get('type') == 'word':
                     end_ms = word_marks[j].get('time', start_ms + 750)
                     break
             if end_ms <= start_ms: end_ms = start_ms + 100
             marks_with_ends.append({'start': start_ms, 'end': end_ms, 'text': word_value})
        # --- End Pre-processing ---

        # --- Group words into ASS Dialogue lines ---
        current_event_words = []        # Words collected for the current Dialogue event
        event_start_time_ms = -1
        last_word_end_time_ms = 0      # End time of the absolute previous word

        for i, word_info in enumerate(marks_with_ends):
            word = word_info['text']
            start_ms = word_info['start']
            end_ms = word_info['end']

            # Skip noise/silence markers
            if word.lower() in ["<sil>", "[noise]", "[laughter]", ""] or not word:
                if current_event_words: # Finalize previous event before silence
                    event_text_formatted = _format_words_into_lines(current_event_words, max_chars_per_visual_line)
                    start_ts = _ms_to_ass_time(event_start_time_ms)
                    event_duration_ms = event_last_word_end_time_ms - event_start_time_ms
                    final_end_time_ms = event_last_word_end_time_ms
                    if event_duration_ms < min_duration_ms:
                        final_end_time_ms = event_start_time_ms + min_duration_ms
                    end_ts = _ms_to_ass_time(final_end_time_ms)
                    ass_lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,25,25,{margin_v},,{event_text_formatted}")
                    current_event_words = []
                    event_start_time_ms = -1
                last_word_end_time_ms = end_ms # Update last end time even for silence
                continue

            # Initialize start time if needed
            if event_start_time_ms < 0: event_start_time_ms = start_ms

            # --- Conditions to finalize the PREVIOUS event ---
            pause_duration = start_ms - last_word_end_time_ms
            event_would_exceed_duration = ((end_ms - event_start_time_ms) / 1000.0) > max_duration_sec

            start_new_event = (
                current_event_words and # Only finalize if there's something to finalize
                (pause_duration > pause_threshold_ms or event_would_exceed_duration)
            )

            if start_new_event:
                # Finalize the previous event
                event_text_formatted = _format_words_into_lines(current_event_words, max_chars_per_visual_line)
                start_ts = _ms_to_ass_time(event_start_time_ms)
                event_duration_ms = event_last_word_end_time_ms - event_start_time_ms
                final_end_time_ms = event_last_word_end_time_ms
                if event_duration_ms < min_duration_ms: final_end_time_ms = event_start_time_ms + min_duration_ms
                end_ts = _ms_to_ass_time(final_end_time_ms)
                ass_lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,25,25,{margin_v},,{event_text_formatted}")
                # Reset for new event starting with current word
                current_event_words = [word]
                event_start_time_ms = start_ms
                event_last_word_end_time_ms = end_ms
            else:
                # Add word to current event buffer
                current_event_words.append(word)
                event_last_word_end_time_ms = end_ms # Update end time of current event

            # Update the absolute last word end time for next iteration's pause check
            last_word_end_time_ms = end_ms
        # --- End Main Word Loop ---

        # --- Add the very last event ---
        if current_event_words:
            event_text_formatted = _format_words_into_lines(current_event_words, max_chars_per_visual_line)
            start_ts = _ms_to_ass_time(event_start_time_ms)
            event_duration_ms = event_last_word_end_time_ms - event_start_time_ms
            final_end_time_ms = event_last_word_end_time_ms
            if event_duration_ms < min_duration_ms: final_end_time_ms = event_start_time_ms + min_duration_ms
            end_ts = _ms_to_ass_time(final_end_time_ms)
            ass_lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,25,25,{margin_v},,{event_text_formatted}")
        # --- End Grouping Logic ---

        # --- Write ASS File ---
        if len(ass_lines) <= 1: # Only header written
             print("SUB UTIL WARNING: No dialogue events generated for ASS file.")
             return False

        with open(output_ass_path, "w", encoding="utf-8") as f:
            f.write("\n".join(ass_lines))

        print(f"SUB UTIL: ASS file generated successfully: {output_ass_path}")
        return True

    except Exception as e:
        print(f"SUB UTIL ERROR: Error generating ASS file {output_ass_path}: {e}")
        traceback.print_exc()
        return False