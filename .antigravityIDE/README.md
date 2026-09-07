# .antigravityIDE

This directory is reserved for IDE binaries and IDE-specific tooling, as defined by the XRLF v3 contract for the LUMAX project.

## Purpose

- **`.antigravityIDE/`** → IDE binaries, editor extensions, IDE-specific launchers, and any executable tooling tied to the integrated development environment.
- **`.antigravity/`** → XRLF steering, contract references, and agent orchestration metadata only.

## Rules

1. Do not place XRLF steering files here. Those belong in `.antigravity/`.
2. Do not place source code here. This folder is for IDE/runtime binaries only.
3. Keep this directory out of version control where appropriate (see `.gitignore`).

## Reference

- XRLF contract: `XRLF.CONTRACT.XRLF` or `.xrlf/xrlf.contract.xrlf`
- Steering: `.antigravity/xrlf_steering.xml`
- Cursor rules: `.cursorrules`