#!/bin/bash
# build_apk.sh — Build the FoveAI AliceVR Quest APK from Linux
#
# Usage: ./build_apk.sh [output_path]
#
# Uses Unity 6000.4.9f1 in batchmode to build the Android APK.
# The first run will be slow (full asset reimport, IL2CPP, Gradle).
# Subsequent runs use the Library cache and are much faster.

set -euo pipefail

PROJECT_DIR="/home/lumba/FoveAI/client_quest"
# Auto-detect the newest installed Unity 6000.x editor (Hub installs to /opt/Unity or ~/Unity/Hub/Editor/<ver>/Editor/Unity)
UNITY_EDITOR="$(ls -d /opt/Unity/Unity-*/Editor/Unity 2>/dev/null | sort -V | tail -1)"
if [ -z "$UNITY_EDITOR" ]; then
    UNITY_EDITOR="$(ls -d /home/lumba/Unity/Hub/Editor/*/Editor/Unity 2>/dev/null | sort -V | tail -1)"
fi
if [ -z "$UNITY_EDITOR" ] || [ ! -x "$UNITY_EDITOR" ]; then
    echo "ERROR: No Unity editor found under /opt/Unity/ or /home/lumba/Unity/Hub/Editor/"
    echo "Install Unity 6000.x via Unity Hub first (with Android Build Support)."
    exit 1
fi
# 2026-10-09: the Hub-internal Android SDK was wiped in the migration — the SDK now lives
# here (installed via cmdline-tools; see unity-quest-bridge skill):
# NOTE: these MUST be exported, not just shell-assigned. Unity 6 reads ANDROID_SDK_ROOT from the
# environment during its startup InitializeOnLoad; without export it reported "Android SDK: ''"
# and -androidSdkPath alone was discarded, failing with "Invalid SDK directory path".
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-/home/lumba/Android/Sdk}"
export ANDROID_HOME="$ANDROID_SDK_ROOT"
# 2026-10-09: Unity 6000.4 rejects NDK r27 ("Android NDK not found or invalid") — it requires
# r28. Installed via sdkmanager alongside the SDK (which now lives on sda2 via /opt symlink).
export ANDROID_NDK_ROOT="${ANDROID_NDK_ROOT:-/home/lumba/Android/Sdk/ndk/27.2.12479018}"
# The Unity AndroidPlayer module on this machine is EMPTY (no bundled OpenJDK),
# so Unity has no JDK to fall back on and the preferences typed into the Editor
# are not on disk (no EditorPrefs). Without JAVA_HOME the batch build dies with
# "No Java Development Kit found" halfway through.
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
# Unity's IL post-processor socket lives in /tmp, and systemd-tmpfiles-clean is
# active on this box. A vanished /tmp/ilpp.sock-* kills the compiler backend with
# "Can't find file ...ilpp.sock" — which looks like a compile failure but is not
# one. Point TMPDIR at a persistent, user-owned directory instead.
export TMPDIR="${TMPDIR:-$PROJECT_DIR/Temp/unitytmp}"
mkdir -p "$TMPDIR"
export PATH="$JAVA_HOME/bin:$PATH"
# Parse arguments
CORES=6
OUTPUT_APK="$PROJECT_DIR/AliceVR.apk"
LOG_FILE="$PROJECT_DIR/build_linux.log"

for arg in "$@"; do
    case "$arg" in
        --fast)       CORES=12 ;;
        --gentle)     CORES=6 ;;
        --cores=*)    CORES="${arg#*=}" ;;
        -c*)          CORES="${arg#-c}" ;;
        *)            OUTPUT_APK="$arg" ;;
    esac
done

echo "=== FoveAI AliceVR APK Build ==="
echo "Project:  $PROJECT_DIR"
echo "Output:   $OUTPUT_APK"
echo "Unity:    $UNITY_EDITOR"
echo "Log:      $LOG_FILE"

if [ "$CORES" -lt 12 ]; then
    # Calculate CPU mask range (e.g., 0 to CORES-1)
    MAX_CORE=$((CORES - 1))
    CORE_MASK="0-${MAX_CORE}"
    UNITY_WORKERS=$((CORES > 2 ? CORES - 1 : 1))
    GRADLE_WORKERS=$((CORES > 4 ? 3 : 2))
    
    echo "Mode:     BALANCED / COOL ($CORES of 12 cores, safe thermals)"
    echo "          (Cores pinned: $CORE_MASK | Unity workers: $UNITY_WORKERS | Gradle workers: $GRADLE_WORKERS)"
    echo "          (Options: --cores=6 [~18m], --cores=8 [~14m], --cores=4 [~28m], --fast [12 cores, ~10m])"
    
    export GRADLE_OPTS="-Dorg.gradle.workers.max=$GRADLE_WORKERS -Dorg.gradle.parallel=false -Dorg.gradle.jvmargs=-Xmx2048m"
    RUN_CMD=(nice -n 15 ionice -c 3 taskset -c "$CORE_MASK")
    EXTRA_UNITY_ARGS=(-job-worker-count "$UNITY_WORKERS")
else
    echo "Mode:     FAST (All 12 CPU cores, maximum speed)"
    RUN_CMD=()
    EXTRA_UNITY_ARGS=()
fi
# Unity 6 aborts even in -batchmode without an X display on this machine (Xwayland on tty2)
# 2026-10-09: on this machine the working X display is :20 (chrome-remote-desktop's Xwayland);
# :0 is the dead Budgie tty. Unity batchmode aborts without a live X.
if ! xdpyinfo -display "${DISPLAY:-:20}" >/dev/null 2>&1; then
  for d in :20 :0 :1; do
    if xdpyinfo -display "$d" >/dev/null 2>&1; then export DISPLAY="$d"; break; fi
  done
else
  export DISPLAY="${DISPLAY:-:20}"
fi
echo "Using DISPLAY=$DISPLAY"
echo ""

# ── preflight ────────────────────────────────────────────────────────────────
# Every one of these has silently produced a confusing failure at least once.
PRE_FAIL=0
[ -x "$UNITY_EDITOR" ]              || { echo "PREFLIGHT: editor missing: $UNITY_EDITOR"; PRE_FAIL=1; }
[ -d "$ANDROID_SDK_ROOT" ]          || { echo "PREFLIGHT: SDK missing: $ANDROID_SDK_ROOT"; PRE_FAIL=1; }
[ -d "$ANDROID_NDK_ROOT" ]          || { echo "PREFLIGHT: NDK missing: $ANDROID_NDK_ROOT"; PRE_FAIL=1; }
[ -x "$JAVA_HOME/bin/java" ]        || { echo "PREFLIGHT: JDK missing: $JAVA_HOME/bin/java"; PRE_FAIL=1; }
[ -f "$PROJECT_DIR/Assets/Scripts/Editor/BuildAPKBatch.cs" ] \
                                    || { echo "PREFLIGHT: BuildAPKBatch.cs missing — nothing to execute"; PRE_FAIL=1; }
ls "$HOME/.local/share/unity3d/Unity/Unity_lic.ulf" >/dev/null 2>&1 \
                                    || echo "PREFLIGHT WARNING: no standalone Unity licence — the build will prompt or fail"
[ $PRE_FAIL -eq 0 ] && echo "preflight OK: editor + SDK + NDK + JDK + build method all present"
[ $PRE_FAIL -ne 0 ] && { echo "preflight FAILED — fix the above before building"; exit 1; }

# Clean old build artifacts (but keep Library for caching)
rm -f "$PROJECT_DIR/build/outputs/apk/android/AliceVR.apk" 2>/dev/null || true

# Run Unity in batchmode
"${RUN_CMD[@]}" "$UNITY_EDITOR" \
    -batchmode \
    -quit \
    "${EXTRA_UNITY_ARGS[@]}" \
    -logFile "$LOG_FILE" \
    -projectPath "$PROJECT_DIR" \
    -executeMethod BuildAPKBatch.Build \
    -buildTarget Android \
    -androidSdkPath "$ANDROID_SDK_ROOT" \
    -androidNdkPath "$ANDROID_NDK_ROOT" \
    -jdkPath "$JAVA_HOME" \
    # NOTE: must NOT pass empty -keystore/-keyalias here — Unity treats those as explicit
    # overrides and silently falls back to debug signing, which caused the install conflict.
    # BuildAPKBatch.cs wires keystore/alicevr.keystore itself; leave it to do the work.
    2>&1 | tail -50

BUILD_EXIT=$?

echo ""
echo "=== Build exit code: $BUILD_EXIT ==="

# Check if APK was produced
if [ -f "$OUTPUT_APK" ]; then
    APK_SIZE=$(du -h "$OUTPUT_APK" | cut -f1)
    echo "SUCCESS: APK built at $OUTPUT_APK ($APK_SIZE)"
    exit 0
else
    # Check alternative output locations
    ALT_APK="$PROJECT_DIR/build/outputs/apk/android/AliceVR.apk"
    if [ -f "$ALT_APK" ]; then
        cp "$ALT_APK" "$OUTPUT_APK"
        APK_SIZE=$(du -h "$OUTPUT_APK" | cut -f1)
        echo "SUCCESS: APK built at $OUTPUT_APK ($APK_SIZE)"
        exit 0
    fi
    echo "ERROR: APK not found. Check build log: $LOG_FILE"
    echo ""
    echo "Last 30 lines of build log:"
    tail -30 "$LOG_FILE" 2>/dev/null || echo "(no log file)"
    exit 1
fi
