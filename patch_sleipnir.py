import sys

with open("/home/lumba/FoveAI/sleipnir_launcher.sh", "r") as f:
    content = f.read()

old_block = """    # ── Node 3: Creative Service (:8412 — Dreamscape image gen) ──
    if port_alive "$CREATIVE_PORT"; then"""

new_block = """    # ── Node 4: Theme API (:8415 — Gallery & Nano-UI) ──
    if port_alive 8415; then
        log "Theme API already online (:8415)"
    else
        log "Launching Theme API (:8415)..."
        cd "$FOVEAI_DIR"
        nohup "$VENV_PYTHON" theme/theme_api.py >> /home/lumba/foveai_theme_api.log 2>&1 &
        for i in $(seq 1 10); do
            port_alive 8415 && break
            sleep 0.5
        done
        if port_alive 8415; then
            log "  ✅ Theme API online (:8415)"
        else
            warn "  ⚠️  Theme API did not bind :8415"
        fi
    fi

    # ── Node 3: Creative Service (:8412 — Dreamscape image gen) ──
    if port_alive "$CREATIVE_PORT"; then"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/sleipnir_launcher.sh", "w") as f:
        f.write(content)
    print("Patched sleipnir_launcher.sh successfully")
else:
    print("Could not find block to patch in sleipnir_launcher.sh")
