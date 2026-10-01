import json
import os
import random


def generate_random_function_name():
    verbs = [
        "get",
        "set",
        "update",
        "delete",
        "create",
        "fetch",
        "parse",
        "render",
        "initialize",
        "destroy",
    ]
    nouns = [
        "User",
        "Config",
        "Database",
        "Session",
        "Request",
        "Response",
        "Token",
        "Cache",
        "UI",
        "Profile",
    ]
    return f"{random.choice(verbs)}{random.choice(nouns)}"


def generate_random_class_name():
    adjectives = [
        "Base",
        "Abstract",
        "Default",
        "Async",
        "Sync",
        "Global",
        "Local",
        "Remote",
    ]
    nouns = [
        "Manager",
        "Service",
        "Controller",
        "Handler",
        "Provider",
        "Adapter",
        "Factory",
    ]
    return f"{random.choice(adjectives)}{random.choice(nouns)}"


def generate_code_block(num_functions, num_classes):
    code = ""
    entities = []

    for _ in range(num_classes):
        cls_name = generate_random_class_name()
        entities.append(cls_name)
        code += f"class {cls_name} {{\n    constructor() {{}}\n    init() {{}}\n}}\n\n"

    for _ in range(num_functions):
        func_name = generate_random_function_name()
        entities.append(func_name)
        code += f"function {func_name}(data) {{\n    // boilerplate\n    return data;\n}}\n\n"

    return code, entities


def generate_dataset(num_samples, output_file):
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    system_prompt = "You are a highly efficient Context Router. The user is about to provide a massive code dump and a request. Your job is to extract ONLY the exact functions, classes, or code snippets that are absolutely critical to solving the user's request. Discard all irrelevant boilerplate. Be concise. Do not explain your reasoning."

    with open(output_file, "w", encoding="utf-8") as f:
        for _ in range(num_samples):
            code, entities = generate_code_block(
                random.randint(5, 15), random.randint(1, 5)
            )

            # Pick 1 to 3 targets
            num_targets = random.randint(1, min(3, len(entities)))
            targets = random.sample(entities, num_targets)

            # Create a fake user request
            requests = [
                f"Fix the bug in {targets[0]}",
                f"Update the logic for {targets[0]} and {targets[-1]}",
                f"I'm getting a timeout error when calling {targets[0]}.",
                f"Can you optimize {targets[0]}?",
                f"Refactor {', '.join(targets)} to use async/await.",
            ]

            user_content = f"Here is the massive context:\n\n{code}\n\n--- END CONTEXT ---\n\n{random.choice(requests)}"
            assistant_content = ", ".join(targets)

            sample = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_content},
                ]
            }
            f.write(json.dumps(sample) + "\n")


if __name__ == "__main__":
    output_path = os.path.join("datasets", "smart-router-v1.jsonl")
    print(f"Generating 5000 synthetic routing samples to {output_path}...")
    generate_dataset(5000, output_path)
    print("Done!")
