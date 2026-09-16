# LUMAX Monetization Roadmap
> Strategy: **Open-Core + Freemium SaaS**  
> Last updated: 2026-07-14

---

## 🧭 North Star

> *"LUMAX is the AI memory layer for developer teams.  
> The tools are free. The persistent team brain is paid."*

The open-source core is the distribution engine.  
The hosted, multi-user memory layer is the business.

---

## 🟢 / 🔴 Feature Boundary (Open-Core Line)

### FREE — Always MIT Open Source

| Feature | Description |
|---|---|
| Jenna VS Code Extension | Full chat, inline completions, model switcher, memory search |
| Foveated Memory Server | Self-hosted `server.js` — single user, local |
| XRL Compression Engine | Context compression + checkpoint protocol |
| TokenSlayer | Structural code skeleton tool |
| Sleipnir Launcher | Local service orchestrator |
| MCP integrations | All current MCP server tools |
| All CLI tooling | Standalone scripts, standalone publish |

### 🔒 PAID — Jenna Cloud (Premium Tier)

| Feature | Tier | Why paid |
|---|---|---|
| **Team Memory** | Team | Shared workspace memory across multiple developers |
| **Cloud Sync** | Personal Pro | Foveated Memory synced across machines |
| **Multi-user Sessions** | Team | Concurrent Jenna sessions, shared context |
| **Memory Dashboard** | Team | Web UI — search, browse, manage team memory |
| **Longer recall horizon** | Pro + Team | Extended TF-IDF recall depth (beyond local limits) |
| **Priority model routing** | Pro + Team | Faster inference, GPU-backed cloud fallback |
| **SSO / GitHub Org auth** | Team | Enterprise auth, seat management |
| **Audit log** | Team | Who accessed what memory, when |
| **SLA + Support** | Enterprise | Dedicated support channel |

---

## 📦 Pricing Model (Proposed)

| Tier | Price | Target |
|---|---|---|
| **Free** | €0 / forever | Solo devs, hobbyists, evaluators |
| **Personal Pro** | €9/mo | Freelancers, solo professionals |
| **Team** | €19/seat/mo | Small dev teams (3–20 seats) |
| **Enterprise** | Custom | Orgs, white-label, on-prem |

> **Rule:** Never paywalling local/offline use. That kills trust.

---

## 🗺️ Three-Phase Roadmap

### Phase 1 — Foundation *(Now → 3 months)*
**Goal:** Prove value, build audience. Zero cloud cost.

- [ ] Publish Jenna to Open VSX (workflow ready ✅)
- [ ] README + landing page / GitHub social card
- [ ] `CHANGELOG.md` discipline — ship v0.1, v0.2 with release notes
- [ ] GitHub Discussions enabled — community signal
- [ ] Add GitHub Sponsors button (supplemental income, credibility signal)
- [ ] Instrument: count DAU via anonymous telemetry opt-in (VSCode `telemetry` API)

**Cloud cost: ~€0.** Everything runs locally.

---

### Phase 2 — Jenna Cloud Alpha *(3–6 months)*
**Goal:** First paying users. Minimal infra.

- [ ] Deploy Foveated Memory proxy to a single VPS (Hetzner CX21 ≈ €5/mo)
- [ ] Add auth layer: GitHub OAuth → JWT → per-user memory namespace
- [ ] Stripe integration for Personal Pro billing
- [ ] Jenna extension: detect cloud vs local mode via `jenna.cloudUrl` setting
- [ ] Memory Dashboard v1: simple Next.js app, read-only search UI
- [ ] Invite-only alpha → 20–50 users, gather feedback

**Cloud cost: €5–20/mo** (1–2 VPS instances). Covered by first 2–3 paying users.

---

### Phase 3 — Team Tier + Growth *(6–18 months)*
**Goal:** Recurring revenue, team adoption.

- [ ] Multi-user memory namespaces (workspace → org)
- [ ] Team invite flow, seat management
- [ ] Memory Dashboard v2: write, annotate, share memory entries
- [ ] Ollama/LM Studio cloud fallback routing (GPU instance on demand)
- [ ] GitHub Marketplace listing
- [ ] Enterprise: on-prem deployment guide (Docker-free — pure Node/Python)

**Cloud cost: €50–200/mo** at 50+ team seats. Self-funding by then.

---

## ☁️ Cloud Infrastructure — Honest Cost Estimate

> **Short answer: No substantial upfront investment needed.**

| Stage | Setup | Monthly | What it buys |
|---|---|---|---|
| Alpha (Phase 2 start) | €0 | €5–10 | 1× Hetzner VPS, runs server.js + Postgres |
| 10 paying Pro users | €0 | €20 | Covers costs 4× over at €9/user |
| 50 team seats | €0 | €80–150 | Load balancer + 2 VPS + managed DB |
| 200+ seats | €500 setup | €300–600 | Proper multi-region, CDN, backups |

**Stack recommendation (no vendor lock-in, low cost):**
- **VPS:** Hetzner Cloud (EU, cheap, fast) or Fly.io (free tier to start)
- **DB:** Postgres on same VPS initially → Supabase when scaling
- **Auth:** Clerk.dev (generous free tier) or self-hosted via GitHub OAuth
- **Billing:** Stripe (0 monthly cost, 1.4–2.9% per transaction)
- **Frontend:** Vercel (free tier sufficient for dashboard v1)

**Total to launch Phase 2:** ~€0 upfront, ~€5–10/mo recurring.  
First paying user covers 1–2 months of infra.

---

## 🔑 Key Risks & Mitigations

| Risk | Mitigation |
|---|---|
| "Why not just self-host?" | Make cloud 10× easier: one-click, zero config |
| OpenAI / GitHub Copilot dominance | Our moat is *memory* + local-first, not raw completion quality |
| Slow adoption | Open VSX + GitHub SEO is free distribution. Ship early. |
| Churn | Memory lock-in (benevolent): their history lives in Jenna Cloud |

---

## 🎯 Revenue Milestone Targets

| Milestone | MRR | Seats / Users |
|---|---|---|
| Ramen profitable | €500/mo | ~28 Pro or 26 team seats |
| Part-time sustainable | €2,000/mo | ~110 Pro or 2–3 small teams |
| Full-time sustainable | €5,000/mo | ~280 Pro or 5–8 teams |

---

## Next Actions (this week)

1. **Copy this file** to repo root as `MONETIZE.md`
2. **Enable GitHub Sponsors** on the `lumax` org
3. **Add telemetry stub** to Jenna extension (opt-in, anonymous install count)
4. **Register** `jenna.cloud` or similar domain (€10/yr)

---

*"Ship the free tool. Charge for the shared brain."*
