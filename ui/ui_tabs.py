# ui/ui_tabs.py
from tkinter import filedialog
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
from tkinterdnd2 import DND_FILES # Import necessary constants
import os # For basename
import traceback # For error logging

class ClippingTab(ctk.CTkFrame):
    """Frame containing widgets for the Video Clipping tab."""
    def __init__(self, master, app_logic, **kwargs):
        super().__init__(master, **kwargs)
        self.app_logic = app_logic # Reference to main VideoClipperApp instance
        print("Initializing ClippingTab UI...")

        # Make the main frame within the tab scrollable
        scrollable_frame = ctk.CTkScrollableFrame(self)
        scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self._create_widgets(scrollable_frame) # Pass scrollable frame as master
        print("ClippingTab UI widgets created.")

    def _create_widgets(self, master_frame):
        """Creates widgets inside the scrollable frame for the Clipping Tab."""

        # --- Input & Queue Section ---
        input_queue_frame = ctk.CTkFrame(master_frame)
        input_queue_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(input_queue_frame, text="Input Videos/Folder", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 5), anchor="w")
        input_frame = ctk.CTkFrame(input_queue_frame)
        input_frame.pack(fill="x")

        input_entry = ctk.CTkEntry(input_frame, textvariable=self.app_logic.input_path_var, placeholder_text="Drag & Drop or Browse")
        input_entry.pack(side="left", expand=True, padx=(0, 10), pady=5)
        # --- DnD Binding ---
        try:
            input_entry.drop_target_register(DND_FILES)
            input_entry.dnd_bind('<<Drop>>', self.app_logic._drop_input) # Call main app's drop handler
        except Exception as e:
            print(f"Warning: Failed to initialize Drag and Drop for ClippingTab Input: {e}")
        # --- End DnD ---
        input_button = ctk.CTkButton(input_frame, text="Browse", command=self.app_logic._select_input, width=80)
        input_button.pack(side="right", pady=5)

        # Batch Mode Checkbox
        ctk.CTkCheckBox(input_queue_frame, text="Add Folder Contents (Batch Mode)", variable=self.app_logic.batch_mode_var).pack(pady=5, anchor="w")

        # Queue Display
        ctk.CTkLabel(input_queue_frame, text="Video Queue", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5), anchor="w")
        tree_frame = ctk.CTkFrame(input_queue_frame) # Frame to hold tree and scrollbar
        tree_frame.pack(fill='x', pady=5)

        # Create Treeview instance (store ref here for direct manipulation)
        self.queue_tree = ttk.Treeview(tree_frame, columns=('Filepath',), show='headings', height=6, style="Treeview")
        self.queue_tree.heading('Filepath', text='Queued Videos')
        self.queue_tree.column('Filepath', width=600, anchor='w') # Adjust width
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.queue_tree.pack(side='left', fill='x', expand=True)

        # Clear Queue Button
        clear_queue_button = ctk.CTkButton(input_queue_frame, text="Clear Queue", command=self.app_logic._clear_queue, width=100, fg_color="red", hover_color="#C40000")
        clear_queue_button.pack(pady=5, anchor="e")


        # --- Processing Options Section ---
        options_frame = ctk.CTkFrame(master_frame)
        options_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(options_frame, text="Clipping Options", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 10), anchor="w")

        # Clip Length Controls
        clip_length_frame = ctk.CTkFrame(options_frame)
        clip_length_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(clip_length_frame, text="Clip Length (s)  Min:").pack(side="left", padx=(0, 5))
        # Store spinbox refs on self for potential theme updates
        self.min_length_spinbox = tk.Spinbox(clip_length_frame, from_=1, to=600, increment=1, textvariable=self.app_logic.min_clip_length_var, width = 5,
                                             highlightthickness=0, relief="flat", wrap=True, justify='center')
        self.min_length_spinbox.pack(side="left", padx = (0,10))
        ctk.CTkLabel(clip_length_frame, text="Max:").pack(side="left", padx=5)
        self.max_length_spinbox = tk.Spinbox(clip_length_frame, from_=1, to=600, increment=1, textvariable=self.app_logic.max_clip_length_var, width=5,
                                             highlightthickness=0, relief="flat", wrap=True, justify='center')
        self.max_length_spinbox.pack(side="left", padx=5)
        self.apply_spinbox_theme_tags(self.app_logic.theme) # Apply initial theme colors

        # Clip Count Slider
        clip_count_frame = ctk.CTkFrame(options_frame)
        clip_count_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(clip_count_frame, text="Number of Clips:", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0,10))
        # Store label ref on self to update it
        self.clip_count_label = ctk.CTkLabel(clip_count_frame, text="5", width=25, anchor='e') # Default text
        self.clip_count_label.pack(side="right", padx=(5,0)) # Pack label first
        # Use command=self._update_clip_count_label (method defined below in THIS class)
        clip_count_slider = ctk.CTkSlider(clip_count_frame, from_=1, to=20, number_of_steps=19,
                                          variable=self.app_logic.clip_count_var,
                                          command=self._update_clip_count_label) # <<< --- FIXED COMMAND --- >>>
        clip_count_slider.pack(side="left", fill="x", expand=True, padx=5) # Pack slider after label
        self._update_clip_count_label() # Call initially to set label based on var

        # Scene Detection Options
        scene_frame = ctk.CTkFrame(options_frame)
        scene_frame.pack(fill="x", pady=5)
        ctk.CTkCheckBox(scene_frame, text="Use Scene Detection", variable=self.app_logic.scene_detect_var).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(scene_frame, text="Threshold:").pack(side="left", padx=5)
        scene_threshold_entry = ctk.CTkEntry(scene_frame, textvariable=self.app_logic.scene_threshold_var, width=50, justify='center')
        scene_threshold_entry.pack(side="left", padx=5)

        # Other Option Checkboxes
        ctk.CTkLabel(options_frame, text="Other Options:", font=ctk.CTkFont(size=14)).pack(pady=(10, 2), anchor="w")
        option_checkboxes_frame = ctk.CTkFrame(options_frame)
        option_checkboxes_frame.pack(fill="x", pady=5)
        col1_frame = ctk.CTkFrame(option_checkboxes_frame)
        col1_frame.pack(side="left", padx=5, anchor="nw")
        col2_frame = ctk.CTkFrame(option_checkboxes_frame)
        col2_frame.pack(side="left", padx=5, anchor="nw")
        options = [
            ("Remove Audio", self.app_logic.remove_audio_var, col1_frame),
            ("Extract Audio (.mp3)", self.app_logic.extract_audio_var, col1_frame),
            ("Vertical Crop (9:16)", self.app_logic.vertical_crop_var, col1_frame),
            ("Mirror Video", self.app_logic.mirror_var, col2_frame),
            ("Enhance Video", self.app_logic.enhance_var, col2_frame)
        ]
        for text, var, frame in options:
            ctk.CTkCheckBox(frame, text=text, variable=var).pack(anchor="w", pady=2)

        # --- Output & Start Section ---
        output_start_frame = ctk.CTkFrame(master_frame)
        output_start_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(output_start_frame, text="Output Location (Save Clips To)", font=ctk.CTkFont(size=16)).pack(pady=(0, 5), anchor="w")
        output_frame = ctk.CTkFrame(output_start_frame)
        output_frame.pack(fill="x")
        output_entry = ctk.CTkEntry(output_frame, textvariable=self.app_logic.output_path_var, placeholder_text="Select where clips are saved")
        output_entry.pack(side="left", expand=True, padx=(0, 10), pady=5)
        output_button = ctk.CTkButton(output_frame, text="Browse", command=self.app_logic._select_output, width=100)
        output_button.pack(side="right", pady=5)

        # Start/Stop Button (created here, store ref on self for state updates)
        self.start_stop_button = ctk.CTkButton(
            output_start_frame,
            text="Start Clipping Queue",
            command=self.app_logic._toggle_processing, # Calls method in main app
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.start_stop_button.pack(pady=15)
        # Initial state set by main app's _update_button_state call later

    # --- Method to update the clip count label (NOW INSIDE ClippingTab) ---
    def _update_clip_count_label(self, value=None):
        """Update clip count label based on slider value."""
        try:
            # Get value from main app's variable
            count = self.app_logic.clip_count_var.get()
            # Check if the label widget exists before configuring
            if hasattr(self, 'clip_count_label') and self.clip_count_label.winfo_exists():
                self.clip_count_label.configure(text=f"{count}") # Display the count
        except Exception as e:
             print(f"Error updating clip count label: {e}")
             if hasattr(self, 'clip_count_label') and self.clip_count_label.winfo_exists():
                  self.clip_count_label.configure(text="N/A") # Show error state

    # --- Public method for main app to update queue display ---
    def update_queue_display(self, video_queue):
        """Updates the Treeview widget with the current video queue."""
        try:
            selected_item = self.queue_tree.focus() # Get currently focused item ID
            # Clear existing items safely
            for item in self.queue_tree.get_children():
                try: self.queue_tree.delete(item)
                except tk.TclError: pass # Ignore if item already gone

            # Insert new items
            for i, file_path in enumerate(video_queue):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                display_name = os.path.basename(file_path)
                try: self.queue_tree.insert('', tk.END, values=(display_name,), tags=(tag,), iid=file_path)
                except tk.TclError: self.queue_tree.insert('', tk.END, values=(display_name,), tags=(tag,)) # Fallback iid

            # Restore selection if item still exists
            if selected_item and self.queue_tree.exists(selected_item):
                self.queue_tree.focus(selected_item)
                self.queue_tree.selection_set(selected_item)

            # Apply theme tags *after* inserting
            self.apply_treeview_theme_tags(self.app_logic.theme)

        except Exception as e:
            print(f"Error updating ClippingTab queue display: {e}")
            traceback.print_exc()

    def apply_treeview_theme_tags(self, theme_name):
        """Helper to apply theme colors to Treeview rows."""
        style = ttk.Style()
        if theme_name == "dark":
            odd_bg, even_bg, fg_color, sel_bg = "#2A2D2E", "#242424", "white", "#36719F"
        else: # Assume light
            odd_bg, even_bg, fg_color, sel_bg = "#FFFFFF", "#F0F0F0", "black", "#0078D7"
        try:
            self.queue_tree.tag_configure('oddrow', background=odd_bg, foreground=fg_color)
            self.queue_tree.tag_configure('evenrow', background=even_bg, foreground=fg_color)
            # Update selection color via style map
            style.map('Treeview', background=[('selected', sel_bg)])
        except Exception as e: print(f"Could not apply treeview styling in ClippingTab: {e}")

    def apply_spinbox_theme_tags(self, theme_name):
         """Applies theme colors to the tk.Spinbox widgets in this tab."""
         bg = "#333333" if theme_name == "dark" else "#EBEBEB"
         fg = "#FFFFFF" if theme_name == "dark" else "#000000"
         try:
             # Check if widgets exist before configuring
             if hasattr(self, 'min_length_spinbox') and self.min_length_spinbox.winfo_exists():
                 self.min_length_spinbox.configure(bg=bg, fg=fg)
             if hasattr(self, 'max_length_spinbox') and self.max_length_spinbox.winfo_exists():
                 self.max_length_spinbox.configure(bg=bg, fg=fg)
         except Exception as e: print(f"Error applying theme to spinboxes: {e}")


# ==============================================================================
# ==============================================================================


class AIShortTab(ctk.CTkFrame):
    """Frame containing widgets for the AI Short Generator tab."""
    def __init__(self, master, app_logic, **kwargs):
        super().__init__(master, **kwargs)
        self.app_logic = app_logic # Reference to main VideoClipperApp instance
        print("Initializing AIShortTab UI...")

        # Make the main frame within the tab scrollable
        scrollable_frame = ctk.CTkScrollableFrame(self)
        scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self._create_widgets(scrollable_frame)
        print("AIShortTab UI widgets created.")


    def _create_widgets(self, master_frame):
        """Creates widgets inside the scrollable frame for the AI Short Tab."""
        ctk.CTkLabel(master_frame, text="AI Short Generator", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 15), anchor="w", padx=10)

        # --- Inputs ---
        input_section_frame = ctk.CTkFrame(master_frame)
        input_section_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(input_section_frame, text="Inputs", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 5), anchor="w")

        # Background Video Selection
        bg_video_frame = ctk.CTkFrame(input_section_frame)
        bg_video_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(bg_video_frame, text="Background Video:", width=150, anchor="w").pack(side="left", padx=5)
        bg_video_entry = ctk.CTkEntry(bg_video_frame, textvariable=self.app_logic.ai_video_path_var, placeholder_text="Select base video footage")
        bg_video_entry.pack(side="left", expand=True, padx=(0, 10))
        # Create method in *this* class to call the main app's filedialog
        bg_video_button = ctk.CTkButton(bg_video_frame, text="Select Video", command=self._select_ai_video, width=110)
        bg_video_button.pack(side="left")

        # Script Text Input
        ctk.CTkLabel(input_section_frame, text="Script Text:", font=ctk.CTkFont(size=14)).pack(pady=(10, 2), anchor="w")
        # Store reference to the textbox on self for easy access
        self.script_textbox = ctk.CTkTextbox(input_section_frame, height=150, wrap="word") # Enable word wrap
        self.script_textbox.pack(fill="x", pady=(0, 10), padx=5)
        self.script_textbox.insert("0.0", "Enter the script for the AI voiceover here...\nOne sentence or phrase per line is often best for subtitle timing.")


        # --- Options ---
        options_section_frame = ctk.CTkFrame(master_frame)
        options_section_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(options_section_frame, text="AI Options", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 10), anchor="w")

        # Polly Voice Selection (Example)
        polly_frame = ctk.CTkFrame(options_section_frame)
        polly_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(polly_frame, text="AI Voice (Polly):", width=150, anchor="w").pack(side="left", padx=5)
        # Consider fetching voices dynamically if possible, otherwise use a static list
        polly_voices = ["Joanna", "Matthew", "Ivy", "Justin", "Kendra", "Kimberly", "Salli", "Joey", "Stephen", "Brian", "Emma", "Amy", "Geraint", "Nicole", "Russell", "Olivia"]
        voice_menu = ctk.CTkOptionMenu(polly_frame, variable=self.app_logic.ai_polly_voice_var, values=polly_voices)
        voice_menu.pack(side="left", padx=5)

        # Subtitle Font Size
        style_frame = ctk.CTkFrame(options_section_frame)
        style_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(style_frame, text="Subtitle Font Size:", width=150, anchor="w").pack(side="left", padx=5)
        # Store spinbox ref for theme updates
        self.font_size_spinbox = tk.Spinbox(style_frame, from_=10, to=72, increment=2,
                                            textvariable=self.app_logic.ai_font_size_var, width=5,
                                            highlightthickness=0, relief="flat", wrap=True, justify='center')
        self.font_size_spinbox.pack(side="left", padx=5)
        self.apply_spinbox_theme_tags(self.app_logic.theme) # Apply initial theme

        # Add more styling widgets here (e.g., color buttons) if re-implementing


        # --- Output ---
        output_section_frame = ctk.CTkFrame(master_frame)
        output_section_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(output_section_frame, text="Output Location", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 10), anchor="w")

        ai_output_frame = ctk.CTkFrame(output_section_frame)
        ai_output_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(ai_output_frame, text="Save AI Short To:", width=150, anchor="w").pack(side="left", padx=5)
        ai_output_entry = ctk.CTkEntry(ai_output_frame, textvariable=self.app_logic.ai_output_path_var, placeholder_text="Select save location for the final short")
        ai_output_entry.pack(side="left", expand=True, padx=(0, 10))
        # Create method in *this* class to call the main app's filedialog
        ai_output_button = ctk.CTkButton(ai_output_frame, text="Select Location", command=self._select_ai_output, width=110)
        ai_output_button.pack(side="left")

        # --- Generate Button ---
        # Store reference on self for state updates
        self.generate_button = ctk.CTkButton(
            master_frame, # Pack in the main scrollable frame
            text="Generate AI Short",
            command=self.app_logic._apply_ai_short_generation, # Calls method in main app
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.generate_button.pack(pady=20)
        # Initial state set by main app's _update_button_state call


    # --- Methods specific to this tab's widgets ---
    def _select_ai_video(self):
        """Handles 'Select Video' button click for AI background source."""
        path = filedialog.askopenfilename(title="Select Background Video",
                                          filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv *.wmv"), ("All Files", "*.*")])
        if path:
            self.app_logic.ai_video_path_var.set(path) # Set variable in main app logic

    def _select_ai_output(self):
        """Handles 'Select Location' button click for final AI short output."""
        # Suggest starting in the main output directory if set
        initial_dir = self.app_logic.output_path_var.get() or None
        path = filedialog.askdirectory(title="Select Output Location for AI Short", initialdir=initial_dir)
        if path:
            self.app_logic.ai_output_path_var.set(path) # Set variable in main app logic

    def apply_spinbox_theme_tags(self, theme_name):
         """Applies theme colors to the tk.Spinbox widgets in this tab."""
         bg = "#333333" if theme_name == "dark" else "#EBEBEB"
         fg = "#FFFFFF" if theme_name == "dark" else "#000000"
         try:
             # Check if widget exists before configuring
             if hasattr(self, 'font_size_spinbox') and self.font_size_spinbox.winfo_exists():
                 self.font_size_spinbox.configure(bg=bg, fg=fg)
         except Exception as e:
             print(f"Error applying theme to AI tab spinbox: {e}")