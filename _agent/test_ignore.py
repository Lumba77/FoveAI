import fnmatch

patterns = [l.strip() for l in open('.tokenslayer-ignore') if l.strip() and not l.startswith('#')]
print(f"Loaded {len(patterns)} ignore patterns")

tests = [
    ("Scripts/AUTOTEST_Lumax_current.ps1", True),   # should match Scripts/AUTOTEST_*.ps1
    ("Scripts/generate_repo_skeleton.py", False),     # should NOT match (our generator)
    ("Tools/foveai_stress_meter/stress_meter.py", True), # should match Tools/foveai_stress_meter/
    ("Backend/Cognition/soul_core.py", False),        # should NOT match
    ("Frontend/3D_Avatar_Chatbot/index.html", True),  # should match Frontend/3D_Avatar_Chatbot/
    ("Forge/scratch/TokenSlayer/standalone/tokenslayer.js", False), # should NOT match
    ("Scripts/tokenslayer-scan-repo.cmd", False),     # should NOT match (our script)
    ("Backend/HomeAssistant/configuration.yaml", True), # should match Backend/HomeAssistant/
    ("Tools/foveai-solver/cli.js", True),              # should match Tools/foveai-solver/
    ("Backend/Memory/memory_service.py", False),       # should NOT match
]

all_pass = True
for path, expected_ignored in tests:
    matched = any(fnmatch.fnmatch(path, p) for p in patterns)
    status = "IGNORED" if matched else "KEEP"
    expected = "IGNORED" if expected_ignored else "KEEP"
    result = "PASS" if matched == expected_ignored else "FAIL"
    if result == "FAIL":
        all_pass = False
    print(f"  [{result}] {status}: {path} (expected {expected})")

print(f"\n{'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")