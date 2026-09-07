import urllib.request
import urllib.parse
import re

def ddg_search(query: str) -> str:
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
        
        snippets = re.findall(r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
        titles = re.findall(r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
        
        out = []
        for i, (title, snippet) in enumerate(zip(titles[:5], snippets[:5])):
            clean_title = re.sub(r'<[^>]*>', '', title).strip()
            clean_snippet = re.sub(r'<[^>]*>', '', snippet).strip()
            out.append(f"{i+1}. {clean_title}\n   {clean_snippet}")
            
        if not out:
            return "No web results found."
        return "\n\n".join(out)
    except Exception as e:
        return f"Error executing web search: {e}"

print(ddg_search("FoveAI AI companion"))
