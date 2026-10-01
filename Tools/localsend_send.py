import http.client
import json
import os
import ssl
import sys
import tempfile
from urllib.parse import urlencode


def send_file(target_ip, file_path, port=53317):
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.", flush=True)
        return False

    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    print(
        f"[*] Preparing to send '{file_name}' ({file_size / (1024 * 1024):.2f} MB) to {target_ip}:{port} via LocalSend...",
        flush=True,
    )

    # Load PC LocalSend credentials from settings.json
    settings_path = os.path.expandvars(r"%APPDATA%\LocalSend\settings.json")
    if not os.path.exists(settings_path):
        print("Error: LocalSend settings.json not found on PC.", flush=True)
        return False

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    security = json.loads(settings["flutter.ls_security_context"])
    cert_str = security["certificate"]
    key_str = security["privateKey"]
    alias = settings.get("flutter.ls_alias", "LUMAX-PC")

    # Create temporary PEM files for SSL context
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pem") as fc:
        fc.write(cert_str)
        cert_file = fc.name

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".pem") as fk:
        fk.write(key_str)
        key_file = fk.name

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)

    try:
        # Step 1: Query device info
        conn = http.client.HTTPSConnection(target_ip, port, context=ctx, timeout=10)
        conn.request("GET", "/api/localsend/v2/info")
        res = conn.getresponse()
        if res.status != 200:
            print(f"Failed to get info from target: HTTP {res.status}")
            return False

        device_info = json.loads(res.read().decode("utf-8"))
        print(
            f"[+] Connected to: {device_info.get('alias', 'Unknown')} ({device_info.get('deviceModel', 'Device')})"
        )

        # Step 2: Prepare upload
        file_id = "apk-file-01"
        prepare_payload = {
            "info": {
                "alias": alias,
                "version": "2.2",
                "deviceModel": "Windows",
                "deviceType": "desktop",
                "fingerprint": "lumax-pc-authorized",
                "port": 53317,
                "protocol": "https",
                "download": False,
            },
            "files": {
                file_id: {
                    "id": file_id,
                    "fileName": file_name,
                    "size": file_size,
                    "fileType": "application/vnd.android.package-archive",
                    "sha256": None,
                    "preview": None,
                }
            },
        }

        body_bytes = json.dumps(prepare_payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body_bytes)),
        }

        print("[*] Sending upload request... Waiting for acceptance on Quest 3...")
        conn.request(
            "POST", "/api/localsend/v2/prepare-upload", body=body_bytes, headers=headers
        )
        res = conn.getresponse()

        if res.status != 200:
            print(f"[-] Upload request rejected or failed: HTTP {res.status}")
            print(res.read().decode("utf-8"))
            return False

        resp_data = json.loads(res.read().decode("utf-8"))
        session_id = resp_data.get("sessionId")
        files_map = resp_data.get("files", {})
        token = files_map.get(file_id)

        if not session_id or not token:
            print(f"[-] Missing session or token from response: {resp_data}")
            return False

        print(f"[+] Request ACCEPTED by Quest! (Session: {session_id[:8]}...)")
        print("[*] Uploading APK payload...")

        # Step 3: Stream the APK binary
        upload_params = urlencode(
            {"sessionId": session_id, "fileId": file_id, "token": token}
        )
        upload_url = f"/api/localsend/v2/upload?{upload_params}"

        conn.putrequest("POST", upload_url)
        conn.putheader("Content-Type", "application/octet-stream")
        conn.putheader("Content-Length", str(file_size))
        conn.endheaders()

        chunk_size = 1024 * 1024  # 1MB chunks
        sent_bytes = 0
        last_percent = -1

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                conn.send(chunk)
                sent_bytes += len(chunk)
                percent = int((sent_bytes / file_size) * 100)
                if percent != last_percent and percent % 5 == 0:
                    print(
                        f"    --> Progress: {percent}% ({sent_bytes / (1024 * 1024):.1f} / {file_size / (1024 * 1024):.1f} MB)"
                    )
                    last_percent = percent

        upload_res = conn.getresponse()
        if upload_res.status in (200, 204):
            print(
                f"\n🎉 [SUCCESS] '{file_name}' successfully transferred to your Quest 3!"
            )
            return True
        else:
            print(
                f"\n[-] Upload failed: HTTP {upload_res.status} {upload_res.read().decode('utf-8')}"
            )
            return False

    except Exception as e:
        print(f"\n[-] Error during LocalSend transfer: {e}")
        return False
    finally:
        try:
            os.unlink(cert_file)
            os.unlink(key_file)
        except:
            pass


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 2 else "192.168.8.108"
    file = (
        sys.argv[2]
        if len(sys.argv) > 2
        else (
            sys.argv[1]
            if len(sys.argv) > 1
            else r"c:\Users\danie\program\LUMAX\FoveAI\client_quest\AliceVR.apk"
        )
    )
    send_file(target, file)
