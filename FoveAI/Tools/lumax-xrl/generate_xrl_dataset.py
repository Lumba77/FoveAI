import json
import os
import random

# Sample simulated repository data to generate synthetic examples
FILES = {
    "Backend/Cognition/soul_core.py": [
        {"name": "initialize_soul", "desc": "Initializes the Sovereign Core"},
        {"name": "process_user_query", "desc": "Processes incoming chat messages"},
        {"name": "evaluate_safety", "desc": "Checks if the query is safe"},
    ],
    "Frontend/3D_Avatar_Chatbot/main.js": [
        {"name": "renderAvatar", "desc": "Renders the WebGL avatar"},
        {"name": "updateLipSync", "desc": "Updates mouth shapes based on audio"},
        {"name": "triggerAnimation", "desc": "Plays an animation state"},
    ],
    "sleipnir_launcher.js": [
        {"name": "purgeZombies", "desc": "Kills orphaned processes holding ports"},
        {"name": "SwarmWorkerNode", "desc": "Class representing a microservice"},
        {"name": "deploy", "desc": "Starts a worker node"},
    ],
}

# Queries that correspond to needing specific functions
QUERIES = [
    ("How does the system kill old ports?", "sleipnir_launcher.js", "purgeZombies"),
    (
        "I need to see the logic for updating the mouth movements.",
        "Frontend/3D_Avatar_Chatbot/main.js",
        "updateLipSync",
    ),
    (
        "What happens when a user query comes in?",
        "Backend/Cognition/soul_core.py",
        "process_user_query",
    ),
    ("Show me how the worker nodes are deployed.", "sleipnir_launcher.js", "deploy"),
    (
        "Check the avatar rendering code.",
        "Frontend/3D_Avatar_Chatbot/main.js",
        "renderAvatar",
    ),
]


def generate_mock_skeleton(filepath):
    lines = [f"// File: {filepath}"]
    uris = []
    line_num = 10
    for sym in FILES[filepath]:
        hash_val = f"{random.randint(0, 0xFFFFFF):06x}"
        uri = f"xrl://foveai/{filepath}:{line_num}:{hash_val}"
        uris.append({"uri": uri, "name": sym["name"]})
        lines.append(f"/* NODE:{uri} */")
        if filepath.endswith(".py"):
            lines.append(f"def {sym['name']}(*args, **kwargs): ...")
        else:
            lines.append(f"function {sym['name']}() {{ ... }}")
        line_num += 15
    return "\n".join(lines), uris


def generate_dataset(num_samples=100):
    dataset = []

    for _ in range(num_samples):
        query_text, target_file, target_func = random.choice(QUERIES)

        skeleton, uris = generate_mock_skeleton(target_file)

        # Find the correct URI
        target_uri = next(u["uri"] for u in uris if u["name"] == target_func)

        # Add some random noise or other files to the skeleton to make it realistic
        other_file = random.choice([f for f in FILES if f != target_file])
        other_skeleton, _ = generate_mock_skeleton(other_file)

        full_skeleton = f"{skeleton}\n\n{other_skeleton}"

        system_prompt = "You are an autonomous XRL Context Fetcher. Given a codebase skeleton and a user request, identify which XRL URIs need to be expanded to provide the necessary 'flesh' (context). Output ONLY the XRL URIs, one per line."
        user_prompt = f"User Request: {query_text}\n\nCode Skeletons:\n{full_skeleton}"
        assistant_reply = target_uri

        dataset.append(
            {
                "conversations": [
                    {"from": "system", "value": system_prompt},
                    {"from": "user", "value": user_prompt},
                    {"from": "assistant", "value": assistant_reply},
                ]
            }
        )

    return dataset


if __name__ == "__main__":
    out_dir = "Tools/foveai-xrl"
    os.makedirs(out_dir, exist_ok=True)

    data = generate_dataset(500)
    out_file = os.path.join(out_dir, "xrl_prefetch_dataset.jsonl")

    with open(out_file, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(item) + "\n" for item in data)

    print(f"Generated {len(data)} synthetic samples at {out_file}")
