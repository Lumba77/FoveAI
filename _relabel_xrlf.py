"""
_relabel_xrlf.py — Fix the XRLF manifest header base_model_name
================================================================
The qwen4b-concise-v1.0.xrlf bundle was packed with base_model_name =
"gemma-4-12b-it-qat-GGUF-MoQ" (copied from the Gemma template), even
though the embedded GGUF core is actually Qwen 4B Concise. This makes
the XRLF server on port 8300 report the WRONG model name, which collides
with the standard Gemma model in providers.json and causes the plugin to
"keep running the standard model".

This script rewrites the header's base_model_name to the correct value
and fixes the section-table offsets (since the string length changes).

Usage:
    python _relabel_xrlf.py [path-to.xrlf] [new-base-model-name]
"""

import os
import struct
import sys

# Mirror the schema constants
MAGIC = b"XRLF"
HEADER_STRUCT = struct.Struct("<4sHHHIH6s")   # 22 bytes
HEADER_SIZE = HEADER_STRUCT.size
SECTION_ENTRY_STRUCT = struct.Struct("<HQQH")  # type(H) offset(Q) length(Q) flags(H)
SECTION_ENTRY_SIZE = SECTION_ENTRY_STRUCT.size


def relabel(path: str, new_name: str):
    with open(path, "rb") as f:
        data = bytearray(f.read())

    # Parse header
    magic, version, base_len, xrl_len, flags, section_count, _reserved = \
        HEADER_STRUCT.unpack(data[:HEADER_SIZE])

    if magic != MAGIC:
        print(f"ERROR: Not an XRLF file (magic={magic!r})")
        sys.exit(1)

    cursor = HEADER_SIZE
    old_base = data[cursor:cursor + base_len].decode("utf-8")
    cursor += base_len
    old_xrl = data[cursor:cursor + xrl_len].decode("utf-8")
    cursor += xrl_len
    section_table_offset = cursor

    print(f"Old base_model_name : {old_base!r}")
    print(f"Old xrl_source_model: {old_xrl!r}")
    print(f"New base_model_name : {new_name!r}")

    # Guard: fail if new name would collide with existing xrl_source reading
    new_base_bytes = new_name.encode("utf-8")
    delta = len(new_base_bytes) - base_len

    # ── 1. Update header base_len field ────────────────────────────────────
    # Re-pack header with the SAME magic/version/flags/section_count but new base length.
    new_header = HEADER_STRUCT.pack(
        magic, version, len(new_base_bytes), xrl_len, flags, section_count, _reserved
    )
    data[0:HEADER_SIZE] = new_header

    # ── 2. Replace the base_model_name bytes in place (rest may shift) ─────
    # Store the xrl_source string + everything after it.
    tail_start = HEADER_SIZE + base_len + xrl_len
    tail = bytes(data[tail_start:])

    # Reassemble: header + new_base + xrl_source + tail
    xrl_source_bytes = old_xrl.encode("utf-8")
    new_data = bytearray()
    new_data += bytes(data[0:HEADER_SIZE])
    new_data += new_base_bytes
    new_data += xrl_source_bytes
    new_data += tail

    # ── 3. Fix section-table offsets by `delta` (they start after names) ──
    # The section table begins at: HEADER_SIZE + new_base_len + xrl_len
    new_section_table_offset = HEADER_SIZE + len(new_base_bytes) + xrl_len
    # Every section entry's offset (bytes 2:10 within the 22-byte entry) must
    # be shifted by delta.
    for i in range(section_count):
        entry_start = new_section_table_offset + i * SECTION_ENTRY_SIZE
        stype, offset, length, sflags = SECTION_ENTRY_STRUCT.unpack(
            new_data[entry_start:entry_start + SECTION_ENTRY_SIZE]
        )
        new_offset = offset + delta
        new_data[entry_start:entry_start + SECTION_ENTRY_SIZE] = \
            SECTION_ENTRY_STRUCT.pack(stype, new_offset, length, sflags)

    # ── 4. Write back ──────────────────────────────────────────────────────
    backup = path + ".bak"
    if not os.path.exists(backup):
        os.rename(path, backup)
        print(f"Backup created: {backup}")

    with open(path, "wb") as f:
        f.write(new_data)

    print(f"Wrote {path} ({len(new_data)} bytes, delta={delta:+d})")
    print("DONE. Restart the XRLF server (or the proxy) for the change to take effect.")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "qwen4b-concise-v1.0.xrlf"
    new_name = sys.argv[2] if len(sys.argv) > 2 else "xrlf-qwen4b-concise"
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), target)
    relabel(path, new_name)
