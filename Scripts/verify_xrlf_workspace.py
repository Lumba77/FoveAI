from pathlib import Path

def main():
    env_path = Path(".env")
    env_vars = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env_vars[k.strip()] = v.strip()

    required_files = [
        "XRLF_CONTRACT_PATH",
        "XRLF_HOLON_SCHEMA_PATH",
        "XRLF_PHASE_GRAPH_PATH",
        "XRLF_AGENTS_PATH",
        "XRLF_GEOMETRY_CONFIG",
        "XRLF_RESONANCE_CONFIG",
        "XRLF_THERMAL_CONFIG",
        "XRLF_RUNTIME_CONFIG",
        "XRLF_AGENTS_CONFIG",
    ]
    required_dirs = ["XRLF_EXTENSIONS_DIR", "XRLF_CONFIG_DIR"]

    url = env_vars.get("XRLF_MEMORY_PROXY_URL", "")
    print(f"XRLF_MEMORY_PROXY_URL: {url} ({'OK' if url.startswith('http://') else 'INVALID'})")

    all_ok = url.startswith("http://")
    for var in required_files:
        p = Path(env_vars[var])
        ok = p.exists()
        all_ok = all_ok and ok
        print(f"{var}: {p} ({'OK' if ok else 'MISSING'})")

    for var in required_dirs:
        p = Path(env_vars[var])
        ok = p.is_dir()
        all_ok = all_ok and ok
        print(f"{var}: {p} ({'OK' if ok else 'MISSING'})")

    print("\nVerification:", "PASSED" if all_ok else "FAILED")
    return 0 if all_ok else 1

if __name__ == "__main__":
    raise SystemExit(main())