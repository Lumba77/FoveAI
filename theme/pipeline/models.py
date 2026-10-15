from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any

class UIStructure(BaseModel):
    menu_position: str
    glass_opacity: float = Field(ge=0, le=1)
    shadow_intensity: str
    animation_style: str
    css_grid_template_columns: Optional[str] = None
    css_grid_template_rows: Optional[str] = None
    css_grid_areas: Optional[str] = None

class ThemeSpec(BaseModel):
    schema_version: str = "1.0"
    theme_name: str
    fv_bg_dark: str
    fv_bg_panel: Optional[str] = None
    fv_text_main: str
    fv_text_muted: Optional[str] = None
    fv_accent: str
    fv_accent_2: Optional[str] = None
    fv_warn: Optional[str] = None
    fv_danger: Optional[str] = None
    fv_ok: Optional[str] = None
    ui_structure: UIStructure
    background_prompt: Optional[str] = None
    background_image_url: Optional[str] = None
    audio_assets: Optional[dict] = None
    functional_aspects: Optional[str] = None
    aesthetic_plan: Optional[dict] = None
    requested_assets: Optional[List[dict]] = None
    scores: Optional[dict] = None
    
    # Internal fields for provenance
    _vlm_text: Optional[str] = None
    _visionary_text: Optional[str] = None
    _critic_text: Optional[str] = None
