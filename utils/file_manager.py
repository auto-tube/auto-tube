import os
import shutil
import logging
from datetime import datetime
from typing import Optional, List, Union

class FileOrganizer:
    """
    A utility class for managing and organizing output files from video processing workflows.
    
    This class provides methods for organizing files into date-based directories, 
    cleaning up temporary files, and managing output storage.
    """

    def __init__(self, output_folder: str):
        """
        Initialize the FileOrganizer with a specified output directory.

        Args:
            output_folder (str): Base directory for storing processed files.
        """
        self.output_folder = os.path.abspath(output_folder)
        os.makedirs(self.output_folder, exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)

    def organize_output(self, file_extensions: List[str] = [".mp4", ".mp3"]) -> None:
        """
        Organize processed files into date-based subdirectories.

        Args:
            file_extensions (List[str], optional): File types to organize. 
                                                   Defaults to [".mp4", ".mp3"].
        """
        try:
            # Create date-based subdirectory
            date_folder = os.path.join(
                self.output_folder, 
                datetime.now().strftime("%Y-%m-%d")
            )
            os.makedirs(date_folder, exist_ok=True)

            # Organize matching files
            organized_count = 0
            for filename in os.listdir(self.output_folder):
                if any(filename.endswith(ext) for ext in file_extensions):
                    source_path = os.path.join(self.output_folder, filename)
                    destination_path = os.path.join(date_folder, filename)
                    
                    # Skip if file already exists in destination
                    if os.path.exists(destination_path):
                        self.logger.warning(f"File {filename} already exists. Skipping.")
                        continue

                    shutil.move(source_path, destination_path)
                    organized_count += 1

            self.logger.info(f"Organized {organized_count} files into {date_folder}")

        except Exception as e:
            self.logger.error(f"Error organizing files: {e}")
            raise

    def cleanup_old_files(
        self, 
        days_to_keep: int = 30, 
        extensions: Optional[List[str]] = None
    ) -> None:
        """
        Remove files older than a specified number of days.

        Args:
            days_to_keep (int, optional): Number of days to retain files. Defaults to 30.
            extensions (List[str], optional): File extensions to clean. 
                                              If None, cleans all files.
        """
        current_time = datetime.now()
        cleaned_files = 0

        for root, _, files in os.walk(self.output_folder):
            for file in files:
                file_path = os.path.join(root, file)
                
                # Check file extension filter
                if extensions and not any(file.endswith(ext) for ext in extensions):
                    continue

                # Check file age
                file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                if (current_time - file_modified).days > days_to_keep:
                    try:
                        os.remove(file_path)
                        cleaned_files += 1
                        self.logger.info(f"Removed old file: {file_path}")
                    except Exception as e:
                        self.logger.error(f"Could not remove {file_path}: {e}")

        self.logger.info(f"Cleaned {cleaned_files} files older than {days_to_keep} days")

# Example usage
def setup_file_management(base_output_directory: str):
    """
    Convenience function to set up file management for a video processing workflow.

    Args:
        base_output_directory (str): Root directory for storing processed files.

    Returns:
        FileOrganizer: Configured file management utility.
    """
    return FileOrganizer(base_output_directory)