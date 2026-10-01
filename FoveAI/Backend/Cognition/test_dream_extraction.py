import re


# Mocking MindCore for test
class MindCoreMock:
    @staticmethod
    def clean_response(raw_text: str, disable_think: bool = False) -> dict:
        # Extract Agentic XML structures
        thought_match = re.search(r"<thought>(.*?)<\/thought>", raw_text, re.DOTALL)
        thought = thought_match.group(1).strip() if thought_match else ""

        # Extract DREAM tags for image generation
        dream_match = re.search(r"\[DREAM\](.*?)\[/DREAM\]", raw_text, re.DOTALL)
        dream = dream_match.group(1).strip() if dream_match else ""

        clean_text = re.sub(
            r"<(thought|tool_call)>.*?<\/\1>", "", raw_text, flags=re.DOTALL
        )
        clean_text = re.sub(
            r"\[DREAM\].*?\[/DREAM\]", "", clean_text, flags=re.DOTALL
        ).strip()

        if disable_think:
            clean_text = re.sub(
                r"<thought>.*?</thought>", "", clean_text, flags=re.DOTALL
            )

        return {"text": clean_text, "thought": thought, "dream": dream}


def test_dream_extraction():
    test_text = "I am thinking about a city. <thought>I should show them a city.</thought> [DREAM] A neon cyberpunk city at night [/DREAM] Here is what I see."
    result = MindCoreMock.clean_response(test_text)

    print(f"Clean Text: {result['text']}")
    print(f"Thought: {result['thought']}")
    print(f"Dream Prompt: {result['dream']}")

    assert result["dream"] == "A neon cyberpunk city at night"
    assert "DREAM" not in result["text"]
    assert "thought" not in result["text"]
    print("Test Passed: Dream extraction is working correctly.")


if __name__ == "__main__":
    test_dream_extraction()
