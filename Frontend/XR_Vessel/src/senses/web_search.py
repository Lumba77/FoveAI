"""Web Search Service - Backend for WebSearch.ts. Port: 8005"""

import logging
import os
from datetime import datetime
from typing import List, Literal, Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Configuration
SERVICE_NAME = "web_search"
SERVICE_PORT = 8005
SERVICE_VERSION = "1.0.0"

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "web_search.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("web_search")

# Rate limiting
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 30
request_history: dict[str, list[float]] = {}

# FastAPI App
app = FastAPI(
    title="Web Search Service",
    description="Co-Coder web search backend for FoveAI XR Vessel",
    version=SERVICE_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Models
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    engine: Literal["google", "bing", "duckduckgo"] = "duckduckgo"
    max_results: int = Field(default=10, ge=1, le=20)


class SearchResultItem(BaseModel):
    title: str
    url: str
    snippet: str
    source: str


class SearchResponse(BaseModel):
    success: bool
    query: str
    engine: str
    results: List[SearchResultItem]
    result_count: int
    timestamp: str
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    port: int
    timestamp: str


# Rate limiter
async def check_rate_limit(client_ip: str) -> bool:
    now = datetime.utcnow().timestamp()
    window_start = now - RATE_LIMIT_WINDOW
    if client_ip in request_history:
        request_history[client_ip] = [t for t in request_history[client_ip] if t > window_start]
    else:
        request_history[client_ip] = []
    if len(request_history.get(client_ip, [])) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    request_history[client_ip].append(now)
    return True


class SearchEngineError(Exception):
    pass


# Search implementations
async def search_duckduckgo(query: str, max_results: int) -> List[SearchResultItem]:
    try:
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.5",
        }
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.post(url, data={"q": query, "kl": "us-en"}, headers=headers)
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            for result in soup.select(".result")[:max_results]:
                title_elem = result.select_one(".result__title a")
                snippet_elem = result.select_one(".result__snippet")
                if title_elem:
                    href = title_elem.get("href", "")
                    if href.startswith("//"):
                        href = "https:" + href
                    elif href.startswith("/"):
                        continue
                    results.append(SearchResultItem(
                        title=title_elem.get_text(strip=True),
                        url=href,
                        snippet=snippet_elem.get_text(strip=True)[:300] if snippet_elem else "",
                        source="duckduckgo"
                    ))
            return results
    except Exception as e:
        logger.error(f"DuckDuckGo error: {e}")
        raise SearchEngineError(f"DuckDuckGo failed: {str(e)}")


async def search_bing(query: str, max_results: int) -> List[SearchResultItem]:
    try:
        url = "https://www.bing.com/search"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, params={"q": query, "count": max_results}, headers=headers)
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            for result in soup.select(".b_algo")[:max_results]:
                title_elem = result.select_one("h2 a")
                snippet_elem = result.select_one(".b_caption p")
                if title_elem:
                    results.append(SearchResultItem(
                        title=title_elem.get_text(strip=True),
                        url=title_elem.get("href", ""),
                        snippet=snippet_elem.get_text(strip=True)[:300] if snippet_elem else "",
                        source="bing"
                    ))
            return results
    except Exception as e:
        logger.error(f"Bing error: {e}")
        raise SearchEngineError(f"Bing failed: {str(e)}")


async def search_google(query: str, max_results: int) -> List[SearchResultItem]:
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    cx = os.getenv("GOOGLE_SEARCH_CX")
    if api_key and cx:
        return await _search_google_api(query, max_results, api_key, cx)
    return await _search_google_scrape(query, max_results)


async def _search_google_api(query: str, max_results: int, api_key: str, cx: str) -> List[SearchResultItem]:
    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {"key": api_key, "cx": cx, "q": query, "num": min(max_results, 10)}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)
            data = response.json()
            results = []
            for item in data.get("items", []):
                results.append(SearchResultItem(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    source="google"
                ))
            return results
    except Exception as e:
        logger.warning(f"Google API failed, falling back: {e}")
        return await _search_google_scrape(query, max_results)


async def _search_google_scrape(query: str, max_results: int) -> List[SearchResultItem]:
    try:
        url = "https://www.google.com/search"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, params={"q": query, "num": max_results}, headers=headers)
            soup = BeautifulSoup(response.text, "html.parser")
            results = []
            for result in soup.select(".g")[:max_results]:
                title_elem = result.select_one("h3")
                link_elem = result.select_one("a")
                snippet_elem = result.select_one(".VwiC3b, .s3v94d")
                if title_elem and link_elem:
                    href = link_elem.get("href", "")
                    if href.startswith("/url?q="):
                        href = href.split("/url?q=")[1].split("&amp;")[0]
                    results.append(SearchResultItem(
                        title=title_elem.get_text(strip=True),
                        url=href,
                        snippet=snippet_elem.get_text(strip=True)[:300] if snippet_elem else "",
                        source="google"
                    ))
            return results
    except Exception as e:
        logger.error(f"Google scrape error: {e}")
        raise SearchEngineError(f"Google failed: {str(e)}")


SEARCH_ENGINES = {
    "duckduckgo": search_duckduckgo,
    "bing": search_bing,
    "google": search_google,
}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    if request.url.path == "/health":
        return await call_next(request)
    if not await check_rate_limit(client_ip):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"success": False, "error": "Rate limit exceeded", "retry_after": RATE_LIMIT_WINDOW}
        )
    return await call_next(request)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        port=SERVICE_PORT,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.post("/search", response_model=SearchResponse)
async def search_web(request: SearchRequest, http_request: Request):
    client_ip = http_request.client.host if http_request.client else "unknown"
    logger.info(f"Search from {client_ip}: engine={request.engine}, query={request.query[:50]}...")
    
    try:
        search_func = SEARCH_ENGINES.get(request.engine)
        if not search_func:
            raise HTTPException(status_code=400, detail=f"Unknown engine: {request.engine}")
        
        results = await search_func(request.query, request.max_results)
        logger.info(f"Search completed: {len(results)} results")
        
        return SearchResponse(
            success=True,
            query=request.query,
            engine=request.engine,
            results=results,
            result_count=len(results),
            timestamp=datetime.utcnow().isoformat(),
        )
    except SearchEngineError as e:
        logger.error(f"Search engine error: {e}")
        return SearchResponse(
            success=False,
            query=request.query,
            engine=request.engine,
            results=[],
            result_count=0,
            timestamp=datetime.utcnow().isoformat(),
            error=str(e),
        )
    except Exception as e:
        logger.exception("Unexpected error")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/engines")
async def list_engines():
    return {
        "engines": [
            {"id": "duckduckgo", "name": "DuckDuckGo", "requires_api_key": False},
            {"id": "bing", "name": "Bing", "requires_api_key": False},
            {"id": "google", "name": "Google", "requires_api_key": bool(os.getenv("GOOGLE_SEARCH_API_KEY"))},
        ]
    }


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting {SERVICE_NAME} on port {SERVICE_PORT}")
    uvicorn.run("web_search:app", host="0.0.0.0", port=SERVICE_PORT, log_level="info")
