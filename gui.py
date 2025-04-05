# gui.py
import os
from typing import List, Optional
from xml.etree.ElementPath import ops # Note: ops from xml.etree seems unused, maybe leftover?
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk # ttk added for Style
import threading
import time
from tkinterdnd2 import * # Requires pip install tkinterdnd2-universal or similar
import traceback # For detailed error printing
import sys
import random # Keep random

# --- Import components from new structure ---
# Use try-except for robustness, especially during development/setup
MODULE_IMPORTS_OK = False
PROCESS_MANAGER_LOADED = False
UI_TABS_LOADED = False
VIDEO_PROCESSOR_LOADED = False
AI_UTILS_LOADED = False
try:
    from ui.ui_tabs import ClippingTab, AIShortTab, MetadataTab # Added MetadataTab import
    UI_TABS_LOADED = True
    from core.processing_manager import (run_clipping_queue, run_ai_short_generation,
                                         run_gemini_script_generation, run_gemini_metadata_generation) # Added metadata func
    PROCESS_MANAGER_LOADED = True
    from utils.video_processor import FFmpegNotFoundError
    VIDEO_PROCESSOR_LOADED = True
    from utils.ai_utils import GeminiError
    AI_UTILS_LOADED = True
    MODULE_IMPORTS_OK = PROCESS_MANAGER_LOADED and UI_TABS_LOADED and VIDEO_PROCESSOR_LOADED and AI_UTILS_LOADED
    print("GUI: Core modules imported successfully.")
except ImportError as e:
    print(f"ERROR [GUI Import]: Failed to import application modules: {e}")
    print("Defining dummy placeholders...")
    # --- CORRECTED DUMMY DEFINITIONS ---
    if not UI_TABS_LOADED:
        class ClippingTab(ctk.CTkFrame): pass
        class AIShortTab(ctk.CTkFrame): pass
        class MetadataTab(ctk.CTkFrame): pass
    if not PROCESS_MANAGER_LOADED:
        def run_clipping_queue(*args, **kwargs): print("Error: Clipping processing module not loaded")
        def run_ai_short_generation(*args, **kwargs): print("Error: AI Short processing module not loaded")
        def run_gemini_script_generation(*args, **kwargs): print("Error: Script Gen processing module not loaded")
        def run_gemini_metadata_generation(*args, **kwargs): print("Error: Metadata Gen processing module not loaded")
    if not VIDEO_PROCESSOR_LOADED:
        class FFmpegNotFoundError(Exception): pass
    if not AI_UTILS_LOADED:
        class GeminiError(Exception): pass
    # --- END CORRECTION ---
# --- End Imports ---


class VideoClipperApp:
    """ Main application class """
    def __init__(self, root: TkinterDnD.Tk):
        self.root = root
        self.theme = "dark"
        # State Flags
        self.is_processing = False; self.is_generating_short = False; self.is_generating_script = False
        self.is_generating_hashtags = False; self.is_generating_tags = False; self.is_generating_titles = False
        # Thread Refs
        self.processing_thread = None; self.generation_thread = None; self.script_gen_thread = None
        self.hashtag_gen_thread = None; self.tag_gen_thread = None; self.title_gen_thread = None
        # Data
        self.video_queue = []

        if MODULE_IMPORTS_OK:
            try:
                self._configure_root()
                self._create_variables()
                self._create_ui()
                self._apply_treeview_theme_tags() # Apply initial theme
                self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
                print("VideoClipperApp initialized successfully.")
            except Exception as e: self._show_init_error(e)
        else: self._show_import_error()

    def _show_import_error(self):
        self.root.title("Autotube - Load Error"); self.root.geometry("600x200")
        ctk.CTkLabel(self.root, text="FATAL ERROR: Failed to load application modules.\nCheck console, project structure, __init__.py files,\nand venv dependencies.",
                     text_color="red", font=ctk.CTkFont(size=14), wraplength=550).pack(pady=40, padx=20)
        print("GUI ERROR: Cannot start due to import errors.")

    def _show_init_error(self, error):
         self.root.title("Autotube - Init Error"); self.root.geometry("600x200")
         ctk.CTkLabel(self.root, text=f"FATAL ERROR during GUI init.\n\n{type(error).__name__}: {error}\n\nCheck console.",
                      text_color="red", font=ctk.CTkFont(size=14)).pack(pady=40, padx=20)
         print(f"GUI ERROR: Init failed: {error}"); traceback.print_exc()

    def _configure_root(self):
        ctk.set_appearance_mode(self.theme); ctk.set_default_color_theme("blue")
        self.root.title("Autotube: Clip Master & AI Content Tools"); self.root.geometry("1200x850"); self.root.minsize(1000, 800)

    def _create_variables(self):
        print("GUI: Creating UI variables..."); self.input_path_var = tk.StringVar(); self.output_path_var = tk.StringVar()
        self.min_clip_length_var = tk.IntVar(value=15); self.max_clip_length_var = tk.IntVar(value=45)
        self.scene_threshold_var = tk.DoubleVar(value=30.0); self.clip_count_var = tk.IntVar(value=5)
        self.scene_detect_var = tk.BooleanVar(value=False); self.remove_audio_var = tk.BooleanVar(value=False)
        self.extract_audio_var = tk.BooleanVar(value=True); self.vertical_crop_var = tk.BooleanVar(value=True)
        self.mirror_var = tk.BooleanVar(value=False); self.enhance_var = tk.BooleanVar(value=True)
        self.batch_mode_var = tk.BooleanVar(value=False)
        self.ai_video_path_var = tk.StringVar(); self.ai_output_path_var = tk.StringVar()
        self.ai_script_prompt_var = tk.StringVar(); self.ai_polly_voice_var = tk.StringVar(value="Joanna") # Default example
        self.ai_font_size_var = tk.IntVar(value=24)
        self.metadata_context_var = None # This seems unused - context is retrieved directly from textbox
        self.metadata_hashtag_count_var = tk.IntVar(value=10); self.metadata_tag_count_var = tk.IntVar(value=15); self.metadata_title_count_var = tk.IntVar(value=5)
        self.progress_var = tk.DoubleVar(value=0.0); self.status_var = tk.StringVar(value="Status: Idle"); self.remaining_time_var = tk.StringVar(value="Est. Time Remaining: N/A")
        print("GUI: UI variables created.")

    def _create_ui(self):
        print("GUI: Creating main UI layout..."); self.main_frame = ctk.CTkFrame(self.root); self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        progress_frame = ctk.CTkFrame(self.main_frame); progress_frame.pack(fill="x", padx=5, pady=(5, 10))
        ctk.CTkLabel(progress_frame, text="Progress:", anchor="w").pack(side="left", padx=5)
        self.progress_bar = ctk.CTkProgressBar(progress_frame, variable=self.progress_var); self.progress_bar.pack(side="left", fill="x", expand=True, pady=5, padx=5)
        ctk.CTkLabel(progress_frame, textvariable=self.remaining_time_var, width=180, anchor="e").pack(side="right", padx=5)
        self.tab_view = ctk.CTkTabview(self.main_frame, anchor="nw"); self.tab_view.pack(fill="both", expand=True, padx=5, pady=0)
        self.tab_view.add("Video Clipper"); self.tab_view.add("AI Short Generator"); self.tab_view.add("Metadata Tools")
        print("GUI: Tabs added."); print("GUI: Creating Clipping Tab content..."); self.clipping_tab = ClippingTab(master=self.tab_view.tab("Video Clipper"), app_logic=self); self.clipping_tab.pack(fill="both", expand=True)
        print("GUI: Creating AI Short Tab content..."); self.ai_short_tab = AIShortTab(master=self.tab_view.tab("AI Short Generator"), app_logic=self); self.ai_short_tab.pack(fill="both", expand=True)
        print("GUI: Creating Metadata Tab content..."); self.metadata_tab = MetadataTab(master=self.tab_view.tab("Metadata Tools"), app_logic=self); self.metadata_tab.pack(fill="both", expand=True)
        print("GUI: All Tab content created."); status_frame = ctk.CTkFrame(self.root, height=25); status_frame.pack(side="bottom", fill="x", padx=10, pady=(5, 10))
        ctk.CTkLabel(status_frame, textvariable=self.status_var, anchor="w").pack(side="left", padx=10); print("GUI: Status bar created."); print("GUI: Main UI creation complete.")

    # --- Action Methods ---
    def _select_input(self):
        print("GUI Action: Browse input."); added_count = 0
        try:
            if self.batch_mode_var.get():
                path = filedialog.askdirectory(title="Select Folder Containing Videos")
                paths = None # Clear paths if folder selected
            else:
                path = None # Clear path if files selected
                paths = filedialog.askopenfilenames(title="Select Video File(s)", filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv *.wmv *.flv"), ("All Files", "*.*")])

            if path and os.path.isdir(path): # Process folder
                files_in_folder = [f for f in os.listdir(path) if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv"))]
                if not files_in_folder:
                    messagebox.showwarning("No Videos", f"No video files found in the selected folder:\n{path}")
                    return # Exit if no videos found
                for file in files_in_folder:
                     fp = os.path.join(path, file)
                     if fp not in self.video_queue:
                         self.video_queue.append(fp)
                         added_count += 1
                if added_count > 0:
                    self.input_path_var.set(f"Folder: ...{os.path.basename(path)} ({added_count} added)")
            elif paths: # Process selected files
                for p in paths:
                    if p not in self.video_queue:
                        self.video_queue.append(p)
                        added_count += 1
                if added_count > 0:
                    self.input_path_var.set(os.path.basename(paths[0]) if len(self.video_queue) == 1 else f"{len(self.video_queue)} files in queue")
                    # Update display based on total queue length

            if added_count > 0:
                self._update_queue_display()
                print(f"GUI: Added {added_count} video(s) to queue. Total: {len(self.video_queue)}")
            elif not path and not paths:
                 print("GUI: No input selected.") # No selection made
            # No warning needed if folder/files were selected but all were duplicates

        except OSError as e: messagebox.showerror("Folder Error", f"Could not read the selected folder:\n{e}")
        except Exception as e: messagebox.showerror("Input Selection Error", f"An unexpected error occurred during input selection:\n{e}"); traceback.print_exc()

    def _drop_input(self, event):
        print(f"GUI Action: Drop. Data: {event.data}"); added_count = 0; first_name = ""
        try:
            # splitlist correctly handles paths with spaces, potentially enclosed in {}
            items = self.root.tk.splitlist(event.data)
            dropped_files = []
            for item in items:
                item_path = item.strip('{}') # Remove potential curly braces
                if os.path.isdir(item_path):
                    try:
                        print(f"GUI Drop: Processing folder: {item_path}")
                        found_in_folder = False
                        for file in os.listdir(item_path):
                            if file.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv")):
                                fp = os.path.join(item_path, file)
                                dropped_files.append(fp)
                                found_in_folder = True
                        if not found_in_folder: print(f"GUI Drop: No video files found in folder {item_path}")
                    except OSError as e: print(f"Warn: Could not read dropped folder {item_path}: {e}")
                elif os.path.isfile(item_path) and item_path.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv")):
                     print(f"GUI Drop: Processing file: {item_path}")
                     dropped_files.append(item_path)
                else:
                     print(f"GUI Drop: Ignoring non-video item: {item_path}")

            # Add unique files to queue
            for fp in dropped_files:
                if fp not in self.video_queue:
                    self.video_queue.append(fp)
                    added_count += 1
                    if not first_name: first_name = os.path.basename(fp)

            if added_count > 0:
                self._update_queue_display()
                display_text = first_name if len(self.video_queue) == 1 else f"{len(self.video_queue)} files in queue"
                self.input_path_var.set(display_text)
                print(f"GUI Drop: Added {added_count} video(s). Total queue: {len(self.video_queue)}")
            else:
                print("GUI Drop: No new video files added from drop.")
                if not self.video_queue: # If queue was empty and drop added nothing new
                    self.input_path_var.set("")


        except Exception as e: messagebox.showerror("Drop Error", f"Failed to process dropped items:\n{e}"); traceback.print_exc()

    def _select_output(self):
        print("GUI Action: Select output."); path = filedialog.askdirectory(title="Select Output Folder");
        if path: self.output_path_var.set(path)

    def _clear_queue(self):
        print("GUI Action: Clear queue.");
        if self.is_processing: messagebox.showwarning("Busy", "Cannot clear the queue while processing."); return
        if not self.video_queue: return # Nothing to clear
        if messagebox.askyesno("Confirm Clear", f"Are you sure you want to remove all {len(self.video_queue)} videos from the queue?"):
            self.video_queue = []
            self._update_queue_display()
            self.input_path_var.set("") # Clear input path display too
            print("Queue cleared.")

    def _toggle_processing(self):
        if self.is_processing:
            print("GUI Action: Stop clipping requested.")
            # Set flag, thread checks this flag
            self.is_processing = False
            # Update UI immediately for responsiveness
            self._update_button_state()
            self.status_var.set("Status: Stopping clipping...")
            # The thread itself will call _processing_complete when it actually stops
        else:
            print("GUI Action: Start clipping requested.")
            self._start_clipping_processing()

    def _start_clipping_processing(self):
        """Validates inputs and starts the clipping thread."""
        if not MODULE_IMPORTS_OK: messagebox.showerror("Module Error", "Core processing modules are not loaded correctly. Cannot start."); return
        if self.is_generating_short or self.is_generating_script or self.is_processing or self.is_generating_hashtags or self.is_generating_tags or self.is_generating_titles:
             messagebox.showwarning("Busy", "Another process (AI generation or clipping) is already running."); return

        out_path = self.output_path_var.get()
        if not out_path or not os.path.isdir(out_path): messagebox.showerror("Output Error", "Please select a valid output folder first."); return
        if not self.video_queue: messagebox.showerror("Input Error", "The video clipping queue is empty. Please add videos."); return

        try:
            min_len = self.min_clip_length_var.get()
            max_len = self.max_clip_length_var.get()
            clip_count = self.clip_count_var.get()
            scene_thresh = self.scene_threshold_var.get()

            if min_len <= 0 or max_len <= 0: raise ValueError("Clip lengths must be positive.")
            if min_len > max_len: raise ValueError("Minimum clip length cannot be greater than maximum clip length.")
            if clip_count <= 0: raise ValueError("Number of clips must be positive.")
            if self.scene_detect_var.get() and (scene_thresh <= 0 or scene_thresh > 100): raise ValueError("Scene threshold must be between 0 and 100.")

            # Create options dict *inside* try after validation passes
            options = {
                "clip_count": clip_count,
                "min_clip_length": min_len,
                "max_clip_length": max_len,
                "scene_detect": self.scene_detect_var.get(),
                "scene_threshold": scene_thresh,
                "remove_audio": self.remove_audio_var.get(),
                "extract_audio": self.extract_audio_var.get(),
                "vertical_crop": self.vertical_crop_var.get(),
                "mirror": self.mirror_var.get(),
                "enhance": self.enhance_var.get(),
            }
        except (tk.TclError, ValueError) as e:
            messagebox.showerror("Input Error", f"Invalid value for a clipping option: {e}\nPlease check the settings in the 'Video Clipper' tab.")
            return # Stop if options invalid

        self.is_processing = True
        self._update_button_state()
        self.progress_var.set(0)
        self.remaining_time_var.set("Est. Time: Calculating...")
        self.status_var.set("Status: Starting clipping process...")

        queue_copy = list(self.video_queue) # Process a copy
        update_progress_cb = lambda index, total, start_t: self.root.after(0, self._update_progress_bar, index, total, start_t)
        update_status_cb = lambda status_text: self.root.after(0, self.status_var.set, status_text)
        # Pass a mutable dict for the thread to communicate back if it was stopped
        processing_state_ref = {'active': True}
        completion_cb = lambda p_type, p_count, e_count, t_count, state_ref: self.root.after(0, self._processing_complete, p_type, p_count, e_count, t_count, state_ref)

        # Pass 'ops' if it's actually needed by run_clipping_queue, otherwise remove it.
        # Currently seems unused based on import statement. Assuming it's needed for now.
        self.processing_thread = threading.Thread(
            target=run_clipping_queue,
            args=(queue_copy, out_path, options, update_progress_cb, update_status_cb, completion_cb, processing_state_ref),
            daemon=True
        )
        self.processing_thread.start()
        print(f"GUI: Clipping thread started for {len(queue_copy)} videos.")

    def _start_script_generation(self):
        """Validates prompt and starts Gemini script generation thread."""
        print("GUI Action: Generate script requested.")
        if not MODULE_IMPORTS_OK or not AI_UTILS_LOADED: messagebox.showerror("Module Error", "AI or Processing modules not loaded correctly."); return
        if self.is_processing or self.is_generating_short or self.is_generating_script or self.is_generating_hashtags or self.is_generating_tags or self.is_generating_titles:
            messagebox.showwarning("Busy", "Another process is already running."); return

        prompt_text = self.ai_script_prompt_var.get().strip()
        if not prompt_text: messagebox.showerror("Input Error", "Please enter a niche or topic idea in the prompt box."); return

        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key: messagebox.showerror("API Key Error", "GOOGLE_API_KEY environment variable is not set.\nPlease configure it to use AI features."); return

        try:
            # Check if Gemini is configured within the loaded module
            from utils.ai_utils import GEMINI_CONFIGURED
            if not GEMINI_CONFIGURED:
                 raise ImportError("Gemini configuration flag is False.")
        except (ImportError, NameError, AttributeError):
            messagebox.showerror("API Config Error", "Google Gemini API is not configured correctly within the application.\nCheck ai_utils.py and API key setup."); return

        self.is_generating_script = True
        self._update_button_state()
        self.status_var.set("Status: Generating script via Gemini...")
        self.progress_var.set(0) # No specific progress for this
        self.remaining_time_var.set("Est. Time: N/A")

        print("GUI: Starting Gemini script generation thread...")
        # Callback to handle the result (script or error) in the main thread
        finish_script_cb = lambda script, error: self.root.after(0, self._script_generation_complete, script, error)

        self.script_gen_thread = threading.Thread(
            target=run_gemini_script_generation,
            args=(prompt_text, finish_script_cb),
            daemon=True
        )
        self.script_gen_thread.start()

    def _start_metadata_generation(self, metadata_type: str):
        """Generic function to start generation for hashtags, tags, or titles."""
        print(f"GUI Action: Generate {metadata_type} requested.")
        valid_types = ['hashtags', 'tags', 'titles']
        if metadata_type not in valid_types:
            print(f"Error: Invalid metadata type requested: {metadata_type}")
            messagebox.showerror("Internal Error", f"Invalid metadata type: {metadata_type}")
            return

        if not MODULE_IMPORTS_OK or not AI_UTILS_LOADED: messagebox.showerror("Module Error", "AI or Processing modules not loaded correctly."); return
        if self.is_processing or self.is_generating_short or self.is_generating_script or self.is_generating_hashtags or self.is_generating_tags or self.is_generating_titles:
            messagebox.showwarning("Busy", "Another process is already running."); return

        context_text = ""
        state_flag_attr = f"is_generating_{metadata_type}"
        count_var_attr = f"metadata_{metadata_type.rstrip('s')}_count_var" # e.g., metadata_hashtag_count_var
        thread_attr = f"{metadata_type.rstrip('s')}_gen_thread" # e.g., hashtag_gen_thread

        # Get context from the correct tab's textbox
        if hasattr(self, 'metadata_tab') and hasattr(self.metadata_tab, 'context_textbox'):
            try:
                context_text = self.metadata_tab.context_textbox.get("1.0", "end-1c").strip()
            except Exception as e:
                print(f"Error getting context text from metadata tab: {e}")
                messagebox.showerror("Internal UI Error", "Could not access the context text box in the Metadata tab.")
                return
        else:
            messagebox.showerror("Internal UI Error", "Metadata tab or its context text box not found.")
            return

        if not context_text:
            messagebox.showerror("Input Error", "Please enter a topic, description, or script text in the 'Context' box for the AI.")
            return

        # Get the count for the specific metadata type
        try:
            count = 0
            if hasattr(self, count_var_attr):
                count_var = getattr(self, count_var_attr)
                count = count_var.get()
                if count <= 0: raise ValueError("Count must be a positive number.")
            else:
                raise AttributeError(f"Count variable '{count_var_attr}' not found in app.")
        except (AttributeError, tk.TclError, ValueError) as e:
            messagebox.showerror("Input Error", f"Invalid count value for {metadata_type.capitalize()}: {e}\nPlease check the settings in the 'Metadata Tools' tab.")
            return

        # Check API Key and Gemini Config (same as script gen)
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key: messagebox.showerror("API Key Error", "GOOGLE_API_KEY environment variable is not set."); return
        try:
            from utils.ai_utils import GEMINI_CONFIGURED
            if not GEMINI_CONFIGURED: raise ImportError("Gemini configuration flag is False.")
        except (ImportError, NameError, AttributeError):
            messagebox.showerror("API Config Error", "Google Gemini API is not configured correctly."); return

        # Set state and update UI
        setattr(self, state_flag_attr, True)
        self._update_button_state()
        self.status_var.set(f"Status: Generating {metadata_type.capitalize()} via Gemini...")
        self.progress_var.set(0)
        self.remaining_time_var.set("Est. Time: N/A")

        print(f"GUI: Starting Gemini {metadata_type} generation thread...")
        # Callback to handle the result in the main thread
        finish_meta_cb = lambda m_type, r_list, err: self.root.after(0, self._metadata_generation_complete, m_type, r_list, err)

        # Start the thread
        gen_thread = threading.Thread(
            target=run_gemini_metadata_generation,
            args=(metadata_type, context_text, count, finish_meta_cb),
            daemon=True
        )
        setattr(self, thread_attr, gen_thread)
        gen_thread.start()

    # --- Specific starters call the generic one ---
    def _start_hashtag_generation(self):
        self._start_metadata_generation('hashtags')

    def _start_tag_generation(self):
        self._start_metadata_generation('tags')

    def _start_title_generation(self):
        self._start_metadata_generation('titles')

    # --- *** CORRECTED INDENTATION FOR THIS METHOD *** ---
    def _apply_ai_short_generation(self):
         """Validates inputs and starts the AI short generation thread."""
         print("GUI Action: Generate AI Short requested.");
         if not MODULE_IMPORTS_OK: messagebox.showerror("Module Error", "Core processing modules not loaded."); return
         if self.is_processing or self.is_generating_short or self.is_generating_script or self.is_generating_hashtags or self.is_generating_tags or self.is_generating_titles:
              messagebox.showwarning("Busy", "Another process is already running."); return

         # --- Input Validation ---
         video_path = self.ai_video_path_var.get()
         output_dir = self.ai_output_path_var.get()
         script_text = ""

         # Get script text from the AI Short Tab's textbox
         if hasattr(self, 'ai_short_tab') and hasattr(self.ai_short_tab, 'script_textbox'):
             try:
                 script_text = self.ai_short_tab.script_textbox.get("1.0", "end-1c").strip()
             except Exception as e:
                 print(f"Error getting script text from AI short tab: {e}")
                 messagebox.showerror("Internal UI Error", "Could not access the script text box in the AI Short Generator tab.")
                 return
         else:
             messagebox.showerror("Internal UI Error", "AI Short Generator tab or its script text box not found.")
             return

         try:
             font_size = self.ai_font_size_var.get()
             if font_size <= 0: raise ValueError("Font size must be positive.")
         except (tk.TclError, ValueError):
             messagebox.showerror("Input Error", "Invalid font size specified. Please enter a positive number.")
             return

         polly_voice = self.ai_polly_voice_var.get()

         if not video_path or not os.path.isfile(video_path): messagebox.showerror("Input Error", "Please select a valid background video file."); return
         if not output_dir or not os.path.isdir(output_dir): messagebox.showerror("Input Error", "Please select a valid output folder location."); return
         if not script_text: messagebox.showerror("Input Error", "The AI script text box is empty. Please generate or paste a script."); return
         if not polly_voice: messagebox.showerror("Input Error", "Please select an AI Voice (e.g., Polly voice)."); return # Check if TTS is configured?

         # --- Prepare Output Path ---
         base_name = os.path.basename(video_path)
         name, _ = os.path.splitext(base_name)
         # Add timestamp and random element to avoid collisions
         output_filename = f"{name}_AI_Short_{int(time.time())}_{random.randint(100,999)}.mp4"
         final_output_path = os.path.join(output_dir, output_filename)

         if os.path.exists(final_output_path):
             if not messagebox.askyesno("Confirm Overwrite", f"The output file:\n'{output_filename}'\nalready exists in the output directory.\n\nOverwrite it?"):
                 print("GUI: AI Short generation cancelled by user (overwrite).")
                 return

         # --- Prepare Temp Directory ---
         ai_temp_dir = os.path.join(output_dir, f"temp_ai_{int(time.time())}_{random.randint(100,999)}")
         try:
             os.makedirs(ai_temp_dir, exist_ok=True)
             print(f"GUI: Created temporary directory: {ai_temp_dir}")
         except OSError as e:
             messagebox.showerror("Directory Error", f"Could not create temporary directory for AI processing:\n{ai_temp_dir}\nError: {e}")
             self._reset_generation_state() # Reset button etc. if dir creation fails
             return

         # --- Start Generation Thread ---
         self.is_generating_short = True
         self._update_button_state()
         self.progress_var.set(0)
         self.remaining_time_var.set("Est. Time: Starting...")
         self.status_var.set("Status: Starting AI short generation...")
         print("GUI: Starting AI short generation thread...")

         ai_options = {
             'polly_voice': polly_voice,
             'font_size': font_size
             # Add other AI options here if needed
         }
         update_progress_cb = lambda index, total, start_t: self.root.after(0, self._update_progress_bar, index, total, start_t)
         update_status_cb = lambda status_text: self.root.after(0, self.status_var.set, status_text)
         processing_state_ref = {'active': True} # For potential stop functionality if added later
         completion_cb = lambda p_type, p_count, e_count, t_count, state_ref: self.root.after(0, self._processing_complete, p_type, p_count, e_count, t_count, state_ref)

         self.generation_thread = threading.Thread(
              target=run_ai_short_generation,
              args=(script_text, video_path, final_output_path, ai_temp_dir, ai_options, update_progress_cb, update_status_cb, completion_cb, processing_state_ref),
              daemon=True
         )
         self.generation_thread.start()

    # --- Callback Methods ---
    def _update_progress_bar(self, index, total_items, start_time):
        # Guard against updates after process completion/stop
        # Check *specific* flag if possible, or a general 'any busy' flag
        is_busy = self.is_processing or self.is_generating_short # Add other flags if they use this bar
        if not is_busy: return

        try:
            if total_items <= 0: # Avoid division by zero
                self.progress_var.set(0.0)
                self.remaining_time_var.set("Est. Time: N/A")
                return

            elapsed_time = time.time() - start_time
            # Ensure progress is between 0 and 1. Index is 0-based.
            progress_percent = ((index + 1) / total_items)
            self.progress_var.set(max(0.0, min(1.0, progress_percent)))

            # Calculate remaining time only if some progress made and time elapsed
            if index < total_items - 1 and elapsed_time > 1 and (index + 1) > 0:
                time_per_item = elapsed_time / (index + 1)
                remaining_items = total_items - (index + 1)
                remaining_time_sec = time_per_item * remaining_items
                minutes, seconds = divmod(int(remaining_time_sec), 60)
                self.remaining_time_var.set(f"Est. Time: {minutes}m {seconds}s")
            elif index >= total_items - 1:
                # Process is finishing or finished according to index
                self.remaining_time_var.set("Est. Time: Finishing...")
            else: # Very beginning or calculation not stable yet
                self.remaining_time_var.set("Est. Time: Calculating...")
        except Exception as e:
            print(f"Error updating progress bar: {e}")
            # Optionally reset display if error occurs
            # self.progress_var.set(0.0)
            # self.remaining_time_var.set("Est. Time: Error")

    def _processing_complete(self, process_type, processed_count, error_count, total_items, processing_state_from_thread):
        print(f"GUI Callback: Processing complete reported for: {process_type}")
        was_stopped_manually = not processing_state_from_thread.get('active', False) # Check if thread was told to stop

        # Reset the specific state flag
        if process_type == "Clipping":
            self.is_processing = False
            # Clear the queue only if clipping finished (stopped or completed)
            self.video_queue = []
            self._update_queue_display()
            self.input_path_var.set("") # Clear input display after queue is cleared
        elif process_type == "AI Short Generation":
            self.is_generating_short = False
            # Consider cleaning up the temp AI dir here if needed

        self._update_button_state() # Update buttons now that state is reset

        # Determine message based on outcome
        if was_stopped_manually:
            completion_message = f"{process_type} process was stopped by the user."
            if process_type == "Clipping":
                 completion_message += f"\nProcessed: {processed_count}, Errors: {error_count}, Skipped: {total_items - processed_count - error_count}"
            self.status_var.set(f"Status: Idle. {process_type} stopped.")
            messagebox.showinfo(f"{process_type} Stopped", completion_message)
        else:
            # Process completed naturally
            completion_message = f"{process_type} process finished."
            if total_items > 0: # Provide counts if items were processed
                 completion_message += f"\nTotal items: {total_items}, Succeeded: {processed_count}, Errors: {error_count}"

            if error_count > 0:
                status_end = f"finished with {error_count} error(s)."
                self.status_var.set(f"Status: Idle. {process_type} {status_end}")
                messagebox.showwarning(f"{process_type} Finished with Errors", completion_message + "\nCheck console/logs for details.")
            else:
                status_end = "finished successfully."
                self.status_var.set(f"Status: Idle. {process_type} {status_end}")
                messagebox.showinfo(f"{process_type} Complete", completion_message)

        # Final UI state for progress bar
        self.progress_var.set(1.0 if not was_stopped_manually and total_items > 0 else 0.0) # Full bar on success, 0 if stopped early
        self.remaining_time_var.set("Est. Time: Done")

    def _script_generation_complete(self, generated_script: Optional[str], error: Optional[Exception]):
        print("GUI Callback: Script generation complete.");
        self.is_generating_script = False;
        self._update_button_state()

        if error:
            error_type = type(error).__name__
            error_msg = f"Script generation failed ({error_type}):\n{error}"
            print(f"GUI ERROR: {error_msg}")
            self.status_var.set("Status: Script generation failed!")
            # Show specific error types if useful
            if isinstance(error, GeminiError): # Or specific API errors
                 messagebox.showerror("Gemini API Error", f"Error generating script:\n{error}")
            else:
                 messagebox.showerror("Script Generation Error", error_msg[:1000]) # Limit length
        elif generated_script:
            self.status_var.set("Status: Idle. Script generated successfully.")
            print("GUI: Populating AI Short tab script textbox.")
            if hasattr(self, 'ai_short_tab') and hasattr(self.ai_short_tab, 'script_textbox'):
                 try:
                     textbox = self.ai_short_tab.script_textbox
                     textbox.configure(state="normal") # Enable before modifying
                     textbox.delete("1.0", "end")
                     textbox.insert("1.0", generated_script)
                     textbox.configure(state="disabled") # Disable again if it should be read-only
                     messagebox.showinfo("Script Generated", "AI script generated and placed in the 'AI Short Generator' tab.")
                 except Exception as e:
                     messagebox.showerror("UI Error", f"Failed to update script textbox: {e}")
                     print(f"--- Generated Script (UI Error) ---\n{generated_script}\n--- End Script ---")
            else:
                 # Fallback if UI elements not found
                 print(f"--- Generated Script (UI Not Found) ---\n{generated_script}\n--- End Script ---")
                 messagebox.showwarning("Script Generated", "Script generated successfully (see console), but could not update the UI textbox.")
        else:
            # No error, but script is empty/None
            self.status_var.set("Status: Idle. AI returned an empty script.")
            messagebox.showwarning("Empty Script", "The AI returned an empty or invalid script. Try refining your prompt.")

    def _metadata_generation_complete(self, metadata_type: str, result_list: Optional[List[str]], error: Optional[Exception]):
        print(f"GUI Callback: Metadata generation complete for: {metadata_type}")
        state_flag_attr = f"is_generating_{metadata_type}"
        setattr(self, state_flag_attr, False) # Reset the specific flag
        self._update_button_state()

        if error:
            error_type = type(error).__name__
            error_msg = f"Failed to generate {metadata_type} ({error_type}):\n{error}"
            print(f"GUI ERROR: {error_msg}")
            self.status_var.set(f"Status: {metadata_type.capitalize()} generation failed!")
            if isinstance(error, GeminiError):
                 messagebox.showerror("Gemini API Error", f"Error generating {metadata_type}:\n{error}")
            else:
                 messagebox.showerror(f"{metadata_type.capitalize()} Generation Error", error_msg[:1000])
        elif result_list and len(result_list) > 0:
            self.status_var.set(f"Status: Idle. {metadata_type.capitalize()} generated successfully.")
            print(f"GUI: Populating {metadata_type} output box.")
            if hasattr(self, 'metadata_tab'):
                 # Determine the correct output widget based on type
                 output_widget_attr = f"{metadata_type.rstrip('s')}_output_box" # e.g., hashtag_output_box
                 if hasattr(self.metadata_tab, output_widget_attr):
                     output_widget = getattr(self.metadata_tab, output_widget_attr)
                     # Ensure it's a Textbox before manipulating
                     if isinstance(output_widget, ctk.CTkTextbox):
                         try:
                             output_text = "\n".join(result_list) # Join list items with newlines
                             output_widget.configure(state="normal") # Enable writing
                             output_widget.delete("1.0", "end")
                             output_widget.insert("1.0", output_text)
                             output_widget.configure(state="disabled") # Make read-only again
                             print(f"GUI: Displayed {len(result_list)} generated {metadata_type}.")
                         except Exception as e:
                             messagebox.showerror("UI Error", f"Failed to update {metadata_type} output box: {e}")
                             print(f"--- Generated {metadata_type} (UI Error) ---\n{result_list}\n--- End ---")
                     else:
                         print(f"Error: Target widget '{output_widget_attr}' in MetadataTab is not a CTkTextbox.")
                         messagebox.showerror("Internal UI Error", f"Could not display {metadata_type}: Output area is not configured correctly.")
                 else:
                     print(f"Error: MetadataTab is missing the output widget attribute '{output_widget_attr}'.")
                     messagebox.showerror("Internal UI Error", f"Could not display {metadata_type}: Output area not found.")
            else:
                 print("Error: MetadataTab instance not found in the main app.")
                 messagebox.showerror("Internal Error", "Cannot access the Metadata tab to display results.")
        else:
            # No error, but result list is empty or None
            self.status_var.set(f"Status: Idle. AI returned no {metadata_type}.")
            messagebox.showwarning(f"Empty Results", f"The AI did not return any {metadata_type} based on the provided context.")


    # --- Helper Methods ---
    def _update_queue_display(self):
        # Check if clipping_tab exists and is a valid widget before calling its method
        if hasattr(self, 'clipping_tab') and isinstance(self.clipping_tab, ctk.CTkFrame) and self.clipping_tab.winfo_exists():
             if hasattr(self.clipping_tab, 'update_queue_display'):
                 try:
                     self.clipping_tab.update_queue_display(self.video_queue)
                     print(f"GUI Helper: Updated queue display. Count: {len(self.video_queue)}")
                 except Exception as e:
                     print(f"Error calling update_queue_display on ClippingTab: {e}")
             else:
                 print("Warn: ClippingTab has no 'update_queue_display' method.")
        # else:
            # print("Debug: ClippingTab not ready for queue display update.") # Optional debug

    def _update_button_state(self):
        """ Disables/Enables buttons based on the application's processing state. """
        any_busy = (self.is_processing or self.is_generating_short or self.is_generating_script or
                    self.is_generating_hashtags or self.is_generating_tags or self.is_generating_titles)
        print(f"GUI Helper: Updating button states. Any busy: {any_busy}") # Debug print

        # --- Clipping Button ---
        try:
            if hasattr(self, 'clipping_tab') and hasattr(self.clipping_tab, 'start_stop_button'):
                btn = self.clipping_tab.start_stop_button
                if btn and btn.winfo_exists():
                    if self.is_processing:
                        # Currently processing: Show Stop button, enabled
                        btn.configure(text="Stop Clipping", fg_color="red", hover_color="#C40000", state="normal")
                    elif any_busy:
                         # Another process is busy: Disable start button
                         btn.configure(text="Start Clipping Queue", state="disabled")
                    else:
                        # Idle: Show Start button, enabled (green)
                        btn.configure(text="Start Clipping Queue", fg_color="green", hover_color="darkgreen", state="normal")
        except Exception as e: print(f"Error updating Clipping Button state: {e}")

        # --- Script Generation Button ---
        try:
            if hasattr(self, 'ai_short_tab') and hasattr(self.ai_short_tab, 'generate_script_button'):
                btn = self.ai_short_tab.generate_script_button
                if btn and btn.winfo_exists():
                    if self.is_generating_script:
                        # Generating script: Show "Generating...", disabled
                        btn.configure(text="Generating Script...", state="disabled")
                    elif any_busy:
                         # Another process busy: Disable generate button
                         btn.configure(text="Generate Script with Gemini", state="disabled")
                    else:
                        # Idle: Show normal text, enabled, default colors
                         fg, hc = ctk.ThemeManager.theme["CTkButton"]["fg_color"], ctk.ThemeManager.theme["CTkButton"]["hover_color"]
                         btn.configure(text="Generate Script with Gemini", state="normal", fg_color=fg, hover_color=hc) # Use theme default
        except Exception as e: print(f"Error updating Script Gen Button state: {e}")

        # --- AI Short Generation Button ---
        try:
            if hasattr(self, 'ai_short_tab') and hasattr(self.ai_short_tab, 'generate_button'):
                btn = self.ai_short_tab.generate_button
                if btn and btn.winfo_exists():
                    if self.is_generating_short:
                        # Generating short: Show "Generating...", disabled
                        btn.configure(text="Generating AI Short...", state="disabled")
                    elif any_busy:
                         # Another process busy: Disable generate button
                         btn.configure(text="Generate AI Short", state="disabled")
                    else:
                        # Idle: Show normal text, enabled, default colors
                         fg, hc = ctk.ThemeManager.theme["CTkButton"]["fg_color"], ctk.ThemeManager.theme["CTkButton"]["hover_color"]
                         btn.configure(text="Generate AI Short (using Script Text)", state="normal", fg_color=fg, hover_color=hc)
        except Exception as e: print(f"Error updating AI Short Gen Button state: {e}")

        # --- Metadata Buttons ---
        try:
            if hasattr(self, 'metadata_tab'):
                 for meta_type in ['hashtag', 'tag', 'title']:
                     btn_attr = f'generate_{meta_type}_button'
                     # Adjust state flag name to match definition (plural)
                     busy_flag_attr = f'is_generating_{meta_type}s' # e.g., is_generating_hashtags
                     btn = getattr(self.metadata_tab, btn_attr, None)

                     if btn and btn.winfo_exists():
                         is_this_meta_busy = getattr(self, busy_flag_attr, False)
                         if is_this_meta_busy:
                             # This specific metadata type is generating
                             btn.configure(text=f"Generating {meta_type.capitalize()}s...", state="disabled")
                         elif any_busy:
                              # Another process (but not this one) is busy
                              btn.configure(text=f"Generate {meta_type.capitalize()}s", state="disabled")
                         else:
                              # Idle
                              btn.configure(text=f"Generate {meta_type.capitalize()}s", state="normal")
        except Exception as e: print(f"Error updating metadata button states: {e}")


    def _change_theme(self, new_theme):
        print(f"GUI: Changing theme to: {new_theme}"); valid_themes = ["dark", "light", "system"]; theme_lower = new_theme.lower()
        if theme_lower not in valid_themes: print(f"Warn: Invalid theme '{new_theme}'. Using system default."); theme_lower = "system"
        ctk.set_appearance_mode(theme_lower); self.theme = theme_lower # Store current theme

        # Update components that might need explicit theme changes
        try: # Update Spinboxes in all relevant tabs
            if hasattr(self, 'clipping_tab') and self.clipping_tab.winfo_exists():
                 if hasattr(self.clipping_tab, 'apply_spinbox_theme_tags'): self.clipping_tab.apply_spinbox_theme_tags(self.theme)
            if hasattr(self, 'ai_short_tab') and self.ai_short_tab.winfo_exists():
                 if hasattr(self.ai_short_tab, 'apply_spinbox_theme_tags'): self.ai_short_tab.apply_spinbox_theme_tags(self.theme)
            if hasattr(self, 'metadata_tab') and self.metadata_tab.winfo_exists():
                 if hasattr(self.metadata_tab, 'apply_spinbox_theme_tags'): self.metadata_tab.apply_spinbox_theme_tags(self.theme)
        except Exception as e: print(f"Warn: Could not update Spinbox theme colors: {e}")

        # Apply theme to Treeview (which uses ttk styles)
        self._apply_treeview_theme_tags()

    def _apply_treeview_theme_tags(self):
        # Check if clipping_tab exists and has the necessary method
        if hasattr(self, 'clipping_tab') and hasattr(self.clipping_tab, 'apply_treeview_theme_tags') and self.clipping_tab.winfo_exists():
             try:
                 self.clipping_tab.apply_treeview_theme_tags(self.theme)
                 print(f"GUI Helper: Applied theme '{self.theme}' to Treeview.")
             except Exception as e:
                  print(f"Error applying theme tags to Treeview: {e}")
        # else:
             # print("Debug: ClippingTab or its theme method not ready for Treeview theming.") # Optional debug

    # --- Reset State Methods (mostly used internally or for error recovery) ---
    def _reset_processing_state(self):
        print("GUI Helper: Resetting clipping processing state.")
        self.is_processing = False
        if self.processing_thread and self.processing_thread.is_alive():
            # Ideally, the thread checks the flag, but this is a hard reset
            print("Warn: Forcing processing state reset while thread might be active.")
        self._update_button_state()
        self.status_var.set("Status: Idle")
        self.progress_var.set(0)
        self.remaining_time_var.set("Est. Time: N/A")

    def _reset_generation_state(self):
        print("GUI Helper: Resetting AI short generation state.")
        self.is_generating_short = False
        if self.generation_thread and self.generation_thread.is_alive():
            print("Warn: Forcing generation state reset while thread might be active.")
        self._update_button_state()
        self.status_var.set("Status: Idle")
        self.progress_var.set(0)
        self.remaining_time_var.set("Est. Time: N/A")

    def _reset_script_gen_state(self):
        print("GUI Helper: Resetting script generation state.")
        self.is_generating_script = False
        if self.script_gen_thread and self.script_gen_thread.is_alive():
             print("Warn: Forcing script gen state reset while thread might be active.")
        self._update_button_state()
        self.status_var.set("Status: Idle")

    def _reset_metadata_gen_state(self, meta_type):
        # meta_type should be 'hashtags', 'tags', or 'titles'
        state_flag_attr = f"is_generating_{meta_type}"
        thread_attr = f"{meta_type.rstrip('s')}_gen_thread"
        print(f"GUI Helper: Resetting {meta_type} generation state.")
        setattr(self, state_flag_attr, False)
        thread = getattr(self, thread_attr, None)
        if thread and thread.is_alive():
             print(f"Warn: Forcing {meta_type} gen state reset while thread might be active.")
        self._update_button_state()
        self.status_var.set("Status: Idle")


    def _on_closing(self):
        print("GUI: Close button clicked.");
        # Check all processing/generation flags
        process_running = (self.is_processing or self.is_generating_short or self.is_generating_script or
                           self.is_generating_hashtags or self.is_generating_tags or self.is_generating_titles)

        if process_running:
            if messagebox.askyesno("Confirm Exit", "A background process is still running.\nExiting now will terminate it abruptly.\n\nAre you sure you want to exit?"):
                print("GUI: User confirmed exit while process running. Terminating.")
                # Set flags to false (though threads might not see this immediately before termination)
                self.is_processing=False
                self.is_generating_short=False
                self.is_generating_script=False
                self.is_generating_hashtags=False
                self.is_generating_tags=False
                self.is_generating_titles=False
                # Force destroy the window, which should stop daemon threads eventually
                self.root.destroy()
            else:
                print("GUI: Exit cancelled by user.")
        else:
            print("GUI: Exiting normally.");
            self.root.destroy()


# --- Main Execution ---
def main():
    """Main function to run the application."""
    root = None
    try:
        # Initialize TkinterDnD root window
        root = TkinterDnD.Tk()
        print("Root TkinterDnD window created.")
    except Exception as e:
        print(f"FATAL ERROR: Failed to create the main TkinterDnD root window: {e}")
        traceback.print_exc()
        # Attempt to show a basic Tk error message if possible
        try:
            import tkinter as tk
            error_root = tk.Tk()
            error_root.withdraw() # Hide the empty root window
            messagebox.showerror("Startup Error", f"Failed to initialize application window components.\nError: {e}\n\nSee console for details.")
            error_root.destroy()
        except Exception as tk_err:
             print(f"Could not even show a Tk error message: {tk_err}")
        return # Stop execution if root window fails

    # Proceed only if root window creation was successful
    if root:
        if MODULE_IMPORTS_OK:
            try:
                app = VideoClipperApp(root)
                print("Starting application main event loop...")
                root.mainloop()
                print("Application main event loop finished.")
            except Exception as app_e:
                print(f"FATAL ERROR during application execution: {app_e}")
                traceback.print_exc()
                messagebox.showerror("Fatal Application Error", f"A critical error occurred during application runtime:\n\n{app_e}\n\nSee console for details.")
                # Try to destroy root if it exists
                try: root.destroy()
                except: pass
        else:
            # Modules failed to import, app couldn't be fully initialized
            # The _show_import_error method should have configured the root window already
            print("GUI cannot start fully due to import errors. Displaying error window.")
            root.mainloop() # Show the error window created by _show_import_error
            print("Error window closed.")
    else:
         # This case should technically not be reached if the initial try/except worked,
         # but included for completeness.
         print("GUI could not start because the root window was not created.")


if __name__ == "__main__":
    logger = None
    try:
        # Attempt to use the structured logger
        from utils.logger_config import setup_logging
        logger = setup_logging()
        logger.info(f"--- Autotube App Start --- Python Version: {sys.version.split()[0]}, OS: {sys.platform} ---")
    except ImportError:
        # Fallback to basic logging if logger_config is missing or fails
        import logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        logging.warning("Structured logger not found or failed to import. Using basic logging.")
        logging.info(f"--- Autotube App Start (Basic Logging) --- Python Version: {sys.version.split()[0]}, OS: {sys.platform} ---")
    except Exception as log_e:
        # Catch any other error during logging setup
        print(f"CRITICAL ERROR setting up logging: {log_e}")
        traceback.print_exc()

    # Run the main application function
    main()
    print("--- Autotube App End ---")