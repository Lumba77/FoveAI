$ErrorActionPreference = 'Stop'
$p = Resolve-Path 'server.js'
$c = [IO.File]::ReadAllText($p)

$anchor = "    writeEnv(out.join('\n'));`r`n}`r`n"
$anchorLF = "    writeEnv(out.join('\n'));`n}`n"

$helperLines = @(
'',
'// ── Atomic active-model-alias synchronization ────────────────────────────────',
'// The active model is mirrored across several env aliases',
'// (LUMAX_MODEL_LOCAL_ID, LUMAX_MODEL_ACTIVE_ID, LOCAL_LLM_MODEL,',
'// LUMAX_MODEL_ID). If any controller writes only one of them, the others go',
'// stale and different readers resolve different models ("contest between two',
'// models"). This single helper writes ALL aliases to the same value so they can',
'// never drift apart. LUMAX_MODEL_DORMANT_ID is deliberately NOT touched (it is',
'// meant to stay a separate lightweight model used by dormant/sleep mode).',
"const ACTIVE_MODEL_ALIASES = ['LUMAX_MODEL_LOCAL_ID', 'LUMAX_MODEL_ACTIVE_ID', 'LOCAL_LLM_MODEL', 'LUMAX_MODEL_ID'];",
'',
'function syncActiveModel(modelId) {',
"    const clean = String(modelId).trim() || 'qwopus3.5-9b-coder-mtp-moq';",
'    for (const alias of ACTIVE_MODEL_ALIASES) {',
'        setEnvVar(alias, clean);',
'        process.env[alias] = clean;',
'    }',
'    // Vision flags follow the model type (coder = text-only)',
"    const isCoder = clean.includes('qwopus') || clean.includes('coder');",
"    setEnvVar('LUMAX_LOCAL_VISION', isCoder ? 'false' : 'true');",
"    setEnvVar('LUMAX_LOCAL_VISION_ENABLED', isCoder ? 'false' : 'true');",
"    setEnvVar('LUMAX_GGUF_NATIVE_VISION', isCoder ? 'false' : 'true');",
'    return clean;',
'}',
''
)
$helper = ($helperLines -join "`r`n")

if ($c.Contains($anchor)) {
    $c = $c.Replace($anchor, $anchor + $helper)
    Write-Output 'INSERTED after setEnvVar (CRLF)'
} elseif ($c.Contains($anchorLF)) {
    $c = $c.Replace($anchorLF, $anchorLF + $helper)
    Write-Output 'INSERTED after setEnvVar (LF)'
} else {
    Write-Output 'ANCHOR NOT FOUND'
    $i = $c.IndexOf('writeEnv(out.join')
    Write-Output ('writeEnv index: ' + $i)
    if ($i -ge 0) { Write-Output $c.Substring($i, 120) }
    exit 1
}

[IO.File]::WriteAllText($p, $c)
Write-Output 'HELPER ADDED'
