# utils/subtitle_utils.py
import os
import traceback
import sys
import time
import random
from typing import List, Dict, Any, Optional

print("Loading subtitle_utils.py") # Debug print

# --- Time Formatting Helpers ---

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
        # Round centiseconds correctly
        centiseconds = int(round((total_seconds - int(total_seconds)) * 100))
        if centiseconds >= 100:
             total_seconds += 1 # Add a full second
             centiseconds = 0    # Reset centiseconds
        # Recalculate H, M, S from the potentially adjusted total_seconds
        hours, remainder = divmod(int(total_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02}:{seconds:02}.{centiseconds:02}"
    except Exception as e:
        print(f"Error formatting ASS time for {total_milliseconds}: {e}")
        return "0:00:00.00" # Fallback


# --- SRT Generation (from Polly marks - kept for potential alternative) ---
# This function is kept but currently unused by the main AI Short flow which uses ASS
def generate_srt_from_polly_speech_marks(parsed_speech_marks: List[Dict[str, Any]],
                                         output_srt_path: str,
                                         max_chars_per_line: int = 42,
                                         max_duration_sec: float = 7.0) -> bool:
    """
    Generates an SRT subtitle file from Polly word speech marks.
    Groups words into lines based on character limits and max duration.
    """
    print(f"SUB UTIL: Generating SRT from {len(parsed_speech_marks)} marks -> {output_srt_path}")
    if not parsed_speech_marks:
        print("SUB UTIL ERROR: No speech marks provided for SRT generation.")
        return False

    try:
        srt_entries = []
        current_line_text = []
        line_start_time_ms = -1
        line_end_time_ms = -1 # End time of the last word added
        subtitle_index = 1

        # Pre-process marks to estimate word end times
        marks_with_ends = []
        word_marks = [m for m in parsed_speech_marks if m.get('type') == 'word' and m.get('value')]
        if not word_marks:
             print("SUB UTIL ERROR: No valid 'word' type speech marks found.")
             return False

        for i, mark in enumerate(word_marks):
             start_ms = mark.get('time', 0)
             word_value = mark.get('value', '')
             # Estimate end as start of next word, or add default duration if last
             end_ms = start_ms + 750 # Default duration if last word
             for j in range(i + 1, len(word_marks)):
                 if word_marks[j].get('type') == 'word':
                     end_ms = word_marks[j].get('time', start_ms + 750)
                     break
             # Basic validation: end must be after start
             if end_ms <= start_ms: end_ms = start_ms + 100 # Ensure minimal duration
             marks_with_ends.append({'start': start_ms, 'end': end_ms, 'text': word_value})
        # --- End Pre-processing ---


        # --- Group words into lines ---
        for i, word_info in enumerate(marks_with_ends):
            word = word_info['text']
            start_ms = word_info['start']
            end_ms = word_info['end']

            # Skip noise/silence markers if present (adapt list if needed)
            if word.lower() in ["<sil>", "[noise]", "[laughter]", "", None]:
                if current_line_text: # Finalize previous line
                    start_ts = _seconds_to_srt_time(line_start_time_ms / 1000.0)
                    end_ts = _seconds_to_srt_time(line_end_time_ms / 1000.0)
                    srt_entries.append(f"{subtitle_index}\n{start_ts} --> {end_ts}\n{' '.join(current_line_text)}\n")
                    subtitle_index += 1
                    current_line_text = []
                    line_start_time_ms = -1
                continue # Move to next word

            # Start a new line if buffer is empty
            if not current_line_text:
                current_line_text.append(word)
                line_start_time_ms = start_ms
                line_end_time_ms = end_ms
                continue

            # Test adding the current word
            test_line = " ".join(current_line_text + [word])
            # Use end time of *current* word to check potential duration
            current_potential_duration_ms = (end_ms - line_start_time_ms) if line_start_time_ms >= 0 else (end_ms - start_ms)

            # Conditions to finalize the current subtitle line
            finalize_line = (
                len(test_line) > max_chars_per_line or
                (current_potential_duration_ms / 1000.0) > max_duration_sec
            )

            if finalize_line:
                # Finalize previous line (using end time of *last word added*)
                start_ts = _seconds_to_srt_time(line_start_time_ms / 1000.0)
                end_ts = _seconds_to_srt_time(line_end_time_ms / 1000.0)
                srt_entries.append(f"{subtitle_index}\n{start_ts} --> {end_ts}\n{' '.join(current_line_text)}\n")
                subtitle_index += 1
                # Start new line with current word
                current_line_text = [word]
                line_start_time_ms = start_ms
                line_end_time_ms = end_ms
            else:
                # Add word to current line
                current_line_text.append(word)
                line_end_time_ms = end_ms # Update end time to this word's end

        # Add the very last buffered line
        if current_line_text:
            start_ts = _seconds_to_srt_time(line_start_time_ms / 1000.0)
            end_ts = _seconds_to_srt_time(line_end_time_ms / 1000.0)
            srt_entries.append(f"{subtitle_index}\n{start_ts} --> {end_ts}\n{' '.join(current_line_text)}\n")
        # --- End Grouping ---


        # --- Write SRT File ---
        if not srt_entries:
             print("SUB UTIL WARNING: No subtitle entries generated.")
             return False

        with open(output_srt_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(srt_entries))

        print(f"SUB UTIL: SRT file generated successfully: {output_srt_path}")
        return True

    except Exception as e:
        print(f"SUB UTIL ERROR: Error generating SRT: {e}")
        traceback.print_exc()
        return False


# --- ASS Generation (from Polly marks) ---
def generate_ass_file_with_style(parsed_speech_marks: List[Dict[str, Any]],
                                 output_ass_path: str,
                                 font_size: int = 24,
                                 font_name: str = "Arial", # Default Font
                                 primary_color: str = "&H00FFFFFF&", # White (AABBGGRR)
                                 outline_color: str = "&H00000000&", # Black
                                 outline_width: float = 1.5,
                                 shadow: float = 0.8,
                                 alignment: int = 2, # 2 = BottomCenter
                                 margin_v: int = 25, # Vertical margin from edge
                                 max_chars_per_line: int = 42, # Approx max chars per visual line
                                 max_duration_sec: float = 7.0 # Max seconds per subtitle event
                                 ) -> bool:
    """
    Generates an ASS subtitle file from Polly word speech marks with basic styling.
    Groups words into lines, using {\\N} for line breaks within an event.

    Args:
        parsed_speech_marks: List of dicts from Polly {'time': ms, 'type': 'word', 'value': 'word'}
        output_ass_path: Path to save the .ass file.
        font_size: Font size.
        font_name: Font name (ensure available to FFmpeg/libass).
        primary_color: ASS color format (&HAABBGGRR& - White default).
        outline_color: ASS color format (&HAABBGGRR& - Black default).
        outline_width: Outline thickness.
        shadow: Shadow depth (usually 0-2).
        alignment: ASS alignment value (1-9, see ASS spec).
        margin_v: Vertical margin (pixels from edge, uses PlayResY).
        max_chars_per_line: Approx max chars before forcing a new visual line using {\\N}. <<-- CORRECTED DOCSTRING
        max_duration_sec: Approx max seconds before forcing a new subtitle event.

    Returns:
        True if successful, False otherwise.
    """
    print(f"SUB UTIL: Generating ASS from {len(parsed_speech_marks)} marks -> {output_ass_path}")
    if not parsed_speech_marks:
        print("SUB UTIL ERROR: No speech marks provided for ASS generation.")
        return False

    try:
        # --- ASS Header and Style Definition ---
        primary_color = primary_color if primary_color.startswith("&H") else "&H00FFFFFF&"
        outline_color = outline_color if outline_color.startswith("&H") else "&H00000000&"

        ass_header = f"""[Script Info]
Title: Generated by AutoTube AI Short
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_color},&H000000FF,&{outline_color},&H6A000000,0,0,0,0,100,100,0,0,1,{outline_width:.1f},{shadow:.1f},{alignment},25,25,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        ass_lines = [ass_header.strip()]

        # --- Pre-process marks (same as SRT version) ---
        marks_with_ends = []
        word_marks = [m for m in parsed_speech_marks if m.get('type') == 'word' and m.get('value')]
        if not word_marks: return False

        for i, mark in enumerate(word_marks):
             start_ms = mark.get('time', 0)
             word_value = mark.get('value', '')
             end_ms = start_ms + 750 # Default duration
             for j in range(i + 1, len(word_marks)):
                 if word_marks[j].get('type') == 'word':
                     end_ms = word_marks[j].get('time', start_ms + 750)
                     break
             if end_ms <= start_ms: end_ms = start_ms + 100
             marks_with_ends.append({'start': start_ms, 'end': end_ms, 'text': word_value})
        # --- End Pre-processing ---

        # --- Group words into ASS Dialogue lines ---
        current_visual_line_parts = [] # Words for the current visual line
        current_event_visual_lines = [] # List of visual lines (strings) for the current Dialogue event
        event_start_time_ms = -1
        event_last_word_end_time_ms = -1 # End time of the last word added to the *event*

        for i, word_info in enumerate(marks_with_ends):
            word = word_info['text']
            start_ms = word_info['start']
            end_ms = word_info['end']

            # Skip noise/silence markers
            if word.lower() in ["<sil>", "[noise]", "[laughter]", ""] or not word:
                if current_event_visual_lines or current_visual_line_parts: # Finalize event before silence
                    if current_visual_line_parts: current_event_visual_lines.append(" ".join(current_visual_line_parts))
                    if current_event_visual_lines:
                        start_ts = _ms_to_ass_time(event_start_time_ms)
                        end_ts = _ms_to_ass_time(event_last_word_end_time_ms)
                        event_text = "{\\N}".join(current_event_visual_lines) # Use ASS newline
                        ass_lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,25,25,{margin_v},,{event_text}")
                    current_visual_line_parts = []
                    current_event_visual_lines = []
                    event_start_time_ms = -1
                continue

            # Initialize start time for a new event
            if event_start_time_ms < 0:
                event_start_time_ms = start_ms

            # Test adding word to current visual line
            test_visual_line_len = len(" ".join(current_visual_line_parts + [word]))
            # Test event duration if this word is added
            current_event_duration_ms = (end_ms - event_start_time_ms)

            # --- Conditions to finalize the PREVIOUS event ---
            # Finalize if adding this word makes the *event* too long
            finalize_event = (
                (current_event_duration_ms / 1000.0) > max_duration_sec and (current_event_visual_lines or current_visual_line_parts)
            )

            if finalize_event:
                # Finish the previous event
                if current_visual_line_parts: current_event_visual_lines.append(" ".join(current_visual_line_parts))
                if current_event_visual_lines:
                    start_ts = _ms_to_ass_time(event_start_time_ms)
                    end_ts = _ms_to_ass_time(event_last_word_end_time_ms) # End of previous word
                    event_text = "{\\N}".join(current_event_visual_lines)
                    ass_lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,25,25,{margin_v},,{event_text}")

                # Reset for the new event starting with the current word
                current_visual_line_parts = [word]
                current_event_visual_lines = []
                event_start_time_ms = start_ms
                event_last_word_end_time_ms = end_ms
                continue

            # --- Conditions to force a new VISUAL line *within* the current event ---
            force_visual_newline = (
                 current_visual_line_parts and test_visual_line_len > max_chars_per_line
            )

            if force_visual_newline:
                # Add the completed visual line to the event's list
                current_event_visual_lines.append(" ".join(current_visual_line_parts))
                # Start a new visual line with the current word
                current_visual_line_parts = [word]
                event_last_word_end_time_ms = end_ms # Update overall event end time
            else:
                # Add word to the current visual line buffer
                current_visual_line_parts.append(word)
                event_last_word_end_time_ms = end_ms # Update overall event end time

        # --- Add the very last event ---
        if current_visual_line_parts: # Add the last buffered visual line
             current_event_visual_lines.append(" ".join(current_visual_line_parts))
        if current_event_visual_lines and event_start_time_ms >= 0: # If there's content for the last event
            start_ts = _ms_to_ass_time(event_start_time_ms)
            end_ts = _ms_to_ass_time(event_last_word_end_time_ms)
            event_text = "{\\N}".join(current_event_visual_lines) # Join visual lines
            ass_lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,25,25,{margin_v},,{event_text}")
        # --- End Grouping Logic ---

        # --- Write ASS File ---
        if len(ass_lines) <= 1: # Only header written
             print("SUB UTIL WARNING: No dialogue events generated for ASS file.")
             return False

        with open(output_ass_path, "w", encoding="utf-8") as f:
            # Join lines with standard OS newline for the file itself
            f.write(os.linesep.join(ass_lines))

        print(f"SUB UTIL: ASS file generated successfully: {output_ass_path}")
        return True

    except Exception as e:
        print(f"SUB UTIL ERROR: Error generating ASS file {output_ass_path}: {e}")
        traceback.print_exc()
        return False