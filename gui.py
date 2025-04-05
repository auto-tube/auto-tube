# gui.py
import os
import sys
import json
import platform
from typing import List, Optional
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import time
from tkinterdnd2 import * # Requires pip install tkinterdnd2-universal or similar
import traceback
import random
import logging # Import logging for fallback

# --- Import components ---
MODULE_IMPORTS_OK = False
PROCESS_MANAGER_LOADED = False
UI_TABS_LOADED = False
VIDEO_PROCESSOR_LOADED = False
AI_UTILS_LOADED = False
TTS_UTILS_LOADED = False
HELPERS_LOADED = False
FILE_MANAGER_LOADED = False
LOGGER_LOADED = False

# Use a top-level try-except for logger setup first
try:
    from utils.logger_config import setup_logging
    logger = setup_logging()
    LOGGER_LOADED = True
except ImportError as log_e:
    print(f"Warning: Failed to import structured logger: {log_e}. Using basic logging.")
    # Configure basic logging immediately
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger('autotube_fallback')
    LOGGER_LOADED = True # Still consider logger loaded for basic functionality
except Exception as log_setup_e:
    # Catch any other error during logger setup
    logging.basicConfig(level=logging.ERROR) # Minimal logger
    logger = logging.getLogger('autotube_init_error')
    logger.error(f"CRITICAL ERROR setting up logger: {log_setup_e}", exc_info=True)
    # We need to show an error message even before the GUI exists
    try:
        import tkinter as tk
        from tkinter import messagebox
        error_root = tk.Tk()
        error_root.withdraw()
        messagebox.showerror("Fatal Initialization Error", f"Could not set up logging.\nError: {log_setup_e}\n\nApplication cannot start.")
        error_root.destroy()
    except Exception:
        print(f"FATAL ERROR SETTING UP LOGGER: {log_setup_e}")
        traceback.print_exc()
    sys.exit(1) # Exit if logging fails catastrophically


try:
    # Core components
    from ui.ui_tabs import ClippingTab, AIShortTab, MetadataTab, SettingsTab # Include SettingsTab
    UI_TABS_LOADED = True
    from core.processing_manager import (run_clipping_queue, run_ai_short_generation,
                                         run_gemini_script_generation, run_gemini_metadata_generation)
    PROCESS_MANAGER_LOADED = True
    from utils.video_processor import VideoProcessor, FFmpegNotFoundError # Import VP class and error
    VIDEO_PROCESSOR_LOADED = True
    from utils.ai_utils import GeminiError, configure_google_api # Import config function
    AI_UTILS_LOADED = True
    from utils.tts_utils import configure_polly_client # Import config function
    TTS_UTILS_LOADED = True
    from utils.helpers import find_ffmpeg_executables # Import finder only
    HELPERS_LOADED = True
    from utils.file_manager import FileOrganizer
    FILE_MANAGER_LOADED = True

    MODULE_IMPORTS_OK = (PROCESS_MANAGER_LOADED and UI_TABS_LOADED and
                         VIDEO_PROCESSOR_LOADED and AI_UTILS_LOADED and
                         TTS_UTILS_LOADED and HELPERS_LOADED and FILE_MANAGER_LOADED and LOGGER_LOADED)
    if MODULE_IMPORTS_OK:
        logger.info("GUI: Core modules imported successfully.")
    else:
        # Log which specific modules failed if LOGGER_LOADED is True
        if LOGGER_LOADED:
             failed_modules = [
                 name for name, loaded in [
                     ("Process Manager", PROCESS_MANAGER_LOADED),
                     ("UI Tabs", UI_TABS_LOADED),
                     ("Video Processor", VIDEO_PROCESSOR_LOADED),
                     ("AI Utils", AI_UTILS_LOADED),
                     ("TTS Utils", TTS_UTILS_LOADED),
                     ("Helpers", HELPERS_LOADED),
                     ("File Manager", FILE_MANAGER_LOADED)
                 ] if not loaded
             ]
             logger.warning(f"GUI: Not all core modules were imported successfully. Failed: {', '.join(failed_modules)}")
        else:
             print("Warning: Not all core modules were imported successfully (Logger not available for details).")


except ImportError as e:
    err_msg = f"ERROR [GUI Import]: Failed to import application modules: {e}"
    # Use logger if available, otherwise print
    if LOGGER_LOADED: logger.critical(err_msg, exc_info=True)
    else: print(err_msg); traceback.print_exc()

    print("Defining dummy placeholders because of import errors...")
    # --- CORRECTED Dummies ---
    if not UI_TABS_LOADED:
        class ClippingTab(ctk.CTkFrame): pass
        class AIShortTab(ctk.CTkFrame): pass
        class MetadataTab(ctk.CTkFrame): pass
        class SettingsTab(ctk.CTkFrame): pass
    if not PROCESS_MANAGER_LOADED:
        def run_clipping_queue(*args, **kwargs): logger.error("Dummy: Clipping processing module not loaded")
        def run_ai_short_generation(*args, **kwargs): logger.error("Dummy: AI Short processing module not loaded")
        def run_gemini_script_generation(*args, **kwargs): logger.error("Dummy: Script Gen processing module not loaded")
        def run_gemini_metadata_generation(*args, **kwargs): logger.error("Dummy: Metadata Gen processing module not loaded")
    if not VIDEO_PROCESSOR_LOADED:
        class FFmpegNotFoundError(Exception): pass
        class VideoProcessor: pass
    if not AI_UTILS_LOADED:
        def configure_google_api(*args, **kwargs): logger.error("Dummy configure_google_api called")
        class GeminiError(Exception): pass
        GEMINI_CONFIGURED = False # Need this for checks
    if not TTS_UTILS_LOADED:
        def configure_polly_client(*args, **kwargs): logger.error("Dummy configure_polly_client called")
        POLLY_CONFIGURED = False # Need this for checks
    if not HELPERS_LOADED:
        def find_ffmpeg_executables(*args, **kwargs): logger.error("Dummy find_ffmpeg called"); return None, None
    if not FILE_MANAGER_LOADED:
        class FileOrganizer:
             def __init__(self, *args, **kwargs): pass # Corrected dummy init
             def organize_output(self, *args, **kwargs): logger.error("Dummy FileOrganizer.organize_output called") # Corrected dummy method
    # --- End Dummies ---
# --- End Imports ---

# --- Constants ---
APP_NAME = "Autotube"
CONFIG_FILENAME = "autotube_config.json"

class VideoClipperApp:
    """ Main application class """
    def __init__(self, root: TkinterDnD.Tk):
        self.root = root
        self.theme = "dark" # Default theme
        self.config_path = self._get_config_path()
        self.ffmpeg_exec = None # Store discovered paths
        self.ffprobe_exec = None

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
                logger.info(f"--- Initializing {APP_NAME} GUI ---")
                self._create_variables()
                self._load_settings()      # Load settings first (defines self.theme, API keys etc.)
                self._configure_apis()     # Configure APIs using loaded/env settings
                self._find_and_verify_ffmpeg() # Find FFmpeg (no config path needed now)
                self._configure_root()     # Apply theme, set title etc.
                self._create_ui()          # Create widgets
                self._apply_treeview_theme_tags() # Apply theme to treeview
                self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
                logger.info(f"{APP_NAME} GUI initialized successfully.")
                # Perform initial config check AFTER UI is created so status bar exists
                self.root.after(100, self._check_initial_config) # Delay check slightly
                self.root.after(150, self._update_button_state) # Initial button state update

            except Exception as e:
                logger.critical("Fatal error during GUI initialization", exc_info=True)
                self._show_init_error(e) # Show fatal init error window
        else:
            logger.critical("GUI cannot initialize fully due to module import errors.")
            self._show_import_error() # Show fatal import error window

    # --- Initialization Error Handling ---
    def _show_import_error(self):
        self.root.title(f"{APP_NAME} - Load Error"); self.root.geometry("600x200")
        ctk.CTkLabel(self.root, text="FATAL ERROR: Failed to load application modules.\nCheck console/logs, project structure, __init__.py files,\nand virtual environment dependencies.",
                     text_color="red", font=ctk.CTkFont(size=14), wraplength=550).pack(pady=40, padx=20)
        logger.critical("GUI ERROR: Cannot start due to import errors.")

    def _show_init_error(self, error):
         self.root.title(f"{APP_NAME} - Init Error"); self.root.geometry("600x200")
         ctk.CTkLabel(self.root, text=f"FATAL ERROR during GUI initialization.\n\n{type(error).__name__}: {error}\n\nCheck console/logs for details.",
                      text_color="red", font=ctk.CTkFont(size=14), wraplength=550).pack(pady=40, padx=20)
         logger.critical(f"GUI Init Error: {error}", exc_info=True)

    # --- Configuration & Setup ---
    def _configure_root(self):
        """Configures the root window appearance based on loaded theme."""
        logger.debug(f"Configuring root window with theme: {self.theme}")
        ctk.set_appearance_mode(self.theme) # Set appearance mode based on loaded/default theme
        ctk.set_default_color_theme("blue")
        self.root.title(f"{APP_NAME}: Clip Master & AI Content Tools");
        self.root.geometry("1200x850");
        self.root.minsize(1000, 800)

    def _get_config_path(self) -> str:
        """Determines the path for the configuration file."""
        app_support_dir = ""
        system = platform.system()

        if system == "Windows": app_support_dir = os.getenv('APPDATA')
        elif system == "Darwin": app_support_dir = os.path.expanduser('~/Library/Application Support')
        else: # Linux/Other
            app_support_dir = os.path.expanduser(os.getenv('XDG_CONFIG_HOME', '~/.config'))
            # Fallback to data dir if config dir doesn't exist
            if not os.path.isdir(app_support_dir):
                app_support_dir = os.path.expanduser(os.getenv('XDG_DATA_HOME', '~/.local/share'))

        # Final fallback to home directory if others fail
        if not app_support_dir or not os.path.isdir(app_support_dir):
             app_support_dir = os.path.expanduser('~')
             logger.warning(f"Could not determine standard config/data directory ({system}), using home directory: {app_support_dir}")

        app_config_dir = os.path.join(app_support_dir, APP_NAME)
        config_file = os.path.join(app_config_dir, CONFIG_FILENAME)
        try:
            os.makedirs(app_config_dir, exist_ok=True)
            logger.info(f"GUI Config: Using configuration file path: {config_file}")
            return config_file
        except OSError as e:
            logger.error(f"GUI Config Error: Could not create config directory {app_config_dir}: {e}")
            fallback_path = os.path.abspath(CONFIG_FILENAME) # Fallback to current dir
            logger.warning(f"GUI Config Warning: Falling back to config file in current directory: {fallback_path}")
            return fallback_path

    def _create_variables(self):
        """Creates all Tkinter variables for the application with defaults."""
        logger.info("GUI: Creating UI variables with default values...");
        # --- Clipping Tab Vars ---
        self.input_path_var = tk.StringVar(); self.output_path_var = tk.StringVar()
        self.min_clip_length_var = tk.IntVar(value=15); self.max_clip_length_var = tk.IntVar(value=45)
        self.scene_threshold_var = tk.DoubleVar(value=30.0); self.clip_count_var = tk.IntVar(value=5)
        self.scene_detect_var = tk.BooleanVar(value=False); self.remove_audio_var = tk.BooleanVar(value=False)
        self.extract_audio_var = tk.BooleanVar(value=True); self.vertical_crop_var = tk.BooleanVar(value=True)
        self.mirror_var = tk.BooleanVar(value=False); self.enhance_var = tk.BooleanVar(value=True)
        self.batch_mode_var = tk.BooleanVar(value=False)

        # --- AI Short Tab Vars ---
        self.ai_video_path_var = tk.StringVar(); self.ai_output_path_var = tk.StringVar()
        self.ai_script_prompt_var = tk.StringVar(); self.ai_polly_voice_var = tk.StringVar(value="Joanna") # Example default
        self.ai_font_size_var = tk.IntVar(value=48)

        # --- Metadata Tab Vars ---
        self.metadata_hashtag_count_var = tk.IntVar(value=10); self.metadata_tag_count_var = tk.IntVar(value=15); self.metadata_title_count_var = tk.IntVar(value=5)

        # --- Settings Tab Vars (REMOVED FFmpeg Paths) ---
        self.google_api_key_var = tk.StringVar() # Loaded from config/env
        self.aws_access_key_var = tk.StringVar() # Loaded from config/env
        self.aws_secret_key_var = tk.StringVar() # Loaded from config/env
        self.aws_region_var = tk.StringVar(value="us-east-1") # Default region, loaded from config/env
        self.organize_output_var = tk.BooleanVar(value=True) # Default to organize

        # --- Status/Progress Vars ---
        self.progress_var = tk.DoubleVar(value=0.0); self.status_var = tk.StringVar(value="Status: Initializing..."); self.remaining_time_var = tk.StringVar(value="Est. Time Remaining: N/A")
        logger.info("GUI: UI variables created.")

    def _load_settings(self):
        """Loads settings from the JSON configuration file."""
        logger.info(f"GUI: Loading settings from {self.config_path}...")
        settings_loaded = False
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                # Load into variables, using existing variable defaults if key is missing
                # API keys are loaded but might be overridden by Env Vars later in _configure_apis
                self.google_api_key_var.set(settings.get("google_api_key", self.google_api_key_var.get()))
                self.aws_access_key_var.set(settings.get("aws_access_key_id", self.aws_access_key_var.get()))
                self.aws_secret_key_var.set(settings.get("aws_secret_access_key", self.aws_secret_key_var.get()))
                self.aws_region_var.set(settings.get("aws_region_name", self.aws_region_var.get()))

                # Other settings
                self.output_path_var.set(settings.get("default_output_path", self.output_path_var.get()))
                self.organize_output_var.set(settings.get("organize_output", self.organize_output_var.get()))
                self.theme = settings.get("theme", self.theme) # Load theme preference

                logger.info("GUI: Settings loaded successfully from config file.")
                settings_loaded = True
            else:
                logger.info("GUI: Config file not found. Using default variable values.")
                # Keep the default theme if no config file
        except json.JSONDecodeError:
            logger.error(f"GUI Error: Invalid JSON in config file: {self.config_path}. Using default values.", exc_info=True)
            messagebox.showerror("Config Error", f"Could not load settings.\nInvalid format in {self.config_path}.\n\nPlease fix or delete the file. Using default settings.")
            # Keep default theme on error
        except Exception as e:
            logger.error(f"GUI Error: Failed to load settings file {self.config_path}", exc_info=True)
            messagebox.showerror("Config Error", f"Failed to load settings from {self.config_path}:\n{e}\n\nUsing default settings.")
            # Keep default theme on error

        # Set default output path if still empty after loading attempts
        if not self.output_path_var.get():
            default_output = os.path.join(os.path.expanduser("~"), "Autotube_Output")
            self.output_path_var.set(default_output)
            logger.info(f"GUI: Default output path set to user's home directory: {default_output}")


    def _save_settings(self):
        """Saves current settings to the JSON configuration file."""
        logger.info(f"GUI: Saving settings to {self.config_path}...")
        # Only save settings that are meant to be persisted via the GUI
        settings = {
            "google_api_key": self.google_api_key_var.get(), # Save the value from the GUI input
            "aws_access_key_id": self.aws_access_key_var.get(), # Save the value from the GUI input
            "aws_secret_access_key": self.aws_secret_key_var.get(), # Save the value from the GUI input
            "aws_region_name": self.aws_region_var.get(), # Save the value from the GUI input
            # REMOVED: ffmpeg_path, ffprobe_path saving - rely on auto-detection
            "default_output_path": self.output_path_var.get(),
            "organize_output": self.organize_output_var.get(),
            "theme": self.theme # Save the currently active theme
        }
        try:
            # Ensure directory exists before writing
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4)
            logger.info("GUI: Settings saved successfully.")
            messagebox.showinfo("Settings Saved", "Settings have been saved successfully.")

            # Re-configure APIs and re-check FFmpeg after saving, then update UI state
            logger.info("GUI: Re-configuring APIs and checking FFmpeg after saving settings...")
            self._configure_apis() # Re-check env vars vs newly saved vars
            self._find_and_verify_ffmpeg() # Re-run detection (though paths aren't saved)
            self._check_initial_config() # Update status bar warnings if any
            self._update_button_state() # Update button enable/disable state

        except Exception as e:
            logger.error(f"GUI Error: Failed to save settings to {self.config_path}", exc_info=True)
            messagebox.showerror("Save Error", f"Could not save settings to {self.config_path}:\n{e}")

    def _configure_apis(self):
        """Configures external APIs using Environment Variables > Saved Settings."""
        logger.info("GUI: Configuring external APIs (Priority: Environment Variables > Saved Settings)...")

        # --- Configure Google Gemini ---
        if AI_UTILS_LOADED:
            try:
                g_key_env = os.environ.get("GOOGLE_API_KEY")
                g_key_gui = self.google_api_key_var.get() # Get value potentially loaded from config
                final_g_key = None
                source = "Not configured"

                if g_key_env:
                    final_g_key = g_key_env
                    source = "Environment Variable"
                elif g_key_gui:
                    final_g_key = g_key_gui
                    source = "Saved Settings"

                if final_g_key:
                    logger.info(f"Using Google API Key from: {source}")
                else:
                    logger.warning("Google API Key not found in Environment Variables or Settings.")

                configure_google_api(final_g_key) # Pass final key (or None) to the utility function

            except Exception as e:
                 logger.error("GUI Error: Failed during Google API configuration", exc_info=True)
        else:
            logger.warning("GUI Warn: AI Utils module not loaded, cannot configure Google API.")

        # --- Configure AWS Polly ---
        if TTS_UTILS_LOADED:
            try:
                access_key_env = os.environ.get("AWS_ACCESS_KEY_ID")
                secret_key_env = os.environ.get("AWS_SECRET_ACCESS_KEY")
                region_env = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")

                # Get values potentially loaded from config
                access_key_gui = self.aws_access_key_var.get()
                secret_key_gui = self.aws_secret_key_var.get()
                region_gui = self.aws_region_var.get()

                final_access_key = None
                final_secret_key = None
                final_region = None
                source = "Default Chain (e.g., ~/.aws/credentials, IAM role)"

                # Prioritize Env Vars
                if access_key_env and secret_key_env:
                    final_access_key = access_key_env
                    final_secret_key = secret_key_env
                    final_region = region_env if region_env else region_gui # Allow Env Region override GUI Region
                    source = "Environment Variables"
                # Fallback to GUI/Config settings
                elif access_key_gui and secret_key_gui:
                    final_access_key = access_key_gui
                    final_secret_key = secret_key_gui
                    final_region = region_gui # Use GUI region if keys are from GUI
                    source = "Saved Settings"
                # If only region is set (in Env or GUI), use it, but keys rely on default chain
                elif not final_access_key and not final_secret_key:
                     final_region = region_env if region_env else region_gui

                logger.info(f"Configuring AWS Polly using credentials/region from: {source}")
                if final_region:
                    logger.info(f"AWS Region specified: {final_region}")
                else:
                     logger.info("AWS Region not specified, relying on Boto3 default.")


                # Call configure_polly_client with determined values (or None for defaults)
                # It's designed to handle None values and use the default Boto3 chain
                configure_polly_client(
                    aws_access_key_id=final_access_key, # Will be None if using default chain
                    aws_secret_access_key=final_secret_key, # Will be None if using default chain
                    aws_region_name=final_region # Pass determined region or None
                )
            except Exception as e:
                 logger.error("GUI Error: Failed during AWS Polly configuration", exc_info=True)
        else:
            logger.warning("GUI Warn: TTS Utils module not loaded, cannot configure AWS Polly.")

    def _find_and_verify_ffmpeg(self):
        """Finds FFmpeg/FFprobe using auto-detection (bundled, env, PATH) and verifies them."""
        logger.info("GUI: Locating and verifying FFmpeg/FFprobe...")
        self.ffmpeg_exec = None # Reset found paths
        self.ffprobe_exec = None

        if not HELPERS_LOADED:
            logger.warning("GUI Warn: Helpers module not loaded, cannot automatically locate FFmpeg.")
            return # Cannot proceed without the finder function

        try:
            # Call finder without config path arguments - relies on auto-detection
            self.ffmpeg_exec, self.ffprobe_exec = find_ffmpeg_executables()

            if not self.ffmpeg_exec or not self.ffprobe_exec:
                logger.warning("GUI Warn: FFmpeg or FFprobe could not be located automatically (checked bundled, environment variables, system PATH).")
                # Specific error message will be shown by _check_initial_config
            else:
                 logger.info(f"GUI: Auto-detected FFmpeg='{self.ffmpeg_exec}', FFprobe='{self.ffprobe_exec}'")
                 # --- Verification Step ---
                 if VIDEO_PROCESSOR_LOADED:
                      logger.debug("GUI: Verifying detected FFmpeg/FFprobe paths using VideoProcessor...")
                      try:
                           # Attempt to initialize VideoProcessor with detected paths.
                           # This implicitly calls its internal _check_ffmpeg method.
                           # Use a dummy output folder for the check.
                           _ = VideoProcessor(output_folder=".", # Dummy, doesn't need to exist for check
                                              ffmpeg_path=self.ffmpeg_exec,
                                              ffprobe_path=self.ffprobe_exec)
                           logger.info("GUI: FFmpeg/FFprobe paths verified successfully.")
                      except FFmpegNotFoundError as verify_e:
                           logger.error(f"GUI Error: Verification FAILED for detected FFmpeg/FFprobe paths: {verify_e}")
                           self.ffmpeg_exec = None # Invalidate paths if verification fails
                           self.ffprobe_exec = None
                      except ValueError as verify_e: # Catch potential folder errors from VP init too
                            logger.error(f"GUI Error: Verification failed (ValueError during VideoProcessor init, possibly unrelated to FFmpeg path itself): {verify_e}")
                            # Invalidate paths to be safe, as VP couldn't fully initialize.
                            self.ffmpeg_exec = None
                            self.ffprobe_exec = None
                      except Exception as verify_e:
                            logger.error("GUI Error: Unexpected error during FFmpeg path verification", exc_info=True)
                            self.ffmpeg_exec = None # Invalidate paths on unexpected error
                            self.ffprobe_exec = None
                 else:
                      logger.warning("GUI Warn: VideoProcessor module not loaded, cannot perform verification of detected FFmpeg paths.")

        except Exception as e:
             logger.error("GUI Error: Unexpected error occurred while finding/verifying FFmpeg", exc_info=True)
             self.ffmpeg_exec = None # Ensure paths are invalidated on any exception during the process
             self.ffprobe_exec = None


    def _check_initial_config(self):
        """Checks for missing essential configs (APIs, FFmpeg) and updates status bar."""
        logger.debug("Performing initial configuration check...")
        warnings = []

        # Check Gemini Config (uses flag set by ai_utils.configure_google_api)
        if AI_UTILS_LOADED:
             try:
                 # Dynamically import the flag AFTER configuration attempt
                 from utils.ai_utils import GEMINI_CONFIGURED
                 if not GEMINI_CONFIGURED:
                     warnings.append("Google API Key missing or invalid (Check Environment Variable 'GOOGLE_API_KEY' or Settings). AI features disabled.")
             except ImportError:
                 logger.error("Could not import GEMINI_CONFIGURED flag from ai_utils.")
             except NameError:
                  logger.error("GEMINI_CONFIGURED flag not found in ai_utils.")
        else:
             warnings.append("AI Utils module not loaded. AI features disabled.")

        # Check Polly Config (uses flag set by tts_utils.configure_polly_client)
        if TTS_UTILS_LOADED:
             try:
                 # Dynamically import the flag AFTER configuration attempt
                 from utils.tts_utils import POLLY_CONFIGURED
                 if not POLLY_CONFIGURED:
                     warnings.append("AWS Polly not configured (Check Env Vars [AWS_*], Settings, or default credential chain [e.g., ~/.aws/credentials]). TTS features disabled.")
             except ImportError:
                  logger.error("Could not import POLLY_CONFIGURED flag from tts_utils.")
             except NameError:
                   logger.error("POLLY_CONFIGURED flag not found in tts_utils.")
        else:
            warnings.append("TTS Utils module not loaded. TTS features disabled.")

        # Check FFmpeg/FFprobe (based on verified paths)
        if not self.ffmpeg_exec or not self.ffprobe_exec:
            warnings.append("FFmpeg/FFprobe not found or verified (Check bundled 'bin' folder, Environment Variables, or system PATH). Video processing disabled.")

        # Update Status Bar
        if warnings:
            warning_summary = f"{len(warnings)} configuration issue(s) detected."
            self.status_var.set(f"Status: {warning_summary} Check logs or Settings.")
            logger.warning("--- GUI CONFIGURATION ISSUES ---")
            for i, w in enumerate(warnings, 1):
                logger.warning(f"{i}. {w}")
            logger.warning("--- END CONFIGURATION ISSUES ---")
            # Optionally show a popup, but status bar + logs might be sufficient
            # messagebox.showwarning("Configuration Incomplete", "Found configuration issues:\n\n- " + "\n- ".join(warnings) + "\n\nPlease check Settings or logs for details.")
        else:
            current_status = self.status_var.get()
            # Only set to Idle if it was previously initializing or showing issues
            if "Initializing..." in current_status or "Issues Detected" in current_status or "Idle" in current_status:
                 self.status_var.set("Status: Idle. Configuration OK.")
            logger.info("GUI: Initial configuration check passed.")

    # --- UI Creation ---
    def _create_ui(self):
        """Creates the main UI layout, tabs, and status bar."""
        logger.info("GUI: Creating main UI layout...");
        self.main_frame = ctk.CTkFrame(self.root); self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Progress Bar Area
        progress_frame = ctk.CTkFrame(self.main_frame); progress_frame.pack(fill="x", padx=5, pady=(5, 10))
        ctk.CTkLabel(progress_frame, text="Progress:", anchor="w").pack(side="left", padx=5)
        self.progress_bar = ctk.CTkProgressBar(progress_frame, variable=self.progress_var); self.progress_bar.pack(side="left", fill="x", expand=True, pady=5, padx=5)
        ctk.CTkLabel(progress_frame, textvariable=self.remaining_time_var, width=180, anchor="e").pack(side="right", padx=5)

        # Tab View
        self.tab_view = ctk.CTkTabview(self.main_frame, anchor="nw"); self.tab_view.pack(fill="both", expand=True, padx=5, pady=0)
        self.tab_view.add("Video Clipper"); self.tab_view.add("AI Short Generator"); self.tab_view.add("Metadata Tools"); self.tab_view.add("Settings")
        logger.info("GUI: Tabs added.");

        # Instantiate and Pack Tab Content (check if classes loaded)
        if UI_TABS_LOADED:
            logger.info("GUI: Creating Clipping Tab content...");
            self.clipping_tab = ClippingTab(master=self.tab_view.tab("Video Clipper"), app_logic=self)
            self.clipping_tab.pack(fill="both", expand=True)

            logger.info("GUI: Creating AI Short Tab content...");
            self.ai_short_tab = AIShortTab(master=self.tab_view.tab("AI Short Generator"), app_logic=self)
            self.ai_short_tab.pack(fill="both", expand=True)

            logger.info("GUI: Creating Metadata Tab content...");
            self.metadata_tab = MetadataTab(master=self.tab_view.tab("Metadata Tools"), app_logic=self)
            self.metadata_tab.pack(fill="both", expand=True)

            logger.info("GUI: Creating Settings Tab content...");
            self.settings_tab = SettingsTab(master=self.tab_view.tab("Settings"), app_logic=self)
            self.settings_tab.pack(fill="both", expand=True)
            logger.info("GUI: All Tab content created.");
        else:
             logger.error("GUI Error: UI Tab classes not loaded. Cannot populate tabs.")
             # Optionally add labels indicating the error in each tab
             for tab_name in ["Video Clipper", "AI Short Generator", "Metadata Tools", "Settings"]:
                 try: ctk.CTkLabel(self.tab_view.tab(tab_name), text="Error: UI components failed to load.", text_color="red").pack(pady=20)
                 except Exception: pass # Ignore if tab itself is broken

        # Status Bar
        status_frame = ctk.CTkFrame(self.root, height=25); status_frame.pack(side="bottom", fill="x", padx=10, pady=(5, 10))
        self.status_label = ctk.CTkLabel(status_frame, textvariable=self.status_var, anchor="w"); self.status_label.pack(side="left", padx=10);
        logger.info("GUI: Status bar created."); logger.info("GUI: Main UI creation complete.")

    # --- Action Methods ---

    # REMOVED: _browse_ffmpeg, _browse_ffprobe methods as paths are auto-detected

    def _select_input(self):
        logger.debug("GUI Action: Browse input."); added_count=0; path=None; paths=None;
        try:
            if self.batch_mode_var.get():
                logger.debug("Browsing for input folder (batch mode)")
                path=filedialog.askdirectory(title="Select Folder Containing Videos")
            else:
                logger.debug("Browsing for input file(s)")
                paths=filedialog.askopenfilenames(title="Select Video File(s)", filetypes=[("Video Files","*.mp4 *.mov *.avi *.mkv *.wmv *.flv"),("All Files","*.*")])

            if path and os.path.isdir(path): # Batch mode folder selected
                files_in_folder=[f for f in os.listdir(path) if f.lower().endswith((".mp4",".mov",".avi",".mkv",".wmv",".flv"))];
                if not files_in_folder:
                     messagebox.showwarning("No Videos Found", f"No compatible video files found in the selected folder:\n{path}")
                     logger.warning(f"No video files found in selected folder: {path}")
                     return
                logger.info(f"Adding {len(files_in_folder)} files from folder: {path}")
                for file in files_in_folder:
                    fp=os.path.join(path,file);
                    if fp not in self.video_queue:
                         self.video_queue.append(fp); added_count+=1
                if added_count>0:
                    self.input_path_var.set(f"Folder: ...{os.path.basename(path)} ({added_count} new files added)")
            elif paths: # Single/Multiple files selected
                logger.info(f"Adding {len(paths)} selected files.")
                for p in paths:
                    if p not in self.video_queue:
                         self.video_queue.append(p); added_count+=1
                if added_count > 0:
                     # Update display text based on queue size
                     if len(self.video_queue) == 1: self.input_path_var.set(os.path.basename(self.video_queue[0]))
                     else: self.input_path_var.set(f"{len(self.video_queue)} files in queue")

            if added_count > 0:
                self._update_queue_display()
                logger.info(f"GUI: Added {added_count} new video(s) to the queue. Total queue size: {len(self.video_queue)}")
            elif not path and not paths:
                 logger.debug("GUI: No input path or files were selected.")

        except OSError as e:
            messagebox.showerror("Folder Read Error", f"Could not read the selected folder:\n{e}")
            logger.error(f"Error reading selected folder: {path}", exc_info=True)
        except Exception as e:
            messagebox.showerror("Input Selection Error", f"An unexpected error occurred while selecting input:\n{e}")
            logger.error("Unexpected error during input selection", exc_info=True)

    def _drop_input(self, event):
        logger.debug(f"GUI Action: File/Folder Drop detected. Data: {event.data}"); added_count=0; first_added_name=""; dropped_files=[]
        try:
            # Use splitlist to handle paths with spaces, potentially enclosed in {}
            items = self.root.tk.splitlist(event.data)
            logger.debug(f"Parsed dropped items: {items}")

            for item in items:
                # Clean up potential curly braces added by some systems
                item_path=item.strip('{}')
                logger.debug(f"Processing dropped item: {item_path}")

                if os.path.isdir(item_path):
                    logger.debug(f"Item is a directory: {item_path}")
                    found_in_dir=False
                    try:
                        for f in os.listdir(item_path):
                             if f.lower().endswith((".mp4",".mov",".avi",".mkv",".wmv",".flv")):
                                fp=os.path.join(item_path,f)
                                dropped_files.append(fp)
                                found_in_dir=True
                        if not found_in_dir:
                             logger.debug(f"No compatible video files found in dropped directory: {item_path}")
                        else:
                             logger.debug(f"Found video files within dropped directory: {item_path}")
                    except OSError as e:
                         logger.warning(f"Could not read dropped directory {item_path}: {e}")
                         messagebox.showwarning("Drop Error", f"Could not read the dropped folder:\n{item_path}\n\nError: {e}")
                    except Exception as e:
                         logger.error(f"Unexpected error processing dropped directory {item_path}", exc_info=True)

                elif os.path.isfile(item_path) and item_path.lower().endswith((".mp4",".mov",".avi",".mkv",".wmv",".flv")):
                    logger.debug(f"Item is a compatible video file: {item_path}")
                    dropped_files.append(item_path)
                else:
                    logger.debug(f"Ignoring dropped item (not a folder or compatible video file): {item_path}")

            # Add unique files to the queue
            for fp in dropped_files:
                if fp not in self.video_queue:
                    self.video_queue.append(fp)
                    added_count+=1
                    if not first_added_name: # Store name of the first *new* file added
                        first_added_name = os.path.basename(fp)
                else:
                     logger.debug(f"Skipping duplicate file: {fp}")

            if added_count > 0:
                self._update_queue_display()
                # Update display text based on queue size
                if len(self.video_queue) == 1: self.input_path_var.set(first_added_name) # Show the single file name
                else: self.input_path_var.set(f"{len(self.video_queue)} files in queue") # Show count for multiple
                logger.info(f"Drop Event: Added {added_count} new video(s). Total queue size: {len(self.video_queue)}")
            else:
                 logger.debug("Drop Event: No new compatible video files were added from the drop.")

            # Clear display if queue becomes empty (e.g., if duplicates were dropped)
            if not self.video_queue:
                self.input_path_var.set("")

        except Exception as e:
            messagebox.showerror("Drop Processing Error", f"Failed to process dropped files/folders:\n{e}")
            logger.error("Error processing drop event", exc_info=True)

    def _select_output(self):
        # Selects the DEFAULT output folder (saved in Settings)
        logger.info("GUI Action: Selecting default output folder via browse button.");
        current_path=self.output_path_var.get();
        # Try to start the dialog in the currently set directory if it's valid
        initial_dir = current_path if current_path and os.path.isdir(current_path) else os.path.expanduser("~")

        path = filedialog.askdirectory(title="Select Default Output Folder", initialdir=initial_dir)
        if path:
            self.output_path_var.set(path)
            logger.info(f"GUI: Default output folder set to: {path}")
            # Maybe save settings automatically here, or rely on user pressing Save in Settings tab?
            # For now, just update the variable. User needs to Save Settings explicitly.
        else:
             logger.debug("GUI: Default output folder selection cancelled.")


    def _clear_queue(self):
        logger.info("GUI Action: Clear video queue button clicked.");
        if self.is_processing:
            messagebox.showwarning("Busy", "Cannot clear the queue while video clipping is in progress.")
            logger.warning("Attempted to clear queue while processing.")
            return
        if not self.video_queue:
             logger.debug("Queue is already empty.")
             messagebox.showinfo("Queue Empty", "The video queue is already empty.")
             return

        if messagebox.askyesno("Confirm Clear Queue", f"Are you sure you want to remove all {len(self.video_queue)} video(s) from the queue?"):
            self.video_queue = []
            self._update_queue_display()
            self.input_path_var.set("") # Clear the input display field
            logger.info("Video queue cleared by user confirmation.")
            self.status_var.set("Status: Idle. Queue cleared.")
        else:
            logger.info("User cancelled clearing the video queue.")


    # --- Start Processing Methods ---
    def _toggle_processing(self):
        """Starts or stops the clipping process."""
        if self.is_processing:
            # Request stop
            logger.info("GUI Action: Stop Clipping button clicked.")
            # Signal the running thread to stop (if thread uses a state dict)
            if self.processing_thread and hasattr(self.processing_thread, 'state'):
                self.processing_thread.state['active'] = False
                logger.info("Signaled clipping thread to stop.")
            else:
                 logger.warning("Cannot signal clipping thread to stop (thread object or state missing).")
            self.is_processing = False # Set state immediately for UI responsiveness
            self._update_button_state()
            self.status_var.set("Status: Stopping clipping process...")
            # Note: The thread needs to check the 'active' flag periodically to actually stop
        else:
            # Request start
            logger.info("GUI Action: Start Clipping Queue button clicked.")
            self._start_clipping_processing()

    def _start_clipping_processing(self):
        logger.info("Attempting to start clipping process...")

        # --- Pre-checks ---
        if not MODULE_IMPORTS_OK:
             logger.error("Cannot start clipping: Core application modules are missing.")
             messagebox.showerror("Module Loading Error", "Cannot start clipping because core application modules failed to load. Check logs for details."); return
        if not self.ffmpeg_exec or not self.ffprobe_exec:
             logger.error("Cannot start clipping: FFmpeg/FFprobe not found or verified.")
             messagebox.showerror("FFmpeg Error", "FFmpeg/FFprobe executables were not found or could not be verified.\n\nPlease ensure FFmpeg is installed and accessible (check bundled 'bin', PATH, or environment variables).\nSee logs for detection details."); return
        if any([self.is_processing, self.is_generating_short, self.is_generating_script, self.is_generating_hashtags, self.is_generating_tags, self.is_generating_titles]):
             logger.warning("Cannot start clipping: Another process is already running.")
             messagebox.showwarning("Busy", "Another process (Clipping, AI Short Gen, Script Gen, or Metadata Gen) is currently running. Please wait for it to complete."); return

        out_path = self.output_path_var.get()
        if not out_path:
             logger.warning("Cannot start clipping: Default output path is not set.")
             messagebox.showerror("Output Path Error", "The Default Output Folder is not set.\nPlease set it in the Settings tab."); return
        if not os.path.isdir(out_path):
             logger.warning(f"Cannot start clipping: Default output path is invalid or not a directory: {out_path}")
             messagebox.showerror("Output Path Error", f"The specified Default Output Folder is invalid or not accessible:\n{out_path}\nPlease check the path in the Settings tab."); return
        if not self.video_queue:
             logger.warning("Cannot start clipping: The video queue is empty.")
             messagebox.showerror("Input Error", "The video queue is empty. Please add videos using the Browse button or drag-and-drop."); return

        # --- Get and Validate Options ---
        try:
            options={
                "clip_count": self.clip_count_var.get(),
                "min_clip_length": self.min_clip_length_var.get(),
                "max_clip_length": self.max_clip_length_var.get(),
                "scene_detect": self.scene_detect_var.get(),
                "scene_threshold": self.scene_threshold_var.get(),
                "remove_audio": self.remove_audio_var.get(),
                "extract_audio": self.extract_audio_var.get(),
                "vertical_crop": self.vertical_crop_var.get(),
                "mirror": self.mirror_var.get(),
                "enhance": self.enhance_var.get()
                }
            # Basic validation
            assert options["min_clip_length"] > 0, "Minimum clip length must be greater than 0."
            assert options["max_clip_length"] > 0, "Maximum clip length must be greater than 0."
            assert options["min_clip_length"] <= options["max_clip_length"], "Minimum clip length cannot be greater than Maximum clip length."
            assert options["clip_count"] > 0, "Number of clips to find must be greater than 0."
            if options["scene_detect"]:
                assert 0.0 < options["scene_threshold"] <= 100.0, "Scene detection threshold must be between 0 (exclusive) and 100 (inclusive)."
        except (tk.TclError, ValueError, AssertionError) as e:
             logger.error(f"Clipping option validation failed: {e}")
             messagebox.showerror("Invalid Clipping Option", f"There is an issue with one of the clipping settings:\n\n{e}"); return

        # Add non-UI option
        options["organize_output"] = self.organize_output_var.get() # Get from settings var

        # --- Start Processing Thread ---
        self.is_processing=True
        self._update_button_state()
        self.progress_var.set(0)
        self.remaining_time_var.set("Est. Time: Calculating...")
        self.status_var.set(f"Status: Starting clipping process for {len(self.video_queue)} video(s)...")

        queue_copy = list(self.video_queue) # Process a copy so GUI can clear original if needed
        # Define callbacks for the thread
        update_progress_cb = lambda index, total, start_time: self.root.after(0, self._update_progress_bar, index, total, start_time)
        update_status_cb = lambda status_text: self.root.after(0, self.status_var.set, status_text)
        # Pass a mutable state dictionary for stop signal
        processing_state = {'active': True}
        # Define completion callback
        completion_cb = lambda proc_type, proc_count, err_count, total, state: self.root.after(0, self._processing_complete, proc_type, proc_count, err_count, total, state)

        # Create and start the thread
        self.processing_thread = threading.Thread(
            target=run_clipping_queue,
            args=(queue_copy, out_path, options, update_progress_cb, update_status_cb, completion_cb, processing_state),
            daemon=True # Allows app to exit even if thread is running (though we try to signal stop)
        )
        # Store state in thread object if possible (useful for signaling stop)
        self.processing_thread.state = processing_state
        self.processing_thread.start()
        logger.info(f"GUI: Clipping thread started successfully for {len(queue_copy)} videos.")

    def _start_script_generation(self):
        logger.info("Attempting to start AI script generation...")

        # --- Pre-checks ---
        if not AI_UTILS_LOADED: logger.error("Cannot generate script: AI Utils module missing."); messagebox.showerror("Module Error", "AI components failed to load."); return
        try:
            from utils.ai_utils import GEMINI_CONFIGURED
            assert GEMINI_CONFIGURED, "Google Gemini API is not configured."
        except (ImportError, AssertionError, NameError) as e:
             logger.warning(f"Cannot generate script: Pre-check failed - {e}.")
             messagebox.showerror("API Configuration Error", "Google Gemini API is not configured or the check failed.\nPlease configure the API Key in Environment Variables or Settings."); return
        if any([self.is_processing, self.is_generating_short, self.is_generating_script, self.is_generating_hashtags, self.is_generating_tags, self.is_generating_titles]):
             logger.warning("Cannot generate script: Another process is already running.")
             messagebox.showwarning("Busy", "Another process is currently running. Please wait."); return

        prompt_text = self.ai_script_prompt_var.get().strip()
        if not prompt_text:
             logger.warning("Cannot generate script: Prompt text is empty.")
             messagebox.showerror("Input Error", "Please enter a niche, topic, or idea in the prompt box to generate a script."); return

        # --- Start Generation Thread ---
        self.is_generating_script = True
        self._update_button_state()
        self.status_var.set("Status: Generating script via Gemini...")
        self.progress_var.set(0) # No specific progress for this
        self.remaining_time_var.set("Est. Time: N/A")
        logger.info("GUI: Starting Gemini script generation thread...")

        # Define completion callback
        completion_cb = lambda script, error: self.root.after(0, self._script_generation_complete, script, error)

        # Create and start the thread
        self.script_gen_thread = threading.Thread(
            target=run_gemini_script_generation,
            args=(prompt_text, completion_cb),
            daemon=True
            )
        self.script_gen_thread.start()

    def _start_metadata_generation(self, metadata_type: str):
        """Generic function to start generation for 'hashtags', 'tags', or 'titles'."""
        logger.info(f"Attempting to start generation for: {metadata_type}"); mt=metadata_type.lower();
        valid_types = ['hashtags', 'tags', 'titles']
        if mt not in valid_types:
            logger.error(f"Invalid metadata type requested: {metadata_type}"); return

        # --- Pre-checks ---
        if not AI_UTILS_LOADED: logger.error(f"Cannot generate {mt}: AI Utils module missing."); messagebox.showerror("Module Error", "AI components failed to load."); return
        try:
             from utils.ai_utils import GEMINI_CONFIGURED
             assert GEMINI_CONFIGURED, "Google Gemini API is not configured."
        except (ImportError, AssertionError, NameError) as e:
             logger.warning(f"Cannot generate {mt}: Pre-check failed - {e}.")
             messagebox.showerror("API Configuration Error", "Google Gemini API is not configured or the check failed.\nPlease configure the API Key in Environment Variables or Settings."); return
        if any([self.is_processing, self.is_generating_short, self.is_generating_script, self.is_generating_hashtags, self.is_generating_tags, self.is_generating_titles]):
             logger.warning(f"Cannot generate {mt}: Another process is already running.")
             messagebox.showwarning("Busy", "Another process is currently running. Please wait."); return

        context_text = ""; state_attr = f"is_generating_{mt}"; count_attr = f"metadata_{mt.rstrip('s')}_count_var"; thread_attr = f"{mt.rstrip('s')}_gen_thread"; # e.g., is_generating_hashtags, metadata_hashtag_count_var, hashtag_gen_thread

        # Get Context (needs MetadataTab reference)
        try:
            if not hasattr(self, 'metadata_tab') or not isinstance(self.metadata_tab, MetadataTab):
                 raise AttributeError("MetadataTab UI element not found or not initialized correctly.")
            context_text = self.metadata_tab.context_textbox.get("1.0", "end-1c").strip()
            assert context_text, "Context text cannot be empty."
        except (AttributeError, tk.TclError, AssertionError) as e:
             logger.warning(f"Cannot generate {mt}: Context input invalid/empty: {e}")
             messagebox.showerror("Input Error", f"Please enter a topic, description, or context in the text box to generate {mt}."); return

        # Get Count
        try:
            if not hasattr(self, count_attr):
                 raise AttributeError(f"Count variable '{count_attr}' not found in application logic.")
            count = getattr(self, count_attr).get()
            assert isinstance(count, int) and count > 0, f"Number of {mt} must be a positive integer."
        except (AttributeError, tk.TclError, ValueError, AssertionError) as e:
             logger.error(f"Invalid count value for {mt}: {e}")
             messagebox.showerror("Input Error", f"Invalid number specified for {mt.capitalize()}:\n\n{e}"); return

        # --- Start Generation Thread ---
        setattr(self, state_attr, True) # Set the specific flag, e.g., self.is_generating_hashtags = True
        self._update_button_state()
        self.status_var.set(f"Status: Generating {mt.capitalize()} via Gemini...")
        self.progress_var.set(0) # No specific progress
        self.remaining_time_var.set("Est. Time: N/A")
        logger.info(f"GUI: Starting Gemini {mt} generation thread...")

        # Define completion callback
        completion_cb = lambda m_type, results, error: self.root.after(0, self._metadata_generation_complete, m_type, results, error)

        # Create and start the thread
        thread = threading.Thread(
            target=run_gemini_metadata_generation,
            args=(mt, context_text, count, completion_cb), # Pass metadata_type string
            daemon=True
        )
        setattr(self, thread_attr, thread) # Store thread reference, e.g., self.hashtag_gen_thread = thread
        thread.start()

    # --- Specific Metadata Generation Starters ---
    def _start_hashtag_generation(self): self._start_metadata_generation('hashtags')
    def _start_tag_generation(self): self._start_metadata_generation('tags')
    def _start_title_generation(self): self._start_metadata_generation('titles')

    def _apply_ai_short_generation(self):
         logger.info("Attempting to start AI Short video generation...")

         # --- Pre-checks ---
         if not MODULE_IMPORTS_OK: logger.error("Cannot generate AI short: Core modules missing."); messagebox.showerror("Module Loading Error","Core application modules failed to load."); return
         if not self.ffmpeg_exec or not self.ffprobe_exec: logger.error("Cannot generate AI short: FFmpeg missing."); messagebox.showerror("FFmpeg Error","FFmpeg/FFprobe not found or verified.\nCheck logs and ensure FFmpeg is accessible."); return
         if not TTS_UTILS_LOADED: logger.error("Cannot generate AI short: TTS Utils module missing."); messagebox.showerror("Module Error", "TTS components failed to load."); return
         try:
             from utils.tts_utils import POLLY_CONFIGURED
             assert POLLY_CONFIGURED, "AWS Polly is not configured."
         except (ImportError, AssertionError, NameError) as e:
             logger.warning(f"Cannot generate AI short: Pre-check failed - {e}.")
             messagebox.showerror("AWS Polly Error","AWS Polly TTS is not configured or the check failed.\nCheck Env Vars, Settings, or your default AWS credentials."); return
         if any([self.is_processing, self.is_generating_short, self.is_generating_script, self.is_generating_hashtags, self.is_generating_tags, self.is_generating_titles]):
             logger.warning("Cannot generate AI short: Another process is already running.")
             messagebox.showwarning("Busy","Another process is currently running. Please wait."); return

         # --- Get and Validate Inputs ---
         video_path = self.ai_video_path_var.get()
         output_dir = self.ai_output_path_var.get()
         script_text = ""
         polly_voice = self.ai_polly_voice_var.get()
         font_size = 0

         try: # Get script from textbox (needs AI Short Tab reference)
            if not hasattr(self, 'ai_short_tab') or not isinstance(self.ai_short_tab, AIShortTab):
                 raise AttributeError("AIShortTab UI element not found.")
            script_text = self.ai_short_tab.script_textbox.get("1.0","end-1c").strip()
            assert script_text, "Script text cannot be empty."
         except (AttributeError, tk.TclError, AssertionError) as e:
             logger.warning(f"Cannot generate AI short: Script input invalid/empty: {e}")
             messagebox.showerror("Input Error","The script text box is empty or cannot be accessed."); return

         try: # Get font size
            font_size = self.ai_font_size_var.get()
            assert isinstance(font_size, int) and font_size > 0, "Font size must be a positive integer."
         except (tk.TclError, ValueError, AssertionError) as e:
             logger.warning(f"Invalid font size input: {e}")
             messagebox.showerror("Input Error", f"Invalid font size specified:\n{e}"); return

         if not video_path or not os.path.isfile(video_path):
             logger.warning(f"Invalid background video path: {video_path}");
             messagebox.showerror("Input Error","Please select a valid background video file."); return
         if not output_dir:
             logger.warning("AI short output directory not selected.");
             messagebox.showerror("Input Error","Please select an output location for the AI short."); return
         if not os.path.isdir(output_dir):
             logger.warning(f"AI short output directory is invalid: {output_dir}");
             messagebox.showerror("Input Error",f"The selected output location is not a valid directory:\n{output_dir}"); return
         if not polly_voice:
             logger.warning("Polly voice not selected.");
             messagebox.showerror("Input Error","Please select an AI Voice for the text-to-speech."); return

         # --- Prepare Paths and Temp Dir ---
         base_name, _ = os.path.splitext(os.path.basename(video_path))
         timestamp = int(time.time())
         random_id = random.randint(100,999)
         output_filename = f"{base_name}_AI_Short_{timestamp}_{random_id}.mp4"
         final_output_path = os.path.join(output_dir, output_filename)

         # Check for overwrite
         if os.path.exists(final_output_path):
             if not messagebox.askyesno("Confirm Overwrite",f"The output file '{output_filename}' already exists in the selected location.\n\nDo you want to overwrite it?"):
                 logger.info("AI Short generation cancelled by user due to existing file.")
                 return # User chose not to overwrite

         # Create temporary directory for intermediate files
         temp_dir_name = f"temp_ai_short_{timestamp}_{random_id}"
         temp_dir_path = os.path.join(output_dir, temp_dir_name)
         try:
            os.makedirs(temp_dir_path, exist_ok=True)
            logger.info(f"Created temporary directory: {temp_dir_path}")
         except OSError as e:
            logger.error(f"Cannot create temporary directory: {temp_dir_path}", exc_info=True)
            messagebox.showerror("Directory Error",f"Could not create a temporary directory for processing:\n{e}\n\nPlease check permissions for the output location.");
            # Don't reset state here, maybe _apply_ai_short_generation should call a reset if it fails early?
            return

         # --- Start Generation Thread ---
         self.is_generating_short = True
         self._update_button_state()
         self.progress_var.set(0)
         self.remaining_time_var.set("Est. Time: Starting...")
         self.status_var.set("Status: Starting AI short video generation...")
         logger.info("GUI: Starting AI short generation thread...")

         # Define options dictionary
         options = {
             'polly_voice': polly_voice,
             'font_size': font_size,
             'organize_output': self.organize_output_var.get() # Include organization preference
             }

         # Define callbacks
         update_progress_cb = lambda index, total, start_time: self.root.after(0, self._update_progress_bar, index, total, start_time)
         update_status_cb = lambda status_text: self.root.after(0, self.status_var.set, status_text)
         processing_state = {'active': True} # For potential stop signal
         completion_cb = lambda proc_type, proc_count, err_count, total, state: self.root.after(0, self._processing_complete, proc_type, proc_count, err_count, total, state)

         # Create and start thread
         self.generation_thread = threading.Thread(
             target=run_ai_short_generation,
             args=(script_text, video_path, final_output_path, temp_dir_path, options, update_progress_cb, update_status_cb, completion_cb, processing_state),
             daemon=True
         )
         self.generation_thread.state = processing_state # Store state
         self.generation_thread.start()


    # --- Callback Methods ---
    def _update_progress_bar(self, index, total_items, start_time):
        """Callback to update the progress bar and estimated time remaining."""
        # Check if any relevant process is actually running
        is_busy = self.is_processing or self.is_generating_short
        if not is_busy:
            # logger.debug("Progress update called but no relevant process is active.")
            return # Don't update if nothing is supposed to be running

        try:
            if total_items <= 0: # Avoid division by zero
                self.progress_var.set(0.0)
                self.remaining_time_var.set("Est. Time: N/A")
                return

            # Calculate progress (ensure it's between 0 and 1)
            # index is 0-based, so add 1 for calculation
            current_item_num = index + 1
            progress_percent = current_item_num / total_items
            self.progress_var.set(max(0.0, min(1.0, progress_percent)))

            elapsed_time = time.time() - start_time

            # Calculate estimated remaining time
            if current_item_num < total_items and elapsed_time > 1 and current_item_num > 0:
                time_per_item = elapsed_time / current_item_num
                remaining_items = total_items - current_item_num
                remaining_time_sec = time_per_item * remaining_items
                minutes, seconds = divmod(int(remaining_time_sec), 60)
                self.remaining_time_var.set(f"Est. Time: {minutes}m {seconds}s")
            elif current_item_num >= total_items: # Process is finishing or complete
                self.remaining_time_var.set("Est. Time: Finishing...")
            else: # Early stages, not enough data
                self.remaining_time_var.set("Est. Time: Calculating...")

        except Exception as e:
             logger.error("Error updating progress bar", exc_info=True)
             self.progress_var.set(0.0) # Reset on error
             self.remaining_time_var.set("Est. Time: Error")

    def _processing_complete(self, process_type, processed_count, error_count, total_items, processing_state_from_thread):
        """Callback executed when clipping or AI short generation finishes or is stopped."""
        logger.info(f"GUI Callback: '{process_type}' process finished or stopped.")

        # Determine if the process was stopped by the user signal
        was_stopped = not processing_state_from_thread.get('active', True) # Assume active if key missing

        # --- Reset State ---
        if process_type == "Clipping":
            self.is_processing = False
            if not was_stopped: # Clear queue only if completed normally
                 logger.info("Clipping completed, clearing video queue.")
                 self.video_queue = []
                 self._update_queue_display()
                 self.input_path_var.set("")
            else:
                 logger.info("Clipping was stopped, keeping remaining items in queue.")
                 # Update display in case some were processed before stop
                 if not self.video_queue: self.input_path_var.set("")
                 elif len(self.video_queue) == 1: self.input_path_var.set(os.path.basename(self.video_queue[0]))
                 else: self.input_path_var.set(f"{len(self.video_queue)} files in queue")


        elif process_type == "AI Short Generation":
            self.is_generating_short = False
            # No queue to clear here

        self._update_button_state() # Re-enable buttons

        # --- Prepare Messages ---
        msg_func = messagebox.showinfo
        msg_title = f"{process_type} Complete"
        status_msg = f"Status: Idle. {process_type} finished."
        completion_message = ""

        if was_stopped:
            msg_title = f"{process_type} Stopped"
            status_msg = f"Status: Idle. {process_type} stopped by user."
            completion_message = f"{process_type} process was stopped."
            logger.info(f"{process_type} was stopped. Processed before stop: {processed_count}, Errors: {error_count}")
            # For clipping, show skipped count if stopped
            if process_type == "Clipping" and total_items > 0:
                 skipped_count = total_items - processed_count - error_count
                 completion_message += f"\nItems processed before stop: {processed_count}\nErrors before stop: {error_count}\nItems remaining: {skipped_count}"

        else: # Process completed normally
            completion_message = f"{process_type} finished."
            status_msg_end = "successfully."
            logger.info(f"{process_type} finished normally. Success: {processed_count}, Errors: {error_count}, Total: {total_items}")

            if total_items > 0:
                completion_message += f"\nTotal Items: {total_items}\nSuccessful: {processed_count}\nErrors: {error_count}"
                # Add skipped count for clipping if relevant
                if process_type == "Clipping":
                    skipped_count = total_items - processed_count - error_count
                    if skipped_count > 0: completion_message += f"\nSkipped: {skipped_count}"


            if error_count > 0:
                status_msg_end = f"with {error_count} error(s)."
                msg_func = messagebox.showwarning
                msg_title = f"{process_type} Finished with Errors"
                completion_message += "\n\nPlease check the application logs for error details."
                logger.warning(f"{process_type} finished with {error_count} errors.")

            status_msg = f"Status: Idle. {process_type} {status_msg_end}"

        # --- Update UI ---
        self.status_var.set(status_msg)
        # Set progress to 100% if completed normally and had items, else 0% if stopped or no items
        self.progress_var.set(1.0 if not was_stopped and total_items > 0 and processed_count == total_items else 0.0)
        self.remaining_time_var.set("Est. Time: Done")
        msg_func(msg_title, completion_message) # Show the final message box

    def _script_generation_complete(self, generated_script: Optional[str], error: Optional[Exception]):
        """Callback executed when Gemini script generation finishes."""
        logger.info("GUI Callback: Script generation complete.")
        self.is_generating_script = False
        self._update_button_state() # Re-enable buttons

        if error:
            error_type = type(error).__name__
            # Make GeminiError messages slightly more user-friendly
            if isinstance(error, GeminiError):
                 error_msg = f"Script generation failed (Gemini API Error):\n{error}\n\n(Check API key, quotas, and network connection)"
            else:
                 error_msg = f"Script generation failed unexpectedly ({error_type}):\n{error}"
            logger.error(f"Script Generation Error: {error_msg}", exc_info=isinstance(error, Exception) and not isinstance(error, GeminiError))
            self.status_var.set("Status: Idle. Script generation failed!")
            messagebox.showerror("Script Generation Error", error_msg[:1000]) # Limit message length

        elif generated_script:
            self.status_var.set("Status: Idle. Script generated successfully.")
            logger.info("GUI: Populating script textbox with generated content.")
            try:
                if not hasattr(self, 'ai_short_tab') or not self.ai_short_tab.winfo_exists() or not hasattr(self.ai_short_tab, 'script_textbox'):
                     raise AttributeError("AI Short Tab or its script textbox UI element not found.")

                script_textbox = self.ai_short_tab.script_textbox
                script_textbox.configure(state="normal") # Enable editing
                script_textbox.delete("1.0", "end")      # Clear existing content
                script_textbox.insert("1.0", generated_script) # Insert new script
                # Keep it editable: script_textbox.configure(state="normal")
                messagebox.showinfo("Script Generated", "AI script has been generated and placed in the script text box.")
                # Optionally switch focus to the AI Short tab
                # self.tab_view.set("AI Short Generator")

            except Exception as e:
                 logger.error("Failed to update script textbox UI element", exc_info=True)
                 messagebox.showerror("UI Update Error",f"Failed to display the generated script in the text box:\n{e}\n\nThe script might be printed in the console/log.")
                 # Fallback: print script to console if UI update fails
                 print("\n--- GENERATED SCRIPT (UI Update Failed) ---")
                 print(generated_script)
                 print("--- END GENERATED SCRIPT ---\n")

        else: # No error, but script is empty or None
             logger.warning("Script generation returned successfully but the result was empty.")
             self.status_var.set("Status: Idle. Generated script was empty.")
             messagebox.showwarning("Empty Script", "The AI generated an empty script. You might want to try refining your prompt.")

    def _metadata_generation_complete(self, metadata_type: str, result_list: Optional[List[str]], error: Optional[Exception]):
        """Callback executed when Gemini metadata generation finishes."""
        mt = metadata_type.lower() # e.g., 'hashtags'
        state_attr = f"is_generating_{mt}" # e.g., 'is_generating_hashtags'
        logger.info(f"GUI Callback: Metadata generation complete for: {mt}")

        # Reset state flag
        if hasattr(self, state_attr):
            setattr(self, state_attr, False)
        else:
             logger.warning(f"Could not find state attribute '{state_attr}' to reset.")

        self._update_button_state() # Re-enable buttons

        if error:
            error_type = type(error).__name__
            if isinstance(error, GeminiError):
                 error_msg = f"Failed to generate {mt} (Gemini API Error):\n{error}\n\n(Check API key, quotas, and network connection)"
            else:
                 error_msg = f"Failed to generate {mt} unexpectedly ({error_type}):\n{error}"
            logger.error(f"{mt.capitalize()} Generation Error: {error_msg}", exc_info=isinstance(error, Exception) and not isinstance(error, GeminiError))
            self.status_var.set(f"Status: Idle. {mt.capitalize()} generation failed!")
            messagebox.showerror(f"{mt.capitalize()} Generation Error", error_msg[:1000])

        elif result_list and len(result_list) > 0:
            self.status_var.set(f"Status: Idle. {mt.capitalize()} generated successfully.")
            logger.info(f"GUI: Populating {mt} output box with {len(result_list)} items.")
            try:
                if not hasattr(self, 'metadata_tab') or not self.metadata_tab.winfo_exists():
                     raise AttributeError("MetadataTab UI element not found.")

                # Determine the correct output box widget attribute name
                widget_attr = f"{mt.rstrip('s')}_output_box" # e.g., 'hashtag_output_box'
                if not hasattr(self.metadata_tab, widget_attr):
                    raise AttributeError(f"MetadataTab does not have the expected output widget attribute: '{widget_attr}'")

                widget = getattr(self.metadata_tab, widget_attr)
                if not isinstance(widget, ctk.CTkTextbox):
                     raise TypeError(f"Expected widget '{widget_attr}' to be a CTkTextbox, but found {type(widget)}.")

                # Format output (one item per line)
                output_text = "\n".join(result_list)

                widget.configure(state="normal") # Enable writing
                widget.delete("1.0", "end")      # Clear previous content
                widget.insert("1.0", output_text)  # Insert new results
                widget.configure(state="disabled") # Disable editing after population
                logger.info(f"Successfully displayed {len(result_list)} generated {mt}.")
                # Optionally add a small confirmation message?
                # messagebox.showinfo(f"{mt.capitalize()} Generated", f"{len(result_list)} {mt} generated and displayed.")

            except Exception as e:
                 logger.error(f"Failed to update {mt} output box UI element", exc_info=True)
                 messagebox.showerror("UI Update Error",f"Failed to display the generated {mt} in the output box:\n{e}\n\nResults might be printed in the console/log.")
                 # Fallback: print results to console
                 print(f"\n--- GENERATED {mt.upper()} (UI Update Failed) ---")
                 print("\n".join(result_list))
                 print(f"--- END GENERATED {mt.upper()} ---\n")

        else: # No error, but result_list is None or empty
             logger.warning(f"{mt.capitalize()} generation returned successfully but the result list was empty.")
             self.status_var.set(f"Status: Idle. Generated {mt} list was empty.")
             messagebox.showwarning(f"Empty Results", f"The AI returned no {mt} based on the provided context.")


    # --- Helper Methods ---
    def _update_queue_display(self):
        """Safely calls the method on ClippingTab to update the Treeview."""
        if hasattr(self,'clipping_tab') and isinstance(self.clipping_tab, ClippingTab) and self.clipping_tab.winfo_exists():
            if hasattr(self.clipping_tab,'update_queue_display') and callable(self.clipping_tab.update_queue_display):
                try:
                    logger.debug("Calling update_queue_display on ClippingTab.")
                    self.clipping_tab.update_queue_display(self.video_queue)
                except Exception as e:
                    logger.error(f"Error calling update_queue_display on ClippingTab: {e}", exc_info=True)
            else:
                logger.warning("ClippingTab instance exists but is missing the 'update_queue_display' method.")
        #else: logger.debug("ClippingTab instance not available or destroyed, cannot update queue display.")


    def _update_button_state(self):
        """ Disables/Enables buttons based on processing state and config validity. """
        any_busy = (self.is_processing or self.is_generating_short or self.is_generating_script or
                    self.is_generating_hashtags or self.is_generating_tags or self.is_generating_titles)
        logger.debug(f"GUI Helper: Updating button states. Any process busy: {any_busy}")

        # Check configuration status
        ffmpeg_ok = self.ffmpeg_exec is not None and self.ffprobe_exec is not None
        gemini_ok = False
        polly_ok = False

        if AI_UTILS_LOADED:
             try: from utils.ai_utils import GEMINI_CONFIGURED; gemini_ok = GEMINI_CONFIGURED
             except (ImportError, NameError): pass # Defaults to False
        if TTS_UTILS_LOADED:
             try: from utils.tts_utils import POLLY_CONFIGURED; polly_ok = POLLY_CONFIGURED
             except (ImportError, NameError): pass # Defaults to False

        logger.debug(f"Button State Checks: FFmpeg OK: {ffmpeg_ok}, Gemini OK: {gemini_ok}, Polly OK: {polly_ok}")

        # Get default theme colors (with fallback)
        try:
            default_fg = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
            default_hc = ctk.ThemeManager.theme["CTkButton"]["hover_color"]
        except Exception as theme_err:
            logger.warning(f"Could not get default button colors from ThemeManager: {theme_err}. Using fallback.")
            default_fg = ("#3a7ebf", "#1f538d") # Default blue
            default_hc = ("#325882", "#14375e") # Default blue hover

        # --- Update Clipping Button ---
        try:
            if hasattr(self, 'clipping_tab') and self.clipping_tab.winfo_exists() and hasattr(self.clipping_tab, 'start_stop_button'):
                btn = self.clipping_tab.start_stop_button
                if self.is_processing: # Currently clipping
                    btn.configure(text="Stop Clipping", fg_color="red", hover_color="#C40000", state="normal")
                elif not ffmpeg_ok: # FFmpeg missing
                    btn.configure(text="FFmpeg Missing!", state="disabled", fg_color="grey")
                elif any_busy: # Another process running
                    btn.configure(text="Start Clipping Queue", state="disabled", fg_color=default_fg) # Use default color when disabled by other process
                else: # Ready to start
                    btn.configure(text="Start Clipping Queue", fg_color="green", hover_color="darkgreen", state="normal")
            else: logger.debug("Clipping tab or start/stop button not found for state update.")
        except Exception as e: logger.error(f"Error updating Clipping button state: {e}", exc_info=True)

        # --- Update AI Script Generation Button ---
        try:
            if hasattr(self, 'ai_short_tab') and self.ai_short_tab.winfo_exists() and hasattr(self.ai_short_tab, 'generate_script_button'):
                btn = self.ai_short_tab.generate_script_button
                if self.is_generating_script: # Currently generating script
                    btn.configure(text="Generating Script...", state="disabled", fg_color=default_fg)
                elif not gemini_ok: # Gemini API not configured
                    btn.configure(text="Configure Gemini API", state="disabled", fg_color="grey")
                elif any_busy: # Another process running
                    btn.configure(text="Generate Script with Gemini", state="disabled", fg_color=default_fg)
                else: # Ready to generate
                    btn.configure(text="Generate Script with Gemini", state="normal", fg_color=default_fg, hover_color=default_hc)
            else: logger.debug("AI Short tab or generate script button not found for state update.")
        except Exception as e: logger.error(f"Error updating Script Gen button state: {e}", exc_info=True)

        # --- Update AI Short Generation Button ---
        try:
             if hasattr(self, 'ai_short_tab') and self.ai_short_tab.winfo_exists() and hasattr(self.ai_short_tab, 'generate_button'):
                btn = self.ai_short_tab.generate_button
                if self.is_generating_short: # Currently generating short
                    btn.configure(text="Generating AI Short...", state="disabled", fg_color=default_fg)
                elif not ffmpeg_ok: # FFmpeg missing
                    btn.configure(text="FFmpeg Missing!", state="disabled", fg_color="grey")
                elif not polly_ok: # Polly missing
                    btn.configure(text="Configure AWS Polly", state="disabled", fg_color="grey")
                elif any_busy: # Another process running
                    btn.configure(text="Generate AI Short", state="disabled", fg_color=default_fg)
                else: # Ready to generate
                    btn.configure(text="Generate AI Short", state="normal", fg_color=default_fg, hover_color=default_hc)
             else: logger.debug("AI Short tab or generate button not found for state update.")
        except Exception as e: logger.error(f"Error updating AI Short Gen button state: {e}", exc_info=True)

        # --- Update Metadata Buttons ---
        try:
            if hasattr(self, 'metadata_tab') and self.metadata_tab.winfo_exists():
                 for meta_type in ['hashtags','tags','titles']:
                     btn_attr = f'generate_{meta_type.rstrip("s")}_button' # e.g., generate_hashtag_button
                     busy_attr = f'is_generating_{meta_type}' # e.g., is_generating_hashtags
                     btn = getattr(self.metadata_tab, btn_attr, None)

                     if btn and btn.winfo_exists():
                         is_meta_busy = getattr(self, busy_attr, False)
                         button_text_base = f"Generate {meta_type.capitalize()}"

                         if is_meta_busy: # This specific metadata type is generating
                             btn.configure(text=f"Generating {meta_type.capitalize()}...", state="disabled", fg_color=default_fg)
                         elif not gemini_ok: # Gemini API not configured
                             btn.configure(text="Configure Gemini API", state="disabled", fg_color="grey")
                         elif any_busy: # Another process (could be different metadata or clipping/short) is running
                             btn.configure(text=button_text_base, state="disabled", fg_color=default_fg)
                         else: # Ready to generate this metadata type
                             btn.configure(text=button_text_base, state="normal", fg_color=default_fg, hover_color=default_hc)
                     # else: logger.debug(f"Metadata button '{btn_attr}' not found for state update.")
            # else: logger.debug("Metadata tab not found for state update.")
        except Exception as e: logger.error(f"Error updating Metadata button states: {e}", exc_info=True)

        logger.debug("Button state update complete.")


    def _change_theme(self, new_theme: str):
        """Changes the application theme."""
        logger.info(f"GUI: Changing theme to: {new_theme}");
        valid_themes = ["dark", "light", "system"]
        theme_lower = new_theme.lower()
        if theme_lower not in valid_themes:
            logger.warning(f"Invalid theme '{new_theme}' requested. Defaulting to 'system'.")
            theme_lower = "system"

        ctk.set_appearance_mode(theme_lower)
        self.theme = theme_lower # Store the applied theme name
        logger.info(f"Theme set to '{self.theme}'. Applying to components.")

        # Update components that need explicit theme changes
        self._apply_treeview_theme_tags()
        # Add calls for other components if needed (e.g., Spinbox colors)
        # Example:
        # try:
        #     for tab in [self.clipping_tab, self.ai_short_tab, self.metadata_tab, self.settings_tab]:
        #          if hasattr(tab,'winfo_exists') and tab.winfo_exists() and hasattr(tab,'apply_spinbox_theme_tags'):
        #               tab.apply_spinbox_theme_tags(self.theme)
        # except Exception as e:
        #      logger.warning(f"Could not update Spinbox theme colors: {e}")


    def _apply_treeview_theme_tags(self):
        """Applies theme colors to the Treeview in ClippingTab."""
        if hasattr(self,'clipping_tab') and isinstance(self.clipping_tab, ClippingTab) and self.clipping_tab.winfo_exists():
            if hasattr(self.clipping_tab,'apply_treeview_theme_tags') and callable(self.clipping_tab.apply_treeview_theme_tags):
                try:
                    logger.debug(f"Applying theme '{self.theme}' to Treeview tags.")
                    self.clipping_tab.apply_treeview_theme_tags(self.theme)
                except Exception as e:
                    logger.error(f"Error applying theme tags to Treeview: {e}", exc_info=True)
            else:
                logger.warning("ClippingTab instance exists but is missing the 'apply_treeview_theme_tags' method.")
        # else: logger.debug("ClippingTab instance not available or destroyed, cannot apply treeview theme.")


    # --- Reset State Methods (Mostly for error recovery or cancellation) ---
    def _reset_processing_state(self):
        """Resets state flags and UI related to clipping."""
        logger.debug("Resetting clipping processing state.");
        self.is_processing = False
        # Reset thread ref? Depends on how stop is handled. Best leave it until next start.
        self._update_button_state()
        self.status_var.set("Status: Idle")
        self.progress_var.set(0)
        self.remaining_time_var.set("Est. Time: N/A")

    def _reset_generation_state(self):
        """Resets state flags and UI related to AI short generation."""
        logger.debug("Resetting AI short generation state.");
        self.is_generating_short = False
        self._update_button_state()
        self.status_var.set("Status: Idle")
        self.progress_var.set(0)
        self.remaining_time_var.set("Est. Time: N/A")

    def _reset_script_gen_state(self):
        """Resets state flags and UI related to script generation."""
        logger.debug("Resetting script generation state.");
        self.is_generating_script = False
        self._update_button_state()
        self.status_var.set("Status: Idle")
        # No progress bar for this one normally

    def _reset_metadata_gen_state(self, meta_type: str):
        """Resets state flags and UI related to a specific metadata generation type."""
        mt = meta_type.lower()
        logger.debug(f"Resetting {mt} generation state.")
        state_flag_attr = f"is_generating_{mt}"
        if hasattr(self, state_flag_attr):
            setattr(self, state_flag_attr, False)
        else:
             logger.warning(f"Could not find state flag '{state_flag_attr}' to reset.")
        self._update_button_state()
        self.status_var.set("Status: Idle")
        # No progress bar for these

    # --- Closing ---
    def _on_closing(self):
        """Handles the window close event."""
        logger.info("GUI: Window close requested.");
        process_running = (self.is_processing or self.is_generating_short or self.is_generating_script or
                           self.is_generating_hashtags or self.is_generating_tags or self.is_generating_titles)
        confirm_exit = True # Assume OK to exit unless process running

        if process_running:
            logger.warning("Close requested while a process is running.")
            confirm_exit = messagebox.askyesno(
                "Confirm Exit",
                "A background process is still running.\n\n"
                "Exiting now may cause the process to terminate abruptly and could lead to incomplete or corrupted files.\n\n"
                "Are you sure you want to exit?"
            )

        if confirm_exit:
            logger.info("GUI: Exiting application.")
            # Optionally try to save settings on exit?
            # self._save_settings() # Be careful, might pop up message box during shutdown
            # Attempt clean shutdown
            # Signal threads to stop if possible (more robust stop logic needed in threads)
            if self.processing_thread and hasattr(self.processing_thread, 'state'): self.processing_thread.state['active'] = False
            if self.generation_thread and hasattr(self.generation_thread, 'state'): self.generation_thread.state['active'] = False
            # Add similar signaling for script/metadata if they support it
            # Give a brief moment for threads to potentially react?
            # time.sleep(0.1)
            self.root.destroy()
        else:
            logger.info("GUI: Exit cancelled by user.")


# --- Main Execution ---
def main():
    root = None
    try:
        # Initialize TkinterDnD root window
        logger.info("Creating TkinterDnD root window...")
        root = TkinterDnD.Tk()
        root.withdraw() # Hide root window initially until setup is complete or error shown
        logger.info("Root TkinterDnD window created successfully.")

    except Exception as e:
        logger.critical("FATAL ERROR: Failed to create the main TkinterDnD root window.", exc_info=True)
        # Try to show a basic Tkinter error message if GUI libs loaded partially
        try:
            import tkinter as tk
            from tkinter import messagebox
            error_root = tk.Tk()
            error_root.withdraw()
            messagebox.showerror("Fatal Startup Error", f"Failed to initialize the main application window.\n\nError: {e}\n\nPlease check logs and ensure TkinterDnD2 is installed correctly.")
            error_root.destroy()
        except Exception as fallback_e:
             logger.error(f"Could not display Tkinter error message: {fallback_e}")
             print(f"FATAL STARTUP ERROR: {e}") # Print to console as last resort
        sys.exit(1) # Exit if window creation fails

    # Proceed only if root window was created
    if root:
        if MODULE_IMPORTS_OK:
            try:
                logger.info("Initializing VideoClipperApp...")
                app = VideoClipperApp(root)
                logger.info("Initialization complete. Showing main window.")
                root.deiconify() # Show the window now that it's set up
                logger.info("Starting Tkinter main event loop...")
                root.mainloop()
                logger.info("Tkinter main event loop finished.")
            except Exception as app_e:
                logger.critical("FATAL ERROR during application execution", exc_info=True)
                messagebox.showerror("Fatal Application Error", f"A critical error occurred during application runtime:\n\n{app_e}\n\nPlease check logs for details.")
                try:
                    root.destroy() # Attempt to close the window on error
                except Exception: pass # Ignore errors during destroy
                sys.exit(1)
        else:
            logger.error("GUI cannot start fully due to module import errors. Showing error window.")
            # The _show_import_error should have been called within __init__
            # We still need to run mainloop for that error window to be interactive.
            root.deiconify() # Show the error window created by _show_import_error
            root.mainloop()
            logger.info("Error window closed by user.")
            sys.exit(1) # Exit after error window is closed
    else:
        # This case should theoretically not be reached due to sys.exit above if root fails
        logger.critical("GUI could not start because the root window object is None.")
        sys.exit(1)


if __name__ == "__main__":
    # Logger should be initialized at the very top now
    try:
        logger.info(f"--- {APP_NAME} Application Start ---")
        logger.info(f"Python Version: {sys.version.split()[0]}")
        logger.info(f"Platform: {platform.system()} ({platform.release()})")
        logger.info(f"CustomTkinter Version: {ctk.__version__}") # Log CTk version
        # Add other relevant versions if needed
    except NameError:
        print("Logger not initialized before __main__ guard.") # Should not happen with current structure
        sys.exit(1)
    except Exception as init_log_e:
         logger.error(f"Error during initial info logging: {init_log_e}")

    main() # Run the main application logic

    logger.info(f"--- {APP_NAME} Application End ---")