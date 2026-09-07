from bs4 import BeautifulSoup
import os

path = r"C:\Users\lumba\.gemini\antigravity-cli\brain\7d891572-6aa5-41cd-bee1-d131a09fe632\.system_generated\steps\3230\content.md"

if not os.path.exists(path):
    print("File not found")
else:
    with open(path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Try finding the article tag or readme ID
    readme = soup.find('article') or soup.find(id='readme')
    if readme:
        print(readme.get_text()[:4000]) # Print first 4000 chars of readme
    else:
        # Fallback to general text
        text = soup.get_text()
        print("Fallback:")
        print("\n".join([line.strip() for line in text.split('\n') if line.strip()][:100]))
