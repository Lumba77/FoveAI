
file_path = r"c:\Users\danie\program\LUMAX\Tools\foveated-memory\server.js"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 1. Inject MCPGateway require at line 58
new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    if "const WT_EXE =" in line:
        new_lines.append(
            "\n// ── MCP Gateway Init ────────────────────────────────────────────────────────\n"
        )
        new_lines.append("const MCPGateway = require('./mcp_gateway');\n")
        new_lines.append(
            "const mcpGateway = new MCPGateway(path.resolve(__dirname, '..', '..', 'mcp-config.json'));\n"
        )

lines = new_lines

# 2. Inject initialization before _server.listen
new_lines = []
for i, line in enumerate(lines):
    if "_server.listen(config.proxy_port" in line:
        new_lines.append("mcpGateway.init().then(() => {\n")
        new_lines.append(line)
    elif "const _dashboardServer = dashboardApp.listen" in line:
        new_lines.append(line)
        # Assuming the end of _server.listen is somewhere before this, wait, this is tricky.
        # It's better to just close the .then() at the end of the file, but server.js is long.
        # Let's just use top-level await if Node version supports it, or an IIFE for the whole listen block.
    else:
        new_lines.append(line)

# Let's use a more precise patch:
# Find _server.listen(config.proxy_port, '127.0.0.1', () => {
# and replace it with:
# mcpGateway.init().then(() => {
#     _server.listen(config.proxy_port, '127.0.0.1', () => {
# Find the closing of _server.listen... wait, it's easier to just wrap the whole end of the file.

with open("patch.js", "w", encoding="utf-8") as f:
    f.writelines(lines)
