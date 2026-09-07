# CORS Proxy Setup Guide

This project includes a CORS proxy solution to enable browser-based AI API calls
without CORS blocking.

## 🎯 Problem

Browser security (CORS policy) blocks direct API calls from the frontend to AI
providers like OpenAI, Claude, and Watsonx.

## ✅ Solution

We provide **two proxy options** that work seamlessly across environments:

### 1. **Local Development** - Standalone Express Server

For local development, use the Express proxy server on port **3001**:

```bash
cd nexus-proxy
npm install
npm start
```

Server runs at: **http://localhost:3001**

### 2. **Production (Vercel)** - Serverless Function

For Vercel deployments, the proxy runs as a serverless function at:

**`/api/proxy`** (relative URL, same domain as frontend)

No separate deployment needed - Vercel automatically serves `/api/proxy.js` as a
serverless function.

## 🔧 Configuration

### Auto-Detection

The frontend **automatically detects** the environment:

- **localhost** → Uses `http://localhost:3001`
- **Production** → Uses `/api/proxy`

### Manual Override

You can manually set the proxy URL in Settings:

1. Open Settings modal
2. Check "Enable CORS Proxy"
3. Enter custom proxy URL (optional)
4. Save settings

## 📦 Deployment

### Deploying to Vercel

```bash
# Deploy the entire project (includes frontend + /api/proxy serverless function)
vercel deploy --prod
```

Vercel automatically:

- ✅ Deploys static frontend files
- ✅ Deploys `/api/proxy.js` as a serverless function
- ✅ No additional configuration needed

### Local Development

**Option A: Full Stack (Frontend + Proxy)**

Terminal 1 - Frontend:

```bash
npm run dev
# or
vercel dev
```

Terminal 2 - Proxy Server:

```bash
cd nexus-proxy
npm start
```

**Option B: Frontend Only (No Proxy)**

If you don't need AI features locally:

```bash
npm run dev
```

Just disable the proxy in settings UI.

## 🔒 Security Features

### Allowlist Protection

Both proxy implementations only allow requests to:

- ✅ `api.openai.com` (OpenAI)
- ✅ `api.anthropic.com` (Claude)
- ✅ `iam.cloud.ibm.com` (Watsonx IAM)
- ✅ `*.ml.cloud.ibm.com` (Watsonx inference)

Any other URL is blocked with HTTP 403.

### CORS Origins

**Local Server** (`nexus-proxy/server.js`):

```bash
# Allow all origins (development)
npm start

# Restrict to specific origins (production)
ALLOWED_ORIGINS=https://yourdomain.com npm start
```

**Vercel Serverless** (`api/proxy.js`):

- Currently allows all origins (`*`)
- For production, edit `/api/proxy.js` to restrict origins

## 🧪 Testing

### Test Proxy Health

**Local:**

```bash
curl http://localhost:3001/health
```

**Vercel:**

```bash
curl https://your-app.vercel.app/api/proxy -X OPTIONS
```

### Test API Call Through Proxy

```javascript
const response = await fetch('http://localhost:3001/proxy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        url: 'https://api.openai.com/v1/models',
        method: 'GET',
        headers: { Authorization: 'Bearer YOUR_KEY' },
    }),
});

console.log(await response.json());
```

## 📁 File Structure

```
3D-Avatar-Chatbot/
├── api/
│   └── proxy.js              # Vercel serverless function (production)
├── nexus-proxy/
│   ├── server.js             # Express server (local development)
│   ├── package.json          # Proxy dependencies
│   └── README.md             # Proxy documentation
├── src/
│   ├── LLMManager.js         # Frontend: proxy client logic
│   └── main.js               # Frontend: proxy configuration UI
└── index.html                # Settings UI with proxy controls
```

## 🚨 Troubleshooting

### Port Conflict (EADDRINUSE)

**Problem:** Frontend and proxy both try to use port 8080

**Solution:** The proxy now uses port **3001** by default

```bash
# Verify frontend is on 8080
npm run dev

# Verify proxy is on 3001
cd nexus-proxy && npm start
```

### CORS Error Despite Proxy

**Check:**

1. Proxy is running and healthy
2. Proxy is enabled in Settings UI
3. Proxy URL is correct (`http://localhost:3001` or `/api/proxy`)
4. API keys are valid

**Debug:**

```javascript
// In browser console
llmManager.getSettings().proxy;
// Should show: { enable_proxy: true, proxy_url: "..." }
```

### Vercel Deployment - Proxy Not Found

**Check:**

1. `/api/proxy.js` file exists
2. File exports default function
3. Redeploy: `vercel --prod`

**Test:**

```bash
curl https://your-app.vercel.app/api/proxy -X OPTIONS -v
# Should return 200 OK with CORS headers
```

## 🎓 How It Works

### Request Flow

**Without Proxy (Blocked by CORS):**

```
Browser → AI API ❌ CORS ERROR
```

**With Proxy (CORS Bypassed):**

```
Browser → Proxy → AI API ✅
        ← Proxy ← AI API ✅
```

### Implementation

1. **Frontend** sends request to proxy with target URL:

    ```javascript
    POST /proxy
    { url: "https://api.openai.com/...", headers: {...}, body: {...} }
    ```

2. **Proxy** validates URL against allowlist

3. **Proxy** forwards request to AI provider (server-to-server, no CORS)

4. **Proxy** returns response to frontend

## 📚 Additional Resources

- [Express Server Docs](nexus-proxy/README.md)
- [Vercel Serverless Functions](https://vercel.com/docs/functions)
- [LLM Manager Documentation](docs/LLM_MANAGER_README.md)

## 💡 Tips

- **Local Development:** Run proxy server in background terminal
- **Production:** No action needed, Vercel handles it
- **Testing:** Use browser DevTools Network tab to debug proxy calls
- **Security:** Never commit API keys to git

---

**Need Help?** Check the troubleshooting section or review the code in
`/api/proxy.js` and `nexus-proxy/server.js`.
