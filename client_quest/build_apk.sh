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
OUTPUT_APK="${1:-$PROJECT_DIR/AliceVR.apk}"
LOG_FILE="$PROJECT_DIR/build_linux.log"

echo "=== FoveAI AliceVR APK Build ==="
echo "Project:  $PROJECT_DIR"
echo "Output:   $OUTPUT_APK"
echo "Unity:    $UNITY_EDITOR"
echo "Log:      $LOG_FILE"
echo ""

# Clean old build artifacts (but keep Library for caching)
rm -f "$PROJECT_DIR/build/outputs/apk/android/AliceVR.apk" 2>/dev/null || true

# Run Unity in batchmode
"$UNITY_EDITOR" \
    -batchmode \
    -quit \
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
