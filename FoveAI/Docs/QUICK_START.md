# LUMAX-lite: 5-Minute Quick Start

**For:** New workers and AI agents getting started with LUMAX-lite

---

## Prerequisites Check

Before starting, ensure you have:
- [ ] Python 3.10+ installed
- [ ] Redis server available
- [ ] Access to the LUMAX-lite repository

---

## Step 1: Start All Services (30 seconds)

```bash
cd /home/lumba/LUMAX-lite
bash Scripts/start_all_wsl2.sh
```

Wait for the message: "All services started successfully"

---

## Step 2: Verify Services Running (30 seconds)

```bash
# Quick health check for all services
for port in 8000 8002 8003 8009 8080; do
  echo -n "Port $port: "
  curl -s http://localhost:$port/health | head -c 50
  echo ""
done
```

Expected output should show JSON responses with `"status": "ok"` or similar.

---

## Step 3: Test Basic Functionality (2 minutes)

### Test Soul Service (LLM)
```bash
curl -X POST http://localhost:8000/compagent \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello, are you online?"}]}'
```

### Test Memory Service
```bash
curl http://localhost:8002/health
```

### Test Cognee Knowledge Graph
```bash
curl http://localhost:8009/health
```

### Test Web UI
Open browser to: http://localhost:8080

---

## Step 4: Access Documentation (30 seconds)

```bash
# View current status
cat uptodate.md | head -50

# View architecture
cat ARCHITECTURE.md | head -30

# View onboarding guide
cat Docs/ONBOARDING.md
```

---

## Step 5: Join MCP Server (if using Cline)

Add to VS Code Cline MCP settings:

```json
{
  "mcpServers": {
    "lumax-memory": {
      "command": "/home/lumba/LUMAX-lite/.venv/sentry/bin/python",
      "args": ["/home/lumba/LUMAX-lite/backend/Memory/cline_mcp_server.py"],
      "transportType": "stdio"
    }
  }
}
```

Then test with:
```
Use get_cognee_status to check the knowledge graph
```

---

## Common First Tasks

### Search Previous Sessions
```bash
curl -X POST http://localhost:8009/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "your topic", "topK": 5}'
```

### View Service Logs
```bash
tail -f .logs/*.log
```

### Check What's Running
```bash
ps aux | grep -E "compagent|creative|memory|cognee|web_app" | grep -v grep
```

### Check Ports in Use
```bash
ss -tlnp | grep -E "8000|8002|8003|8009|8080"
```

---

## Troubleshooting Quick Fixes

### Service Not Starting
```bash
# Kill any zombie Python processes
pkill -f "python.*compagent"
pkill -f "python.*creative"
pkill -f "python.*memory"

# Restart
bash Scripts/start_all_wsl2.sh
```

### Port Already in Use
```bash
# Find what's using the port
ss -tlnp | grep :8000

# Kill the process (replace PID)
kill -9 <PID>
```

### Redis Not Running
```bash
# Start Redis
redis-server --daemonize yes

# Verify
redis-cli ping  # Should return PONG
```

---

## Next Steps

After completing quick start:

1. **Read [ONBOARDING.md](ONBOARDING.md)** - Full onboarding guide
2. **Read [Docs/SERVICE_REFERENCE.md](SERVICE_REFERENCE.md)** - Service details
3. **Read [../uptodate.md](../uptodate.md)** - Current status
4. **Read [../ARCHITECTURE.md](../ARCHITECTURE.md)** - System architecture

---

## Getting Help

1. Check `uptodate.md` for current known issues
2. Review logs in `.logs/` directory
3. Search Cognee: `curl -X POST http://localhost:8009/api/v1/search -d '{"query": "your error"}'`
4. Log findings in `context.md`

---

*Quick Start guide - For complete documentation see Docs/ directory*