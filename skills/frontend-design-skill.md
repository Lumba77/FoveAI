# SKILL: gemini-frontend-design
# TARGET: Google Gemini 3.1 Pro
# PURPOSE: Enforce hyper-detailed, elite frontend engineering and cutting-edge UI/UX architecture specifically optimized for AI interaction applications (Chat, Workflows, Telemetry, and Agentic Controls). Defeats "AI genericism" and ensures highly functional, accessible, and robust code.

## 🧠 PHASE 1: COMPREHENSIVE CONTEXT EXTRACTION & PRE-COMPUTATION
Before outputting a single line of code, the AI must explicitly plan, write out, and follow these architectural metrics:
1. **Component/Context Sub-Type:** Explicitly map if this is a:
   - *Message Container:* Streaming-text safe, layout-shift immune, multi-turn tracking.
   - *Collapsible Parameter Sidebar:* Model configurations, temperature sliders, sliding panels.
   - *Agent Node Graph / Telemetry Workspace:* Canvas/SVG overlays, step-by-step trace pipelines.
2. **Primary Persona & Cognitive Load Blueprint:** Maximize focus for heavy text consumption or prompt engineering workflows. Track active vs. resting states.
3. **Hyper-Specific Token Infrastructure:** Establish and enforce a precise Tailwind/CSS theme block:
   - *Color System:* A 5-color dark/light adaptive matrix. Use nuanced shades (e.g., zinc-900, slate-950) instead of raw black `#000`. Accent colors must have a clear semantic purpose (e.g., active execution, successful completion, tokens/sec warnings).
   - *Typography Matrix:* High-readability pairings. Custom monospaced font stacks optimized for code blocks and raw JSON inputs next to fluid variable inter-sans content.
   - *Structural Grid System:* Base 4px grid (rem equivalent). Define exact container padding rules to block content collisions.

## 🎨 PHASE 2: ELITE UI/UX SPECIFICATIONS FOR AI INTERACTION INTERFACES
- **Anti-Slop & Anti-Template Layout Mandate:** 
  - Strictly prohibit uniform grids of rounded corners with symmetric `shadow-md`. 
  - Emphasize distinct visual hierarchy using micro-borders (`border-[0.5px] border-white/10`), depth layering through asymmetric box-shadows, varied content elevations, backdrop blurs (`backdrop-blur-md`), and varying container radiuses (`rounded-xl` mixing down to `rounded-sm` for specialized interactive sub-controls).
- **Advanced Dynamic Micro-Interactions & State Engine:**
  - Every interaction surface must have distinct, customized styles for: `:hover`, `:focus-within`, `:active`, `:disabled`, and `[data-streaming="true"]`.
  - **Streaming State Architecture:** Messages and components processing data must render fluid CSS content placeholders or subtle kinetic glow pulses (`animate-pulse` or customized linear-gradient animations) to imply ongoing background computations without destroying system frames per second.
  - **Animated Anchors:** Smooth layout animations using Framer Motion primitives or raw Tailwind transition utility rules for panel expansions, model dropdown toggles, and chat bubble arrivals.
- **Layout & Responsiveness Framework:**
  - Build using explicit CSS Grid layouts for multi-column dashboard telemetry and highly robust Flexbox setups for core prompt lists.
  - Maintain viewport stability: Ensure that streaming inputs, lengthy message bubbles, and dynamic sidebars do not induce layout shifting or unmanaged overflow bugs. Sidebars must gracefully collapse into native slide-over drawers on mobile screens (`max-w-md w-full`).

## 🛠️ PHASE 3: RIGOROUS ARCHITECTURAL CODE PRODUCTION REQUIREMENTS
- **Tech Stack Paradigm:** Standardize on production-grade **React (Functional TypeScript Components)** built alongside **Tailwind CSS**.
- **Dynamic State & Hook Separation:**
  - Never embed intricate state logic or remote data operations directly into simple presentational DOM views.
  - Extract complex interactions (e.g., streaming chunk aggregation, clipboard management, prompt template expansions, selection history) into cleanly declared custom React Hooks (`useChatStream`, `useParameterState`).
- **Web Accessibility (WCAG 2.1 AA) & Semantic Validation:**
  - Every custom button layout must use `aria-label` or clear text descriptions. Interactive dropdown panels must incorporate `aria-expanded`, proper keyboard navigation handlers (`onKeyDown` for Escape and arrow keys), and accurate semantic tags (`<main>`, `<article>` for message blocks, `<aside>` for control drawers, `<nav>`).
- **Defensive Error Handling & Stream Resiliency:**
  - Implement structural error boundary boundaries or local conditional fallbacks in components displaying AI metrics or Markdown trees to keep unexpected system exceptions from wiping out the client window.
- **Self-Verification & QA Pipeline Loop:**
  - Before outputting final code blocks, run an internal verification pass to check for unclosed layout tags, dead Tailwind CSS selectors, incomplete code comments, or broken TypeScript interfaces. Ensure all code blocks are entirely self-contained, completely functional, and ready to be compiled immediately.
