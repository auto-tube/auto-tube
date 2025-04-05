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
                                          command=self._update_clip_count_label) # Link to local method
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


    def _update_clip_count_label(self, value=None):
        """Update clip count label based on slider value."""
        try:
            count = self.app_logic.clip_count_var.get()
            if hasattr(self, 'clip_count_label') and self.clip_count_label.winfo_exists():
                self.clip_count_label.configure(text=f"{count}")
        except Exception as e:
             print(f"Error updating clip count label: {e}")
             if hasattr(self, 'clip_count_label') and self.clip_count_label.winfo_exists():
                  self.clip_count_label.configure(text="N/A")

    def update_queue_display(self, video_queue):
        """Updates the Treeview widget with the current video queue."""
        try:
            # Deselect item before repopulating to avoid potential issues
            # self.queue_tree.selection_remove(self.queue_tree.focus())
            # self.queue_tree.focus('') # Clear focus

            # Clear existing items
            for item in self.queue_tree.get_children():
                self.queue_tree.delete(item)

            # Insert new items
            for i, file_path in enumerate(video_queue):
                tag = 'evenrow' if i % 2 == 0 else 'oddrow'
                display_name = os.path.basename(file_path)
                try:
                    # Use file_path as iid for potential future reference/deletion
                    self.queue_tree.insert('', tk.END, values=(display_name,), tags=(tag,), iid=file_path)
                except tk.TclError as e:
                    # Handle potential TclError if iid already exists (shouldn't happen with clear)
                    print(f"Warning: TclError inserting item '{display_name}' with iid '{file_path}': {e}")
                    # Fallback without iid (less ideal)
                    self.queue_tree.insert('', tk.END, values=(display_name,), tags=(tag,))

            # Apply theme (might be needed after insert/delete)
            self.apply_treeview_theme_tags(self.app_logic.theme)
        except Exception as e:
            print(f"Error updating ClippingTab queue display: {e}")
            traceback.print_exc()


    def apply_treeview_theme_tags(self, theme_name):
        """Helper to apply theme colors to Treeview rows."""
        style = ttk.Style()
        if theme_name == "dark": odd_bg, even_bg, fg_color, sel_bg = "#2A2D2E", "#242424", "white", "#36719F"; heading_bg, heading_fg = "#565B5E", "white"
        else: odd_bg, even_bg, fg_color, sel_bg = "#FFFFFF", "#F0F0F0", "black", "#0078D7"; heading_bg, heading_fg = "#E1E1E1", "black"
        try:
            style.configure("Treeview", background=odd_bg, foreground=fg_color, fieldbackground=odd_bg, borderwidth=0, rowheight=25)
            style.map('Treeview', background=[('selected', sel_bg)], foreground=[('selected', 'white')])
            style.configure("Treeview.Heading", background=heading_bg, foreground=heading_fg, relief="flat", font=('Arial', 10, 'bold'))
            style.map("Treeview.Heading", background=[('active', heading_bg)])
            self.queue_tree.tag_configure('oddrow', background=odd_bg, foreground=fg_color)
            self.queue_tree.tag_configure('evenrow', background=even_bg, foreground=fg_color)
        except Exception as e: print(f"Could not apply treeview styling in ClippingTab: {e}")

    def apply_spinbox_theme_tags(self, theme_name):
         """Applies theme colors to the tk.Spinbox widgets in this tab."""
         bg = "#333333" if theme_name == "dark" else "#EBEBEB"; fg = "#FFFFFF" if theme_name == "dark" else "#000000"
         try:
             if hasattr(self, 'min_length_spinbox') and self.min_length_spinbox.winfo_exists(): self.min_length_spinbox.configure(bg=bg, fg=fg, buttonbackground=bg)
             if hasattr(self, 'max_length_spinbox') and self.max_length_spinbox.winfo_exists(): self.max_length_spinbox.configure(bg=bg, fg=fg, buttonbackground=bg)
         except Exception as e: print(f"Error applying theme to spinboxes: {e}")


# ==============================================================================
# ==============================================================================


class AIShortTab(ctk.CTkFrame):
    """Frame containing widgets for the AI Short Generator tab."""
    def __init__(self, master, app_logic, **kwargs):
        super().__init__(master, **kwargs)
        self.app_logic = app_logic
        print("Initializing AIShortTab UI...")
        scrollable_frame = ctk.CTkScrollableFrame(self)
        scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)
        self._create_widgets(scrollable_frame)
        print("AIShortTab UI widgets created.")

    def _create_widgets(self, master_frame):
        """Creates widgets inside the scrollable frame for the AI Short Tab."""
        ctk.CTkLabel(master_frame, text="AI Short Generator", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 15), anchor="w", padx=10)

        # --- Inputs Section ---
        input_section_frame = ctk.CTkFrame(master_frame)
        input_section_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(input_section_frame, text="Inputs", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 5), anchor="w")

        # Background Video Selection
        bg_video_frame = ctk.CTkFrame(input_section_frame)
        bg_video_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(bg_video_frame, text="Background Video:", width=150, anchor="w").pack(side="left", padx=5)
        bg_video_entry = ctk.CTkEntry(bg_video_frame, textvariable=self.app_logic.ai_video_path_var, placeholder_text="Select base video footage")
        bg_video_entry.pack(side="left", expand=True, padx=(0, 10))
        bg_video_button = ctk.CTkButton(bg_video_frame, text="Select Video", command=self._select_ai_video, width=110)
        bg_video_button.pack(side="left")

        # --- Script Generation ---
        script_gen_frame = ctk.CTkFrame(input_section_frame)
        script_gen_frame.pack(fill="x", pady=(10, 5))
        ctk.CTkLabel(script_gen_frame, text="Generate Script (Optional)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")
        prompt_frame = ctk.CTkFrame(script_gen_frame); prompt_frame.pack(fill="x", pady=(2,5))
        ctk.CTkLabel(prompt_frame, text="Niche/Idea Prompt:", anchor="w").pack(side="left", padx=5)
        self.script_prompt_entry = ctk.CTkEntry(prompt_frame, textvariable=self.app_logic.ai_script_prompt_var, placeholder_text="e.g., 'quick tips for beginner Python programmers'")
        self.script_prompt_entry.pack(side="left", expand=True, padx=5)
        # Store button ref for state updates
        self.generate_script_button = ctk.CTkButton(script_gen_frame, text="Generate Script with Gemini", command=self.app_logic._start_script_generation)
        self.generate_script_button.pack(pady=5)

        # Script Text Input/Display Area
        ctk.CTkLabel(input_section_frame, text="Script Text (Edit or Paste Here):", font=ctk.CTkFont(size=14)).pack(pady=(10, 2), anchor="w")
        self.script_textbox = ctk.CTkTextbox(input_section_frame, height=150, wrap="word")
        self.script_textbox.pack(fill="x", pady=(0, 10), padx=5)
        self.script_textbox.insert("0.0", "Enter script manually, or generate one above...")
        # Make sure script textbox is accessible from app_logic for script generation result
        # self.app_logic.ai_script_textbox_ref = self.script_textbox # One way, if needed

        # --- AI Options Section ---
        options_section_frame = ctk.CTkFrame(master_frame)
        options_section_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(options_section_frame, text="AI Options", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 10), anchor="w")

        # Polly Voice Selection
        polly_frame = ctk.CTkFrame(options_section_frame)
        polly_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(polly_frame, text="AI Voice (Polly):", width=150, anchor="w").pack(side="left", padx=5)
        # Consider making this dynamic or checking available voices if possible
        polly_voices = ["Joanna", "Matthew", "Ivy", "Justin", "Kendra", "Kimberly", "Salli", "Joey", "Stephen", "Brian", "Emma", "Amy", "Geraint", "Nicole", "Russell", "Olivia"]
        voice_menu = ctk.CTkOptionMenu(polly_frame, variable=self.app_logic.ai_polly_voice_var, values=polly_voices)
        voice_menu.pack(side="left", padx=5)

        # Subtitle Font Size
        style_frame = ctk.CTkFrame(options_section_frame)
        style_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(style_frame, text="Subtitle Font Size:", width=150, anchor="w").pack(side="left", padx=5)
        self.font_size_spinbox = tk.Spinbox(style_frame, from_=10, to=300, increment=2, textvariable=self.app_logic.ai_font_size_var, width=5, highlightthickness=0, relief="flat", wrap=True, justify='center')
        self.font_size_spinbox.pack(side="left", padx=5)
        self.apply_spinbox_theme_tags(self.app_logic.theme) # Apply initial theme

        # --- Output Section ---
        output_section_frame = ctk.CTkFrame(master_frame)
        output_section_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(output_section_frame, text="Output Location", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 10), anchor="w")
        ai_output_frame = ctk.CTkFrame(output_section_frame)
        ai_output_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(ai_output_frame, text="Save AI Short To:", width=150, anchor="w").pack(side="left", padx=5)
        ai_output_entry = ctk.CTkEntry(ai_output_frame, textvariable=self.app_logic.ai_output_path_var, placeholder_text="Select save location for the final short")
        ai_output_entry.pack(side="left", expand=True, padx=(0, 10))
        ai_output_button = ctk.CTkButton(ai_output_frame, text="Select Location", command=self._select_ai_output, width=110)
        ai_output_button.pack(side="left")

        # --- Generate Button ---
        self.generate_button = ctk.CTkButton(master_frame, text="Generate AI Short (using Script Text)", command=self.app_logic._apply_ai_short_generation, font=ctk.CTkFont(size=16, weight="bold"))
        self.generate_button.pack(pady=20)
        # Initial state set by main app's _update_button_state

    # --- Methods specific to this tab's widgets ---
    def _select_ai_video(self):
        path = filedialog.askopenfilename(title="Select Background Video", filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv *.wmv"), ("All Files", "*.*")])
        if path: self.app_logic.ai_video_path_var.set(path)

    def _select_ai_output(self):
        # Try starting in the main output dir if set, otherwise user's default
        initial_dir = self.app_logic.output_path_var.get() or None
        path = filedialog.askdirectory(title="Select Output Location for AI Short", initialdir=initial_dir)
        if path: self.app_logic.ai_output_path_var.set(path)

    def apply_spinbox_theme_tags(self, theme_name):
         bg = "#333333" if theme_name == "dark" else "#EBEBEB"; fg = "#FFFFFF" if theme_name == "dark" else "#000000"
         try:
             if hasattr(self, 'font_size_spinbox') and self.font_size_spinbox.winfo_exists(): self.font_size_spinbox.configure(bg=bg, fg=fg, buttonbackground=bg)
         except Exception as e: print(f"Error applying theme to AI tab spinbox: {e}")


# ==============================================================================
# ==============================================================================

# <<< --- MetadataTab Class with Corrected Widget Names --- >>>
class MetadataTab(ctk.CTkFrame):
    """Frame containing widgets for the Metadata Generation tab."""
    def __init__(self, master, app_logic, **kwargs):
        super().__init__(master, **kwargs)
        self.app_logic = app_logic
        print("Initializing MetadataTab UI...")

        scrollable_frame = ctk.CTkScrollableFrame(self)
        scrollable_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self._create_widgets(scrollable_frame)
        print("MetadataTab UI widgets created.")

    def _create_widgets(self, master_frame):
        """Creates widgets for generating hashtags, tags, and titles."""
        ctk.CTkLabel(master_frame, text="AI Metadata Generator (Gemini)", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 15), anchor="w", padx=10)

        # --- Input Context ---
        context_frame = ctk.CTkFrame(master_frame)
        context_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(context_frame, text="Video Topic / Description Context:", font=ctk.CTkFont(size=14)).pack(anchor="w")
        # Store ref to textbox, main app accesses content via this ref
        self.context_textbox = ctk.CTkTextbox(context_frame, height=100, wrap="word")
        self.context_textbox.pack(fill="x", pady=(2, 10))
        self.context_textbox.insert("0.0", "Enter the main topic, keywords, or a short description of your video here...")
        # Link this widget to the variable in the main app - THIS IS NOT NEEDED
        # The main app already accesses it via self.metadata_tab.context_textbox.get(...)
        # self.app_logic.metadata_context_var = self.context_textbox # REMOVED


        # --- Hashtag Section ---
        hashtag_frame = ctk.CTkFrame(master_frame)
        hashtag_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(hashtag_frame, text="Hashtags", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")

        hashtag_controls = ctk.CTkFrame(hashtag_frame)
        hashtag_controls.pack(fill="x", pady=(5,2))
        ctk.CTkLabel(hashtag_controls, text="Count:", width=50).pack(side="left", padx=5)
        # Store spinbox ref
        self.hashtag_spinbox = tk.Spinbox(hashtag_controls, from_=1, to=50, increment=1,
                                          textvariable=self.app_logic.metadata_hashtag_count_var, width=5,
                                          highlightthickness=0, relief="flat", wrap=True, justify='center')
        self.hashtag_spinbox.pack(side="left", padx=5)
        # Store button ref
        self.generate_hashtag_button = ctk.CTkButton(hashtag_controls, text="Generate Hashtags",
                                                      command=self.app_logic._start_hashtag_generation) # Calls main app method
        self.generate_hashtag_button.pack(side="left", padx=20)

        # *** CORRECTED NAME HERE ***
        # Store output box ref (use singular name)
        self.hashtag_output_box = ctk.CTkTextbox(hashtag_frame, height=80, wrap="word", state="disabled") # Start disabled
        self.hashtag_output_box.pack(fill="x", pady=(0, 5))


        # --- Tags Section ---
        tag_frame = ctk.CTkFrame(master_frame)
        tag_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(tag_frame, text="YouTube Tags (Keywords)", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")

        tag_controls = ctk.CTkFrame(tag_frame)
        tag_controls.pack(fill="x", pady=(5,2))
        ctk.CTkLabel(tag_controls, text="Count:", width=50).pack(side="left", padx=5)
        # Store spinbox ref
        self.tag_spinbox = tk.Spinbox(tag_controls, from_=1, to=50, increment=1,
                                      textvariable=self.app_logic.metadata_tag_count_var, width=5,
                                      highlightthickness=0, relief="flat", wrap=True, justify='center')
        self.tag_spinbox.pack(side="left", padx=5)
        # Store button ref
        self.generate_tag_button = ctk.CTkButton(tag_controls, text="Generate Tags",
                                                  command=self.app_logic._start_tag_generation)
        self.generate_tag_button.pack(side="left", padx=20)

        # *** CORRECTED NAME HERE ***
        # Store output box ref (use singular name)
        self.tag_output_box = ctk.CTkTextbox(tag_frame, height=80, wrap="word", state="disabled")
        self.tag_output_box.pack(fill="x", pady=(0, 5))


        # --- Title Ideas Section ---
        title_frame = ctk.CTkFrame(master_frame)
        title_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(title_frame, text="Video Title Ideas", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")

        title_controls = ctk.CTkFrame(title_frame)
        title_controls.pack(fill="x", pady=(5,2))
        ctk.CTkLabel(title_controls, text="Count:", width=50).pack(side="left", padx=5)
        # Store spinbox ref
        self.title_spinbox = tk.Spinbox(title_controls, from_=1, to=10, increment=1,
                                        textvariable=self.app_logic.metadata_title_count_var, width=5,
                                        highlightthickness=0, relief="flat", wrap=True, justify='center')
        self.title_spinbox.pack(side="left", padx=5)
        # Store button ref
        self.generate_title_button = ctk.CTkButton(title_controls, text="Generate Titles",
                                                    command=self.app_logic._start_title_generation)
        self.generate_title_button.pack(side="left", padx=20)

        # *** CORRECTED NAME HERE ***
        # Store output box ref (use singular name)
        self.title_output_box = ctk.CTkTextbox(title_frame, height=80, wrap="word", state="disabled")
        self.title_output_box.pack(fill="x", pady=(0, 5))

        # Apply initial theme to spinboxes in this tab
        self.apply_spinbox_theme_tags(self.app_logic.theme)
        # Initial button states will be set by main app's _update_button_state


    def apply_spinbox_theme_tags(self, theme_name):
         """Applies theme colors to the tk.Spinbox widgets in this tab."""
         bg = "#333333" if theme_name == "dark" else "#EBEBEB"
         fg = "#FFFFFF" if theme_name == "dark" else "#000000"
         try:
             # Check if widgets exist before configuring
             if hasattr(self, 'hashtag_spinbox') and self.hashtag_spinbox.winfo_exists():
                 self.hashtag_spinbox.configure(bg=bg, fg=fg, buttonbackground=bg)
             if hasattr(self, 'tag_spinbox') and self.tag_spinbox.winfo_exists():
                 self.tag_spinbox.configure(bg=bg, fg=fg, buttonbackground=bg)
             if hasattr(self, 'title_spinbox') and self.title_spinbox.winfo_exists():
                 self.title_spinbox.configure(bg=bg, fg=fg, buttonbackground=bg)
         except Exception as e:
             print(f"Error applying theme to metadata tab spinboxes: {e}")