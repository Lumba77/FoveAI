import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
    THEME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    GALLERY_DIR = os.path.join(THEME_DIR, "gallery")
