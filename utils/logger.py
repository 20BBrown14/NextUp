import logging
import sys

def get_logger(name: str = __name__, log_file: str = None, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    
    # Prevent adding duplicate handlers if the logger is called multiple times
    if not logger.handlers:
        logger.setLevel(level)
        
        # Define a clean, readable logging format
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        # 1. Console Handler (outputs to terminal)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # 2. File Handler (optional, writes to a file)
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
    return logger