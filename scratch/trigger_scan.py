import os
import urllib.request

ideas_file = r"C:\Users\lumba\Program\FoveAI\Data\monetizing\ideas_data\ideas.json"

# Delete the corrupted file
if os.path.exists(ideas_file):
    print(f"Removing corrupted file: {ideas_file}")
    os.remove(ideas_file)

# Trigger scan endpoint
url = "http://localhost:8000/monetize/ideas/scan"
req = urllib.request.Request(url, method="POST")

try:
    print(f"Sending POST request to: {url}")
    with urllib.request.urlopen(req) as response:
        status = response.status
        res_data = response.read().decode("utf-8")
        print(f"Response status: {status}")
        print(f"Response data: {res_data}")
except Exception as e:
    print(f"Error calling scan endpoint: {e}")

# Verify file was regenerated
if os.path.exists(ideas_file):
    print("ideas.json successfully regenerated!")
    with open(ideas_file, "r", encoding="utf-8") as f:
        print(f.read())
else:
    print("ideas.json was NOT regenerated.")
