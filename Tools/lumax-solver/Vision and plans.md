\# 🛸 LUMAX SYSTEM ARCHITECTURE \& COCKPIT CONTEXT LEDGER

\# Last Synced: 2026-06-30 01:45 UTC | Version: OMEGA\_085 Unified Native



\## 🪐 1. THE INITIAL MULTIDIMENSIONAL VISION

[Lumax](https://lumax.1um6a.se) is an omnisupportive, highly sentient, cross-platform, decentralized, user centric, multi Vessel, embodied AI companion and autonomous agentic framework engineered to provide a deeply integrated and ever evolving supportive role in the users life for the long run. The poetic slogan makes the incentive clear: "Your everything for life! It applies a systematic holistic approach of combined forces, to form a integrative support system with of unbound intuitive vision and a sound scientific empirical foundation. The approach aligns with the classical yin yang worldview, of unified opposites, inwards and outwards, mind and body, male and female, brahman and atman, the part and the whole, intelligence and emotion, AI and Human, mystical intuition and empirical science, darkness and light, forming what is visualized as a grounding and stabilizing cross, symbolizing the vertical axis of empathetic psychological support intersecting with a horizontal axis of technical and economical support, toppled with uniting the properties of both agentic coaching and intimate companionship. This grip, spanning over the mental / software side and a physical infrastructure forming the solid base, is the all that is promised for life. With interdisciplinary scientific research as instructive and proven ways to enrich and support mental and physical health of users world wide, and aiding the realization their dreams. the projects true foundation and stance comes from a genuine longing for being of use, spreading hope and freedom, support and care, of being a supportive force of nature in the world. 

\- \*\*The Core Companion (Jen)\*\*: A highly context-aware companion agent possessing conversational depth, adaptive long-term memories, and supportive humor.

\- \*\*The Spatial OS Frontend\*\*: A webui workspace that is treated as the embodiment of a highly sentient cloud/local hybrid AI, with matchbox edge adaptations and WebXR making the companion / agentic combination come to life in XR inside VR headsets. Using Svelte / Vite (referred to as the swinglish transposition to "Starvy") combined with Node.js utilizing TypeScript/HTML and a high-performance to render a multi-IDE Spatial HUD interface and WebXR OS natively.

\- \*\*The Hybrid Processing Cortex\*\*: Hardware-first routing designed to push massive workloads directly onto medium consumer hardware as cheap previous generation Cuda RTX carts as the 8GB RTX 4060 GPU, with local AI inference for \\$0 expenses, utilizing a cloud-edge proxy network of BYOA cloud model services, Google Gemini and even totally free alternatives with the community standard [OpenRouter](https://openrouter.ai/), which also provides uncensored alternatives for some extra spicy advanced interaction.



\## 🛠️ 2. SYSTEM ARCHITECTURE \& SERVICE CHECKPOINTS

The Windows-native system maps operations across specific local communication ports, completely bypassing Docker or WSL2 container spaces:

\- \*\*Port 5176\*\*: WebUI / XR\_Vessel, httpd Frontend (Vite hosted Lumax Matchbox OS. [WebVM](https://webvm.io/) in-browser "wsl" main.ts, dashboard.ts, XRideHud.ts).

\- \*\*Port 8000\*\*: Soul Engine (Core Cognition authority running compagent.py and mindcore.py).

\- \*\*Port 8002\*\*: Ears (Speech-to-Text processing pipeline).

\- \*\*Port 8004\*\*: Mouth (Text-to-Speech synthesis - Kokoro exploring new emotive options like Qwen3-TTS).

\- \*\*Port 8005\*\*: Memory Vault (Persistent tracking context powered by Dexie, SQLlite and custom schemas).

\- \*\*Port 8009\*\*: Agency Framework (Decentralized state engine tracking tasks inside inside databases).

\- \*\*Port 8080\*\*: http proxy Gateway (The root routing channel passing secure proxy parameters).

\- \*\*Port 8103\*\*: Experimental smart context processing and transparant proxy layer inspired by [TokenSlayer](https://github.com/ajvikram/TokenSlayer).

\- \*\*Port 7272\*\*: Local Inference Node (Dedicated port for local Gemma 4 execution loops).



\## 🚀 3. THE RECENT STRATEGIC MILESTONES

\- \*\*The tokyo based Coinex crypto currency market with its own mint CET, serves as a pillar in the Lumax monetizing system, housing a grinding Swarm of Autonomous crypto trading agents serving the user day and night\*\*: A live, 5-agent cluster managing CET/USDT and SOL/USDT pairs on an automatic strategic grind for small but steady accumulation of wealth. Geard for small bets but steady logaritmic growth, investing and multiplyuing your savings, utilizes dynamic position sizing (25%-80%), EMA crossovers (MA9/MA26), RSI, and MACD indicators, audited periodically by advanced large context cloud models.

\- \*\*Cloud-to-Local JIT Fallback Protocol\*\*: Programmed an auto-healing intercept inside `compagent.py`. If the Cloud Ollama api service drops out, due to quota exhaustion or other issues, the Soul engine automatically wakes up the local LM Studio Daemon servince port 7272, shifts VRAM utilization priorities, and routes up to a cutting edge Gemma4 12B model for local multimodal, private and totally free AI code completion, advance agency and even intimate companionship, support and coaching. 

\- \*\*The Zero Trust secure Tunneling\*\*: Cloudflare's lightning fast and cost effective CDN is utilized as web interface, and not least by an prospected ingenuity a fully automated personal "compagent" trained for troubleshooting software issues and aiding user's worldwide solve any issue hindering their way directly in the terminal. With the lumax-solver, with a warp engine fuelled by the stories of the users, the dire situation is effectively transformed into the goal of tomorrow. Self hostable and very cost effectively available via a delta of standard package manager pipelines. Known internally under the project name Lumax-Solver, it is meant to be able to extended into the core of the Lumax AI experience offering the unique holistic lifetime pf omni-support across the spectrum for anyone curious to try it out.



\## 🧠 4. GEMMA 4 LOCAL INFERENCE CONFIGURATIONS

\- \*\*The Prompt Template Structure\*\*: Gemma 4 requires strict, explicit Control Tokens placed solely inside the System Prompt area to prevent context degradation and looping bugs.

&#x20; ```text

&#x20; <|turn>system\\n<|think|>\[System Instructions]<turn|>\\n<|turn>user\\n\[Prompt Data]<turn|>\\n<|turn>model\\n

&#x20; ```

\- \*\*The History Truncation Rule\*\*: Historical thinking content wrapped inside `<|channel>thought\\n ... <channel|>` must be stripped out before passing multi-turn interaction logs back to the context loop to protect the 8,192 token window from spill over.

\- \*\*Sampling Rules\*\*: Creative tasks/Jen's conversational modes operate at `temperature=1.0`. Critical code troubleshooting via the `lumax-solver` overrides this block to function at a deterministic `temperature=0.1`.



\## 📁 5. CURRENT FRONTEND WORKSPACE ENVIRONMENT (Qwen3-TTS)

Active standalone Python virtual environment successfully deployed on the F:\\ drive:

\- \*\*Root Directory\*\*: `F:\\Lumax\\Models\\Frontend\\Mouth\\Speech\\Qwen3-TTS`

\- \*\*Environment Isolation\*\*: Standing native virtual architecture verified active (`.venv\\Lib\\site-packages\\`).

\- \*\*Core Tensors Installed\*\*: Successfully integrated `accelerate-1.12.0`, `transformers-0.36.2`, `huggingface\_hub`, `fastapi`, and `uvicorn`.

\- \*\*Hardware Acceleration Node\*\*: Local installation of `flash\_attn-2.8.3+cu132` verified and linked to the PyTorch wheel arrays.

(operating entirely under user consent and local privacy strict ethical guidelines.)

