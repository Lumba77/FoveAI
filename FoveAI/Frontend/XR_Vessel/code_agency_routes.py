"""CodeAgency API Routes — Avatar Self-Modification Backend"""

# ═══════════════════════════════════════════════════════════════════════════════
# CODE AGENCY API — Avatar Self-Modification Backend
# ═══════════════════════════════════════════════════════════════════════════════

# Import code_sheriff for safe self-modification
sys.path.insert(0, os.path.join(FoveAI_ROOT, "Mind", "Cognition"))
try:
    from code_sheriff import (
        NO_TOUCH_LIST,
        snapshot_file,
        validate_file,
    )
    from code_sheriff import (
        edit_file as sheriff_edit_file,
    )

    CODE_SHERIFF_AVAILABLE = True
except Exception as _cs_err:
    CODE_SHERIFF_AVAILABLE = False
    logger.warning(f"[CodeAgency] code_sheriff not available: {_cs_err}")

CODE_PROTECTED = [
    ".env",
    ".git/",
    "__pycache__",
    "venv/",
    "node_modules/",
    "backups/autosave/",
    ".venv/",
    "*.log",
    "*.tmp",
]


def _is_safe_path(path: str) -> bool:
    path = path.replace("\\", "/")
    if CODE_SHERIFF_AVAILABLE:
        for forbidden in NO_TOUCH_LIST:
            if forbidden in path:
                return False
    for protected in CODE_PROTECTED:
        if protected.endswith("/") and protected in path:
            return False
        if protected.startswith("*") and path.endswith(protected[1:]):
            return False
        if protected in path:
            return False
    try:
        (Path(FoveAI_ROOT) / path).resolve().relative_to(Path(FoveAI_ROOT).resolve())
        return True
    except ValueError:
        return False


@app.get("/api/code/ls")
async def code_ls(dir: str = ".", _auth: None = Depends(require_webui_login)):
    try:
        target_dir = Path(FoveAI_ROOT) / dir
        if not str(target_dir.resolve()).startswith(str(Path(FoveAI_ROOT).resolve())):
            return JSONResponse(status_code=403, content={"error": "Access denied"})
        files = []
        for item in sorted(target_dir.iterdir()):
            stat = item.stat()
            files.append(
                {
                    "path": str(item.relative_to(FoveAI_ROOT)).replace("\\", "/"),
                    "size": stat.st_size,
                    "isDir": item.is_dir(),
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        return {"files": files}
    except Exception as e:
        logger.error(f"[CodeAgency] ls failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/code/read")
async def code_read(
    path: str, maxLines: int = 500, _auth: None = Depends(require_webui_login)
):
    try:
        if not _is_safe_path(path):
            return JSONResponse(status_code=403, content={"error": "Protected path"})
        file_path = Path(FoveAI_ROOT) / path
        if not file_path.exists():
            return JSONResponse(status_code=404, content={"error": "File not found"})
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        if len(lines) > maxLines:
            content = (
                "\n".join(lines[:maxLines])
                + f"\n\n... [{len(lines) - maxLines} more lines]"
            )
        return {"content": content, "truncated": len(lines) > maxLines}
    except Exception as e:
        logger.error(f"[CodeAgency] read failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/code/write")
async def code_write(request: Request, _auth: None = Depends(require_webui_login)):
    try:
        data = await request.json()
        path, content = data.get("path", ""), data.get("content", "")
        if not _is_safe_path(path):
            return JSONResponse(
                status_code=403, content={"success": False, "message": "Protected path"}
            )
        file_path = Path(FoveAI_ROOT) / path
        if CODE_SHERIFF_AVAILABLE and file_path.exists():
            snapshot_file(str(file_path))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        validation_errors = []
        if CODE_SHERIFF_AVAILABLE:
            valid, errors = validate_file(str(file_path))
            if not valid:
                validation_errors = errors
        return {
            "success": True,
            "message": f"Wrote {len(content)} chars to {path}",
            "validationErrors": validation_errors,
        }
    except Exception as e:
        logger.error(f"[CodeAgency] write failed: {e}")
        return JSONResponse(
            status_code=500, content={"success": False, "message": str(e)}
        )


@app.post("/api/code/edit")
async def code_edit(request: Request, _auth: None = Depends(require_webui_login)):
    try:
        data = await request.json()
        path, blocks = data.get("path", ""), data.get("blocks", [])
        if not _is_safe_path(path):
            return JSONResponse(
                status_code=403, content={"success": False, "message": "Protected path"}
            )
        file_path = Path(FoveAI_ROOT) / path
        if not file_path.exists():
            return JSONResponse(
                status_code=404, content={"success": False, "message": "File not found"}
            )
        if CODE_SHERIFF_AVAILABLE:
            result = sheriff_edit_file(str(file_path), blocks)
            return result
        else:
            content = file_path.read_text(encoding="utf-8")
            for block in blocks:
                search, replace = block.get("search", ""), block.get("replace", "")
                if search in content:
                    content = content.replace(search, replace, 1)
            file_path.write_text(content, encoding="utf-8")
            return {"success": True, "message": f"Edited {path} ({len(blocks)} blocks)"}
    except Exception as e:
        logger.error(f"[CodeAgency] edit failed: {e}")
        return JSONResponse(
            status_code=500, content={"success": False, "message": str(e)}
        )


@app.get("/api/code/search")
async def code_search(
    q: str, glob: str = "*", _auth: None = Depends(require_webui_login)
):
    import fnmatch

    results = []
    try:
        base_path = Path(FoveAI_ROOT)
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [
                d
                for d in dirs
                if not any(
                    p in d
                    for p in [
                        "__pycache__",
                        "node_modules",
                        ".git",
                        "venv",
                        ".venv",
                        "backups/autosave",
                    ]
                )
            ]
            for filename in files:
                if not fnmatch.fnmatch(filename, glob):
                    continue
                filepath = Path(root) / filename
                try:
                    rel_path = filepath.relative_to(base_path)
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    lines = content.split("\n")
                    for i, line in enumerate(lines, 1):
                        if q.lower() in line.lower():
                            results.append(
                                {
                                    "file": str(rel_path).replace("\\", "/"),
                                    "line": i,
                                    "content": line[:200],
                                    "match": q,
                                }
                            )
                            if (
                                sum(
                                    1
                                    for r in results
                                    if r["file"] == str(rel_path).replace("\\", "/")
                                )
                                >= 5
                            ):
                                break
                except Exception:
                    continue
        return {"results": results[:100]}
    except Exception as e:
        logger.error(f"[CodeAgency] search failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/code/exec")
async def code_exec(request: Request, _auth: None = Depends(require_webui_login)):
    try:
        data = await request.json()
        command = data.get("command", "")
        SAFE_PREFIXES = [
            "npm run",
            "npx tsc",
            "python -m py_compile",
            "node --check",
            "git status",
            "git diff",
            "huggingface-cli download",
            "huggingface-cli",
        ]
        is_safe = any(command.strip().startswith(prefix) for prefix in SAFE_PREFIXES)
        if not is_safe:
            return JSONResponse(
                status_code=403,
                content={"success": False, "message": "Command not in safe list"},
            )
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=FoveAI_ROOT,
            timeout=120,
        )
        return {
            "success": result.returncode == 0,
            "message": result.stdout if result.returncode == 0 else result.stderr,
            "exitCode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=504, content={"success": False, "message": "Command timed out"}
        )
    except Exception as e:
        logger.error(f"[CodeAgency] exec failed: {e}")
        return JSONResponse(
            status_code=500, content={"success": False, "message": str(e)}
        )


@app.get("/api/code/git/status")
async def code_git_status(_auth: None = Depends(require_webui_login)):
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            cwd=FoveAI_ROOT,
            timeout=30,
        )
        return {"status": result.stdout, "exitCode": result.returncode}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/code/config")
async def code_config(
    section: str, key: str, _auth: None = Depends(require_webui_login)
):
    try:
        env_path = Path(FoveAI_ROOT) / ".env"
        if not env_path.exists():
            return {"value": None}
        content = env_path.read_text(encoding="utf-8")
        pattern = rf"^{re.escape(key)}\s*=\s*(.+)$"
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            return {"value": match.group(1).strip().strip('"').strip("'")}
        return {"value": None}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/code/read_image")
async def code_read_image(path: str, _auth: None = Depends(require_webui_login)):
    try:
        if not _is_safe_path(path):
            return JSONResponse(status_code=403, content={"error": "Protected path"})
        file_path = Path(FoveAI_ROOT) / path
        if not file_path.exists():
            return JSONResponse(status_code=404, content={"error": "File not found"})

        import base64
        import mimetypes

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type or not mime_type.startswith("image/"):
            return JSONResponse(status_code=400, content={"error": "Not an image file"})

        with open(file_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")

        return {
            "name": file_path.name,
            "mime_type": mime_type,
            "base64": b64_data,
            "dataUrl": f"data:{mime_type};base64,{b64_data}",
        }
    except Exception as e:
        logger.error(f"[CodeAgency] read_image failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
