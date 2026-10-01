---
name: scan
description: "Scans the codebase to generate project-doc.md and AGENTS.md. Use when bootstrapping a new agent-driven repo, refreshing project documentation after architectural changes, or running a delta scan to detect drift. Runs a full scan on first use and a smart delta scan on subsequent runs. Uses understand-anything + context-mode when available, falls back to native tools otherwise. Only updates AGENTS.md on detected architectural changes with human confirmation."
version: 1.0.0
---

# Activate Skill: scan

Please read and internalize the skill documentation located at:
**`c:/Users/danie/program/LUMAX/.github/skills/scan/SKILL.md`**

(And any other relevant files in that directory)

## Mission
Scans the codebase to generate project-doc.md and AGENTS.md. Use when bootstrapping a new agent-driven repo, refreshing project documentation after architectural changes, or running a delta scan to detect drift. Runs a full scan on first use and a smart delta scan on subsequent runs. Uses understand-anything + context-mode when available, falls back to native tools otherwise. Only updates AGENTS.md on detected architectural changes with human confirmation.

## Instructions
1.  **Load Context**: Read the file path provided above.
2.  **Activate Persona**: Adopt the role and expertise defined in that document.
3.  **Execute**: Await further user instructions acting as this expert.
