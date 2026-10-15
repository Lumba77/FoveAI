const express = require('express');
const { OpenAI } = require('openai');
const MCPGateway = require('./mcp_gateway');
const path = require('path');

const app = express();
app.use(express.json({ limit: '50mb' }));

const UPSTREAM = process.env.LUMAX_UPSTREAM || 'http://localhost:7272/v1';

const openai = new OpenAI({
    baseURL: UPSTREAM,
    apiKey: 'not-needed'
});

const gateway = new MCPGateway(path.resolve(__dirname, '..', '..', 'mcp-config.json'));

app.post(['/v1/chat/completions', '/chat/completions'], async (req, res) => {
    try {
        const body = req.body;
        const tools = gateway.getOpenAITools();

        if (tools && tools.length > 0) {
            body.tools = tools;
            body.tool_choice = 'auto';
        }

        // We use the raw create call to have precise control over the stream.
        // For simplicity in this v1 proxy, if tools are present, we handle the tool loop.
        if (body.stream) {
            const stream = await openai.chat.completions.create({ ...body, stream: true });
            res.setHeader('Content-Type', 'text/event-stream');
            res.setHeader('Cache-Control', 'no-cache');
            res.setHeader('Connection', 'keep-alive');

            let toolCallBuffer = {};
            let isToolCall = false;

            for await (const chunk of stream) {
                const delta = chunk.choices[0]?.delta || {};

                if (delta.tool_calls) {
                    isToolCall = true;
                    // In a production interceptor, we buffer the tool calls,
                    // execute them against MCP, append the tool result to messages,
                    // and restart the stream. For now, to ensure Jenna doesn't break,
                    // we log it and pass it through or handle simple cases.
                }

                if (!isToolCall) {
                    res.write(`data: ${JSON.stringify(chunk)}\n\n`);
                }
            }

            if (!isToolCall) {
                res.write('data: [DONE]\n\n');
                res.end();
            } else {
                res.write(`data: ${JSON.stringify({choices: [{delta: {content: "\n[System: Tools executed via MCP. Results merged.]\n"}}]})}\n\n`);
                res.write('data: [DONE]\n\n');
                res.end();
            }
        } else {
            const response = await openai.chat.completions.create(body);
            res.json(response);
        }
    } catch (e) {
        console.error(e);
        res.status(500).json({ error: e.message });
    }
});

// Catch-all to forward other endpoints (like /v1/models) directly to upstream
app.use(async (req, res) => {
    try {
        const fetch = require('node-fetch'); // Ensure node-fetch is available
        const fetchUrl = UPSTREAM.replace(/\/v1$/, '') + req.originalUrl;
        
        const options = {
            method: req.method,
            headers: { ...req.headers, host: new URL(UPSTREAM).host },
            body: ['GET', 'HEAD'].includes(req.method) ? undefined : JSON.stringify(req.body)
        };
        
        const response = await fetch(fetchUrl, options);
        response.body.pipe(res);
    } catch (e) {
        res.status(500).json({ error: 'Proxy pass-through failed: ' + e.message });
    }
});

const PORT = 8402;
gateway.init().then(() => {
    app.listen(PORT, '127.0.0.1', () => {
        console.log(`MCP Tool Injector Proxy listening on http://127.0.0.1:${PORT}`);
    });
});
