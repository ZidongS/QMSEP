import time
from datetime import datetime

class Timer:
    """Simple timer class for tracking elapsed time"""
    
    def __init__(self):
        self.start_time = time.time()
    
    def elapsed(self) -> float:
        """Return elapsed time in seconds"""
        return time.time() - self.start_time
    
    def reset(self):
        """Reset the timer"""
        self.start_time = time.time()
    
    def format_elapsed(self) -> str:
        """Return formatted elapsed time"""
        elapsed = self.elapsed()
        if elapsed < 60:
            return f"{elapsed:.1f}s"
        elif elapsed < 3600:
            return f"{elapsed/60:.1f}m"
        else:
            return f"{elapsed/3600:.1f}h"