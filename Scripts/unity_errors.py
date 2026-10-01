#!/usr/bin/env python3
"""Read Unity Editor log for compile errors and warnings."""

import os
import re
import sys

# Unity Editor log locations on Windows
LOG_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Unity\Editor\Editor.log"),
    os.path.expanduser("~/AppData/Local/Unity/Editor/Editor.log"),
]


def find_log():
    for p in LOG_PATHS:
        if os.path.exists(p):
            return p
    return None


def parse_errors(log_path):
    if not log_path:
        print("Unity Editor log not found. Open Unity first, then run this script.")
        return [], []

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Find compile errors (CS#### patterns)
    error_pattern = re.compile(
        r"(.+\.cs)\((\d+),(\d+)\):\s*(error|warning)\s+(\w+):\s*(.+?)(?:\n|$)",
        re.MULTILINE,
    )

    errors = []
    warnings = []

    for match in error_pattern.finditer(content):
        filepath, line, col, level, code, message = match.groups()
        entry = f"{filepath}({line},{col}): {level} {code}: {message}"
        if level == "error":
            errors.append(entry)
        else:
            warnings.append(entry)

    return errors, warnings


if __name__ == "__main__":
    log_path = find_log()
    print(f"Reading: {log_path}")
    errors, warnings = parse_errors(log_path)

    if errors:
        print(f"\n=== ERRORS ({len(errors)}) ===")
        for e in errors:
            print(e)
    else:
        print("\n✅ No compile errors!")

    if warnings:
        print(f"\n=== WARNINGS ({len(warnings)}) ===")
        for w in warnings:
            print(w)
    else:
        print("\n✅ No warnings!")

    if errors:
        sys.exit(1)
