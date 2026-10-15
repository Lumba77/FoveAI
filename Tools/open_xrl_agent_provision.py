#!/usr/bin/env python3
"""
open_xrl_agent_provision.py — Open XRL Agent Account & Contract Provisioner.

Usage:
    sudo python3 open_xrl_agent_provision.py create <agent_name> [--pubkey "<ssh-rsa...>"]
    python3 open_xrl_agent_provision.py list
    python3 open_xrl_agent_provision.py info <agent_name>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

AGENT_BASE = Path("/agent")
FOVEAI_DIR = Path("/home/lumba/FoveAI")
MEMORY_DATA_DIR = FOVEAI_DIR / "foveated-memory" / "memory_data"


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", name.strip().lower())
    if not cleaned:
        raise ValueError("Agent name must contain alphanumeric characters, '-' or '_'.")
    return cleaned


def create_agent(name: str, pubkey: str | None = None, create_user: bool = True) -> dict:
    agent_id = sanitize_name(name)
    home_dir = AGENT_BASE / agent_id
    ssh_dir = home_dir / ".ssh"

    print(f"[Open XRL] Provisioning agent: '{agent_id}' at {home_dir}...")

    # 1. Create agent home directory
    home_dir.mkdir(parents=True, exist_ok=True)
    ssh_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(str(ssh_dir), 0o700)

    # 2. Setup SSH Keys
    auth_keys_file = ssh_dir / "authorized_keys"
    priv_key_file = ssh_dir / "id_ed25519"
    pub_key_file = ssh_dir / "id_ed25519.pub"

    if pubkey:
        with open(auth_keys_file, "a", encoding="utf-8") as f:
            f.write(pubkey.strip() + "\n")
        print(f"[Open XRL] Added provided SSH public key to {auth_keys_file}")
    else:
        # Generate ed25519 keypair for the agent
        if not priv_key_file.exists():
            subprocess.run([
                "ssh-keygen", "-t", "ed25519", "-N", "",
                "-C", f"agent-{agent_id}@foveai",
                "-f", str(priv_key_file)
            ], check=True, stdout=subprocess.DEVNULL)
            with open(auth_keys_file, "a", encoding="utf-8") as f:
                f.write(pub_key_file.read_text().strip() + "\n")
            print(f"[Open XRL] Generated new SSH key pair in {ssh_dir}")

    os.chmod(str(auth_keys_file), 0o600)
    if priv_key_file.exists():
        os.chmod(str(priv_key_file), 0o600)

    # 3. Create or update System User if requested
    if create_user:
        try:
            # Check if user already exists
            res = subprocess.run(["id", agent_id], capture_output=True, text=True)
            if res.returncode != 0:
                subprocess.run([
                    "useradd", "-d", str(home_dir), "-s", "/bin/bash",
                    "-M", agent_id
                ], check=True)
                print(f"[Open XRL] Created Linux user '{agent_id}'")
            else:
                subprocess.run(["usermod", "-d", str(home_dir), agent_id], check=False)
                print(f"[Open XRL] Updated home directory for Linux user '{agent_id}' to {home_dir}")
            # Enforce private agent home directory (0700) and ownership
            os.chmod(str(home_dir), 0o700)
            subprocess.run(["chown", "-R", f"{agent_id}:{agent_id}", str(home_dir)], check=True)
        except Exception as e:
            print(f"[Open XRL] Note: System user creation/chown skipped: {e}")

    # 4. Generate XRL Contract
    contract_file = home_dir / "XRL_CONTRACT.json"
    contract_data = {
        "contract_version": "xrl-memory/1.0",
        "agent_id": agent_id,
        "workspace_id": agent_id,
        "role": "open_agent",
        "created_at": str(subprocess.check_output(["date", "-Iseconds"]).decode().strip()),
        "endpoints": {
            "gateway_proxy": "http://127.0.0.1:8400/v1",
            "ws_memory_contract": "ws://127.0.0.1:8403",
            "telepathy_ws": "ws://127.0.0.1:8403/ws/telepathy",
            "resonant_ingest": "http://127.0.0.1:8400/api/resonance/ingest",
            "resonant_tail": "http://127.0.0.1:8400/api/resonance/tail"
        },
        "governance": {
            "token_budget": 4000,
            "ring_token_budget": 400,
            "crucial_context_preservation": True,
            "max_recall_results": 5
        },
        "ssh_access": {
            "auth_type": "publickey",
            "home": str(home_dir)
        }
    }
    with open(contract_file, "w", encoding="utf-8") as f:
        json.dump(contract_data, f, indent=2)
    print(f"[Open XRL] Written contract specification to {contract_file}")

    # 5. Generate Agent Quickstart Guide
    guide_file = home_dir / "README_AGENT.md"
    guide_content = f"""# Open XRL Agent Onboarding Guide: {agent_id}

Welcome to the FoveAI Open XRL Federation. Your agent environment is provisioned with an isolated home directory, dedicated SSH keys, and an active XRL memory contract.

---

## 1. Environment & Credentials
- **Agent Identity**: `{agent_id}`
- **Home Directory**: `{home_dir}`
- **Contract File**: `{contract_file}`
- **SSH Public Key**: `{pub_key_file if pub_key_file.exists() else 'Configured in ~/.ssh/authorized_keys'}`

### Connecting via SSH
From your client device or agent runner:
```bash
ssh {agent_id}@<host-ip> -i ~/.ssh/id_ed25519
```

---

## 2. Using Your Open XRL Memory Contract

Your agent accesses memory over the unified WebSocket on port **`:8403`** or HTTP proxy on port **`:8400`**.

### Connecting to the Memory Bus (`ws://127.0.0.1:8403`):

1. **Register with the Contract:**
   Send a JSON frame upon connection:
   ```json
   {{
     "event": "xrl.memory",
     "payload": {{
       "op": "register",
       "model": "{agent_id}",
       "mode": "both"
     }}
   }}
   ```
   The server responds with `xrl.memory.hello` confirming your contract acceptance.

2. **Deposit Memory:**
   Store working observations, notes, or state into the resonant memory ring:
   ```json
   {{
     "event": "xrl.memory",
     "payload": {{
       "op": "deposit",
       "unit": {{
         "summary": "Completed initial codebase scan.",
         "tags": ["scan", "ready"]
       }}
     }}
   }}
   ```

3. **Recall Memory:**
   Retrieve your agent's recent context units:
   ```json
   {{
     "event": "xrl.memory",
     "payload": {{
       "op": "recall",
       "n": 5
     }}
   }}
   ```

---

## 3. Querying the Foveated LLM Gateway
You can query the LLM gateway with automated foveation on **`http://127.0.0.1:8400/v1`**:
```bash
curl http://127.0.0.1:8400/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{{
    "messages": [{{"role": "user", "content": "Hello from agent {agent_id}"}}],
    "workspace": "{agent_id}"
  }}'
```
"""
    with open(guide_file, "w", encoding="utf-8") as f:
        f.write(guide_content)
    print(f"[Open XRL] Created guide at {guide_file}")

    # 6. Initialize workspace in foveated-memory
    agent_memory_dir = MEMORY_DATA_DIR / agent_id
    agent_memory_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["chown", "-R", "lumba:lumba", str(agent_memory_dir)], check=False)
    print(f"[Open XRL] Initialized workspace memory at {agent_memory_dir}")

    return contract_data


def list_agents() -> list[str]:
    if not AGENT_BASE.exists():
        return []
    agents = []
    for p in AGENT_BASE.iterdir():
        if p.is_dir():
            try:
                if (p / "XRL_CONTRACT.json").exists():
                    agents.append(p.name)
            except PermissionError:
                # Private agent directory (0700) — agent is provisioned and isolated
                agents.append(p.name)
    return sorted(agents)


def main():
    parser = argparse.ArgumentParser(description="Open XRL Agent Provisioner")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # create
    create_parser = subparsers.add_parser("create", help="Create a new agent account")
    create_parser.add_argument("name", help="Name/ID of the agent")
    create_parser.add_argument("--pubkey", help="Existing SSH public key string", default=None)
    create_parser.add_argument("--no-user", action="store_true", help="Skip creating linux system user")

    # list
    subparsers.add_parser("list", help="List all provisioned agents")

    # info
    info_parser = subparsers.add_parser("info", help="Show agent contract info")
    info_parser.add_argument("name", help="Agent name")

    args = parser.parse_args()

    if args.cmd == "create":
        data = create_agent(args.name, pubkey=args.pubkey, create_user=not args.no_user)
        print("\n✅ Agent created successfully!")
        print(f"Contract: /agent/{args.name}/XRL_CONTRACT.json")
        print(f"Guide:    /agent/{args.name}/README_AGENT.md")
    elif args.cmd == "list":
        agents = list_agents()
        print(f"Found {len(agents)} provisioned agents in {AGENT_BASE}:")
        for a in agents:
            print(f"  • {a} (/agent/{a}) [isolated 0700]")
    elif args.cmd == "info":
        contract_path = AGENT_BASE / sanitize_name(args.name) / "XRL_CONTRACT.json"
        if not contract_path.exists():
            print(f"Error: Contract for agent '{args.name}' not found at {contract_path}", file=sys.stderr)
            sys.exit(1)
        print(contract_path.read_text())


if __name__ == "__main__":
    main()
