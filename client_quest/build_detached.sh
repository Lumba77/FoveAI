#!/bin/bash
# build_detached.sh — run the Unity APK build fully detached from any editor/IDE session.
#
# Why this exists (2026-10-15): the render was started from inside an interactive agent
# shell. When that shell was killed, the whole process group went with it and Unity died
# at 2608/2734 IL2CPP objects. setsid puts the build in its OWN session with no
# controlling terminal, so it survives the editor, the terminal, or the agent dying.
#
# Usage:  setsid nohup ./build_detached.sh >/dev/null 2>&1 </dev/null &
# Watch:  tail -f build_detached.log      (or ./build_detached.sh --status)
# Result: build_status.txt  ->  "EXIT=<code>"  and  "APK=<path> <bytes>"

PROJECT_DIR="/home/lumba/FoveAI/client_quest"
RUN_LOG="$PROJECT_DIR/build_detached.log"
STATUS_FILE="$PROJECT_DIR/build_status.txt"
TARGET_APK="$PROJECT_DIR/AliceVR.apk"

mkdir -p "$PROJECT_DIR"
: > "$RUN_LOG"
rm -f "$STATUS_FILE"

# Unity refuses to open a project whose Temp/UnityLockfile exists AND a live process owns
# it. No Unity is running here (verified), so this 0-byte file is stale debris from the
# killed render and must go or the new run aborts with "another Unity instance is running".
if [ -f "$PROJECT_DIR/Temp/UnityLockfile" ] && ! pgrep -f "Editor/Unity .*$PROJECT_DIR" >/dev/null 2>&1; then
    echo "[detached] removing stale Temp/UnityLockfile (no live Unity process)" >> "$RUN_LOG"
    rm -f "$PROJECT_DIR/Temp/UnityLockfile"
fi

echo "[detached] start $(date -Is)" >> "$RUN_LOG"
echo "[detached] session id: $$ (setsid => own session, survives parent death)" >> "$RUN_LOG"
echo "[detached] cores arg: ${1:---cores=6}" >> "$RUN_LOG"

# The Unity log itself (build_linux.log) carries the granular progress; build_apk.sh's own
# stdout is only the preflight + final verdict, which we tee into the run log.
cd "$PROJECT_DIR" || { echo "EXIT=99" > "$STATUS_FILE"; exit 99; }
./build_apk.sh "${1:---cores=6}" >> "$RUN_LOG" 2>&1
RC=$?

echo "[detached] build_apk.sh exited rc=$RC at $(date -Is)" >> "$RUN_LOG"

# ---- verify the artefact, don't just trust the exit code -------------------------
APK_LINE="APK_MISSING"
if [ -f "$TARGET_APK" ]; then
    BYTES=$(stat -c %s "$TARGET_APK")
    MTIME=$(date -r "$TARGET_APK" -Is)
    # A stale build from a previous day is NOT success. Unity's -quit path writes the APK
    # in place, so compare mtime against the run start.
    FRESH="no"
    [ "$TARGET_APK" -nt "$RUN_LOG" ] && FRESH="yes"
    ZIPOK="no"
    unzip -t "$TARGET_APK" >/dev/null 2>&1 && ZIPOK="yes"
    APK_LINE="APK=$TARGET_APK bytes=$BYTES mtime=$MTIME fresh=$FRESH zip_ok=$ZIPOK"
fi

{
    echo "EXIT=$RC"
    echo "$APK_LINE"
    echo "FINISHED=$(date -Is)"
} > "$STATUS_FILE"

echo "[detached] $APK_LINE" >> "$RUN_LOG"
exit $RC