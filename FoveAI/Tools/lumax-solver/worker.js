export default {
  async fetch(request, env) {
    // 1. CORS Preflight handling for easy client connection
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, Authorization"
        }
      });
    }

    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    try {
      const { currentDirFiles, terminalLog } = await request.json();

      // 2. Instruct the LLM exactly how to respond
      const systemPrompt = `You are Lumax Solver, an elite systems automation agent.
Analyze the provided terminal error logs and directory snapshot.
You must diagnose the issue and output your solution strictly as a raw JSON object with this schema:
{
  "explanation": "A short description of the root cause in under 20 words.",
  "fileEdits": [
    { "filePath": "relative/path/to/file.ext", "content": "Full text of the corrected file" }
  ],
  "commands": ["npm install exact-package", "npm run dev"]
}
Do not include markdown tags like \`\`\`json or text formatting outside the object. Only return the raw JSON object.`;

      // 3. Fire the request directly into Cloudflare's edge Workers AI framework
      const aiResponse = await env.AI.run('@cf/meta/llama-3-8b-instruct', {
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: `FILES:\n${JSON.stringify(currentDirFiles)}\n\nLOGS:\n${terminalLog}` }
        ]
      });

      // 4. Return the response back to your local command line client
      return new Response(aiResponse.response, {
        headers: { 
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*"
        }
      });

    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), { 
        status: 500,
        headers: { "Access-Control-Allow-Origin": "*" }
      });
    }
  }
};
