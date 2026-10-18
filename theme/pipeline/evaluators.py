from .models import ThemeSpec

def hex_to_rgb(hex_str: str) -> tuple:
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 3:
        hex_str = ''.join([c*2 for c in hex_str])
    if len(hex_str) != 6:
        return (0,0,0)
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def luminance(r: int, g: int, b: int) -> float:
    a = [v / 255.0 for v in (r, g, b)]
    a = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in a]
    return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722

def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = luminance(*hex_to_rgb(hex1))
    l2 = luminance(*hex_to_rgb(hex2))
    brightest = max(l1, l2)
    darkest = min(l1, l2)
    return (brightest + 0.05) / (darkest + 0.05)

class ThemeEvaluator:
    @staticmethod
    def evaluate(theme_data: dict) -> dict:
        scores = {}
        
        # 1. Contrast (WCAG AA requires 4.5:1 for normal text)
        bg = theme_data.get("fv_bg_dark", "#000000")
        text = theme_data.get("fv_text_main", "#ffffff")
        ratio = contrast_ratio(bg, text)
        scores["contrast_ratio"] = round(ratio, 2)
        scores["accessibility_score"] = min(1.0, ratio / 4.5)
        
        # 2. Completeness
        expected_keys = ["fv_accent", "fv_bg_dark", "fv_text_main", "ui_structure"]
        found = sum(1 for k in expected_keys if k in theme_data)
        scores["completeness_score"] = found / len(expected_keys)
        
        # 3. Feasibility (Check if CSS grid areas look valid)
        ui = theme_data.get("ui_structure", {})
        grid_areas = ui.get("css_grid_areas", "")
        if grid_areas and type(grid_areas) == str and len(grid_areas) > 5:
            scores["feasibility_score"] = 1.0
        else:
            scores["feasibility_score"] = 0.5
            
        canv = float(0.2126 * int(bg[1:3], 16) + 0.7152 * int(bg[3:5], 16)
                     + 0.0722 * int(bg[5:7], 16)) / 255 if bg.startswith("#") and len(bg) == 7 else 0.5
        scores["canvas_calmscore"] = 1.0 if canv < 0.45 else 0.4

        # accent identities must be distinct — the FUI lollipop needs separation
        accents = [theme_data.get("fv_accent", ""), theme_data.get("fv_accent_2", ""),
                   theme_data.get("fv_ok", ""), theme_data.get("fv_danger", "")]
        dists = [contrast_ratio(a, b) for a, b in zip(accents, accents[1:])] if len(accents) == 4 else []
        scores["identity_distinction"] = round(min(1.0, (sum(dists) / len(dists)) / 3.0), 2) if dists else 0.5

        # ── CHIEF AESTHETIAN — the satisfaction verdict ──
        # The gate that must be satisfied: nothing renders before the chief
        # signs. Access + completeness are table stakes; the chief weighs
        # calm canvas and distinct identity above cleverness.
        chief = (0.30 * scores["accessibility_score"]
                 + 0.25 * scores["canvas_calmscore"]
                 + 0.25 * scores["identity_distinction"]
                 + 0.10 * scores["completeness_score"]
                 + 0.10 * scores["feasibility_score"])
        scores["chief_aesthetian"] = round(chief, 2)
        scores["chief_satisfied"] = bool(chief >= 0.75)
        scores["overall"] = round((scores["accessibility_score"] + scores["completeness_score"] + scores["feasibility_score"]) / 3.0, 2)
        return scores
