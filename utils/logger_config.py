# utils/logger_config.py
import logging
import sys
from logging.handlers import RotatingFileHandler
import os

def setup_logging(log_file=None):
    """
    Configure and initialize application-wide logging.

    Args:
        log_file (str, optional): Full path to log file.
        log_level (int, optional): Logging level. Defaults to logging.INFO.

    Returns:
        logging.Logger: Configured logger instance.
    """

    log_level_str = os.environ.get('AUTOTUBE_LOG_LEVEL', 'INFO').upper()
    try:
        log_level = getattr(logging, log_level_str)
    except AttributeError:
        log_level = logging.INFO
        print(f"Invalid log level '{log_level_str}' in environment variable.  Defaulting to INFO.")


    # Default log file in project root's 'logs' directory
    if log_file is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Check if base_dir is empty
        if not base_dir:
            base_dir = os.getcwd()  # Use the current working directory as a fallback

        logs_dir = os.path.join(base_dir, 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        log_file = os.path.join(logs_dir, 'autotube.log')

    # Configure logging with console and file handlers
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),  # Console output
            RotatingFileHandler(
                log_file,
                maxBytes=10*1024*1024,  # 10 MB max log file size
                backupCount=5
            )
        ]
    )

    return logging.getLogger('autotube')