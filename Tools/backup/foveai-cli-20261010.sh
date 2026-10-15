#!/bin/bash
# foveai — one switch for every FoveAI service.
#
# Why masking is part of "stop": the model units use Restart=always, so
# systemd reads a kill signal as a failure and respawns within RestartSec —
# killing by PID can never win. Enabled units also come back on reboot.
# So `stop` masks as well as stops; `start` unmasks. The pair is exact.

set -u

# Everything FoveAI knows about, for STATUS — including deliberately-disabled
# units, because seeing them is the point.
units() {
    systemctl list-unit-files 'foveai-*' 'multigate*' 'xr-vessel*' \
        --no-legend --no-pager 2>/dev/null | awk '{print $1}'
}

# Only what you actually want running, for start/stop/halt.
#
# Without this filter `start` woke every foveai-* unit including the ones
# deliberately left disabled — which is how three llama-servers came up
# holding 6.2 GB of VRAM that nothing was using. An override that overrides
# your own decisions is not an override.
# NOTE: `list-unit-files --enabled` is not a valid flag on this systemd, and
# using it silently returned zero units — `foveai start` would have started
# NOTHING. Filter with is-enabled instead, which is slower but honest.
units_enabled() {
    units | while read -r u; do
        [ "$(systemctl is-enabled "$u" 2>/dev/null)" = "enabled" ] && echo "$u"
    done
}

run() {
    local verb=$1 u
    for u in $(units); do
        if sudo systemctl "$verb" "$u" >/dev/null 2>&1; then
            printf '  %-34s %s\n' "$u" "$verb"
        else
            printf '  %-34s %-6s skipped\n' "$u" "$verb"
        fi
    done
}

run_on() {
    local verb=$1; shift
    local list_fn=$1; shift
    local u
    for u in $($list_fn); do
        if sudo systemctl "$verb" "$u" >/dev/null 2>&1; then
            printf '  %-34s %s\n' "$u" "$verb"
        else
            printf '  %-34s %-6s skipped\n' "$u" "$verb"
        fi
    done
}

case "${1:-status}" in
    stop)
        echo "Stopping + masking enabled FoveAI services..."
        run_on units_enabled stop
        run_on units_enabled mask
        echo "-> all down and masked. Bring back with: foveai start"
        ;;
    start)
        echo "Unmasking + starting enabled FoveAI services..."
        run_on units_enabled unmask
        run_on units_enabled start
        echo "-> all started"
        ;;
    status)
        printf '  %-34s %-10s %s\n' UNIT ACTIVE ENABLED
        for u in $(units); do
            printf '  %-34s %-10s %s\n' "$u" \
                "$(systemctl is-active  "$u" 2>&1)" \
                "$(systemctl is-enabled "$u" 2>&1)"
        done
        ;;
    *)
        echo "usage: foveai {stop|start|status}"
        exit 1
        ;;
esac
