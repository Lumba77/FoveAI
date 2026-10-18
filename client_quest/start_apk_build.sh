#!/bin/bash
# start_apk_build.sh — launch the Unity APK build as a detached, oomd-exempt user service.
#
# Why oomd exemption is mandatory (2026-10-15): a 10-core run reached 2723/2734 IL2CPP
# objects and was then SIGKILLed by systemd-oomd during "Link_Android_arm64
# libil2cpp.so" -> "Failed with result 'oom-kill'". oomd reacts to memory *pressure*
# (swap thrash), not to real exhaustion — this box had 7-8Gi still available and 6.4G
# of swap in use, yet oomd killed the unit anyway. A build is long-running and
# legitimately peaks at multi-GiB during the final link, which is exactly the profile
# oomd is tuned to kill. So we opt this unit out of both pressure kill switches.
#
# The unit is a real systemd service: it survives the editor, terminal, or agent dying
# (unlike setsid, which is still in the launching shell's process tree).
#
# Usage:  ./start_apk_build.sh [cores]     (default 10; 12 freezes this machine)
# Watch:  ./start_apk_build.sh --status
# Result: client_quest/build_status.txt

PROJECT_DIR="/home/lumba/FoveAI/client_quest"
UNIT="foveai-quest-apk"
CORES="${1:-10}"

case "$CORES" in
    --status)
        systemctl --user status "$UNIT.service" --no-pager 2>&1 | head -12
        echo "--- build_status.txt ---"
        cat "$PROJECT_DIR/build_status.txt" 2>/dev/null || echo "(build still running, no status yet)"
        exit 0
        ;;
    --stop)
        systemctl --user stop "$UNIT.service" 2>/dev/null
        echo "stopped $UNIT"
        exit 0
        ;;
esac

if systemctl --user is-active --quiet "$UNIT.service"; then
    echo "ERROR: $UNIT.service is already running — a second Unity instance would be refused."
    systemctl --user status "$UNIT.service" --no-pager 2>&1 | head -8
    exit 1
fi

# A stale lockfile from a killed run makes Unity abort with "another Unity instance is
# running", which is misleading — nothing is running. Clear it only when Unity is absent.
if [ -f "$PROJECT_DIR/Temp/UnityLockfile" ] && ! pgrep -f "Editor/Unity .*-projectPath $PROJECT_DIR" >/dev/null 2>&1; then
    echo "clearing stale Temp/UnityLockfile (no live Unity process)"
    rm -f "$PROJECT_DIR/Temp/UnityLockfile"
fi

systemctl --user reset-failed "$UNIT.service" 2>/dev/null

echo "launching APK build on $CORES cores as $UNIT.service ..."
systemd-run --user \
    --unit="$UNIT" \
    --description="FoveAI Quest APK build (${CORES}-core, oomd-exempt)" \
    --property=WorkingDirectory="$PROJECT_DIR" \
    --property=Nice=5 \
    --property=ManagedOOMMemoryPressure=off \
    --property=ManagedOOMSwap=off \
    --property=OOMPolicy=continue \
    "$PROJECT_DIR/build_detached.sh" "--cores=$CORES"

sleep 5
systemctl --user status "$UNIT.service" --no-pager 2>&1 | grep -E "Active|Main PID|Memory|exited" || true
echo
echo "detached — poll with:  ./start_apk_build.sh --status"
echo "              or:     tail -f $PROJECT_DIR/build_detached.log"