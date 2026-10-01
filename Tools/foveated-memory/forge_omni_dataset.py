import json


def generate_harness_dataset():
    dataset = []

    # 1. Swedish to English JSON Extraction Tasks
    swedish_examples = [
        {
            "user": "Jag älskar att använda React men jag hatar TailwindCSS. Snälla använd alltid Vanilla CSS.",
            "assistant": '{\n  "facts": [],\n  "rules": ["Always use Vanilla CSS", "Do not use TailwindCSS"],\n  "preferences": ["Loves React", "Hates TailwindCSS"]\n}',
        },
        {
            "user": "Förresten, se till att koden alltid är asynkron. Och jag vill inte ha några kommentarer i koden.",
            "assistant": '{\n  "facts": [],\n  "rules": ["Code must always be asynchronous", "Do not include comments in code"],\n  "preferences": []\n}',
        },
        {
            "user": "Jag bygger mest för VR-headset så prestanda är kritiskt. Använd inte tunga bibliotek.",
            "assistant": '{\n  "facts": ["Builds mostly for VR headsets"],\n  "rules": ["Performance is critical", "Do not use heavy libraries"],\n  "preferences": []\n}',
        },
    ]

    for ex in swedish_examples:
        dataset.append(
            {
                "conversations": [
                    {
                        "from": "system",
                        "value": "You are a strict data extractor. You must output a raw JSON object and nothing else. DO NOT output conversational text. DO NOT output markdown. Your response MUST begin with { and end with }.",
                    },
                    {
                        "from": "user",
                        "value": 'You are the LUMAX Cognitive Harness. Your job is to observe the following conversation and extract permanent facts, rules, or preferences about the user and the codebase.\nCRITICAL RULES:\n1. Output ONLY a raw JSON object with this exact structure: {"facts": ["...", "..."], "rules": ["...", "..."], "preferences": ["...", "..."]}\n2. If the user is speaking Swedish (or any non-English language), you MUST translate the extracted facts into English. The entire JSON output must be in English to ensure global context uniformity.\n\nConversation Log:\nUser: '
                        + ex["user"],
                    },
                    {"from": "assistant", "value": ex["assistant"]},
                ]
            }
        )

    # 2. Omni-Routing Tasks
    routing_examples = [
        {
            "user": "Rewrite this entire 2000 line backend file.",
            "assistant": "[ROUTE: CLOUD] (Reason: Heavy coding task requires massive context window)",
        },
        {
            "user": "What time is it?",
            "assistant": "[ROUTE: LOCAL] (Reason: Simple conversational query)",
        },
        {
            "user": "Fix the NavMesh bug in Unity.",
            "assistant": "[ROUTE: LOCAL] [FETCH: HttpMcpServer.cs] [FETCH: NavMesh]",
        },
    ]

    for ex in routing_examples:
        dataset.append(
            {
                "conversations": [
                    {
                        "from": "system",
                        "value": "You are the Lumax Plumax Omni Router. Determine the routing intent and necessary context fetches.",
                    },
                    {"from": "user", "value": ex["user"]},
                    {"from": "assistant", "value": ex["assistant"]},
                ]
            }
        )

    # Output to Unsloth format
    with open("omni_unsloth_dataset.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print(f"Forged {len(dataset)} instruction pairs for Lumax Plumax Super Turbo Omni.")
    print("Dataset saved to omni_unsloth_dataset.json ready for Unsloth.")


if __name__ == "__main__":
    generate_harness_dataset()
