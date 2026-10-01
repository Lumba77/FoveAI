# LUMAX WebUI Clinical Architecture (OMEGA_079)

The Matchbox Vessel's diagnostic UI is a world-class, high-density clinical workstation designed to provide both the user and the LUMAX Hybrid Brain with deep, accurate psychiatric profiling and mirroring.

## Core Components

1. **Dashboard (`Dashboard.ts`)**
   - **Real Telemetry**: Pulls live GPU/CPU/IO data via `/api/soul/vitals` (served by `compagent.py`).
   - **Responsive Scaling**: The dashboard adapts to screen size (45vw width) and handles the main navigation between Cognition, Embers, Senses, Matrix, and Diagnosis tabs.

2. **Diagnostic Matrix (`DiagnosisTab.ts`)**
   - **Data Source**: Driven by `diagnostic_data.json` (the 40x14 matrix of profiles) and `lexicon_data.json` (authoritative definitions, criteria explanations, and differential analysis).
   - **Sticky Headers/Footers**: Utilizes `position: sticky` to keep dimension labels in view while scrolling through 40+ disorders.
   - **Cross-Hair Highlighting**: An interactive `hover` event system that highlights the active row (Diagnosis) and column (Criteria) and syncs them to the **Live Definitions Display** at the bottom.
   - **Aesthetic**: Employs LUMAX's signature cyber-clinical theme with neon-pink (severe) and neon-blue (mild) markers, scanline backgrounds, and glassmorphic panels.

3. **Smart Self-Assessment Test**
   - A full-screen, distraction-free modal that translates the 13 clinical dimensions into indirect, behavioral questions (e.g., *Reality Orientation*, *Attachment Security*).
   - Users provide severity (None, Mild, Severe) and contextual notes.

4. **LUMAX Emulation Profile & Auto-Mirroring**
   - **Manual Override**: Users can select any of the 40 psychiatric profiles for JEN to emulate via `LocalBrain.setPersona()`.
   - **Auto-Mirror Mode**: Users can grant "Consent for Adaptive Behavior". Upon submitting a self-assessment, the results are sent to JEN with explicit instructions to mirror the user's mindset, creating a deeply resonant and empathetic connection.

## Data Flow (Assessment to AI)
1. User completes the Self-Assessment Test.
2. `DiagnosisTab.ts` aggregates results and checks the `consent-adaptive` checkbox.
3. The data is formatted into a prompt within `Dashboard.ts`.
4. The prompt includes `[USER CONSENT FOR ADAPTIVE BEHAVIOR: GRANTED/DECLINED]` and specific instructions for the AI on how to adapt its "Sovereign Ego".
5. The prompt is sent to `LocalBrain.ts` or `CloudBrain`, which injects the `activePersona` into the System Prompt.

## Maintenance Notes
- If modifying the list of disorders in `diagnostic_data.json` or `data_portrait.csv`, you MUST regenerate the lexicon using `python scratch/regenerate_lexicon.py` to ensure tooltip mapping doesn't break.
- Ensure any CSS edits maintain `table-layout: fixed` to preserve the grid structure during hover animations.
