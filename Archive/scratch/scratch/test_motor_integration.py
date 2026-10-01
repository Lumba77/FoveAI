import asyncio
import os
import sys

from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(r"C:\Users\danie\program\LUMAX", ".env"))

sys.path.insert(0, r"C:\Users\danie\program\LUMAX\Backend\Cognition")
from cloud_repertoire import generate_via_slot
from compagent import _parse_motor_actions, _strip_motor_tags


async def main():
    # Force cloud mode
    os.environ["FoveAI_COGNITIVE_MODE"] = "cloud"
    os.environ["FoveAI_MODEL_STRUCTURED_OUTPUT"] = "false"

    # We will test the AI's ability to trigger motor commands.
    system_text = "You are Jen. A user has just walked into the room."
    user_text = "Please show me you can walk forward and look happy."

    print("Testing generate_via_slot with GEMINI (if configured)...")
    try:
        # Use GEMINI public slot
        result = await generate_via_slot("gemini", system_text, user_text)
        print("--- RAW RESULT ---")
        print(result)

        print("\n--- PARSING MOTOR ACTIONS ---")
        actions = _parse_motor_actions(result)
        print(f"Parsed Actions: {actions}")

        print("\n--- STRIPPED RESULT ---")
        stripped = _strip_motor_tags(result)
        print(stripped)

    except Exception as e:
        print(f"Error during test: {e}")


if __name__ == "__main__":
    asyncio.run(main())
