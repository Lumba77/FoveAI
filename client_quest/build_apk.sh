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
UNITY_EDITOR="/home/lumba/Unity/Hub/Editor/6000.4.9f1/Editor/Unity"
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
echo ""

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
    -androidSdkPath "/home/lumba/Unity/Hub/Editor/6000.4.9f1/Editor/Data/PlaybackEngines/AndroidPlayer/SDK" \
    -androidNdkPath "/home/lumba/Unity/Hub/Editor/6000.4.9f1/Editor/Data/PlaybackEngines/AndroidPlayer/NDK" \
    -keystore "" \
    -keyalias "" \
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
