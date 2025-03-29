# gui.py
import os
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk # ttk added for Treeview and Style
import threading
import time
from utils.logger import VideoProcessor, FFmpegNotFoundError # Import VideoProcessor and FFmpegNotFoundError
import scenedetect
# These imports might not be strictly needed in gui.py if only logger uses them directly
# from scenedetect.video_manager import VideoManager
# from scenedetect.detectors import ContentDetector
# from scenedetect.scene_manager import SceneManager
from tkinterdnd2 import * # pip install tkinterdnd2
import subprocess # added for function
import sys # To check OS for path quoting
import traceback # For detailed error printing
import random # For temp file naming

# Placeholder for subtitle script processing function (you will implement this)
def process_subtitle_script(script_path, video_duration):
    """
    Processes a subtitle script, optimizing segment lengths for a given video duration.
    This is a placeholder function. You'll need to implement the actual logic.
    """
    print(f"Placeholder: Processing subtitle script {script_path} for video duration {video_duration}")
    # In a real implementation, parse the script and return structured subtitle data
    return [{"start": 0, "end": 5, "text": "Placeholder Subtitle 1"},
            {"start": 5, "end": 10, "text": "Placeholder Subtitle 2"}]

class VideoClipperApp:
    def __init__(self, root):
        """Initialize the Video Clipper Application."""
        self.root = root
        self.theme = "dark" # Initialize self.theme *before* calling _configure_root()
        self.is_processing = False # <<< --- FIX: Initialize is_processing flag HERE --- >>>
        self._configure_root()
        self._create_variables()
        self._create_ui()
        self.video_processor = None # Initialize video_processor here
        self.video_queue = [] # Initialize video queue
        self.processing_thread = None # To hold the processing thread object
        # self.stop_event = threading.Event() # For potential graceful stop

    def _configure_root(self):
        """Configure the root window settings."""
        ctk.set_appearance_mode(self.theme)
        ctk.set_default_color_theme("blue")
        self.root.title("Clip Master")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 750) # Slightly increased min height for subtitle section

    def _create_variables(self):
        """Create and initialize all tkinter variables."""
        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        # self.subtitle_script_path_var = tk.StringVar() # Removed - handled in post-processing

        # Clip Length Variables (Granular Control)
        self.min_clip_length_var = tk.IntVar(value=15)
        self.max_clip_length_var = tk.IntVar(value=45)

        # Scene Detection Threshold
        self.scene_threshold_var = tk.DoubleVar(value=30.0)

        # Slider-based variables
        self.clip_count_var = tk.IntVar(value=5)

        # Checkbox variables
        self.scene_detect_var = tk.BooleanVar(value=False)
        self.remove_audio_var = tk.BooleanVar(value=False)
        self.extract_audio_var = tk.BooleanVar(value=True)
        self.vertical_crop_var = tk.BooleanVar(value=True)
        self.mirror_var = tk.BooleanVar(value=False)
        self.enhance_var = tk.BooleanVar(value=True)
        self.batch_mode_var = tk.BooleanVar(value=False)

        # Progress variables
        self.progress_var = tk.DoubleVar(value=0)
        self.remaining_time_var = tk.StringVar(value="")

        # Subtitle processing variables
        self.subtitle_video_path_var = tk.StringVar()
        self.subtitle_output_path_var = tk.StringVar()

    def _create_ui(self):
        """Create the main user interface layout."""
        # Main container
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Left sidebar for options
        self.sidebar = ctk.CTkFrame(self.main_frame, width=350)
        self.sidebar.pack(side="left", fill="y", padx=(0, 10), pady=0) # Adjusted padding

        # Right content area
        self.content_area = ctk.CTkFrame(self.main_frame)
        self.content_area.pack(side="right", fill="both", expand=True, padx=(10, 0), pady=0) # Adjusted padding

        self._create_sidebar()
        self._create_content_area()

    def _create_sidebar(self):
        """Create the sidebar with input and configuration options."""
        # --- Scrollable Frame for Sidebar Content ---
        scrollable_sidebar = ctk.CTkScrollableFrame(self.sidebar)
        scrollable_sidebar.pack(fill="both", expand=True)


        # Title
        ctk.CTkLabel(scrollable_sidebar, text="Clip Master", font=("Arial", 24, "bold")).pack(pady=20) # Removed text_color for theme adapt

        # Theme Selection
        theme_frame = ctk.CTkFrame(scrollable_sidebar)
        theme_frame.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(theme_frame, text="Theme:").pack(side="left", padx=5)
        theme_optionmenu = ctk.CTkOptionMenu(theme_frame, values=["dark", "light", "system"], command=self._change_theme)
        theme_optionmenu.set(self.theme.capitalize()) # Set initial value
        theme_optionmenu.pack(side="left", padx=5)

        # Input Selection and Drag-and-Drop
        ctk.CTkLabel(scrollable_sidebar, text="Input Videos/Folder", font=("Arial", 16)).pack(pady=(10, 5), anchor="w", padx=10)
        input_frame = ctk.CTkFrame(scrollable_sidebar)
        input_frame.pack(fill="x", padx=10)

        input_entry = ctk.CTkEntry(input_frame, textvariable=self.input_path_var, placeholder_text="Drag & Drop or Browse") # Added placeholder
        input_entry.pack(side="left", expand=True, padx=(0, 10))

        input_button = ctk.CTkButton(input_frame, text="Browse", command=self._select_input, width=80)
        input_button.pack(side="right")

        # Enable Drag and Drop on the input entry
        input_entry.drop_target_register(DND_FILES)
        input_entry.dnd_bind('<<Drop>>', self._drop_input)

        # Batch Processing Checkbox
        ctk.CTkCheckBox(scrollable_sidebar, text="Add Folder Contents (Batch Mode)", variable=self.batch_mode_var).pack(pady=10, padx=10, anchor="w")

        # Queue Display
        ctk.CTkLabel(scrollable_sidebar, text="Video Queue", font=("Arial", 16)).pack(pady=(10, 5), anchor="w", padx=10)
        # --- Styling for ttk.Treeview ---
        style = ttk.Style()
        style.theme_use("default") # Start with default theme
        # Configure static colors (adjust if needed for better theme matching)
        # Dark theme examples:
        tree_bg = "#2B2B2B"
        tree_fg = "white"
        tree_field_bg = "#2B2B2B"
        tree_selected_bg = "#36719F"
        heading_bg = "#565B5E"
        heading_active_bg = '#6A7379'

        style.configure("Treeview", background=tree_bg, foreground=tree_fg, fieldbackground=tree_field_bg, borderwidth=0, rowheight=25)
        style.map('Treeview', background=[('selected', tree_selected_bg)], foreground=[('selected', tree_fg)])
        style.configure("Treeview.Heading", background=heading_bg, foreground=tree_fg, relief="flat", font=('Arial', 10, 'bold'))
        style.map("Treeview.Heading", background=[('active', heading_active_bg)])
        # --- End Treeview Styling ---

        tree_frame = ctk.CTkFrame(scrollable_sidebar) # Frame for treeview and scrollbar
        tree_frame.pack(fill='x', padx=10, pady=5)

        self.queue_tree = ttk.Treeview(tree_frame, columns=('Filepath',), show='headings', height=6, style="Treeview") # Apply style
        self.queue_tree.heading('Filepath', text='Queued Videos')
        self.queue_tree.column('Filepath', width=280, anchor='w') # Adjust width, anchor text left

        # Scrollbar for Treeview
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side='right', fill='y')
        self.queue_tree.pack(side='left', fill='x', expand=True)

        # Button to Clear Queue
        clear_queue_button = ctk.CTkButton(scrollable_sidebar, text="Clear Queue", command=self._clear_queue, fg_color="red", hover_color="#C40000")
        clear_queue_button.pack(pady=5, padx=10)


        # --- Processing Options Section ---
        ctk.CTkLabel(scrollable_sidebar, text="Processing Options", font=("Arial", 16, "bold")).pack(pady=(15, 5), anchor="w", padx=10)

        # Clip Length Controls
        clip_length_frame = ctk.CTkFrame(scrollable_sidebar)
        clip_length_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkLabel(clip_length_frame, text="Clip Length (s)  Min:").pack(side="left", padx=(0, 5))
        self.min_length_spinbox = tk.Spinbox(clip_length_frame, from_=1, to=600, increment=1, textvariable=self.min_clip_length_var, width = 5,
                                             bg="#333333", fg="#FFFFFF", # Static colors for now
                                             highlightthickness=0, relief="flat", wrap=True, justify='center')
        self.min_length_spinbox.pack(side="left", padx = (0,10))

        ctk.CTkLabel(clip_length_frame, text="Max:").pack(side="left", padx=5)
        self.max_length_spinbox = tk.Spinbox(clip_length_frame, from_=1, to=600, increment=1, textvariable=self.max_clip_length_var, width=5,
                                            bg="#333333", fg="#FFFFFF", # Static colors for now
                                            highlightthickness=0, relief="flat", wrap=True, justify='center')
        self.max_length_spinbox.pack(side="left", padx=5)

        # Clip Count Slider
        clip_count_frame = ctk.CTkFrame(scrollable_sidebar)
        clip_count_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(clip_count_frame, text="Number of Clips:", font=("Arial", 14)).pack(side="left", padx=(0,10))
        clip_count_slider = ctk.CTkSlider(
            clip_count_frame, from_=1, to=20, number_of_steps=19,
            variable=self.clip_count_var, command=self._update_clip_count_label # Update label dynamically
        )
        clip_count_slider.pack(side="left", fill="x", expand=True, padx=5)
        self.clip_count_label = ctk.CTkLabel(clip_count_frame, text="5", width=25, anchor='e') # Fixed width, right align
        self.clip_count_label.pack(side="right", padx=(5,0))
        self._update_clip_count_label() # Set initial label value


        # Scene Detection Options
        scene_frame = ctk.CTkFrame(scrollable_sidebar)
        scene_frame.pack(fill="x", padx=10, pady=5)

        ctk.CTkCheckBox(scene_frame, text="Use Scene Detection", variable=self.scene_detect_var).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(scene_frame, text="Threshold:").pack(side="left", padx=5)
        scene_threshold_entry = ctk.CTkEntry(scene_frame, textvariable=self.scene_threshold_var, width=50, justify='center')
        scene_threshold_entry.pack(side="left", padx=5)

        # Other Option Checkboxes
        ctk.CTkLabel(scrollable_sidebar, text="Other Options:", font=("Arial", 14)).pack(pady=(10, 2), anchor="w", padx=10)
        option_frame = ctk.CTkFrame(scrollable_sidebar)
        option_frame.pack(fill="x", padx=10, pady=5)

        col1_frame = ctk.CTkFrame(option_frame) # Frame for column 1
        col1_frame.pack(side="left", padx=5, anchor="nw")
        col2_frame = ctk.CTkFrame(option_frame) # Frame for column 2
        col2_frame.pack(side="left", padx=5, anchor="nw")

        options = [
            ("Remove Audio", self.remove_audio_var, col1_frame),
            ("Extract Audio (.mp3)", self.extract_audio_var, col1_frame),
            ("Vertical Crop (9:16)", self.vertical_crop_var, col1_frame),
            ("Mirror Video", self.mirror_var, col2_frame),
            ("Enhance Video", self.enhance_var, col2_frame)
        ]

        for text, var, frame in options:
            ctk.CTkCheckBox(frame, text=text, variable=var).pack(anchor="w", pady=2)


    def _create_content_area(self):
        """Create the main content area with processing controls, progress tracking, queue display, and subtitle post-processing."""
        # --- Scrollable Frame for Content Area ---
        scrollable_content = ctk.CTkScrollableFrame(self.content_area)
        scrollable_content.pack(fill="both", expand=True)

        # Output Selection
        ctk.CTkLabel(scrollable_content, text="Output Location (Where clips are saved)", font=("Arial", 16)).pack(pady=(10, 5), anchor="w", padx=20)
        output_frame = ctk.CTkFrame(scrollable_content)
        output_frame.pack(fill="x", padx=20)

        output_entry = ctk.CTkEntry(output_frame, textvariable=self.output_path_var, placeholder_text="Select where to save clips")
        output_entry.pack(side="left", expand=True, padx=(0, 10))

        output_button = ctk.CTkButton(output_frame, text="Browse", command=self._select_output, width=100)
        output_button.pack(side="right")

        # --- Processing Controls and Status ---
        processing_status_frame = ctk.CTkFrame(scrollable_content)
        processing_status_frame.pack(fill="x", padx=20, pady=20)

        ctk.CTkLabel(processing_status_frame, text="Clipping Progress:", font=("Arial", 14)).pack(anchor="w")
        self.progress_bar = ctk.CTkProgressBar(processing_status_frame, variable=self.progress_var) # Removed width, let it fill
        self.progress_bar.pack(pady=(5, 10), fill="x")

        self.video_info_label = ctk.CTkLabel(processing_status_frame, text="Status: Idle", font=("Arial", 12))
        self.video_info_label.pack(anchor="w")

        self.remaining_time_var.set("Est. Time Remaining: N/A") # Default text
        ctk.CTkLabel(processing_status_frame, textvariable=self.remaining_time_var, font=("Arial", 12)).pack(anchor="w")

        # Start/Stop Processing Button (combined)
        self.start_stop_button = ctk.CTkButton(
            scrollable_content, # Pack in the main scrollable area
            text="Start Clipping Queue",
            command=self._toggle_processing, # Use a toggle function
            font=("Arial", 16, "bold")
        )
        self.start_stop_button.pack(pady=10)
        self._update_button_state() # Set initial button color/text


        # ----------------------- Subtitle Post-Processing Section -----------------------
        subtitle_main_frame = ctk.CTkFrame(scrollable_content)
        subtitle_main_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(subtitle_main_frame, text="Subtitle Post-Processing", font=("Arial", 18, "bold")).pack(pady=(10, 5), anchor="w")

        # Select File to Subtitle
        file_select_frame = ctk.CTkFrame(subtitle_main_frame)
        file_select_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(file_select_frame, text="Video to Subtitle:", width=150, anchor="w").pack(side="left", padx=5) # Fixed width for alignment
        file_select_entry = ctk.CTkEntry(file_select_frame, textvariable=self.subtitle_video_path_var, placeholder_text="Select processed clip")
        file_select_entry.pack(side="left", expand=True, padx=(0, 10))
        file_select_button = ctk.CTkButton(file_select_frame, text="Select Video", command=self._select_video_to_subtitle, width=110) # Adjusted width
        file_select_button.pack(side="left")


        # Select Output File for Subtitled Video
        subtitle_output_frame = ctk.CTkFrame(subtitle_main_frame)
        subtitle_output_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(subtitle_output_frame, text="Save Subtitled To:", width=150, anchor="w").pack(side="left", padx=5) # Fixed width for alignment
        subtitle_output_entry = ctk.CTkEntry(subtitle_output_frame, textvariable=self.subtitle_output_path_var, placeholder_text="Select save location")
        subtitle_output_entry.pack(side="left", expand=True, padx=(0, 10))
        subtitle_output_button = ctk.CTkButton(subtitle_output_frame, text="Select Location", command=self._select_subtitle_output, width=110) # Adjusted width
        subtitle_output_button.pack(side="left")


        # Subtitle Text Input
        ctk.CTkLabel(subtitle_main_frame, text="Subtitle Text (One line per subtitle segment):", font=("Arial", 14)).pack(pady=(5, 2), anchor="w")
        self.subtitle_textbox = ctk.CTkTextbox(subtitle_main_frame, height=100) # Adjusted height
        self.subtitle_textbox.pack(fill="x", pady=5)

        # Apply Subtitles Button
        self.apply_subtitle_button = ctk.CTkButton(
            subtitle_main_frame, # Pack inside the subtitle frame
            text="Apply Subtitles to Selected Video", # More specific text
            command=self._apply_subtitles,
            font=("Arial", 14, "bold")
            # Colors managed by theme
        )
        self.apply_subtitle_button.pack(pady=10)

    # --- METHOD DEFINITIONS START HERE ---

    def _update_button_state(self):
        """Updates the text and color of the start/stop button based on processing state."""
        if self.is_processing:
            self.start_stop_button.configure(text="Stop Processing", fg_color="red", hover_color="#C40000")
        else:
            self.start_stop_button.configure(text="Start Clipping Queue", fg_color="green", hover_color="darkgreen")

    def _toggle_processing(self):
        """Starts or stops the video processing queue."""
        if self.is_processing:
            # --- Implement Stop Logic ---
            # Basic stop: Just set the flag. The thread will finish the current video.
            print("Stop requested. Processing will stop after the current video finishes.")
            self.is_processing = False # Signal the thread loop to stop *after* the current item
            self.start_stop_button.configure(text="Stopping...", state="disabled") # Indicate stopping
            self.video_info_label.configure(text="Status: Stopping after current video...")
            # More advanced stop would involve self.stop_event.set() and checks within the loop
        else:
            # Start processing
            self._start_processing() # Call the actual start logic

    def _clear_queue(self):
        """Clears the video processing queue."""
        if self.is_processing:
             messagebox.showwarning("Queue Locked", "Cannot clear queue while processing is active.")
             return
        if not self.video_queue:
             # messagebox.showinfo("Queue Empty", "The video queue is already empty.") # Maybe not needed
             return
        if messagebox.askyesno("Confirm Clear", f"Are you sure you want to remove all {len(self.video_queue)} videos from the queue?"):
            self.video_queue = []
            self._update_queue_display()
            # messagebox.showinfo("Queue Cleared", "Video queue has been cleared.") # Maybe not needed

    def _change_theme(self, new_theme):
        """Change the theme of the application."""
        print(f"Changing theme to: {new_theme}")
        ctk.set_appearance_mode(new_theme)
        self.theme = new_theme # Update internal theme state if needed elsewhere

        # Update Spinbox colors dynamically - simplified to static for now
        spinbox_bg = "#333333" if new_theme == "dark" else "#EBEBEB"
        spinbox_fg = "#FFFFFF" if new_theme == "dark" else "#000000"
        try: # Use try-except as widgets might not exist if UI creation failed
            self.min_length_spinbox.configure(bg=spinbox_bg, fg=spinbox_fg)
            self.max_length_spinbox.configure(bg=spinbox_bg, fg=spinbox_fg)
        except AttributeError:
            print("Warning: Could not update Spinbox theme colors.")


        # Update Treeview style based on new theme
        style = ttk.Style()
        style.theme_use("default")
        if new_theme == "dark":
            tree_bg, tree_fg, tree_field_bg = "#2B2B2B", "white", "#2B2B2B"
            tree_selected_bg = "#36719F"
            heading_bg, heading_active_bg = "#565B5E", '#6A7379'
            odd_bg, even_bg = "#2B2B2B", "#242424"
        else: # Assume light/system maps to light
            tree_bg, tree_fg, tree_field_bg = "#FFFFFF", "black", "#FFFFFF"
            tree_selected_bg = "#0078D7"
            heading_bg, heading_active_bg = "#E1E1E1", '#CCCCCC'
            odd_bg, even_bg = "#FFFFFF", "#F0F0F0"

        try:
            style.configure("Treeview", background=tree_bg, foreground=tree_fg, fieldbackground=tree_field_bg, borderwidth=0, rowheight=25)
            style.map('Treeview', background=[('selected', tree_selected_bg)], foreground=[('selected', tree_fg)])
            style.configure("Treeview.Heading", background=heading_bg, foreground=tree_fg, relief="flat", font=('Arial', 10, 'bold'))
            style.map("Treeview.Heading", background=[('active', heading_active_bg)])
            # Re-apply row tags
            self.queue_tree.tag_configure('oddrow', background=odd_bg)
            self.queue_tree.tag_configure('evenrow', background=even_bg)
            # Force redraw if needed (might not be necessary)
            # self._update_queue_display()
        except Exception as e:
            print(f"Warning: Could not update Treeview theme style: {e}")


    def _select_input(self):
        """Choose a single video file or an entire folder for batch processing and add to queue."""
        if self.batch_mode_var.get():
            path = filedialog.askdirectory(title="Select Folder of Videos")
            if path:
                added_count = 0
                try:
                    for file in os.listdir(path):
                        if file.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".wmv")): # Added more extensions
                            full_path = os.path.join(path, file)
                            if full_path not in self.video_queue: # Avoid duplicates
                                 self.video_queue.append(full_path)
                                 added_count += 1
                except OSError as e:
                    messagebox.showerror("Error Reading Folder", f"Could not read folder contents:\n{e}")
                    return # Stop if folder can't be read
                if added_count > 0:
                     pass # Avoid too many popups
                else:
                     messagebox.showwarning("Warning", "No new video files found in the selected folder.")
                self.input_path_var.set(f"Folder: ...{os.path.basename(path)}") # Display shortened folder path
        else:
            paths = filedialog.askopenfilenames(title="Select Video File(s)", filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv *.wmv"), ("All Files", "*.*")]) # Allow multiple files
            if paths:
                added_count = 0
                for path in paths:
                     if path not in self.video_queue: # Avoid duplicates
                         self.video_queue.append(path)
                         added_count += 1
                if added_count > 0:
                     self.input_path_var.set(os.path.basename(paths[0]) if len(paths) == 1 else f"{len(paths)} files selected") # Display first path or count
                # else: Avoid popup

        self._update_queue_display()


    def _drop_input(self, event):
        """Handle drag and drop events to add videos/folders to the queue."""
        try:
            # Use tk.splitlist to handle paths with spaces correctly
            dropped_items = self.root.tk.splitlist(event.data)
            added_count = 0
            first_added = ""
            for item_path in dropped_items:
                item_path = item_path.strip('{}') # Remove potential curly braces
                if os.path.isdir(item_path):
                    found_in_dir = 0
                    try:
                        for file in os.listdir(item_path):
                            if file.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".wmv")):
                                full_path = os.path.join(item_path, file)
                                if full_path not in self.video_queue:
                                    self.video_queue.append(full_path)
                                    added_count += 1
                                    found_in_dir += 1
                                    if not first_added: first_added = full_path
                    except OSError as e:
                        print(f"Warning: Could not read dropped folder {item_path}: {e}")
                        continue # Skip this folder

                elif os.path.isfile(item_path) and item_path.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".wmv")):
                    if item_path not in self.video_queue:
                        self.video_queue.append(item_path)
                        added_count += 1
                        if not first_added: first_added = item_path

            if added_count > 0:
                 self._update_queue_display()
                 display_text = os.path.basename(first_added) if first_added else "Multiple Items"
                 if added_count > 1: display_text += f" + {added_count-1} more"
                 self.input_path_var.set(display_text)
            # else: Avoid popup
        except Exception as e:
             messagebox.showerror("Drag & Drop Error", f"Failed to process dropped items:\n{e}")
             traceback.print_exc()


    def _update_queue_display(self):
        """Update queue Treeview."""
        try:
            selected_item = self.queue_tree.focus()
            scroll_pos = self.queue_tree.yview()

            # Clear existing items more safely
            for item in self.queue_tree.get_children():
                self.queue_tree.delete(item)

            for i, file_path in enumerate(self.video_queue):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                display_name = os.path.basename(file_path)
                try:
                    # Use full path as item ID (iid)
                    self.queue_tree.insert('', tk.END, values=(display_name,), tags=(tag,), iid=file_path)
                except tk.TclError as e:
                     # Handle potential errors if file_path is not suitable as an iid (rare)
                     print(f"Warning: Could not insert item with iid '{file_path}': {e}")
                     # Fallback to default iid
                     self.queue_tree.insert('', tk.END, values=(display_name,), tags=(tag,))


            # Restore selection if item still exists
            if selected_item and self.queue_tree.exists(selected_item):
                self.queue_tree.focus(selected_item)
                self.queue_tree.selection_set(selected_item)

            # Restore scroll position
            self.queue_tree.yview_moveto(scroll_pos[0])

            # Re-Configure tags (needed if style changed)
            self._apply_treeview_theme_tags() # Use helper

        except Exception as e:
            print(f"Error updating queue display: {e}")
            traceback.print_exc()

    def _apply_treeview_theme_tags(self):
        """Helper to apply theme colors to Treeview rows."""
        style = ttk.Style()
        # Determine colors based on current theme
        if self.theme == "dark":
            odd_bg, even_bg = "#2B2B2B", "#242424"
        else: # Assume light
            odd_bg, even_bg = "#FFFFFF", "#F0F0F0"
        try:
            self.queue_tree.tag_configure('oddrow', background=odd_bg)
            self.queue_tree.tag_configure('evenrow', background=even_bg)
        except Exception as e:
             print(f"Could not apply treeview row styling: {e}")


    def _select_output(self):
        """Choose output folder."""
        path = filedialog.askdirectory(title="Select Output Folder")
        if path:
            self.output_path_var.set(path)

    def _update_clip_count_label(self, value=None): # Accept slider value directly
        """Update clip count label."""
        try:
            count = self.clip_count_var.get() if value is None else int(float(value))
            self.clip_count_label.configure(text=f"{count}")
        except Exception:
            self.clip_count_label.configure(text="N/A")


    # --- START PROCESSING METHOD ---
    def _start_processing(self):
        """Validates inputs and starts the video processing queue thread."""
        if self.is_processing:
             messagebox.showwarning("Busy", "Processing is already running.")
             return

        output_path = self.output_path_var.get()

        if not output_path:
            messagebox.showerror("Error", "Please select an output folder.")
            return

        if not os.path.isdir(output_path):
             messagebox.showerror("Error", f"Output path is not a valid directory:\n{output_path}")
             return


        if not self.video_queue:
            messagebox.showerror("Error", "Video queue is empty. Please add videos.")
            return

        # --- Validation for Clip Lengths ---
        try:
            min_len = self.min_clip_length_var.get()
            max_len = self.max_clip_length_var.get()
            if min_len > max_len:
                messagebox.showerror("Error", "Minimum clip length cannot be greater than maximum clip length.")
                return
            if min_len <= 0 or max_len <= 0:
                 messagebox.showerror("Error", "Clip lengths must be greater than zero.")
                 return
        except tk.TclError:
             messagebox.showerror("Error", "Invalid clip length value. Please enter numbers only.")
             return
        # --- End Validation ---


        # Create VideoProcessor instance here
        try:
            print(f"Initializing VideoProcessor with output: {output_path}")
            self.video_processor = VideoProcessor(output_path)
            print("VideoProcessor Initialized.")
        except FFmpegNotFoundError: # Catch specific error
             messagebox.showerror("Error", "FFmpeg not found. Please install FFmpeg and ensure it's in your system's PATH.")
             return # Don't proceed
        except Exception as e:
            messagebox.showerror("Error", f"Could not initialize Video Processor: {e}")
            traceback.print_exc()
            return # Don't proceed


        options = {
            "clip_count": self.clip_count_var.get(), # Pass as int
            "min_clip_length": min_len,
            "max_clip_length": max_len,
            "scene_detect": self.scene_detect_var.get(),
            "scene_threshold": self.scene_threshold_var.get(),
            "remove_audio": self.remove_audio_var.get(),
            "extract_audio": self.extract_audio_var.get(),
            "vertical_crop": self.vertical_crop_var.get(),
            "mirror": self.mirror_var.get(),
            "enhance": self.enhance_var.get(),
            # Add 'overlap': self.overlap_var.get() if you add an overlap checkbox
        }

        # Start processing
        self.is_processing = True
        # self.stop_event.clear() # Clear stop flag if using events
        self._update_button_state()
        self.progress_var.set(0)
        self.remaining_time_var.set("Est. Time Remaining: Calculating...")


        # Pass a copy of the queue to the thread
        queue_copy = list(self.video_queue)
        self.processing_thread = threading.Thread(target=self._process_queue, args=(queue_copy, output_path, options), daemon=True)
        self.processing_thread.start()

        self.video_info_label.configure(text="Status: Processing started...")


    def _process_queue(self, video_queue, output_path, options):
        """Processes videos in the queue. Runs in a separate thread."""
        total_videos = len(video_queue)
        start_time = time.time()
        processed_count = 0
        error_count = 0

        for index, file_path in enumerate(video_queue):
             # --- Check for stop signal ---
             if not self.is_processing: # Simple flag check
                 print("Stop signal received, breaking processing loop.")
                 break
             # if self.stop_event.is_set(): # Using event
             #     print("Stop event set, breaking processing loop.")
             #     break

             try:
                # Update status label (use root.after for thread safety)
                status_text = f"Processing video {index + 1}/{total_videos}: {os.path.basename(file_path)}"
                # Schedule the update on the main thread
                # Using lambda ensures the *current* value of status_text is used
                self.root.after(0, lambda text=status_text: self.video_info_label.configure(text=text))
                print(status_text) # Also print to console

                # Ensure VideoProcessor instance exists
                if not self.video_processor:
                     # This should not happen if _start_processing logic is correct
                     raise RuntimeError("VideoProcessor not initialized before processing queue.")

                # Process video
                print(f"Calling process_video for: {file_path} with options: {options}")
                processed_clips = self.video_processor.process_video(file_path, **options)

                if isinstance(processed_clips, list) and processed_clips: # Check if list & not empty
                     processed_count += 1
                     print(f"Successfully processed {file_path}. Output clips: {processed_clips}")
                else:
                     # Assume error if no clips returned (or handle specific return value)
                     error_count += 1
                     print(f"Processing {file_path} might have failed (no clips returned or empty list).")


                # Update progress bar (use root.after)
                self.root.after(0, self._update_progress_bar, index, total_videos, start_time)


             except Exception as e:
                error_count += 1
                error_msg = f"CRITICAL ERROR processing {os.path.basename(file_path)}"
                print(error_msg + ":")
                traceback.print_exc() # Print full traceback to console
                # Update status label about the error
                self.root.after(0, self.video_info_label.configure, {"text": f"Error on: {os.path.basename(file_path)}! Check console."})


        # Processing finished naturally or was stopped
        self.root.after(0, self._processing_complete, processed_count, error_count, total_videos)


    def _update_progress_bar(self, index, total_videos, start_time):
        """Update progress bar and remaining time (called via root.after)."""
        # No need to check is_processing here, as it's scheduled by the thread loop

        elapsed_time = time.time() - start_time
        progress_percent = ((index + 1) / total_videos) if total_videos > 0 else 0
        self.progress_var.set(progress_percent) # Value between 0 and 1


        # Calculate remaining time more accurately
        if index < total_videos - 1 and elapsed_time > 1 and (index + 1) > 0:
            time_per_video = elapsed_time / (index + 1)
            remaining_videos = total_videos - (index + 1)
            remaining_time_sec = time_per_video * remaining_videos
            # Format remaining time
            minutes, seconds = divmod(int(remaining_time_sec), 60)
            remaining_time_str = f"{minutes}m {seconds}s"
            self.remaining_time_var.set(f"Est. Time Remaining: {remaining_time_str}")
        elif index >= total_videos - 1: # If processing the last video or done
             self.remaining_time_var.set("Est. Time Remaining: Finishing...")
        else: # Very beginning
             self.remaining_time_var.set("Est. Time Remaining: Calculating...")


    def _processing_complete(self, processed_count, error_count, total_videos):
        """Handle processing completion (called via root.after)."""
        was_stopped = not self.is_processing # Check if stop was requested *before* this method was scheduled

        self.is_processing = False # Ensure flag is reset
        self._update_button_state() # Reset button text/color

        if was_stopped and (processed_count + error_count < total_videos):
             completion_message = f"Processing stopped by user.\n\nProcessed: {processed_count}\nErrors: {error_count}\nSkipped: {total_videos - processed_count - error_count}"
             self.video_info_label.configure(text=f"Status: Stopped.")
        else:
             completion_message = f"Clipping finished.\n\nTotal Videos: {total_videos}\nSuccessfully Processed: {processed_count}\nErrors: {error_count}"
             self.video_info_label.configure(text=f"Status: Idle. {processed_count}/{total_videos} successful.")

        # Set progress to 100% unless stopped very early with only errors
        final_progress = 0 if was_stopped and processed_count == 0 and error_count > 0 else 1
        self.progress_var.set(final_progress)
        self.remaining_time_var.set("Est. Time Remaining: Done")

        messagebox.showinfo("Processing Complete", completion_message)

        # Clear the queue only after completion report
        self.video_queue = []
        self._update_queue_display()


    # --- Subtitle Post-Processing Methods ---

    def _select_video_to_subtitle(self):
        """Select a single video file to add subtitles to."""
        initial_dir = self.output_path_var.get() if self.output_path_var.get() else None
        path = filedialog.askopenfilename(title="Select Video File to Subtitle",
                                          filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv *.wmv"), ("All Files", "*.*")],
                                          initialdir=initial_dir)
        if path:
            self.subtitle_video_path_var.set(path)


    def _select_subtitle_output(self):
        """Select a location to save the newly subtitled video."""
        initial_dir = self.output_path_var.get() if self.output_path_var.get() else None
        path = filedialog.askdirectory(title="Select Output Location for Subtitled Video", initialdir=initial_dir)
        if path:
            self.subtitle_output_path_var.set(path)


    def _apply_subtitles(self):
        """Validates inputs and starts the subtitle application thread."""
        if self.is_processing: # Prevent applying subtitles while clipping
             messagebox.showwarning("Busy", "Cannot apply subtitles while clipping process is running.")
             return

        video_path = self.subtitle_video_path_var.get()
        subtitle_output_dir = self.subtitle_output_path_var.get()
        subtitle_text = self.subtitle_textbox.get("1.0", "end-1c").strip() # Get text and strip whitespace


        if not video_path:
            messagebox.showerror("Error", "Please select a video file to add subtitles to.")
            return
        if not os.path.isfile(video_path):
             messagebox.showerror("Error", f"Selected video file not found:\n{video_path}")
             return
        if not subtitle_output_dir:
             messagebox.showerror("Error", "Please select an output location for the subtitled video.")
             return
        if not os.path.isdir(subtitle_output_dir):
             messagebox.showerror("Error", f"Subtitle output location is not a valid directory:\n{subtitle_output_dir}")
             return
        if not subtitle_text:
            messagebox.showerror("Error", "Subtitle text cannot be empty.")
            return


        # Construct the output file path
        base_name = os.path.basename(video_path)
        name, ext = os.path.splitext(base_name)
        # Ensure output has a standard extension like .mp4
        output_filename = f"{name}_subtitled.mp4"
        output_path = os.path.join(subtitle_output_dir, output_filename)


        # Check if output file already exists
        if os.path.exists(output_path):
            if not messagebox.askyesno("Overwrite?", f"Output file '{output_filename}' already exists in the selected location. Overwrite?"):
                return


        # Disable button while processing
        self.apply_subtitle_button.configure(state="disabled", text="Applying...")
        self.video_info_label.configure(text="Status: Applying subtitles...") # Update status

        # Run subtitle processing in a separate thread
        threading.Thread(target=self._process_subtitles, kwargs={'video_path': video_path,
                                                                  'subtitle_text': subtitle_text,
                                                                  'output_path': output_path,
                                                                  'temp_dir': subtitle_output_dir},
                           daemon=True).start()


    def _process_subtitles(self, video_path, subtitle_text, output_path, temp_dir):
        """
        Creates an SRT file and uses FFmpeg to add subtitles. Runs in a thread.
        """
        temp_srt_file = None # For cleanup
        status_label_update = lambda txt: self.root.after(0, self.video_info_label.configure, {"text": txt})

        try:
            status_label_update("Status: Generating temporary subtitle file...")
            # --- Create the temporary .srt file ---
            temp_srt_filename = f"temp_subtitles_{int(time.time())}_{random.randint(100,999)}.srt"
            temp_srt_file = os.path.join(temp_dir, temp_srt_filename)
            print(f"Creating temp SRT: {temp_srt_file}")

            # --- Basic SRT generation (NEEDS REAL TIMING) ---
            lines = subtitle_text.strip().splitlines()
            if not lines:
                raise ValueError("Subtitle text is empty after stripping.")

            with open(temp_srt_file, "w", encoding="utf-8") as f:
                start_sec = 0.1 # Start slightly after beginning
                # --- !!! Placeholder: Estimate duration per line !!! ---
                words_per_second = 2.5 # Adjusted WPM estimate
                min_duration = 1.5 # Minimum seconds
                max_duration = 7.0 # Maximum seconds

                for i, line in enumerate(lines):
                    line = line.strip()
                    if not line: continue # Skip empty lines in the middle

                    word_count = len(line.split())
                    # Estimate duration based on word count, clamped between min/max
                    estimated_duration = max(min_duration, min(max_duration, round(word_count / words_per_second, 1)))

                    start_hms = self._seconds_to_srt_time(start_sec)
                    end_sec = start_sec + estimated_duration
                    end_hms = self._seconds_to_srt_time(end_sec)

                    f.write(f"{i+1}\n")
                    f.write(f"{start_hms} --> {end_hms}\n")
                    f.write(f"{line}\n\n")
                    start_sec = end_sec + 0.2 # Add small gap between subtitles
            # --- End Placeholder Timing Logic ---
            print(f"Temp SRT created.")


            # --- Construct and Run FFmpeg Command ---
            status_label_update(f"Status: Applying subtitles using FFmpeg...")

            # Prepare paths for FFmpeg command (no extra quotes needed in list)
            clean_video_path = video_path.strip('"')
            clean_output_path = output_path.strip('"')
            # Path for subtitles filter needs careful escaping on Windows
            if sys.platform == 'win32':
                # Escape backslashes and colons
                 subtitle_filter_path = temp_srt_file.replace('\\', '\\\\').replace(':', '\\:')
            else:
                 subtitle_filter_path = temp_srt_file # Linux/macOS usually fine

            vf_filter = f"subtitles='{subtitle_filter_path}'"
            # Example with basic styling:
            # vf_filter = f"subtitles='{subtitle_filter_path}':force_style='FontName=Arial,FontSize=20,PrimaryColour=&Hffffff&,BorderStyle=1,Outline=1,Shadow=0.5'"


            cmd = [
                "ffmpeg",
                "-y", # Overwrite output without asking
                "-i", clean_video_path,
                "-vf", vf_filter,
                "-c:a", "copy", # Copy audio stream (faster, preserves quality)
                # If audio needs re-encoding: "-c:a", "aac", "-b:a", "192k",
                "-c:v", "libx264", # Re-encode video (needed for burning subs)
                "-preset", "medium",
                "-crf", "23", # Adjust quality vs file size
                clean_output_path
            ]

            print(f"Running FFmpeg command: {' '.join(cmd)}")

            # Using subprocess.run
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                    creationflags=creationflags)

            if result.returncode != 0:
                # Log full error, show truncated in messagebox
                error_message = f"FFmpeg Error (Code {result.returncode}):\n{result.stderr or result.stdout}"
                print(error_message)
                self.root.after(0, messagebox.showerror, "FFmpeg Error", error_message[:1000] + "...")
            else:
                # If successful
                success_msg = f"Subtitles applied successfully!\nSaved to: {output_path}"
                print(success_msg)
                self.root.after(0, messagebox.showinfo, "Success", success_msg)


        except Exception as e:
             error_msg = f"Subtitle processing failed: {e}"
             traceback.print_exc() # Print full traceback to console
             self.root.after(0, messagebox.showerror, "Error", error_msg)
        finally:
             # --- Cleanup: Delete temporary SRT file ---
             if temp_srt_file and os.path.exists(temp_srt_file):
                 try:
                     os.remove(temp_srt_file)
                     print(f"Removed temporary file: {temp_srt_file}")
                 except OSError as e:
                     print(f"Error removing temporary file {temp_srt_file}: {e}")
             # --- Re-enable button and reset status ---
             self.root.after(0, self.apply_subtitle_button.configure, {"state": "normal", "text": "Apply Subtitles to Selected Video"})
             if not self.is_processing: # Only reset to Idle if main processing isn't running
                 self.root.after(0, status_label_update, "Status: Idle")


    def _seconds_to_srt_time(self, total_seconds):
        """Converts seconds to HH:MM:SS,mmm format."""
        if total_seconds < 0: total_seconds = 0
        # Use round for milliseconds to avoid potential floating point issues near .999
        milliseconds = int(round((total_seconds - int(total_seconds)) * 1000))
        # Handle potential rollover if milliseconds round up to 1000
        if milliseconds >= 1000:
             total_seconds += 1
             milliseconds = 0
        hours, remainder = divmod(int(total_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


    def _quote_path(self, path: str) -> str:
        """DEPRECATED. Path quoting for direct shell commands. Not needed for list args."""
        return path # Return unchanged path


# --- Main Execution ---
def main():
    """Main function to run the application."""
    # Initialize TkinterDnD root *before* creating the app instance
    root = TkinterDnD.Tk()
    # root.geometry("600x650") # Initial geometry set in VideoClipperApp._configure_root
    app = VideoClipperApp(root)
    root.mainloop()


if __name__ == "__main__":
    """When gui.py is the main file, do:"""
    main()