# ui/ui_tabs.py
from tkinter import filedialog
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
from tkinterdnd2 import DND_FILES # Import necessary constants
import os # For basename
import traceback # For error logging

# --- ClippingTab Class (Corrected Methods) ---
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
        input_queue_frame = ctk.CTkFrame(master_frame); input_queue_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(input_queue_frame, text="Input Videos/Folder", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 5), anchor="w")
        input_frame = ctk.CTkFrame(input_queue_frame); input_frame.pack(fill="x")
        input_entry = ctk.CTkEntry(input_frame, textvariable=self.app_logic.input_path_var, placeholder_text="Drag & Drop or Browse"); input_entry.pack(side="left", expand=True, padx=(0, 10), pady=5)
        try:
            input_entry.drop_target_register(DND_FILES)
            input_entry.dnd_bind('<<Drop>>', self.app_logic._drop_input)
        except Exception as e: print(f"Warning: Failed to initialize Drag and Drop for ClippingTab Input: {e}")
        input_button = ctk.CTkButton(input_frame, text="Browse", command=self.app_logic._select_input, width=80); input_button.pack(side="right", pady=5)
        ctk.CTkCheckBox(input_queue_frame, text="Add Folder Contents (Batch Mode)", variable=self.app_logic.batch_mode_var).pack(pady=5, anchor="w")
        ctk.CTkLabel(input_queue_frame, text="Video Queue", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5), anchor="w")
        tree_frame = ctk.CTkFrame(input_queue_frame); tree_frame.pack(fill='x', pady=5)
        self.queue_tree = ttk.Treeview(tree_frame, columns=('Filepath',), show='headings', height=6, style="Treeview")
        self.queue_tree.heading('Filepath', text='Queued Videos'); self.queue_tree.column('Filepath', width=600, anchor='w')
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.queue_tree.yview); self.queue_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y'); self.queue_tree.pack(side='left', fill='x', expand=True)
        clear_queue_button = ctk.CTkButton(input_queue_frame, text="Clear Queue", command=self.app_logic._clear_queue, width=100, fg_color="red", hover_color="#C40000"); clear_queue_button.pack(pady=5, anchor="e")
        # --- Processing Options Section ---
        options_frame = ctk.CTkFrame(master_frame); options_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(options_frame, text="Clipping Options", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 10), anchor="w")
        clip_length_frame = ctk.CTkFrame(options_frame); clip_length_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(clip_length_frame, text="Clip Length (s)  Min:").pack(side="left", padx=(0, 5))
        self.min_length_spinbox = tk.Spinbox(clip_length_frame, from_=1, to=600, increment=1, textvariable=self.app_logic.min_clip_length_var, width = 5, highlightthickness=0, relief="flat", wrap=True, justify='center'); self.min_length_spinbox.pack(side="left", padx = (0,10))
        ctk.CTkLabel(clip_length_frame, text="Max:").pack(side="left", padx=5)
        self.max_length_spinbox = tk.Spinbox(clip_length_frame, from_=1, to=600, increment=1, textvariable=self.app_logic.max_clip_length_var, width=5, highlightthickness=0, relief="flat", wrap=True, justify='center'); self.max_length_spinbox.pack(side="left", padx=5)
        self.apply_spinbox_theme_tags(self.app_logic.theme) # Apply initial theme
        clip_count_frame = ctk.CTkFrame(options_frame); clip_count_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(clip_count_frame, text="Number of Clips:", font=ctk.CTkFont(size=14)).pack(side="left", padx=(0,10))
        self.clip_count_label = ctk.CTkLabel(clip_count_frame, text="5", width=25, anchor='e'); self.clip_count_label.pack(side="right", padx=(5,0))
        clip_count_slider = ctk.CTkSlider(clip_count_frame, from_=1, to=20, number_of_steps=19, variable=self.app_logic.clip_count_var, command=self._update_clip_count_label); clip_count_slider.pack(side="left", fill="x", expand=True, padx=5)
        self._update_clip_count_label() # Initialize label
        scene_frame = ctk.CTkFrame(options_frame); scene_frame.pack(fill="x", pady=5)
        ctk.CTkCheckBox(scene_frame, text="Use Scene Detection", variable=self.app_logic.scene_detect_var).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(scene_frame, text="Threshold:").pack(side="left", padx=5)
        scene_threshold_entry = ctk.CTkEntry(scene_frame, textvariable=self.app_logic.scene_threshold_var, width=50, justify='center'); scene_threshold_entry.pack(side="left", padx=5)
        ctk.CTkLabel(options_frame, text="Other Options:", font=ctk.CTkFont(size=14)).pack(pady=(10, 2), anchor="w")
        option_checkboxes_frame = ctk.CTkFrame(options_frame); option_checkboxes_frame.pack(fill="x", pady=5)
        col1_frame = ctk.CTkFrame(option_checkboxes_frame); col1_frame.pack(side="left", padx=5, anchor="nw")
        col2_frame = ctk.CTkFrame(option_checkboxes_frame); col2_frame.pack(side="left", padx=5, anchor="nw")
        options = [
            ("Remove Audio", self.app_logic.remove_audio_var, col1_frame),
            ("Extract Audio (.mp3)", self.app_logic.extract_audio_var, col1_frame),
            ("Vertical Crop (9:16)", self.app_logic.vertical_crop_var, col1_frame),
            ("Mirror Video", self.app_logic.mirror_var, col2_frame),
            ("Enhance Video", self.app_logic.enhance_var, col2_frame)
        ]
        # FIX for line 72-75: Use standard loop
        for text, var, frame in options:
            ctk.CTkCheckBox(frame, text=text, variable=var).pack(anchor="w", pady=2)

        # --- Output & Start Section ---
        output_start_frame = ctk.CTkFrame(master_frame); output_start_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(output_start_frame, text="Output Location (Clips)", font=ctk.CTkFont(size=16)).pack(pady=(0, 5), anchor="w")
        output_frame = ctk.CTkFrame(output_start_frame); output_frame.pack(fill="x")
        output_entry = ctk.CTkEntry(output_frame, textvariable=self.app_logic.output_path_var, placeholder_text="Select default output in Settings tab"); output_entry.pack(side="left", expand=True, padx=(0, 10), pady=5)
        output_button = ctk.CTkButton(output_frame, text="Browse", command=self.app_logic._select_output, width=100); output_button.pack(side="right", pady=5)
        self.start_stop_button = ctk.CTkButton(output_start_frame, text="Start Clipping Queue", command=self.app_logic._toggle_processing, font=ctk.CTkFont(size=16, weight="bold")); self.start_stop_button.pack(pady=15)

    def _update_clip_count_label(self, value=None):
        # FIX for line 73 (inside original method) - Standard try-except
        try:
            count = self.app_logic.clip_count_var.get()
            if hasattr(self, 'clip_count_label') and self.clip_count_label.winfo_exists():
                self.clip_count_label.configure(text=f"{count}")
        except Exception as e:
            print(f"Error updating clip count label: {e}")
            # Optionally set a default text on error
            if hasattr(self, 'clip_count_label') and self.clip_count_label.winfo_exists():
                self.clip_count_label.configure(text="Err")

    def update_queue_display(self, video_queue):
        # FIX for line 74 (inside original method) - Standard try-except
        try:
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
                except tk.TclError:
                    # Fallback if iid somehow already exists (shouldn't happen with clear)
                    self.queue_tree.insert('', tk.END, values=(display_name,), tags=(tag,))
            # Apply theme after updates
            self.apply_treeview_theme_tags(self.app_logic.theme)
        except Exception as e:
            print(f"Error updating ClippingTab queue display: {e}")
            traceback.print_exc()

    def apply_treeview_theme_tags(self, theme_name):
        # FIX for line 75 (inside original method) - Standard try-except and assignments
        style = ttk.Style()
        odd_bg, even_bg, fg_color, sel_bg, heading_bg, heading_fg = "", "", "", "", "", "" # Initialize
        if theme_name == "dark":
            odd_bg, even_bg, fg_color, sel_bg = "#2A2D2E", "#242424", "white", "#36719F"
            heading_bg, heading_fg = "#565B5E", "white"
        else: # Assume light theme otherwise
            odd_bg, even_bg, fg_color, sel_bg = "#FFFFFF", "#F0F0F0", "black", "#0078D7"
            heading_bg, heading_fg = "#E1E1E1", "black"
        try:
            style.configure("Treeview", background=odd_bg, foreground=fg_color, fieldbackground=odd_bg, borderwidth=0, rowheight=25)
            style.map('Treeview', background=[('selected', sel_bg)], foreground=[('selected', 'white')])
            style.configure("Treeview.Heading", background=heading_bg, foreground=heading_fg, relief="flat", font=('Arial', 10, 'bold'))
            style.map("Treeview.Heading", background=[('active', heading_bg)]) # Ensure hover/active style matches
            # Apply tags to existing items (or configure tags for future items)
            self.queue_tree.tag_configure('oddrow', background=odd_bg, foreground=fg_color)
            self.queue_tree.tag_configure('evenrow', background=even_bg, foreground=fg_color)
        except Exception as e:
            print(f"Could not apply treeview styling in ClippingTab: {e}")

    def apply_spinbox_theme_tags(self, theme_name):
         bg = "#333333" if theme_name == "dark" else "#EBEBEB"; fg = "#FFFFFF" if theme_name == "dark" else "#000000"
         try:
             # Check widgets exist before configuring
             if hasattr(self, 'min_length_spinbox') and self.min_length_spinbox.winfo_exists():
                 self.min_length_spinbox.configure(bg=bg, fg=fg, buttonbackground=bg)
             if hasattr(self, 'max_length_spinbox') and self.max_length_spinbox.winfo_exists():
                 self.max_length_spinbox.configure(bg=bg, fg=fg, buttonbackground=bg)
         except Exception as e: print(f"Error applying theme to spinboxes: {e}")


# --- AIShortTab Class (Corrected Methods) ---
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
        input_section_frame = ctk.CTkFrame(master_frame); input_section_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(input_section_frame, text="Inputs", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 5), anchor="w")
        # Background Video Selection
        bg_video_frame = ctk.CTkFrame(input_section_frame); bg_video_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(bg_video_frame, text="Background Video:", width=150, anchor="w").pack(side="left", padx=5)
        bg_video_entry = ctk.CTkEntry(bg_video_frame, textvariable=self.app_logic.ai_video_path_var, placeholder_text="Select base video footage"); bg_video_entry.pack(side="left", expand=True, padx=(0, 10))
        bg_video_button = ctk.CTkButton(bg_video_frame, text="Select Video", command=self._select_ai_video, width=110); bg_video_button.pack(side="left")
        # --- Script Generation ---
        script_gen_frame = ctk.CTkFrame(input_section_frame); script_gen_frame.pack(fill="x", pady=(10, 5))
        ctk.CTkLabel(script_gen_frame, text="Generate Script (Optional)", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w")
        prompt_frame = ctk.CTkFrame(script_gen_frame); prompt_frame.pack(fill="x", pady=(2,5))
        ctk.CTkLabel(prompt_frame, text="Niche/Idea Prompt:", anchor="w").pack(side="left", padx=5)
        self.script_prompt_entry = ctk.CTkEntry(prompt_frame, textvariable=self.app_logic.ai_script_prompt_var, placeholder_text="e.g., 'quick tips for beginner Python programmers'"); self.script_prompt_entry.pack(side="left", expand=True, padx=5)
        self.generate_script_button = ctk.CTkButton(script_gen_frame, text="Generate Script with Gemini", command=self.app_logic._start_script_generation); self.generate_script_button.pack(pady=5)
        # Script Text Input/Display Area
        ctk.CTkLabel(input_section_frame, text="Script Text (Edit or Paste Here):", font=ctk.CTkFont(size=14)).pack(pady=(10, 2), anchor="w")
        self.script_textbox = ctk.CTkTextbox(input_section_frame, height=150, wrap="word"); self.script_textbox.pack(fill="x", pady=(0, 10), padx=5); self.script_textbox.insert("0.0", "Enter script manually, or generate one above...")
        # --- AI Options Section ---
        options_section_frame = ctk.CTkFrame(master_frame); options_section_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(options_section_frame, text="AI Options", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 10), anchor="w")
        # Polly Voice Selection
        polly_frame = ctk.CTkFrame(options_section_frame); polly_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(polly_frame, text="AI Voice (Polly):", width=150, anchor="w").pack(side="left", padx=5)
        polly_voices = ["Joanna", "Matthew", "Ivy", "Justin", "Kendra", "Kimberly", "Salli", "Joey", "Stephen", "Brian", "Emma", "Amy", "Geraint", "Nicole", "Russell", "Olivia"]
        voice_menu = ctk.CTkOptionMenu(polly_frame, variable=self.app_logic.ai_polly_voice_var, values=polly_voices); voice_menu.pack(side="left", padx=5)
        # Subtitle Font Size
        style_frame = ctk.CTkFrame(options_section_frame); style_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(style_frame, text="Subtitle Font Size:", width=150, anchor="w").pack(side="left", padx=5)
        self.font_size_spinbox = tk.Spinbox(style_frame, from_=10, to=300, increment=2, textvariable=self.app_logic.ai_font_size_var, width=5, highlightthickness=0, relief="flat", wrap=True, justify='center'); self.font_size_spinbox.pack(side="left", padx=5)
        self.apply_spinbox_theme_tags(self.app_logic.theme) # Apply theme
        # --- Output Section ---
        output_section_frame = ctk.CTkFrame(master_frame); output_section_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(output_section_frame, text="Output Location", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 10), anchor="w")
        ai_output_frame = ctk.CTkFrame(output_section_frame); ai_output_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(ai_output_frame, text="Save AI Short To:", width=150, anchor="w").pack(side="left", padx=5)
        ai_output_entry = ctk.CTkEntry(ai_output_frame, textvariable=self.app_logic.ai_output_path_var, placeholder_text="Select save location for the final short"); ai_output_entry.pack(side="left", expand=True, padx=(0, 10))
        ai_output_button = ctk.CTkButton(ai_output_frame, text="Select Location", command=self._select_ai_output, width=110); ai_output_button.pack(side="left")
        # --- Generate Button ---
        self.generate_button = ctk.CTkButton(master_frame, text="Generate AI Short (using Script Text)", command=self.app_logic._apply_ai_short_generation, font=ctk.CTkFont(size=16, weight="bold")); self.generate_button.pack(pady=20)

    def _select_ai_video(self):
        # FIX for line 135 - Standard method definition
        path = filedialog.askopenfilename(title="Select Background Video", filetypes=[("Video Files", "*.mp4 *.mov *.avi *.mkv *.wmv"), ("All Files", "*.*")])
        if path:
            self.app_logic.ai_video_path_var.set(path)

    def _select_ai_output(self):
        initial_dir = self.app_logic.output_path_var.get() or None
        path = filedialog.askdirectory(title="Select Output Location for AI Short", initialdir=initial_dir)
        if path:
            self.app_logic.ai_output_path_var.set(path)

    def apply_spinbox_theme_tags(self, theme_name):
         bg="#333333" if theme_name=="dark" else "#EBEBEB"; fg="#FFFFFF" if theme_name=="dark" else "#000000"
         try:
             # Check widget exists before configuring
             if hasattr(self, 'font_size_spinbox') and self.font_size_spinbox.winfo_exists():
                 self.font_size_spinbox.configure(bg=bg, fg=fg, buttonbackground=bg)
         except Exception as e: print(f"Error applying theme to AI tab spinbox: {e}")


# --- MetadataTab Class (Corrected Methods) ---
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
        context_frame = ctk.CTkFrame(master_frame); context_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(context_frame, text="Video Topic / Description Context:", font=ctk.CTkFont(size=14)).pack(anchor="w")
        self.context_textbox = ctk.CTkTextbox(context_frame, height=100, wrap="word"); self.context_textbox.pack(fill="x", pady=(2, 10)); self.context_textbox.insert("0.0", "Enter the main topic, keywords, or a short description of your video here...")
        # --- Hashtag Section ---
        hashtag_frame = ctk.CTkFrame(master_frame); hashtag_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(hashtag_frame, text="Hashtags", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        hashtag_controls = ctk.CTkFrame(hashtag_frame); hashtag_controls.pack(fill="x", pady=(5,2))
        ctk.CTkLabel(hashtag_controls, text="Count:", width=50).pack(side="left", padx=5)
        self.hashtag_spinbox = tk.Spinbox(hashtag_controls, from_=1, to=50, increment=1, textvariable=self.app_logic.metadata_hashtag_count_var, width=5, highlightthickness=0, relief="flat", wrap=True, justify='center'); self.hashtag_spinbox.pack(side="left", padx=5)
        self.generate_hashtag_button = ctk.CTkButton(hashtag_controls, text="Generate Hashtags", command=self.app_logic._start_hashtag_generation); self.generate_hashtag_button.pack(side="left", padx=20)
        self.hashtag_output_box = ctk.CTkTextbox(hashtag_frame, height=80, wrap="word", state="disabled"); self.hashtag_output_box.pack(fill="x", pady=(0, 5))
        # --- Tags Section ---
        tag_frame = ctk.CTkFrame(master_frame); tag_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(tag_frame, text="YouTube Tags (Keywords)", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        tag_controls = ctk.CTkFrame(tag_frame); tag_controls.pack(fill="x", pady=(5,2))
        ctk.CTkLabel(tag_controls, text="Count:", width=50).pack(side="left", padx=5)
        self.tag_spinbox = tk.Spinbox(tag_controls, from_=1, to=50, increment=1, textvariable=self.app_logic.metadata_tag_count_var, width=5, highlightthickness=0, relief="flat", wrap=True, justify='center'); self.tag_spinbox.pack(side="left", padx=5)
        self.generate_tag_button = ctk.CTkButton(tag_controls, text="Generate Tags", command=self.app_logic._start_tag_generation); self.generate_tag_button.pack(side="left", padx=20)
        self.tag_output_box = ctk.CTkTextbox(tag_frame, height=80, wrap="word", state="disabled"); self.tag_output_box.pack(fill="x", pady=(0, 5))
        # --- Title Ideas Section ---
        title_frame = ctk.CTkFrame(master_frame); title_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(title_frame, text="Video Title Ideas", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w")
        title_controls = ctk.CTkFrame(title_frame); title_controls.pack(fill="x", pady=(5,2))
        ctk.CTkLabel(title_controls, text="Count:", width=50).pack(side="left", padx=5)
        self.title_spinbox = tk.Spinbox(title_controls, from_=1, to=10, increment=1, textvariable=self.app_logic.metadata_title_count_var, width=5, highlightthickness=0, relief="flat", wrap=True, justify='center'); self.title_spinbox.pack(side="left", padx=5)
        self.generate_title_button = ctk.CTkButton(title_controls, text="Generate Titles", command=self.app_logic._start_title_generation); self.generate_title_button.pack(side="left", padx=20)
        self.title_output_box = ctk.CTkTextbox(title_frame, height=80, wrap="word", state="disabled"); self.title_output_box.pack(fill="x", pady=(0, 5))
        self.apply_spinbox_theme_tags(self.app_logic.theme) # Apply theme

    def apply_spinbox_theme_tags(self, theme_name):
        # FIX for line 182 - Standard try-except
        bg="#333333" if theme_name=="dark" else "#EBEBEB"
        fg="#FFFFFF" if theme_name=="dark" else "#000000"
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


# --- SettingsTab Class (Corrected Version from Previous Step) ---
class SettingsTab(ctk.CTkFrame):
    """Frame containing widgets for application settings."""
    def __init__(self, master, app_logic, **kwargs):
        super().__init__(master, **kwargs)
        self.app_logic = app_logic
        print("Initializing SettingsTab UI...")
        self.grid_columnconfigure(0, weight=1); self.grid_rowconfigure(0, weight=1)
        scrollable_frame = ctk.CTkScrollableFrame(self); scrollable_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        scrollable_frame.grid_columnconfigure(0, weight=1)
        self._create_widgets(scrollable_frame)
        print("SettingsTab UI widgets created.")

    def _create_widgets(self, master_frame):
        master_frame.grid_columnconfigure(0, weight=1); row_index = 0
        ctk.CTkLabel(master_frame, text="Application Settings", font=ctk.CTkFont(size=18, weight="bold")).grid(row=row_index, column=0, pady=(10, 15), padx=10, sticky="w"); row_index += 1
        api_frame = ctk.CTkFrame(master_frame); api_frame.grid(row=row_index, column=0, sticky="ew", padx=10, pady=(0, 10)); api_frame.grid_columnconfigure(1, weight=1); row_index += 1
        ctk.CTkLabel(api_frame, text="API Keys & Configuration", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=2, pady=(5, 10), padx=10, sticky="w")
        ctk.CTkLabel(api_frame, text="(Leave blank to use Environment Variables if set)", font=ctk.CTkFont(size=10)).grid(row=1, column=0, columnspan=2, pady=(0, 10), padx=10, sticky="w")
        ctk.CTkLabel(api_frame, text="Google API Key (Gemini):", anchor="w").grid(row=2, column=0, padx=(10,5), pady=5, sticky="w"); google_entry = ctk.CTkEntry(api_frame, textvariable=self.app_logic.google_api_key_var, show='*'); google_entry.grid(row=2, column=1, padx=(0,10), pady=5, sticky="ew")
        ctk.CTkLabel(api_frame, text="AWS Access Key ID:", anchor="w").grid(row=3, column=0, padx=(10,5), pady=5, sticky="w"); aws_id_entry = ctk.CTkEntry(api_frame, textvariable=self.app_logic.aws_access_key_var, show='*'); aws_id_entry.grid(row=3, column=1, padx=(0,10), pady=5, sticky="ew")
        ctk.CTkLabel(api_frame, text="AWS Secret Access Key:", anchor="w").grid(row=4, column=0, padx=(10,5), pady=5, sticky="w"); aws_secret_entry = ctk.CTkEntry(api_frame, textvariable=self.app_logic.aws_secret_key_var, show='*'); aws_secret_entry.grid(row=4, column=1, padx=(0,10), pady=5, sticky="ew")
        ctk.CTkLabel(api_frame, text="AWS Region:", anchor="w").grid(row=5, column=0, padx=(10,5), pady=5, sticky="w"); aws_regions = ["us-east-1", "us-east-2", "us-west-1", "us-west-2", "eu-west-1", "eu-west-2", "eu-central-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1"]; aws_region_menu = ctk.CTkOptionMenu(api_frame, variable=self.app_logic.aws_region_var, values=aws_regions); aws_region_menu.grid(row=5, column=1, padx=(0,10), pady=5, sticky="w")
        paths_frame = ctk.CTkFrame(master_frame); paths_frame.grid(row=row_index, column=0, sticky="ew", padx=10, pady=10); row_index += 1; ctk.CTkLabel(paths_frame, text="Executable Paths", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, pady=(5, 0), padx=10, sticky="w"); ctk.CTkLabel(paths_frame, text="(FFmpeg/FFprobe auto-detected)", font=ctk.CTkFont(size=10)).grid(row=1, column=0, pady=(0, 10), padx=10, sticky="w")
        output_frame_main = ctk.CTkFrame(master_frame); output_frame_main.grid(row=row_index, column=0, sticky="ew", padx=10, pady=10); output_frame_main.grid_columnconfigure(1, weight=1); row_index += 1
        ctk.CTkLabel(output_frame_main, text="Output & File Management", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, columnspan=3, pady=(5, 10), padx=10, sticky="w")
        ctk.CTkLabel(output_frame_main, text="Default Output Folder:", anchor="w").grid(row=1, column=0, padx=(10,5), pady=5, sticky="w"); def_output_entry = ctk.CTkEntry(output_frame_main, textvariable=self.app_logic.output_path_var, placeholder_text="Folder where processed files are saved"); def_output_entry.grid(row=1, column=1, padx=(0,10), pady=5, sticky="ew"); def_output_browse_btn = ctk.CTkButton(output_frame_main, text="Browse", width=80, command=self.app_logic._select_output); def_output_browse_btn.grid(row=1, column=2, padx=(0,10), pady=5)
        ctk.CTkCheckBox(output_frame_main, text="Organize output files into date folders (YYYY-MM-DD)", variable=self.app_logic.organize_output_var).grid(row=2, column=0, columnspan=3, padx=10, pady=(10,5), sticky="w")
        save_button = ctk.CTkButton(master_frame, text="Save Settings", command=self.app_logic._save_settings, font=ctk.CTkFont(size=16, weight="bold")); save_button.grid(row=row_index, column=0, pady=25, padx=10); row_index += 1

    def apply_spinbox_theme_tags(self, theme_name): pass