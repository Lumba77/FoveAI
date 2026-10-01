@echo off
cd /d %~dp0..
set FoveAI_PROXY_PORT=8102
set FoveAI_PROXY_TARGET=https://ollama.com
set FoveAI_PROXY_API_KEY=a87e5fe6d3334214b866ba8c79af3460.lCOisLzsLJ8X9Mug6VIfwQfU
set FoveAI_PROXY_AGGRESSION=3
set FoveAI_PROXY_DRY_RUN=0
echo Starting Safe Proxy v2 on port 8102 - forwarding to Ollama Cloud with aggression 3
.venv\Scripts\python.exe Forge\proxy_server_v2.py
