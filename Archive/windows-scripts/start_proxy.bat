@echo off
cd /d %~dp0..
set FoveAI_PROXY_PORT=8102
set FoveAI_PROXY_TARGET=https://ollama.com
set FoveAI_PROXY_API_KEY=%FoveAI_PROXY_API_KEY%
set FoveAI_PROXY_AGGRESSION=3
set FoveAI_PROXY_DRY_RUN=0
echo Starting Safe Proxy v2 on port 8102 - forwarding to Ollama Cloud with aggression 3
.venv\Scripts\python.exe Forge\proxy_server_v2.py
