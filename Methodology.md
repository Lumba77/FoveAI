# Methodology (Lumax Playbook)

Living document for the problem-solving methods we use, discover, and refine.

## How to use this file

- Add new methods as soon as they prove useful.
- Keep each method practical: when to use, exact steps, and failure signals.
- Prefer reversible workflows and small, testable changes.

---

## 1) Donor Transplant Protocol (your method)

**What it is**  
Use known-good code from older commits as "donors", then transplant incrementally into the current codebase.

**Best for**  
Recurring regressions with many interacting systems (UI + avatar + XR + backend).

**Where to edit during the 6-step flow**  
- **`Lumax_current`** = the working tree you graft into until the protocol finishes.  
- **`Lumax`** may be **git-reset** to donor commits (UI, then avatar) while donors like **`Lumax_UI` / `Lumax_avatar`** exist as worktrees or renamed copies.  
- After **step 6**, the healed **`Lumax_current`** is renamed back to **`Lumax`** (and committed).  
- Tools/agents should treat **`Lumax_current` as the default save path** whenever you say you are *in* the transplant steps.

**Backup rule (before each risky graft)**  
Take a timestamped copy of **`Lumax_current`** so a bad snippet does not strand you. From the main repo:

`scripts/backup_lumax_transplant_worktree.ps1`

Produces `Lumax_current_backup_YYYYMMDD_HHMMSS` next to `Lumax_current` (includes `.git` unless you pass `-ExcludeGit`).

**Progress ledger** — update as you complete steps: [ops/playbooks/TRANSPLANT_PROGRESS.md](ops/playbooks/TRANSPLANT_PROGRESS.md).

**Apply always (Godot path + guardian)**  
While the transplant is open, **most “my edits don’t show in the scene” confusion is the wrong project folder** — e.g. Godot still opening **`Lumax/Godot`** instead of **`Lumax_current/Godot`**. Pin **`Lumax_current`** in recent projects and **check the window title / project path** before you trust what you see.  
**Also** run **`scripts/automation/godot_guardian_sync.ps1`** on the **same** tree you are editing (`Lumax_current` copy lives under `Lumax_current\scripts\automation\`; use **`-Strict`** when you need a hard stop if Godot rewrites guarded files after a headless import refresh). That catches **cache/drift on disk**; it does **not** fix opening the other folder — you need **both** habits.

**Steps**
1. Create a full safety copy (`Lumax_current`) from the advanced tree.
2. Identify donor commits (UI donor, avatar donor).
3. Copy only small code units (not full folders/files unless required).
4. Align surrounding paths/signals/nodes to current architecture.
5. Smoke-test after every graft.
6. Keep/revert each graft based on evidence.

**Core rule**  
Transplant behavior, not historical assumptions.

---

## 2) Regression Archaeology (Git history analysis)

**What it is**  
Read commit history to reconstruct when behavior changed and why.

**Best for**  
"It used to work" bugs where current state is too complex to reason about directly.

**Steps**
1. Search commit messages around the affected area.
2. Inspect touched files in candidate commits.
3. Build a shortlist: "likely good", "likely breaking", "bridge commits".
4. Validate assumptions with small tests, not guesses.

---

## 3) Feature-Gate Stabilization

**What it is**  
Add temporary exported booleans to disable risky startup paths.

**Best for**  
Crashes during boot/initialization where multiple timers/signals race.

**Pattern**
- Add gate: `@export var <feature>_enabled: bool = false`
- Wrap risky path with `if <feature>_enabled:`
- Re-enable one gate at a time after stability is confirmed.

**Benefit**  
Converts one hard crash into a sequence of manageable experiments.

---

## 4) Incremental Smoke Testing

**What it is**  
Run a fast standard validation after each change.

**Best for**  
High-risk code paths (animation, XR, startup wiring).

**Default checks**
- Headless editor load (`--editor --quit --headless`)
- Short run smoke (`--quit-after ...`) when meaningful
- Scan logs for crash signatures/backtraces

**Rule**  
Never stack multiple high-risk edits before a smoke check.

---

## 5) Log Triangulation (Context + Runtime + Engine)

**What it is**  
Diagnose with three sources together:

- `context.md` / `context2.md`: intent and what was attempted
- `user://logs/lumax_diagnostic.log`: app-level runtime (`LogMaster`)
- `user://logs/godot.log`: engine/runtime details

**Best for**  
Complex failures where one log stream is incomplete.

---

## 6) Contract-Check Method (signals, node paths, scene shape)

**What it is**  
Treat cross-script expectations as contracts:
- signal names
- node paths
- animation library names
- expected child nodes

**Best for**  
Transplants between versions where architecture drift happened.

**Checklist**
- Verify every connected signal exists.
- Verify every hardcoded node path exists.
- Verify expected animation keys/libraries exist before `play()`.

---

## 7) Rollback-First Mindset

**What it is**  
Always preserve a known-good recovery point before risky work.

**Best for**  
Large refactors, scene graph surgery, or repeated unstable runs.

**Practice**
- Snapshot copy first.
- Make small edits.
- If uncertainty rises, revert only the latest graft.

---

## Method entry template (for new discoveries)

```md
## <Method Name>
**What it is**
...

**Best for**
...

**Steps**
1. ...
2. ...

**Failure signals**
- ...

**Notes**
- ...
```

