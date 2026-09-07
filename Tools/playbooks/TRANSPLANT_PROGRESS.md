# UI + Avatar transplant — progress ledger (7 steps)

**Purpose:** Single place for the transplant protocol, donor SHAs, folder layout, backups, and where we actually edit. Update this file when you complete a step or learn something new.

**Related:** [Methodology.md](../Methodology.md) (Donor Transplant) · saved session log: [Avatar UI transplant six-step plan](f51a8c08-fc0b-4e93-b141-19bcf7fc7f47).

If Cursor starts a fresh thread, point the model at **this file** + **Methodology** transplant section.

### Apply absolutely (two layers)

1. **Correct Godot project:** During transplant, the scene you run must be **`…\Lumax_current\Godot`** (receiver). If you open **`…\Lumax\Godot`** by habit, **your edits in `Lumax_current` will not appear** — that is usually not a cache bug, it is the wrong tree. Verify path in the editor before debugging.
2. **Guardian sync:** Run **`Lumax_current\scripts\automation\godot_guardian_sync.ps1 -Strict`** (or **`AUTOTEST_Lumax_current.ps1`**) on that same tree so a **headless import pass** refreshes **`.godot`** and you **detect if Godot silently rewrote** guarded scripts/scenes. Use this whenever “I saved but something still feels stale” **after** you have confirmed you are not in the old folder.

---

## The seven steps (authoritative)

**Why seven:** The first decision (younger vs older donor) is not optional. If you rewind in the wrong order, the second donor commit is not reachable the way you need.

| Step | What you do |
|------|----------------|
| **1. Preparation** | In git history, find a commit where **UI** is good enough and a commit where **animated avatar** is good (not T-pose lock). Record both SHAs. Then decide **which of those two commits is younger** (more recent, closer to `HEAD`) and **which is older**. You will rewind to the **younger** first, then later to the **older**. |
| **2. Copy, then first rewind** | Copy the **current** advanced tree → **`Lumax_current`** (before any git rewind). On **`Lumax`**, checkout the **younger** of the two good commits. |
| **3. First graft** | Copy the rewound **`Lumax`** tree to a **named** folder — **`Lumax_UI`** or **`Lumax_avatar`** depending on which element is “known good” at this checkout — so you always copy **from a label**, not from a vague “whatever Lumax is now.” Surgically graft from that named folder into **`Lumax_current`** until that element works there. **Backup before risky grafts:** `scripts/backup_lumax_transplant_worktree.ps1`. |
| **4. Three-folder checkpoint** | You should have: **`Lumax_current`** (receiver), **`Lumax_UI`** *or* **`Lumax_avatar`** (first named donor), and **`Lumax`** (git tree still on the first donor commit). |
| **5. Second rewind and graft** | Checkout **`Lumax`** to the **other** good commit (the **older** of the pair). Copy that tree to the **other** named folder (`Lumax_avatar` or `Lumax_UI`). Repeat surgical grafts **from that name** into **`Lumax_current`** until **UI and avatar coexist** and the scene is stable. |
| **6. Cleanup and rename** | You now have four trees: **`Lumax_current`**, **`Lumax_UI`**, **`Lumax_avatar`**, and **`Lumax`** (second checkout). Delete **`Lumax_UI`**, **`Lumax_avatar`**, and the old **`Lumax`** folder you no longer need — **only after** you are sure **`.git`** and anything else you need live in **`Lumax_current`** (or you have merged history). Rename **`Lumax_current` → `Lumax`**. |
| **7. Commit** | **`git commit`** (and push if you use a remote) so the **restored `Lumax`** is the recorded project state. Then continue (e.g. APK export). |

**Micro-graft rule:** Prefer **small, testable** changes (snippets / hunks), not blind whole-file swaps, unless you have proven compatibility.

### Mental model (easy to forget)

- **`Lumax_current`** is a **full copy of `Lumax` taken before any git rewind** on `Lumax`. It is **not** “the regressed tree”; it holds **all latest progress** while `Lumax` is the checkout you move backward in time for donors.
- **First vs second revert** follows **step 1 (younger vs older)**, not a fixed “always UI first” rule. **In this repo’s history, UI-good has been the younger commit and avatar-good the older one**, so in practice: **first** checkout on `Lumax` → **UI** state → freeze as **`Lumax_UI`**; **second** checkout → **avatar** state → freeze as **`Lumax_avatar`**. If you ever re-run step 1 and **avatar-good is younger**, the **first** named folder would be **`Lumax_avatar`** and the **second** **`Lumax_UI`** — the **names must match whichever element is good at that checkout**, not habit alone.
- Forgetting that **`Lumax_current` is pre-regress** or mixing up **which revert produced which donor** is how you end up grafting from the wrong era or “fixing” the wrong folder.

---

## Resume here — drift and Godot project path

Earlier transplant work **paused in a messy state**:

- It is **uncertain** whether every edit targeted **`Lumax_current`** or **`Lumax`**. If Godot’s **recent projects** only list **`Lumax`**, you may have been **running and editing the main repo** while another path was supposed to be the receiver — that produces **multiple divergent copies** of the same files (advanced / regressed / partially grafted).
- **From here on:** treat **`Lumax_current`** as the **receiver**. Open the Godot project from **`Lumax_current`** (add it to recent projects if needed).
- **`Lumax` today:** the main folder may reflect **only one git rewind** (or a mixed history), but **new work landed there anyway** — especially **model / soul stack configuration** (Docker, compose, cognition Python, env defaults, etc.). That work does **not** automatically exist in **`Lumax_current`** (which was snapshotted **before** regress and has not tracked those edits).
- **Bridge before more Godot grafts:** copy or merge **model-configuration and related backend changes** from **`Lumax` → `Lumax_current`** first (e.g. `docker-compose.yml`, `Dockerfile*` as you use them, `backend/Cognition/` paths you changed for models/vision, `requirements_lumax.txt`, local `*.env` / examples — whatever you actually touched for “which model runs”). Then smoke-test backends if you rely on them.
- **Working hypothesis to validate:** **UI** changes (e.g. from another model) may be what **breaks scene load**; **avatar** may still need work (T-pose / odd locked pose) after UI is stable.
- **Suggested order now:** (1) **Sync model config** from **`Lumax` → `Lumax_current`**. (2) **Check the UI inside `Lumax_current`** (run the scene, cockpit/WebUI behaviour, no crash on spawn). (3) **Only if the UI is still wrong:** keep grafting from **`Lumax_UI`** into **`Lumax_current`** — same donor you may **already have started** using; micro-graft until it works. (4) **If the UI is already fine, skip step 3** and go straight to **avatar** work: graft from **`Lumax_avatar`** as needed (animation, T-pose / locked pose).

### Where we actually are (avatar, UI, wrong folder, rays)

- **`Lumax_avatar`** is the **frozen donor** for **animation / avatar** fixes. Some of that work was mistakenly applied to **`Lumax`** instead of **`Lumax_current`**, which is why the seven-step story and the on-disk trees diverged.
- **`Lumax_current` today:** the avatar is still broadly in the **T-pose baseline** from **before** those wrong-folder copies — that is a **usable starting point** to try again **carefully**. An earlier attempt (elsewhere) **left T-pose** but landed in a **worse locked pose** (twisted hands/feet — “cerebral palsy” caricature): treat that as **over-correction**; avoid **whole-file** `avatar_controller` (or similar) swaps; use **small hunks** and test after each change.
- **UI in `Lumax_current`** can **look good** right now. **Do not** replace the **entire WebUI tree** or paste a **full donor UI node** from **`Lumax_UI` / `Lumax_avatar` / `Lumax`** unless you must — that risks regressing layout and behaviour you already like.
- **XR lasers / hit dots / what the ray collides with** live mainly outside “layout” code. Prefer surgical sources when tuning interaction:
  - **`Godot/addons/godot-xr-tools/functions/function_pointer.gd`** and **`function_pointer.tscn`** — laser modes, materials, `collide_with_bodies` / `collide_with_areas`, target dot, ray length, pointer events.
  - **`Godot/Scenes/Lumax_Core_lite.tscn`** (and related) — **instances** of pointers, collision masks, parent transforms.
  - **`Godot/Nexus/SkeletonKey.gd`** — display / camera routing that can affect **what the avatar or view sees** (watch for **black view** regressions when merging).
  - **`Godot/backend/WebUI.gd`** — mostly **layout, panels, feeds**; only touch **narrow** parts if you need **mouse_filter**, hit filters, or SubViewport-related behaviour for **pointers**. If in doubt, **diff** and port **functions**, not the whole file.
- **Order from here:** (A) Finish or verify **ray + collider + click/select-on-UI** behaviour in **`Lumax_current`** without bulldozing the WebUI. (B) Then **avatar**: copy **from `Lumax_avatar` only**, **step by step**, watching pose and camera after each graft.

---

## Machine layout (typical)

Base: `C:\Users\lumba\Program`

| Path | Role |
|------|------|
| `Lumax` | Main git working tree during the protocol (checkouts change); later replaced when step 6 completes. |
| `Lumax_current` | **Receiver** — all surgical Godot/UI/avatar edits for the transplant should target this tree while the protocol is open. |
| `Lumax_UI` | Frozen **UI donor** copy (or `git worktree`). |
| `Lumax_avatar` | Frozen **avatar donor** copy (or `git worktree`). |

---

## Donor commits (from the session that created worktrees)

- **UI donor:** `f414550` → `Lumax_UI`
- **Avatar donor:** `12111e7` → `Lumax_avatar`
- **Also discussed:** `ac7572d` (cockpit / tactile), `9c58228` (later `master`)

Re-validate with `git log` if your “good UI” / “good avatar” definitions changed. **Remember:** step 1 is about **age order** of these commits, not only their existence.

---

## What happened before (short log)

1. **`Lumax_current`** created from **`Lumax`**, including **`.git`** after a second copy pass.
2. **Worktrees / copies:** `Lumax_UI` @ `f414550`, `Lumax_avatar` @ `12111e7`.
3. **Whole-file tries** (`WebUI.gd`, `avatar_controller.gd`) hit **incompatibilities** with current nodes / signals / `SkeletonKey`.
4. **`Lumax_current`** was **re-synced from `Lumax`** (`robocopy /MIR`) to drop bad transplants.
5. **Direction:** micro-grafts. Some pose / idle work may exist only on **`Lumax`** until merged into **`Lumax_current`**.

---

## Current status (edit as you go)

**Last ledger update:** 2026-04-08

- [ ] **1** — Donor SHAs + **younger vs older** written down.
- [x] **2** — `Lumax_current` exists; donors exist (`Lumax_UI` / `Lumax_avatar`); main `Lumax` may be at various checkouts — **confirm before grafts**.
- [ ] **3** — First graft pass **complete in `Lumax_current`** (UI or avatar per your step-1 order); use **named donor only** as source.
- [ ] **4** — Three-folder layout verified while on first donor.
- [ ] **5** — Second donor checkout + second named copy + second graft pass; **UI + avatar** stable together in **`Lumax_current`**.
- [ ] **6** — Remove donor folders + old `Lumax` safely; rename **`Lumax_current` → `Lumax`**.
- [ ] **7** — Commit restored **`Lumax`**.

**Backup**

- `Lumax_current_backup_20260407_070838`

---

## Drift warning (repo vs receiver)

**`Lumax`** may contain **soul / Docker / vision / backend / model configuration** changes not present in **`Lumax_current`**. Treat **`Lumax`** as the **source of truth for that stack** until you copy it over; then **`Lumax_current`** should carry the same config while you graft UI/avatar. Alternatively finish Godot transplant first and reconcile one tree at step 6–7 — but **do not assume** the two folders match without a deliberate sync.

---

## Next actions

1. **Model stack:** if anything new landed only in **`Lumax`**, sync those files to **`Lumax_current`** again (compose, cognition, Docker — see drift section).
2. **Godot:** project root **`C:\Users\lumba\Program\Lumax_current\Godot`** — run the scene and test **XR rays** (visible laser, hit marker, buttons/sliders on WebUI respond). **`project.godot` uses `config/name="Lumax_current"`** so **`user://`** and Windows **`%APPDATA%\Godot\app_userdata\Lumax_current\`** (logs, settings) stay **separate** from the main repo’s **`…\app_userdata\Lumax\`**. If you still see only the old folder, reopen the project once from **`Lumax_current`** so the editor picks up the name. **Cache / drift guard:** before trusting that “what you edited is what runs,” run **`Lumax_current\scripts\automation\godot_guardian_sync.ps1`** (or **`Lumax_current\AUTOTEST_Lumax_current.ps1`**, which calls it with **`-Strict`**). That runs a **headless** Godot pass to refresh imports, then compares SHA256 of key scripts/scenes **before vs after**; if Godot rewrites them on disk, you get a **drift** warning (Strict **throws** so you do not start XR on a lying cache). Same idea as **`Lumax\scripts\automation\godot_guardian_sync.ps1`** / **`AUTOTEST.ps1`**, now transposed for **`Lumax_current`** with logs and reports under that tree (`build\guardian\guardian_sync_report.json`).
3. **Rays / collision only:** if interaction is still wrong, diff **`function_pointer.*`**, pointer nodes in **`Lumax_Core_lite.tscn`**, and **small** `SkeletonKey` / `WebUI` hunks — **not** a full WebUI replacement while the layout already looks good.
4. **Backup:** `scripts/backup_lumax_transplant_worktree.ps1` before avatar edits.
5. **Avatar (from `Lumax_avatar` only):** micro-graft toward **natural idle**, not another locked pose; watch **avatar camera / black view** after each change.
6. Update **Current status** and this ledger when something moves.
