import os
import sys
import logging
from typing import Dict, Any, List
import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SpatialDrafter")

app = FastAPI(title="FoveAI Spatial Machines Drafter", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SpatialComponent:
    def __init__(self, ctype: str):
        self.type = ctype
        self.attributes: Dict[str, Any] = {}
        self.children: List['SpatialComponent'] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "attributes": self.attributes,
            "children": [c.to_dict() for c in self.children]
        }

def _clean_text(text: str) -> str:
    return " ".join(text.split())

def dom_to_spatial(node, depth: int = 0) -> SpatialComponent:
    """Recursively converts a BeautifulSoup DOM node into a Spatial Component tree."""
    if depth > 15:
        return SpatialComponent("Null")  # Prevent infinite recursion or insane depths
        
    if node.name is None:
        # It's a text node
        text = _clean_text(str(node))
        if text:
            comp = SpatialComponent("Text")
            comp.attributes["content"] = text
            return comp
        return SpatialComponent("Null")

    # Skip invisible elements
    if node.name in ["script", "style", "meta", "link", "head", "noscript", "svg", "path"]:
        return SpatialComponent("Null")

    comp = SpatialComponent("Block")
    
    if node.name in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        comp.attributes["isHeader"] = True
        comp.attributes["level"] = int(node.name[1])
    
    if node.name == "a":
        comp.attributes["isLink"] = True
        comp.attributes["href"] = node.get("href", "")
        
    if node.name == "button":
        comp.attributes["isButton"] = True

    if node.name == "img":
        comp.type = "Image"
        comp.attributes["src"] = node.get("src", "")
        comp.attributes["alt"] = node.get("alt", "")
        
    # Process children
    for child in node.children:
        child_comp = dom_to_spatial(child, depth + 1)
        if child_comp.type != "Null":
            comp.children.append(child_comp)
            
    # Flatten Blocks that only contain a single Text child into just a Text node (optimization)
    if comp.type == "Block" and len(comp.children) == 1 and comp.children[0].type == "Text":
        # Keep the link/button wrappers though
        if not comp.attributes.get("isLink") and not comp.attributes.get("isButton"):
            return comp.children[0]

    return comp

@app.get("/health")
async def health():
    return {"status": "ok", "service": "SPATIAL_MACHINES"}

@app.post("/spatial/transpile")
async def transpile_url(payload: dict):
    url = payload.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url' parameter")
        
    logger.info(f"Transpiling URL: {url}")
    
    try:
        # Use httpx to fetch the HTML
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            # Mask as a standard browser to avoid basic blocks
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html_content = response.text
            
    except Exception as e:
        logger.error(f"Failed to fetch URL: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch URL: {str(e)}")
        
    # Parse with BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Try to find the main content body, fallback to full body
    main_node = soup.find("main") or soup.find("article") or soup.find("body")
    
    if not main_node:
        raise HTTPException(status_code=500, detail="Could not find a body tag to parse.")
        
    # Transpile the DOM
    spatial_root = dom_to_spatial(main_node)
    
    return {
        "url": url,
        "title": soup.title.string if soup.title else url,
        "spatial_tree": spatial_root.to_dict()
    }

if __name__ == "__main__":
    port = int(os.getenv("FoveAI_SPATIAL_PORT", "8010"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
