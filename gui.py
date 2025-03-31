# gui.py
import os
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk # ttk added for Style
import threading
import time
from tkinterdnd2 import * # pip install tkinterdnd2-universal or specific version
import traceback # For detailed error printing
import sys

# --- Import components from new structure ---
# Use try-except for robustness, especially during development/setup
MODULE_IMPORTS_OK = False
PROCESS_MANAGER_LOADED = False
UI_TABS_LOADED = False
VIDEO_PROCESSOR_LOADED = False
try:
    # Import specific UI tab classes
    from ui.ui_tabs import ClippingTab, AIShortTab
    UI_TABS_LOADED = True
    # Import specific processing functions
    from core.processing_manager import run_clipping_queue, run_ai_short_generation
    PROCESS_MANAGER_LOADED = True
    # Import specific exceptions needed in this file
    from utils.video_processor import FFmpegNotFoundError
    VIDEO_PROCESSOR_LOADED = True
    MODULE_IMPORTS_OK = PROCESS_MANAGER_LOADED and UI_TABS_LOADED and VIDEO_PROCESSOR_LOADED
    print("GUI: Core modules imported successfully.")
except ImportError as e:
    print(f"ERROR [GUI Import]: Failed to import application modules: {e}")
    print("Please ensure core/, ui/, utils/ directories and their __init__.py files exist and contain the necessary code.")
    # Define dummy classes/functions if imports fail
    if not UI_TABS_LOADED:
        class ClippingTab(ctk.CTkFrame): pass
        class AIShortTab(ctk.CTkFrame): pass
    if not PROCESS_MANAGER_LOADED:
        def run_clipping_queue(*args, **kwargs): print("Error: Processing module not loaded")
        def run_ai_short_generation(*args, **kwargs): print("Error: Processing module not loaded")
    if not VIDEO_PROCESSOR_LOADED:
        class FFmpegNotFoundError(Exception): pass
# --- End Imports ---


class VideoClipperApp:
    """
    Main application class managing the GUI, application state,
    and interaction with background processing logic.
    """
    def __init__(self, root: TkinterDnD.Tk): # Type hint root window
        """Initialize the Video Clipper Application."""
        self.root = root
        self.theme = "dark" # Default theme: "dark", "light", "system"
        # --- Process State Flags ---
        self.is_processing = False      # Flag for clipping process active
        self.is_generating_short = False # Flag for AI short process active
        # --- Thread References ---
        self.processing_thread = None
        self.generation_thread = None
        # --- Data ---
        self.video_queue = [] # Holds full paths of videos for clipping queue

        # Only proceed if core modules loaded successfully during import
        if MODULE_IMPORTS_OK:
            try:
                self._configure_root()
                self._create_variables()
                self._create_ui()
                # Apply initial theme AFTER UI elements using ttk are created
                self._apply_treeview_theme_tags() # Applies theme to ClippingTab's Treeview
                # self._apply_spinbox_theme_tags()  # <<< --- REMOVED THIS LINE --- >>>

                # Bind window closing event
                self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
                print("VideoClipperApp initialized successfully.")
            except Exception as e:
                 # Catch errors during initialization
                 print("GUI ERROR: Failed during UI initialization.")
                 traceback.print_exc()
                 self._show_init_error(e)

        else:
            # If imports failed, show a simple error window
            self._show_import_error()

    def _show_import_error(self):
        """Displays an error message if initial module imports failed."""
        self.root.title("Autotube - Load Error")
        self.root.geometry("600x200")
        error_label = ctk.CTkLabel(self.root,
                      text="FATAL ERROR: Failed to load application modules.\n"
                           "Please check console output, project structure,\n"
                           "ensure __init__.py files exist in subdirs,\n"
                           "and ensure all dependencies are installed in the venv.",
                      text_color="red", font=ctk.CTkFont(size=14), wraplength=550)
        error_label.pack(pady=40, padx=20, expand=True, fill="both")
        print("GUI ERROR: Application cannot start due to import errors.")

    def _show_init_error(self, error):
         """Displays an error message if UI initialization fails."""
         self.root.title("Autotube - Initialization Error")
         self.root.geometry("600x200")
         error_label = ctk.CTkLabel(self.root,
                      text=f"FATAL ERROR: Failed during GUI initialization.\n\n{type(error).__name__}: {error}\n\n"
                           "Check console output for more details.",
                      text_color="red", font=ctk.CTkFont(size=14), wraplength=550)
         error_label.pack(pady=40, padx=20, expand=True, fill="both")
         print("GUI ERROR: Application cannot start due to initialization errors.")

    def _configure_root(self):
        """Configure the root window settings."""
        ctk.set_appearance_mode(self.theme)
        ctk.set_default_color_theme("blue") # Or "dark-blue", "green"
        self.root.title("Autotube: Clip Master & AI Short Generator")
        self.root.geometry("1200x800") # Initial size
        self.root.minsize(1000, 750)   # Minimum size

    def _create_variables(self):
        """Create and initialize all tkinter variables for UI options."""
        print("GUI: Creating UI variables...")
        # General Paths
        self.input_path_var = tk.StringVar()  # Displays last selected file/folder in Clipping tab input
        self.output_path_var = tk.StringVar() # Output for Clipping tab

        # Clipping Options
        self.min_clip_length_var = tk.IntVar(value=15)
        self.max_clip_length_var = tk.IntVar(value=45)
        self.scene_threshold_var = tk.DoubleVar(value=30.0)
        self.clip_count_var = tk.IntVar(value=5)
        self.scene_detect_var = tk.BooleanVar(value=False)
        self.remove_audio_var = tk.BooleanVar(value=False)
        self.extract_audio_var = tk.BooleanVar(value=True)
        self.vertical_crop_var = tk.BooleanVar(value=True)
        self.mirror_var = tk.BooleanVar(value=False)
        self.enhance_var = tk.BooleanVar(value=True)
        self.batch_mode_var = tk.BooleanVar(value=False) # For folder selection mode in Clipping tab

        # AI Short Generation Options
        self.ai_video_path_var = tk.StringVar() # Background video source for AI Short
        self.ai_output_path_var = tk.StringVar() # Output location for AI Short
        # ai_script_text is accessed via the widget directly in AIShortTab
        self.ai_polly_voice_var = tk.StringVar(value="Joanna") # Default Polly voice example
        self.ai_font_size_var = tk.IntVar(value=24)

        # Progress variables (used by status bar/progress bar)
        self.progress_var = tk.DoubleVar(value=0.0) # Range 0.0 to 1.0
        self.status_var = tk.StringVar(value="Status: Idle")
        self.remaining_time_var = tk.StringVar(value="Est. Time Remaining: N/A")
        print("GUI: UI variables created.")

    def _create_ui(self):
        """Create the main UI layout with TabView and Status Bar."""
        print("GUI: Creating main UI layout...")
        # Main container Frame
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Progress Bar Area (Above Tabs) ---
        progress_frame = ctk.CTkFrame(self.main_frame)
        progress_frame.pack(fill="x", padx=5, pady=(5, 10))
        ctk.CTkLabel(progress_frame, text="Progress:", anchor="w").pack(side="left", padx=5)
        # Store ref to progress bar
        self.progress_bar = ctk.CTkProgressBar(progress_frame, variable=self.progress_var)
        self.progress_bar.pack(side="left", fill="x", expand=True, pady=5, padx=5)
        ctk.CTkLabel(progress_frame, textvariable=self.remaining_time_var, width=180, anchor="e").pack(side="right", padx=5)

        # --- TabView ---
        self.tab_view = ctk.CTkTabview(self.main_frame, anchor="nw") # Anchor tabs top-left
        self.tab_view.pack(fill="both", expand=True, padx=5, pady=0)
        self.tab_view.add("Video Clipper")
        self.tab_view.add("AI Short Generator")
        print("GUI: Tabs added.")

        # --- Instantiate Tabs ---
        print("GUI: Creating Clipping Tab content...")
        self.clipping_tab = ClippingTab(master=self.tab_view.tab("Video Clipper"), app_logic=self)
        self.clipping_tab.pack(fill="both", expand=True)
        print("GUI: Clipping Tab content created.")

        print("GUI: Creating AI Short Tab content...")
        self.ai_short_tab = AIShortTab(master=self.tab_view.tab("AI Short Generator"), app_logic=self)
        self.ai_short_tab.pack(fill="both", expand=True)
        print("GUI: AI Short Tab content created.")

        # --- Status Bar (At the very bottom) ---
        status_frame = ctk.CTkFrame(self.root, height=25) # Use main root window
        status_frame.pack(side="bottom", fill="x", padx=10, pady=(5, 10))
        ctk.CTkLabel(status_frame, textvariable=self.status_var, anchor="w").pack(side="left", padx=10)
        print("GUI: Status bar created.")
        print("GUI: Main UI creation complete.")

    # --- Action Methods (Called by UI elements in Tabs, orchestrate core logic) ---

    def _select_input(self):
        """Handles 'Browse' button click for video/folder input (ClippingTab)."""
        print("GUI Action: Browse input.")
        added_count = 0
        try:
            if self.batch_mode_var.get():
                path = filedialog.askdirectory(title="Select Folder of Videos")
                if path:
                    for file in os.listdir(path):
                        # Check common video extensions
                        if file.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv")):
                            full_path = os.path.join(path, file)
                            if full_path not in self.video_queue:
                                self.video_queue.append(full_path)
                                added_count += 1
                    if added_count == 0: messagebox.showwarning("No Videos Found", "No supported video files found in the selected folder.")
                    self.input_path_var.set(f"Folder: ...{os.path.basename(path)}") # Show selected folder
            else:
                paths = filedialog.askopenfilenames(title="Select Video File(s)", filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv *.wmv *.flv"), ("All Files", "*.*")]) # Allow multiple files
                if paths:
                    for path in paths:
                        if path not in self.video_queue:
                            self.video_queue.append(path)
                            added_count += 1
                    if added_count > 0:
                        self.input_path_var.set(os.path.basename(paths[0]) if len(paths) == 1 else f"{len(paths)} files selected") # Display first path or count
                    # else: messagebox.showinfo("Info", "Selected video(s) already in queue.") # Avoid popup

            if added_count > 0: self._update_queue_display() # Update the treeview
        except OSError as e: messagebox.showerror("Error Reading Folder", f"Could not read folder contents:\n{e}")
        except Exception as e: messagebox.showerror("Error", f"Failed to select input:\n{e}"); traceback.print_exc()

    def _drop_input(self, event):
        """Handles drag & drop onto the input entry (ClippingTab)."""
        print(f"GUI Action: Input dropped. Data: {event.data}")
        try:
            # Use tk.splitlist for better handling of paths with spaces
            dropped_items = self.root.tk.splitlist(event.data)
            added_count = 0
            first_added_name = ""
            for item_path in dropped_items:
                item_path = item_path.strip('{}') # Remove potential braces from path
                print(f"  Processing dropped item: {item_path}")
                if os.path.isdir(item_path):
                    print(f"  Item is directory. Reading contents...")
                    try:
                        for file in os.listdir(item_path):
                            if file.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv")):
                                full_path = os.path.join(item_path, file)
                                if full_path not in self.video_queue:
                                    self.video_queue.append(full_path)
                                    added_count += 1
                                    if not first_added_name: first_added_name = os.path.basename(full_path)
                    except OSError as e: print(f"  Warning: Could not read dropped folder {item_path}: {e}")
                elif os.path.isfile(item_path) and item_path.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv")):
                    print(f"  Item is valid video file.")
                    if item_path not in self.video_queue:
                        self.video_queue.append(item_path)
                        added_count += 1
                        if not first_added_name: first_added_name = os.path.basename(item_path)
                # else: print(f"  Skipped non-video/non-folder item: {item_path}") # Debug

            if added_count > 0:
                 print(f"Added {added_count} items via drop.")
                 self._update_queue_display()
                 display_text = first_added_name if first_added_name else "Multiple Items"
                 if added_count > 1: display_text += f" + {added_count-1} more"
                 self.input_path_var.set(display_text)
            # else: No popup for no new files

        except Exception as e:
             messagebox.showerror("Drag & Drop Error", f"Failed to process dropped items:\n{e}")
             traceback.print_exc()

    def _select_output(self):
        """Handles 'Browse' for the main clipping output directory."""
        print("GUI Action: Select clipping output.")
        path = filedialog.askdirectory(title="Select Output Folder for Clips")
        if path:
            self.output_path_var.set(path)

    def _clear_queue(self):
        """Clears the video clipping queue."""
        print("GUI Action: Clear queue.")
        if self.is_processing: messagebox.showwarning("Busy", "Cannot clear queue while clipping."); return
        if not self.video_queue: return
        if messagebox.askyesno("Confirm Clear", f"Clear all {len(self.video_queue)} videos from queue?"):
            self.video_queue = []
            self._update_queue_display()
            print("Queue cleared.")

    def _toggle_processing(self):
        """Starts or stops the video clipping queue thread."""
        if self.is_processing:
            print("GUI Action: Stop clipping requested.")
            self.is_processing = False # Signal thread via mutable dict check
            # Visually update button immediately
            if hasattr(self, 'clipping_tab') and hasattr(self.clipping_tab, 'start_stop_button'):
                 self.clipping_tab.start_stop_button.configure(text="Stopping...", state="disabled")
            self.status_var.set("Status: Stopping after current video...")
        else:
            print("GUI Action: Start clipping requested.")
            self._start_clipping_processing()

    def _start_clipping_processing(self):
        """Validates inputs and starts the clipping thread."""
        if not MODULE_IMPORTS_OK: messagebox.showerror("Error", "Core modules not loaded."); return
        if self.is_generating_short: messagebox.showwarning("Busy", "AI Short generation running."); return

        output_path = self.output_path_var.get()
        if not output_path or not os.path.isdir(output_path): messagebox.showerror("Error", "Select valid clipping output folder."); return
        if not self.video_queue: messagebox.showerror("Error", "Clipping queue empty."); return

        try: # Validate options
            min_len = self.min_clip_length_var.get()
            max_len = self.max_clip_length_var.get()
            if min_len > max_len or min_len <= 0 or max_len <= 0: raise ValueError("Invalid min/max length")
            options = {
                "clip_count": self.clip_count_var.get(), "min_clip_length": min_len, "max_clip_length": max_len,
                "scene_detect": self.scene_detect_var.get(), "scene_threshold": self.scene_threshold_var.get(),
                "remove_audio": self.remove_audio_var.get(), "extract_audio": self.extract_audio_var.get(),
                "vertical_crop": self.vertical_crop_var.get(), "mirror": self.mirror_var.get(), "enhance": self.enhance_var.get(),
            }
        except (tk.TclError, ValueError) as e: messagebox.showerror("Input Error", f"Invalid clipping option: {e}"); return

        # --- Start Thread ---
        self.is_processing = True
        self._update_button_state()
        self.progress_var.set(0)
        self.remaining_time_var.set("Est. Time: Calculating...")
        self.status_var.set("Status: Starting clipping process...")
        print("GUI: Starting clipping thread...")

        queue_copy = list(self.video_queue)
        update_prog = lambda idx, total, start: self.root.after(0, self._update_progress_bar, idx, total, start)
        update_stat = lambda txt: self.root.after(0, self.status_var.set, txt)
        processing_state = {'active': True} # Mutable dict for stop signal
        finish_cb = lambda p_type, p_count, e_count, t_count, state: self.root.after(0, self._processing_complete, p_type, p_count, e_count, t_count, state) # Pass state

        self.processing_thread = threading.Thread(
            target=run_clipping_queue, # From core.processing_manager
            args=(queue_copy, output_path, options, update_prog, update_stat, finish_cb, processing_state),
            daemon=True)
        self.processing_thread.start()

    def _apply_ai_short_generation(self):
         """Validates inputs and starts the AI short generation thread."""
         print("GUI Action: Generate AI Short.")
         if not MODULE_IMPORTS_OK: messagebox.showerror("Error", "Core modules not loaded."); return
         if self.is_processing or self.is_generating_short: messagebox.showwarning("Busy", "Another process running."); return

         # Get inputs safely
         video_path = self.ai_video_path_var.get()
         output_dir = self.ai_output_path_var.get()
         script_text = ""
         # Safely access textbox content via the tab instance
         if hasattr(self, 'ai_short_tab') and hasattr(self.ai_short_tab, 'script_textbox') and self.ai_short_tab.script_textbox.winfo_exists():
             script_text = self.ai_short_tab.script_textbox.get("1.0", "end-1c").strip()
         else: messagebox.showerror("Internal Error", "Cannot access script text box."); return

         try: font_size = self.ai_font_size_var.get(); assert font_size > 0
         except (tk.TclError, ValueError, AssertionError): messagebox.showerror("Input Error", "Invalid font size."); return

         polly_voice = self.ai_polly_voice_var.get()

         # Validation
         if not video_path or not os.path.isfile(video_path): messagebox.showerror("Error", "Select valid background video."); return
         if not output_dir or not os.path.isdir(output_dir): messagebox.showerror("Error", "Select valid output location."); return
         if not script_text: messagebox.showerror("Error", "AI script text empty."); return
         if not polly_voice: messagebox.showerror("Error", "Select AI Voice."); return

         # Output path
         base_name = os.path.basename(video_path); name, _ = os.path.splitext(base_name)
         output_filename = f"{name}_AI_Short_{int(time.time())}.mp4"
         final_output_path = os.path.join(output_dir, output_filename)

         if os.path.exists(final_output_path):
             if not messagebox.askyesno("Overwrite?", f"Output file '{output_filename}' exists. Overwrite?"): return

         # --- Start Thread ---
         self.is_generating_short = True
         self._update_button_state()
         self.progress_var.set(0)
         self.remaining_time_var.set("Est. Time: N/A")
         self.status_var.set("Status: Starting AI short generation...")
         print("GUI: Starting AI short generation thread...")

         ai_options = { 'polly_voice': polly_voice, 'font_size': font_size }
         update_prog = lambda idx, total, start: self.root.after(0, self._update_progress_bar, idx, total, start)
         update_stat = lambda txt: self.root.after(0, self.status_var.set, txt)
         processing_state = {'active': True}
         finish_cb = lambda p_type, p_count, e_count, t_count, state: self.root.after(0, self._processing_complete, p_type, p_count, e_count, t_count, state)

         # Temp dir for intermediate AI files
         ai_temp_dir = os.path.join(output_dir, f"temp_ai_{int(time.time())}")
         try: os.makedirs(ai_temp_dir, exist_ok=True)
         except OSError as e: messagebox.showerror("Error", f"Could not create temp dir:\n{ai_temp_dir}\n{e}"); self._reset_generation_state(); return

         self.generation_thread = threading.Thread(
             target=run_ai_short_generation, # From core.processing_manager
             args=(script_text, video_path, final_output_path, ai_temp_dir, ai_options, update_prog, update_stat, finish_cb, processing_state),
             daemon=True)
         self.generation_thread.start()

    # --- Callback Methods (Called via root.after from threads) ---

    def _update_progress_bar(self, index, total_items, start_time):
        """Update progress bar and remaining time."""
        if not self.is_processing and not self.is_generating_short: return

        try:
            elapsed_time = time.time() - start_time
            progress_percent = ((index + 1) / total_items) if total_items > 0 else 0
            self.progress_var.set(max(0.0, min(1.0, progress_percent))) # Clamp 0-1

            if index < total_items - 1 and elapsed_time > 1 and (index + 1) > 0:
                time_per_item = elapsed_time / (index + 1)
                remaining_time_sec = time_per_item * (total_items - (index + 1))
                minutes, seconds = divmod(int(remaining_time_sec), 60)
                self.remaining_time_var.set(f"Est. Time: {minutes}m {seconds}s")
            elif index >= total_items - 1:
                 self.remaining_time_var.set("Est. Time: Finishing...")
            else: # Very beginning or invalid data
                 self.remaining_time_var.set("Est. Time: Calculating...")
        except Exception as e:
            print(f"Error updating progress bar: {e}")
            self.remaining_time_var.set("Est. Time: Error")

    def _processing_complete(self, process_type, processed_count, error_count, total_items, processing_state_from_thread):
        """Handle completion of either process."""
        print(f"GUI Callback: Processing complete for: {process_type}")
        # Check the state dict passed back from thread
        was_stopped = not processing_state_from_thread.get('active', False)

        # Reset the correct flag
        if process_type == "Clipping": self.is_processing = False
        elif process_type == "AI Short Generation": self.is_generating_short = False

        self._update_button_state() # Update buttons

        # Determine completion message
        if was_stopped:
             completion_message = f"{process_type} stopped by user.\n\nProcessed: {processed_count}\nErrors: {error_count}\nSkipped: {total_items - processed_count - error_count}"
             self.status_var.set(f"Status: Stopped.")
        else:
             completion_message = f"{process_type} finished.\n\nTotal Items: {total_items}\nSuccess: {processed_count}\nErrors: {error_count}"
             status_end = f"finished with {error_count} error(s)." if error_count > 0 else "finished successfully."
             self.status_var.set(f"Status: Idle. {process_type} {status_end}")

        self.progress_var.set(1.0) # Set to 100%
        self.remaining_time_var.set("Est. Time: Done")

        # Show final message box
        if error_count > 0 and not was_stopped: messagebox.showwarning(f"{process_type} Finished", completion_message)
        else: messagebox.showinfo(f"{process_type} Complete", completion_message)

        # Clear queue only for clipping process completion
        if process_type == "Clipping":
            self.video_queue = []
            self._update_queue_display()

    # --- Helper Methods ---

    def _update_queue_display(self):
        """Safely update queue Treeview in ClippingTab."""
        # Check if clipping_tab exists and is a valid widget before calling its method
        if hasattr(self, 'clipping_tab') and isinstance(self.clipping_tab, ctk.CTkFrame) and self.clipping_tab.winfo_exists():
             if hasattr(self.clipping_tab, 'update_queue_display'):
                 # Pass the current queue from the main app
                 self.clipping_tab.update_queue_display(self.video_queue)
             else: print("Warning: ClippingTab missing 'update_queue_display' method.")
        # else: print("Warning: ClippingTab not ready for queue display update.") # Debug if needed

    def _update_button_state(self):
        """Updates state/text of process control buttons on relevant tabs."""
        clipping_busy = self.is_processing
        ai_busy = self.is_generating_short
        any_busy = clipping_busy or ai_busy

        # Update Clipping Tab Button
        try:
            if hasattr(self, 'clipping_tab') and hasattr(self.clipping_tab, 'start_stop_button') and self.clipping_tab.start_stop_button.winfo_exists():
                 button = self.clipping_tab.start_stop_button
                 if clipping_busy: button.configure(text="Stop Clipping", fg_color="red", hover_color="#C40000", state="normal")
                 elif ai_busy: button.configure(text="Start Clipping Queue", state="disabled", fg_color="gray50", hover_color="gray40")
                 else: button.configure(text="Start Clipping Queue", fg_color="green", hover_color="darkgreen", state="normal")
        except Exception as e: print(f"Error updating clipping button state: {e}")

        # Update AI Short Tab Button
        try:
            if hasattr(self, 'ai_short_tab') and hasattr(self.ai_short_tab, 'generate_button') and self.ai_short_tab.generate_button.winfo_exists():
                 button = self.ai_short_tab.generate_button
                 if ai_busy: button.configure(text="Generating...", state="disabled")
                 elif clipping_busy: button.configure(text="Generate AI Short", state="disabled", fg_color="gray50", hover_color="gray40")
                 else:
                      # Reset to default enabled colors
                      fg_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
                      hover_color = ctk.ThemeManager.theme["CTkButton"]["hover_color"]
                      button.configure(text="Generate AI Short", state="normal", fg_color=fg_color, hover_color=hover_color)
        except Exception as e: print(f"Error updating AI short button state: {e}")

    def _change_theme(self, new_theme):
        """Change the theme of the application and update styles."""
        # Prevent changing theme while processing? Optional.
        # if self.is_processing or self.is_generating_short:
        #     messagebox.showwarning("Busy", "Cannot change theme while processing.")
        #     # Optionally reset the optionmenu back to self.theme
        #     if hasattr(self, 'clipping_tab') and hasattr(self.clipping_tab, 'theme_optionmenu'):
        #          self.clipping_tab.theme_optionmenu.set(self.theme.capitalize())
        #     return

        print(f"GUI: Changing theme to: {new_theme}")
        valid_themes = ["dark", "light", "system"]
        theme_lower = new_theme.lower()
        if theme_lower not in valid_themes:
            print(f"Warning: Invalid theme '{new_theme}'. Using previous '{self.theme}'.")
            # Optionally reset the OptionMenu here if you store a reference to it
            return

        ctk.set_appearance_mode(theme_lower)
        self.theme = theme_lower # Store current theme name

        # Update Spinbox colors (delegate to tabs)
        try:
            if hasattr(self, 'clipping_tab') and self.clipping_tab.winfo_exists():
                self.clipping_tab.apply_spinbox_theme_tags(self.theme)
            if hasattr(self, 'ai_short_tab') and self.ai_short_tab.winfo_exists():
                 self.ai_short_tab.apply_spinbox_theme_tags(self.theme)
        except Exception as e: print(f"Warning: Could not update Spinbox theme colors: {e}")

        # Update Treeview style (delegate to tab)
        self._apply_treeview_theme_tags()

    def _apply_treeview_theme_tags(self):
        """Applies theme to treeview in clipping tab."""
        # Check if clipping_tab and its method exist
        if hasattr(self, 'clipping_tab') and hasattr(self.clipping_tab, 'apply_treeview_theme_tags') and self.clipping_tab.winfo_exists():
             self.clipping_tab.apply_treeview_theme_tags(self.theme)

    def _reset_generation_state(self):
         """Helper to reset state if AI generation fails very early (e.g., creating temp dir)."""
         print("GUI: Resetting AI generation state due to early failure.")
         self.is_generating_short = False
         self._update_button_state()
         self.status_var.set("Status: Idle")

    def _on_closing(self):
        """Handle window closing event, prompt if processing."""
        print("GUI: Close button clicked.")
        process_running = self.is_processing or self.is_generating_short
        if process_running:
            if messagebox.askyesno("Confirm Exit", "A background process is running.\nExiting now will terminate it abruptly.\n\nAre you sure you want to exit?"):
                print("GUI: Exiting while process running...")
                self.is_processing = False # Signal threads (basic stop)
                self.is_generating_short = False
                # Add cleanup for temp AI dir if generation was stopped?
                # Might be hard if thread holds the path.
                self.root.destroy()
            else:
                print("GUI: Exit cancelled.")
                return # Don't close
        else:
            print("GUI: Exiting normally.")
            self.root.destroy()


# --- Main Execution ---
def main():
    """Main function to run the application."""
    # Initialize TkinterDnD root *before* creating the app instance
    root = None # Initialize to None
    try:
        root = TkinterDnD.Tk() # This implicitly initializes DnD for the root
        print("Root TkinterDnD window created.")
    except Exception as e:
        print(f"FATAL ERROR: Failed to create TkinterDnD root window: {e}")
        traceback.print_exc()
        # Fallback to basic Tkinter error window
        try:
            root_error = tk.Tk()
            root_error.title("Autotube - Load Error")
            root_error.geometry("600x200")
            tk.Label(root_error, text=f"FATAL ERROR: Failed to initialize main window ({type(e).__name__}).\nSee console for details.",
                     fg="red", font=("Arial", 16), wraplength=550).pack(pady=40, padx=20)
            root_error.mainloop()
        except Exception as e2:
             print(f"FATAL ERROR: Could not even create basic error window: {e2}")
        return # Exit script

    # Create and run the application instance only if root and modules are OK
    if root and MODULE_IMPORTS_OK:
        try:
            app = VideoClipperApp(root)
            print("Starting mainloop...")
            root.mainloop() # Start the Tkinter event loop
            print("Mainloop finished.")
        except Exception as app_e:
             print(f"FATAL ERROR during application execution: {app_e}")
             traceback.print_exc()
             try:
                 # Try showing error in a simple messagebox if possible
                 messagebox.showerror("Fatal Application Error", f"An unexpected error occurred:\n\n{app_e}\n\nSee console for details.")
             except:
                 pass # Suppress errors in error reporting
    elif not MODULE_IMPORTS_OK:
         print("GUI was not fully initialized due to import errors.")
         # Error message already shown in __init__ if root was created
         if root: root.mainloop() # Show the error window created in __init__
    else:
         print("GUI could not start because root window creation failed.")


if __name__ == "__main__":
    """Main entry point when script is run directly."""
    # Configure logging first
    logger = None
    try:
        from utils.logger_config import setup_logging
        logger = setup_logging() # Use default log file/level
        logger.info(f"--- Autotube Application Start --- Python: {sys.version.split()[0]}, Platform: {sys.platform} ---")
    except ImportError:
         print("Warning: Could not import logger_config. Basic console logging enabled.")
         import logging
         logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
         logging.info("--- Autotube Application Start (Basic Logging) ---")
    except Exception as e:
         print(f"Error setting up logging: {e}")

    # Run the main application function
    main()