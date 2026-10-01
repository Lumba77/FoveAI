import os
import subprocess
import sys

from dotenv import load_dotenv
from google import genai

FoveAI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
load_dotenv(os.path.join(FoveAI_ROOT, ".env"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    print("\033[91m[LUDO ERROR]\033[0m GEMINI_API_KEY not found in .env")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

SYS_PROMPT = """You are LUDO, a Smart Sudo CLI tool for Windows.
Your job is to translate a user's natural language request into a valid Windows PowerShell script that accomplishes the task.
You must return ONLY the raw PowerShell code. Do not include markdown formatting (like `powershell or `).
Do not include any explanations. Only the executable code.
Ensure the code is safe, robust, and handles errors gracefully where possible."""


def generate_script(prompt, error_context=None):
    if error_context:
        full_prompt = f"The previous script failed with the following error:\n{error_context}\n\nPlease provide an updated PowerShell script to fix this and accomplish: {prompt}"
    else:
        full_prompt = prompt

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=full_prompt,
            config={"system_instruction": SYS_PROMPT},
        )
        script = response.text.strip()
        # Clean up accidental markdown if the model hallucinates it
        if script.startswith("`powershell"):
            script = script[13:]
        if script.startswith("`ps1"):
            script = script[6:]
        if script.startswith("`"):
            script = script[3:]
        if script.endswith("`"):
            script = script[:-3]
        return script.strip()
    except Exception as e:
        print(f"\033[91m[LUDO ERROR]\033[0m Failed to contact AI: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: ludo <natural language command>")
        sys.exit(1)

    user_prompt = " ".join(sys.argv[1:])
    print(f"\033[94m[LUDO]\033[0m Thinking: '{user_prompt}'...")

    error_context = None
    attempts = 0
    max_attempts = 3

    while attempts < max_attempts:
        script = generate_script(user_prompt, error_context)
        if not script:
            sys.exit(1)

        print("\n\033[93m================ Proposed Script ================\033[0m")
        print(script)
        print("\033[93m=================================================\033[0m\n")

        choice = (
            input("\033[92m[?]\033[0m Execute this script? [Y/n]: ").strip().lower()
        )
        if choice not in ["", "y", "yes"]:
            print("\033[91m[LUDO]\033[0m Aborted.")
            sys.exit(0)

        print("\033[94m[LUDO]\033[0m Executing...\n")

        # Execute the script via powershell
        process = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stdout, stderr = process.communicate()

        if stdout:
            print(stdout)

        if process.returncode != 0:
            print(
                f"\033[91m[LUDO]\033[0m Execution Failed (Exit Code: {process.returncode})"
            )
            if stderr:
                print(f"\033[91mError Output:\033[0m\n{stderr}")

            retry_choice = (
                input(
                    "\033[92m[?]\033[0m Ask LUDO to fix this error and retry? [Y/n]: "
                )
                .strip()
                .lower()
            )
            if retry_choice in ["", "y", "yes"]:
                error_context = stderr
                attempts += 1
                continue
            else:
                sys.exit(process.returncode)
        else:
            print("\033[92m[LUDO]\033[0m Success!")
            break

    if attempts >= max_attempts:
        print("\033[91m[LUDO]\033[0m Max retry attempts reached. Giving up.")


if __name__ == "__main__":
    main()
