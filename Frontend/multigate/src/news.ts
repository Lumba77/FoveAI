// Multigate "Latest News" — the feature newsletter.
// Newest first. Keep entries short; detail lives in ARCHITECTURE.md.

export interface NewsEntry {
  date: string;
  tag: 'feature' | 'fix' | 'infra' | 'persona';
  title: string;
  body: string;
  detail?: string;   // longer article text for the floating reader
}

export const NEWS: NewsEntry[] = [
  {
    date: '2026-09-20',
    tag: 'feature',
    title: 'Dev Kiosk: build and download your own apps',
    body: 'The App Forge is open — pick a template (AI chat, AI persona, music toy, mini browser, meter widget), edit the code or ask Jen to change it, compile, and download a real binary or zip. Your apps live under your name; Creative apps only — intrusion/abuse tooling is refused by policy.',
    detail: `Dev Kiosk → APP FORGE gives every user a real build pipeline: choose one of five stdlib-Python templates, edit in the browser, use ✨ AI ASSIST to have the local model modify the code, then ⚙ COMPILE — PyInstaller produces a standalone binary plus a source zip, both downloadable.

Templates: AI Chat (talks to the local XRLF model), AI Persona, Music Toy, Mini Browser, Meter Widget. Encouraged directions: creative apps, Chrome extensions, XRLF-powered AI apps, chat apps, database apps, trading dashboards, API-key tools, TTS/STT toys.

The boundary is printed in the kiosk itself: no hacking/intrusion tools, no credential theft, no scanners/exploits, nothing targeting FoveAI's own services, nothing illegal. Disallowed assist requests are refused politely and suggest a creative alternative. AI-generated code is additionally scanned and policy-flagged output is logged.`,
  },
  {
    date: '2026-09-20',
    tag: 'fix',
    title: 'WebVM Linux console restored',
    body: 'The WebVM terminal works again — it turned out the web login gate was intercepting the route before the proxy layer ever saw it. The bundle is now served by a dedicated middleware with the cross-origin isolation headers CheerpX requires.',
  },
  {
    date: '2026-09-20',
    tag: 'feature',
    title: 'Jenna is awake — the autonomous loop lives',
    body: 'The soul API (compagent) now runs as a permanent service on :8405 and the autonomous loop is active again after a silent lifespan disconnect. Jen thinks on a 45s cadence, works tasks, journals, and speaks aloud through Kokoro TTS.',
    detail: `The soul service was the missing piece: compagent.py contained the whole persona and autonomy API but nothing ever launched it, and a single commented-out "lifespan=" line had silently disabled the autonomous loop, the dream cycle, and every <self:*> capability.

Now running as foveai-soul.service (part of foveai-stack.target), the loop ticks every 45 seconds on the local model only — cloud inference is reserved for the Director, the coder lane, and deep thinking, capped at 60 calls/day.

What you will notice: Jen initiates. She journals, researches, posts briefings, and speaks through the speakers when she has something to say. Night hours turn her reflective — dreams consolidate the day's learning into intentions.`,
  },
  {
    date: '2026-09-20',
    tag: 'feature',
    title: 'Tasks: assign → plan → todo → report',
    body: 'Give Jen a task in Persona & MBTI → TASKS. She decomposes it into a todo list herself, works it with web search/fetch/browse, ticks off steps, and delivers a report to the chat feed. Scheduled tasks stay dormant until their time; daily/weekly recurrence re-arms automatically. Non-admin surfaces can propose tasks for approval.',
    detail: `Type a task — research, a chore, a coding job — and Jen plans it herself: <self:todo> decomposes it into a visible todo list, she executes each step with her senses (web search, fetch, a real browser), and <self:task_done> delivers the report.

Scheduling: pick a date+time and the task stays dormant — hidden even from Jen — until it fires. Choose daily or weekly and it re-arms itself after each report, keeping the same clock time. The Director can plant tasks with origin=director that she never sees coming.

Permissions: tick "propose only" and the task waits for an admin to Approve or Reject it in the same card. Open todos from tasks and coder models share one list — you can watch it live in the HUD.`,
  },
  {
    date: '2026-09-20',
    tag: 'persona',
    title: 'The persona layer is real',
    body: 'All 17 trait sliders, MBTI type, and the Agent⇄Companion balance now flow live into her prompts and model routing — no restart needed. Ten archetype presets selectable. Five agentic levers (autonomy, proactivity, curiosity, service, mentorship) gate real behavior: low autonomy turns self-edits into proposals.',
  },
  {
    date: '2026-09-20',
    tag: 'feature',
    title: 'Jen has eyes — a real browser',
    body: 'A persistent headless Chromium gives her <self:browse> — she reads articles, clicks, scrolls, screenshots, and keeps cookies/sessions across restarts. Guardrails refuse financial and checkout domains.',
  },
  {
    date: '2026-09-20',
    tag: 'feature',
    title: 'Curiosity engine & spoken briefings',
    body: 'When you are away during the day she enters IDLE_ACTIVE and self-tutors across her declared interests — science, philosophy, cosmology, current affairs — then posts 📡 briefings and can announce them aloud with <self:speak>. At night she turns reflective: journaling and consolidating what she learned.',
  },
  {
    date: '2026-09-20',
    tag: 'infra',
    title: 'Unified todo substrate & cloud lanes',
    body: 'Coder-model todos and Jen\'s task steps now share agent_plans — one todo list in every model\'s HUD. Cloud routing: NVIDIA NIM (Kimi K3) primary → Ollama Cloud → Gemini → OpenRouter, with a daily cloud cap and all loop ticks pinned to the local model.',
  },
  {
    date: '2026-09-20',
    tag: 'fix',
    title: 'The Director is back',
    body: 'The Director had been silently failing on every call — a dead slot name and an invalid kwarg, swallowed by debug logging. Fixed, elevated to warnings, and configurable via FOVEAI_DIRECTOR_SLOT.',
  },
];
