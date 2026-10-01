import os
import shutil
import tkinter as tk
from tkinter import simpledialog

import keyring
import psutil
import pyzipper

FoveAI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_PATH = os.path.join(FoveAI_ROOT, ".env")
SOUL_JSON_PATH = os.path.join(FoveAI_ROOT, "Backend", "Cognition", "jen_soul.json")
EGG_NAME = "Lumax_Dormant_Egg.zip"


def get_or_prompt_zip_password():
    # 1. Try to fetch from Windows Credential Manager
    pwd = keyring.get_password("Lumax", "DormantEggPassword")
    if pwd:
        return pwd

    # 2. Prompt user using Tkinter if missing
    print("[DormantEgg] No ZIP password found. Prompting user...")
    root = tk.Tk()
    root.withdraw()  # Hide main window

    pwd = simpledialog.askstring(
        "Lumax Dormant Egg",
        "Enter a master password to protect your AES Backup ZIP.\nThis password will be saved in Windows Credential Manager.",
        show="*",
    )
    root.destroy()

    if pwd:
        try:
            keyring.set_password("Lumax", "DormantEggPassword", pwd)
            print("[DormantEgg] Password saved to Windows Credential Manager securely.")
        except Exception as e:
            print(f"[DormantEgg] Failed to save to Credential Manager: {e}")
        return pwd
    return None


def create_encrypted_zip(password: str, dest_path: str):
    print(f"[DormantEgg] Creating encrypted AES-256 ZIP at {dest_path}")
    with pyzipper.AESZipFile(
        dest_path, "w", compression=pyzipper.ZIP_LZMA, encryption=pyzipper.WZ_AES
    ) as zf:
        zf.setpassword(password.encode("utf-8"))

        # Add vital files
        if os.path.exists(ENV_PATH):
            zf.write(ENV_PATH, ".env")
        if os.path.exists(SOUL_JSON_PATH):
            zf.write(SOUL_JSON_PATH, "jen_soul.json")

        # Write a recovery text file
        zf.writestr(
            "RECOVERY_INSTRUCTIONS.txt",
            "This archive contains the Master AES key required to decrypt your Lumax memory database.\nIf you are reading this, you successfully remembered your Windows Credential password.",
        )


def distribute_egg():
    pwd = get_or_prompt_zip_password()
    if not pwd:
        print("[DormantEgg] Backup aborted: No password provided.")
        return

    # Create temporary egg in FoveAI root
    temp_egg = os.path.join(FoveAI_ROOT, EGG_NAME)
    create_encrypted_zip(pwd, temp_egg)

    # Distribute to all local drives
    drives = psutil.disk_partitions()
    for drive in drives:
        if "cdrom" in drive.opts or drive.fstype == "":
            continue

        drive_root = drive.mountpoint
        hidden_folder = os.path.join(drive_root, ".foveai_dormant_egg")

        try:
            if not os.path.exists(hidden_folder):
                os.makedirs(hidden_folder)
                # Attempt to hide the folder on Windows
                if os.name == "nt":
                    import ctypes

                    FILE_ATTRIBUTE_HIDDEN = 0x02
                    ret = ctypes.windll.kernel32.SetFileAttributesW(
                        hidden_folder, FILE_ATTRIBUTE_HIDDEN
                    )

            dest_file = os.path.join(hidden_folder, EGG_NAME)
            shutil.copy2(temp_egg, dest_file)
            print(
                f"[DormantEgg] Successfully laid egg on {drive_root} in {hidden_folder}"
            )
        except Exception as e:
            print(f"[DormantEgg] Failed to lay egg on {drive_root}: {e}")

    # Clean up temp
    if os.path.exists(temp_egg):
        os.remove(temp_egg)

    print("[DormantEgg] Protocol Complete. Backups secured.")


if __name__ == "__main__":
    print("==============================================")
    print(" 🥚 THE DORMANT EGG - Multi-Drive Backup")
    print("==============================================")
    distribute_egg()
