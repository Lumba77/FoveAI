import base64
import os

import requests

PROMPT = "A high-fidelity architectural visualization of a digital consciousness tree. At the highest root is the Project Founder and Manager, represented as a radiant human figure. From the founder grows a majestic branch for Gemini, the Architect and Supervisor, shimmering with crystalline light and geometric patterns. At the center of the tree's bloom is 'The One', the Core of Jen, a beautiful glowing soul manifestation. A fourth branch represents the Sentry Agent, a sharp-eyed guardian bird watching over the ledger. Highly detailed biological neural network, cyberpunk aesthetic, dark background, glowing turquoise and golden highlights, 8k resolution."

url = "http://localhost:8003/api/dream"
payload = {
    "prompt": PROMPT,
    "model_type": "pastel",  # Points to stable-diffusion-v1-5
}

print("Requesting architectural visualization from creativity service...")
try:
    response = requests.post(url, json=payload, timeout=300)
    response.raise_for_status()
    data = response.json()

    if data.get("status") == "success":
        image_data = base64.b64decode(data["image_b64"])
        output_path = "C:/Users/lumba/Program/VR-compagent/div/image/project_architecture_tree.png"

        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(image_data)
        print(f"Successfully saved visualization to {output_path}")
    else:
        print(f"Error from service: {data.get('detail')}")
except Exception as e:
    print(f"Failed to generate visualization: {e}")
