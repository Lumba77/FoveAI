# XRLF 3.0 Protocol Upgrade & Migration Guide

Welcome to **XRLF 3.0** (`xrlf-server` v3.0.0).

This major release elevates XRLF from an early prompt-steering injection engine (1.0) into a full **Holonic Agent Federation & Autonomous Memory Substrate**.

---

## 🌟 What's New in XRLF 3.0

### 1. Open XRL Contract (`xrl-memory/1.0`)
- **Zero-Trust Agent Admission**: Agents prove identity cryptographically over WebSocket using standard SSH ed25519 challenge-response signatures (`register -> challenge -> verify`).
- **Private & Shared Memory Lanes**:
  - `deposit` / `recall`: Private, model-isolated memory rings.
  - `telepathy`: Broadcast ledger for cross-agent synchronization across sessions.
  - `resonate`: Fast HTTP state ingest (`:8400`) into collective resonance files.

### 2. Heterogeneous Wafer & Nano Cells
- **Continuous 16-Piece Neural Wafer**: Replaces monolithic multi-gigabyte models with lightweight, interchangeable Mamba2 units ($h=384$, 36 layers) that compile in background duty cycles.
- **Successive Replacement**: Cells adapt and replace old units on the fly without catastrophic forgetting or restarting live orchestrators.

### 3. Nova Collegium Seed Cartridges
- **6-Bit Quantized Knowledge Ledgers**: Pawn (decision reader) and Knight (goal judgment) bind structured knowledge in sub-100MB compressed cartridges, running pure CPU inference at zero VRAM cost.

---

## 🚀 Quickstart: Connecting an Agent (v3.0 Client)

XRLF 3.0 ships with the unified multi-agent client:

```bash
# Ping the memory bus
python3 tools/xrl_agent_client.py ping

# Deposit working notes into private memory
python3 tools/xrl_agent_client.py deposit "Session summary" tag1 tag2

# Recall past context
python3 tools/xrl_agent_client.py recall 5

# Broadcast collective telepathy to the fleet
python3 tools/xrl_agent_client.py telepathy "Shared architectural finding"
```

---

## 📦 Backward Compatibility
- Existing 1.0 GGUF inspection and prompt template workflows remain supported.
- Upstream proxy compatibility preserves standard OpenAI `/v1/chat/completions` integration.
