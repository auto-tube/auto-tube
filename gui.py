import os
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import time
from utils.logger import VideoProcessor  # Import VideoProcessor
import scenedetect
from scenedetect.video_manager import VideoManager
from scenedetect.detectors import ContentDetector
from scenedetect.scene_manager import SceneManager
from tkinterdnd2 import *  # pip install tkinterdnd2
import subprocess #added for function

# Placeholder for subtitle script processing function (you will implement this)
def process_subtitle_script(script_path, video_duration):
    """
    Processes a subtitle script, optimizing segment lengths for a given video duration.
    This is a placeholder function.  You'll need to implement the actual logic.
    """
    return [{"start": 0, "end": 5, "text": "Placeholder Subtitle 1"},
            {"start": 5, "end": 10, "text": "Placeholder Subtitle 2"}]

class VideoClipperApp:
    def __init__(self, root):
        """Initialize the Video Clipper Application."""
        #initialize tkinterdnd2, use Tk() instead of initialize()
        self.root = root
        self.theme = "dark"  # Initialize self.theme *before* calling _configure_root()
        self._configure_root()
        self._create_variables()
        self._create_ui()
        self.video_processor = None  # Initialize video_processor here
        self.video_queue = []  # Initialize video queue


    def _configure_root(self):
        """Configure the root window settings."""
        ctk.set_appearance_mode(self.theme)
        ctk.set_default_color_theme("blue")
        self.root.title("Clip Master")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)

    def _create_variables(self):
        """Create and initialize all tkinter variables."""
        self.input_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.subtitle_script_path_var = tk.StringVar() # Remove as parameter, create as file selector

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
        self.sidebar = ctk.CTkFrame(self.main_frame, width=350)  # Increased width for more options
        self.sidebar.pack(side="left", fill="y", padx=10, pady=10)

        # Right content area
        self.content_area = ctk.CTkFrame(self.main_frame)
        self.content_area.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        self._create_sidebar()
        self._create_content_area()

    def _create_sidebar(self):
        """Create the sidebar with input and configuration options."""
        # Title
        ctk.CTkLabel(self.sidebar, text="Clip Master", font=("Arial", 24, "bold"), text_color="white").pack(pady=20)

        # Theme Selection
        theme_frame = ctk.CTkFrame(self.sidebar)
        theme_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(theme_frame, text="Theme:").pack(side="left", padx=5)
        theme_optionmenu = ctk.CTkOptionMenu(theme_frame, values=["dark", "light", "system"], command=self._change_theme)
        theme_optionmenu.pack(side="left", padx=5)

        # Input Selection and Drag-and-Drop
        ctk.CTkLabel(self.sidebar, text="Input", font=("Arial", 16)).pack(pady=(10, 5))
        input_frame = ctk.CTkFrame(self.sidebar)
        input_frame.pack(fill="x", padx=10)

        input_entry = ctk.CTkEntry(input_frame, textvariable=self.input_path_var, width=200)
        input_entry.pack(side="left", expand=True, padx=(0, 10))

        input_button = ctk.CTkButton(input_frame, text="Browse", command=self._select_input, width=80)
        input_button.pack(side="right")

        # Enable Drag and Drop on the input entry
        input_entry.drop_target_register(DND_FILES)
        input_entry.dnd_bind('<<Drop>>', self._drop_input)

        #Queue Display
        self.queue_tree = ttk.Treeview(self.sidebar, columns=('Filepath',), show='headings')
        self.queue_tree.heading('Filepath', text='Video Queue')
        self.queue_tree.pack(fill='x', padx = 10, pady = 5)

        # Batch Processing
        ctk.CTkCheckBox(self.sidebar, text="Batch Processing", variable=self.batch_mode_var).pack(pady=10)

        # Clip Length Controls
        clip_length_frame = ctk.CTkFrame(self.sidebar)
        clip_length_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(clip_length_frame, text="Min Clip Length (s):").pack(side="left", padx=5)
        self.min_length_spinbox = tk.Spinbox(clip_length_frame, from_=15, to=180, textvariable=self.min_clip_length_var, width = 5,
                                             bg="#333333",  # Dark gray background
                                             fg="#FFFFFF",  # White text
                                             highlightthickness=0,
                                             relief="flat")
        self.min_length_spinbox.pack(side="left", padx = 5)

        ctk.CTkLabel(clip_length_frame, text="Max Clip Length (s):").pack(side="left", padx=5)
        self.max_length_spinbox = tk.Spinbox(clip_length_frame, from_=15, to=180, textvariable=self.max_clip_length_var, width=5,
                                            bg="#333333",  # Dark gray background
                                            fg="#FFFFFF",  # White text
                                            highlightthickness=0,
                                            relief="flat")
        self.max_length_spinbox.pack(side="left", padx=5)

        # Scene Detection Options
        scene_frame = ctk.CTkFrame(self.sidebar)
        scene_frame.pack(fill="x", padx=10, pady=10)

        ctk.CTkCheckBox(scene_frame, text="Scene Detection", variable=self.scene_detect_var).pack(anchor="w", pady=5)
        ctk.CTkLabel(scene_frame, text="Scene Threshold:").pack(side="left", padx=5)
        scene_threshold_entry = ctk.CTkEntry(scene_frame, textvariable=self.scene_threshold_var, width=50)
        scene_threshold_entry.pack(side="left", padx=5)

        # Clip Count Slider
        ctk.CTkLabel(self.sidebar, text="Number of Clips", font=("Arial", 14)).pack(pady=(10, 5))
        clip_count_slider = ctk.CTkSlider(
            self.sidebar,
            from_=1,
            to=13,
            number_of_steps=12,
            variable=self.clip_count_var,
            width=250
        )
        clip_count_slider.pack(pady=5)
        self.clip_count_label = ctk.CTkLabel(self.sidebar, text="5 Clips")
        self.clip_count_label.pack()
        clip_count_slider.bind("<ButtonRelease-1>", self._update_clip_count_label)

        # Option Checkboxes
        option_frame = ctk.CTkFrame(self.sidebar)
        option_frame.pack(fill="x", padx=10, pady=10)

        options = [
            ("Remove Audio", self.remove_audio_var),
            ("Extract Audio", self.extract_audio_var),
            ("Vertical Crop", self.vertical_crop_var),
            ("Mirror Video", self.mirror_var),
            ("Enhance Video", self.enhance_var)
        ]

        for text, var in options:
            ctk.CTkCheckBox(option_frame, text=text, variable=var).pack(anchor="w", pady=5)

    def _create_content_area(self):
        """Create the main content area with processing controls, progress tracking, queue display, and subtitle post-processing."""
        # Output Selection
        ctk.CTkLabel(self.content_area, text="Output Location", font=("Arial", 16)).pack(pady=(10, 5))
        output_frame = ctk.CTkFrame(self.content_area)
        output_frame.pack(fill="x", padx=20)

        output_entry = ctk.CTkEntry(output_frame, textvariable=self.output_path_var, width=500)
        output_entry.pack(side="left", expand=True, padx=(0, 10))

        output_button = ctk.CTkButton(output_frame, text="Browse", command=self._select_output, width=100)
        output_button.pack(side="right")

        # Queue Listbox
        ctk.CTkLabel(self.content_area, text="Processing Queue", font=("Arial", 16)).pack(pady=(10, 5))
        self.queue_listbox = tk.Listbox(self.content_area, width=80, height=10)
        self.queue_listbox.pack(fill="x", padx=20, pady=10)

        # Populate queue listbox (sample data)
        self._populate_queue_listbox()

        # Progress Tracking
        progress_frame = ctk.CTkFrame(self.content_area)
        progress_frame.pack(fill="x", padx=20, pady=20)

        self.progress_bar = ctk.CTkProgressBar(progress_frame, variable=self.progress_var, width=550)
        self.progress_bar.pack(pady=10)

        self.video_info_label = ctk.CTkLabel(progress_frame, text="", font=("Arial", 12))
        self.video_info_label.pack()

        ctk.CTkLabel(progress_frame, textvariable=self.remaining_time_var, font=("Arial", 12)).pack()

        # Start Processing Button
        start_button = ctk.CTkButton(
            self.content_area,
            text="Start Clipping",
            command=self._start_processing,
            fg_color="green",
            hover_color="darkgreen",
            font=("Arial", 16, "bold")
        )
        start_button.pack(pady=20)

        # ----------------اريات Subtitle Post-Processing Section -----------------------
        ctk.CTkLabel(self.content_area, text="Subtitle Post-Processing", font=("Arial", 18, "bold")).pack(pady=(20, 5))

        # Select File to Subtitle
        file_select_frame = ctk.CTkFrame(self.content_area)
        file_select_frame.pack(fill="x", padx=20, pady=5)

        file_select_entry = ctk.CTkEntry(file_select_frame, textvariable=self.subtitle_video_path_var, width=400)
        file_select_entry.pack(side="left", expand=True, padx=(0, 10))

        file_select_button = ctk.CTkButton(file_select_frame, text="Select Video", command=self._select_video_to_subtitle, width=120)
        file_select_button.pack(side="right")


        # Select Output File for Subtitled Video
        subtitle_output_frame = ctk.CTkFrame(self.content_area)
        subtitle_output_frame.pack(fill="x", padx=20, pady=5)

        subtitle_output_entry = ctk.CTkEntry(subtitle_output_frame, textvariable=self.subtitle_output_path_var, width=400)
        subtitle_output_entry.pack(side="left", expand=True, padx=(0, 10))

        subtitle_output_button = ctk.CTkButton(subtitle_output_frame, text="Select Output Location", command=self._select_subtitle_output, width=120)
        subtitle_output_button.pack(side="right")


        # Subtitle Text Input
        ctk.CTkLabel(self.content_area, text="Subtitle Text:", font=("Arial", 16)).pack(pady=(5, 2))
        self.subtitle_textbox = ctk.CTkTextbox(self.content_area, width=600, height=150)
        self.subtitle_textbox.pack(fill="x", padx=20, pady=5)

        # Apply Subtitles Button
        apply_button = ctk.CTkButton(
            self.content_area,
            text="Apply Subtitles",
            command=self._apply_subtitles,
            fg_color="blue",
            hover_color="darkblue",
            font=("Arial", 14, "bold")
        )
        apply_button.pack(pady=10)

    def _select_video_to_subtitle(self):
        """Select a single video file to add subtitles to."""
        path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4;*.mov;*.avi")])
        if path:
            self.subtitle_video_path_var.set(path)

    def _select_subtitle_output(self):
        """Select a location to save the newly subtitled video."""
        path = filedialog.askdirectory()
        if path:
            self.subtitle_output_path_var.set(path)

    def _apply_subtitles(self):
        """Apply the subtitles to the selected video."""
        video_path = self.subtitle_video_path_var.get()
        subtitle_output = self.subtitle_output_path_var.get()
        subtitle_text = self.subtitle_textbox.get("0.0", "end")  # Get all text from the textbox

        if not video_path or not subtitle_text or not subtitle_output:
            messagebox.showerror("Error", "Please select a video, enter subtitle text, and choose an output location.")
            return

        threading.Thread(target=self._process_subtitles, kwargs={'video_path': video_path, 'subtitle_text': subtitle_text, 'subtitle_output': subtitle_output}, daemon=True).start()

    def _process_subtitles(self, video_path, subtitle_text, subtitle_output):
        """
        Processes the subtitles and adds them to the video.
        This method runs in a separate thread.
        """
        try:
            #Create the .srt file in temporary file
            temp_srt_file = os.path.join(subtitle_output, "temp_subtitles.srt")
            with open(temp_srt_file, "w", encoding="utf-8") as f:
              for i, line in enumerate(subtitle_text.splitlines()):
                f.write(f"{i+1}\n")
                f.write(f"00:00:00,000 --> 00:00:05,000\n") #placeholder timecode
                f.write(f"{line}\n\n")

            # Generate the output file name in the output directory
            output_filename = os.path.basename(video_path).split('.')[0] + "_subtitled.mp4"
            output_path = os.path.join(subtitle_output, output_filename)

            # Construct the FFmpeg command
            cmd = [
                "ffmpeg",
                "-i", self._quote_path(video_path),
                "-vf", f"subtitles={self._quote_path(temp_srt_file)}", #Add subtitle filter
                self._quote_path(output_path)
            ]

            #Execute the command.
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                error_message = stderr.decode("utf-8")
                messagebox.showerror("Error", f"FFmpeg error: {error_message}")
                return

            # Delete temporary file after using
            os.remove(temp_srt_file)
            messagebox.showinfo("Success", "Subtitles applied successfully!")

        except Exception as e:
            messagebox.showerror("Error", f"Subtitle processing failed: {e}")

    def _quote_path(self, path: str) -> str:
        """Safely quote file paths to handle special characters."""
        return f'"{path}"'

    def _populate_queue_listbox(self):
        """Populate the queue listbox with sample data."""
        sample_queue_data = ["Video 1 - Processing", "Video 2 - Queued", "Video 3 - Complete"]
        for item in sample_queue_data:
            self.queue_listbox.insert(tk.END, item)

    def _update_clip_count_label(self, event=None):
        """Update clip count label."""
        self.clip_count_label.configure(text=f"{self.clip_count_var.get()} Clips")

    def _change_theme(self, theme):
        """Change the theme of the application."""
        self.theme = theme
        ctk.set_appearance_mode(self.theme)

    def _select_input(self):
        """Choose a single video file or an entire folder for batch processing and add to queue."""
        if self.batch_mode_var.get():
            path = filedialog.askdirectory()
            if path:
                for file in os.listdir(path):
                    if file.endswith((".mp4", ".mov", ".avi")):
                        self.video_queue.append(os.path.join(path, file))
        else:
            path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4;*.mov;*.avi")])
            if path:
                self.video_queue.append(path)

        self._update_queue_display()
        if path:  # Only set the path if a file/directory was selected
            self.input_path_var.set(path)

    def _drop_input(self, event):
        """Handle drag and drop events to add videos to the queue."""
        files = event.data.split()
        for file in files:
            if file.endswith((".mp4", ".mov", ".avi")):
                self.video_queue.append(file)
        self._update_queue_display()
        if files:  # Only set the path if a file/directory was selected
            self.input_path_var.set(files[0])

    def _update_queue_display(self):
        """Update queue listbox and treelist."""
        self.queue_listbox.delete(0, tk.END)  # Clear existing listbox items
        self.queue_tree.delete(*self.queue_tree.get_children())  # Clear the treeview

        for file_path in self.video_queue:
            self.queue_listbox.insert(tk.END, os.path.basename(file_path))
            self.queue_tree.insert('', tk.END, values=(os.path.basename(file_path),))

    def _select_output(self):
        """Choose output folder."""
        path = filedialog.askdirectory()
        if path:  # Only set the path if a directory was selected
            self.output_path_var.set(path)

def main():
    """Main function to run the application."""
    app = TkinterDnD.Tk() #Initialize the Tk object for Drag and Drop capabilities
    app.geometry("600x650") #set the window size
    VideoClipperApp(app) #Run the app object
    app.mainloop()#Start the app

if __name__ == "__main__":
    """When gui.py is the main file, do:"""
    main()