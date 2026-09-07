"""
Lumax Album & Song Art Generator
A comprehensive workflow for musicians to generate album and song artwork.
"""

import os
import json
import base64
import io
import zipfile
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from PIL import Image, ImageEnhance
import httpx

# Data directory for storing generated art
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALBUM_ART_DIR = os.path.join(BASE_DIR, "generated_album_art")
os.makedirs(ALBUM_ART_DIR, exist_ok=True)

# ============================================
# REFERENCE DATA
# ============================================

FAMOUS_ALBUM_COVERS = [
    {
        "id": "dark_side_moon",
        "name": "Dark Side of the Moon (1973)",
        "artist": "Pink Floyd",
        "description": "Prismatic spectrum on black background",
        "prompt_keywords": "prism, light spectrum, rainbow, triangle, black background, minimalist, iconic",
        "thumbnail_color": "#1a1a1a"
    },
    {
        "id": "abbey_road",
        "name": "Abbey Road (1969)",
        "artist": "The Beatles",
        "description": "Band walking across zebra crossing",
        "prompt_keywords": "street crossing, silhouettes, urban, photograph style, iconic album cover",
        "thumbnail_color": "#4a4a4a"
    },
    {
        "id": "thriller",
        "name": "Thriller (1982)",
        "artist": "Michael Jackson",
        "description": "White suit, confident pose",
        "prompt_keywords": "white suit, confident pose, studio lighting, portrait, 80s style",
        "thumbnail_color": "#f5f5f5"
    },
    {
        "id": "nevermind",
        "name": "Nevermind (1991)",
        "artist": "Nirvana",
        "description": "Underwater baby chasing dollar bill",
        "prompt_keywords": "underwater, baby, dollar bill, swimming pool, surreal, iconic",
        "thumbnail_color": "#4a90a4"
    },
    {
        "id": "random_access",
        "name": "Random Access Memories (2013)",
        "artist": "Daft Punk",
        "description": "Wooden floor with DAFT PUNK text",
        "prompt_keywords": "wooden floor, hardwood, minimalist text, warm tones, elegant",
        "thumbnail_color": "#8b6f47"
    },
    {
        "id": "good_kid",
        "name": "Good Kid m.A.A.d City (2012)",
        "artist": "Kendrick Lamar",
        "description": "Family photo on polaroid",
        "prompt_keywords": "polaroid, family photo, vintage, suburban, nostalgic",
        "thumbnail_color": "#d4a574"
    },
    {
        "id": "blade_runner",
        "name": "Blade Runner Blues",
        "artist": "Vangelis Style",
        "description": "Neon cityscape, cyberpunk atmosphere",
        "prompt_keywords": "neon, cityscape, cyberpunk, futuristic, moody, atmospheric, synthwave",
        "thumbnail_color": "#ff6b35"
    },
    {
        "id": "discovery",
        "name": "Discovery (2001)",
        "artist": "Daft Punk",
        "description": "Anime style robot characters",
        "prompt_keywords": "anime, robot, futuristic, colorful, sci-fi, character design",
        "thumbnail_color": "#7b68ee"
    },
    {
        "id": "mt_goldie",
        "name": "MTV Unplugged in New York",
        "artist": "Nirvana",
        "description": "Black roses on table",
        "prompt_keywords": "black roses, table, moody, acoustic, intimate, dark aesthetic",
        "thumbnail_color": "#2d2d2d"
    },
    {
        "id": "after_hours",
        "name": "After Hours (2020)",
        "artist": "The Weeknd",
        "description": "Red suit, bandaged face, neon lights",
        "prompt_keywords": "red suit, bandages, neon lights, night city, dramatic, cinematic",
        "thumbnail_color": "#dc143c"
    }
]

ART_STYLES = [
    {
        "id": "photorealistic",
        "name": "Photorealistic",
        "description": "Ultra-realistic photography style",
        "prompt_additions": "photorealistic, ultra detailed, 8k, professional photography, studio lighting",
        "negative_prompt": "cartoon, illustration, painting, drawing, sketch"
    },
    {
        "id": "oil_painting",
        "name": "Oil Painting",
        "description": "Classic oil painting technique",
        "prompt_additions": "oil painting, classical art, brush strokes, textured, renaissance style",
        "negative_prompt": "photo, digital, 3d render, cartoon"
    },
    {
        "id": "cyberpunk",
        "name": "Cyberpunk",
        "description": "Futuristic neon aesthetic",
        "prompt_additions": "cyberpunk, neon lights, futuristic, high tech, dystopian, sci-fi",
        "negative_prompt": "natural, pastoral, vintage, classical"
    },
    {
        "id": "minimalist",
        "name": "Minimalist",
        "description": "Clean, simple design",
        "prompt_additions": "minimalist, clean, simple, geometric, negative space, modern design",
        "negative_prompt": "cluttered, busy, ornate, detailed, complex"
    },
    {
        "id": "art_nouveau",
        "name": "Art Nouveau",
        "description": "Elegant flowing organic forms",
        "prompt_additions": "art nouveau, flowing lines, organic forms, decorative, elegant, mucha style",
        "negative_prompt": "geometric, modern, minimalist, tech"
    },
    {
        "id": "synthwave",
        "name": "Synthwave/Retrowave",
        "description": "80s retro-futuristic aesthetic",
        "prompt_additions": "synthwave, retrowave, 80s, neon grid, sunset, palm trees, vintage futuristic",
        "negative_prompt": "modern, realistic, natural"
    },
    {
        "id": "watercolor",
        "name": "Watercolor",
        "description": "Soft watercolor painting",
        "prompt_additions": "watercolor painting, soft edges, bleeding colors, artistic, hand painted",
        "negative_prompt": "sharp, digital, photo, 3d"
    },
    {
        "id": "pop_art",
        "name": "Pop Art",
        "description": "Bold colors, comic style",
        "prompt_additions": "pop art, bold colors, warhol style, comic book, halftone, vibrant",
        "negative_prompt": "muted, realistic, subtle, natural"
    },
    {
        "id": "dark_fantasy",
        "name": "Dark Fantasy",
        "description": "Gothic, mysterious atmosphere",
        "prompt_additions": "dark fantasy, gothic, mysterious, atmospheric, dramatic lighting, epic",
        "negative_prompt": "bright, cheerful, cartoon, cute"
    },
    {
        "id": "abstract",
        "name": "Abstract Expressionism",
        "description": "Non-representational art",
        "prompt_additions": "abstract expressionism, non-representational, emotional, gestural, modern art",
        "negative_prompt": "realistic, literal, representational, clear subject"
    }
]

COLOR_PROFILES = [
    {
        "id": "neon_nights",
        "name": "Neon Nights",
        "colors": ["#ff007f", "#00f3ff", "#7b68ee"],
        "description": "Vibrant cyberpunk palette"
    },
    {
        "id": "sunset_boulevard",
        "name": "Sunset Boulevard",
        "colors": ["#ff6b35", "#f7c59f", "#2d3436"],
        "description": "Warm sunset tones"
    },
    {
        "id": "ocean_depths",
        "name": "Ocean Depths",
        "colors": ["#0077b6", "#00b4d8", "#90e0ef"],
        "description": "Cool aquatic blues"
    },
    {
        "id": "forest_myst",
        "name": "Forest Mystery",
        "colors": ["#2d5016", "#4a7c23", "#8fbc8f"],
        "description": "Natural green palette"
    },
    {
        "id": "royal_purple",
        "name": "Royal Purple",
        "colors": ["#663399", "#9966cc", "#cc99ff"],
        "description": "Regal purple tones"
    },
    {
        "id": "monochrome",
        "name": "Monochrome",
        "colors": ["#000000", "#808080", "#ffffff"],
        "description": "Classic black and white"
    },
    {
        "id": "fire_ember",
        "name": "Fire & Ember",
        "colors": ["#dc143c", "#ff4500", "#ffd700"],
        "description": "Hot fire colors"
    },
    {
        "id": "pastel_dream",
        "name": "Pastel Dream",
        "colors": ["#ffb3ba", "#bae1ff", "#baffc9"],
        "description": "Soft pastel tones"
    },
    {
        "id": "earth_tones",
        "name": "Earth Tones",
        "colors": ["#8b4513", "#d2691e", "#deb887"],
        "description": "Natural earth colors"
    },
    {
        "id": "electric_lime",
        "name": "Electric Lime",
        "colors": ["#39ff14", "#adff2f", "#006400"],
        "description": "Vibrant green energy"
    }
]

# ControlNet style influence presets
CONTROLNET_PRESETS = [
    {"id": "subtle", "name": "Subtle (0.3)", "strength": 0.3},
    {"id": "balanced", "name": "Balanced (0.5)", "strength": 0.5},
    {"id": "strong", "name": "Strong (0.7)", "strength": 0.7},
    {"id": "dominant", "name": "Dominant (0.9)", "strength": 0.9},
]


def get_famous_albums() -> List[Dict]:
    """Return list of famous album covers for reference."""
    return FAMOUS_ALBUM_COVERS


def get_art_styles() -> List[Dict]:
    """Return list of art styles."""
    return ART_STYLES


def get_color_profiles() -> List[Dict]:
    """Return list of color profiles."""
    return COLOR_PROFILES


def get_controlnet_presets() -> List[Dict]:
    """Return ControlNet strength presets."""
    return CONTROLNET_PRESETS


def build_album_art_prompt(
    band_name: str,
    album_title: str,
    song_contexts: List[Dict[str, str]],
    reference_album: Optional[Dict] = None,
    art_style: Optional[Dict] = None,
    color_profile: Optional[Dict] = None,
    custom_colors: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """
    Build a detailed prompt for album art generation.
    Returns (prompt, negative_prompt) tuple.
    """
    # Base prompt structure
    prompt_parts = []
    negative_parts = ["ugly, deformed, noisy, blurry, distorted, text, watermark"]
    
    # Add band and album context
    if band_name:
        prompt_parts.append(f"Album cover for band '{band_name}'")
    if album_title:
        prompt_parts.append(f"album titled '{album_title}'")
    
    # Add song contexts as thematic elements
    if song_contexts:
        song_themes = []
        for song in song_contexts:
            if song.get("description"):
                song_themes.append(song["description"])
        if song_themes:
            prompt_parts.append(f"thematic elements: {', '.join(song_themes[:3])}")
    
    # Add reference album style
    if reference_album:
        prompt_parts.append(f"inspired by: {reference_album.get('prompt_keywords', '')}")
    
    # Add art style
    if art_style:
        prompt_parts.append(art_style.get("prompt_additions", ""))
        if art_style.get("negative_prompt"):
            negative_parts.append(art_style["negative_prompt"])
    
    # Add color guidance
    if custom_colors:
        color_str = ", ".join(custom_colors)
        prompt_parts.append(f"color palette: {color_str}")
    elif color_profile:
        color_str = ", ".join(color_profile["colors"])
        prompt_parts.append(f"color palette: {color_str}")
    
    # Always add album cover specific guidance
    prompt_parts.append("professional album cover design, square format, high quality, artistic")
    
    prompt = ", ".join(filter(None, prompt_parts))
    negative_prompt = ", ".join(filter(None, negative_parts))
    
    return prompt, negative_prompt


def build_song_art_prompt(
    band_name: str,
    album_title: str,
    song_title: str,
    song_description: str,
    album_art_style: Dict,
    color_profile: Optional[Dict] = None,
    custom_colors: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """
    Build a detailed prompt for individual song art generation.
    Should be consistent with album art style.
    """
    prompt_parts = []
    negative_parts = ["ugly, deformed, noisy, blurry, distorted, text, watermark"]
    
    # Base context
    prompt_parts.append(f"Single cover art for song '{song_title}'")
    if band_name:
        prompt_parts.append(f"by '{band_name}'")
    if album_title:
        prompt_parts.append(f"from album '{album_title}'")
    
    # Song-specific theme
    if song_description:
        prompt_parts.append(f"theme: {song_description}")
    
    # Maintain style consistency with album
    if album_art_style:
        prompt_parts.append(album_art_style.get("prompt_additions", ""))
        if album_art_style.get("negative_prompt"):
            negative_parts.append(album_art_style["negative_prompt"])
    
    # Color guidance
    if custom_colors:
        color_str = ", ".join(custom_colors)
        prompt_parts.append(f"color palette: {color_str}")
    elif color_profile:
        color_str = ", ".join(color_profile["colors"])
        prompt_parts.append(f"color palette: {color_str}")
    
    prompt_parts.append("professional single cover design, square format, high quality, artistic, consistent with album art style")
    
    prompt = ", ".join(filter(None, prompt_parts))
    negative_prompt = ", ".join(filter(None, negative_parts))
    
    return prompt, negative_prompt


def save_generation_session(
    session_id: str,
    project_data: Dict,
    generated_images: Dict[str, str]
) -> str:
    """
    Save a generation session to disk.
    Returns the path to the saved session.
    """
    session_dir = os.path.join(ALBUM_ART_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    
    # Save project metadata
    metadata_path = os.path.join(session_dir, "project.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(project_data, f, indent=2, ensure_ascii=False)
    
    # Save generated images
    for image_name, base64_data in generated_images.items():
        if base64_data:
            # Decode and save image
            image_data = base64.b64decode(base64_data)
            image_path = os.path.join(session_dir, f"{image_name}.png")
            with open(image_path, "wb") as f:
                f.write(image_data)
    
    return session_dir


def create_zip_download(
    session_id: str,
    images: Dict[str, bytes],
    upscale_factor: int = 1
) -> Tuple[bytes, str]:
    """
    Create a zip file containing all generated images.
    Returns (zip_bytes, filename).
    """
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add project metadata
        metadata_path = os.path.join(ALBUM_ART_DIR, session_id, "project.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as f:
                zf.writestr("project_metadata.json", f.read())
        
        # Add images
        for image_name, image_data in images.items():
            suffix = "_upscaled" if upscale_factor > 1 else ""
            zf.writestr(f"{image_name}{suffix}.png", image_data)
    
    zip_buffer.seek(0)
    filename = f"album_art_{session_id}" + ("_upscaled" if upscale_factor > 1 else "") + ".zip"
    
    return zip_buffer.getvalue(), filename


def upscale_image_pil(
    image: Image.Image,
    factor: int = 4,
    method: str = "lanczos"
) -> Image.Image:
    """
    Upscale an image using PIL.
    """
    if method == "lanczos":
        resample = Image.LANCZOS
    elif method == "bicubic":
        resample = Image.BICUBIC
    else:
        resample = Image.BILINEAR
    
    new_width = image.width * factor
    new_height = image.height * factor
    
    return image.resize((new_width, new_height), resample=resample)


def enhance_image_colors(
    image: Image.Image,
    contrast: float = 1.1,
    saturation: float = 1.1,
    sharpness: float = 1.2
) -> Image.Image:
    """
    Enhance image colors for better visual impact.
    """
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(contrast)
    
    # Enhance color/saturation
    enhancer = ImageEnhance.Color(image)
    image = enhancer.enhance(saturation)
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(sharpness)
    
    return image