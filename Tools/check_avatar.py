#!/usr/bin/env python3
"""
check_avatar.py — will this avatar actually animate?

Years were lost because avatars loaded fine and then stood there like furniture.
This answers the question BEFORE you wire one up: it reports whether the file
has animation clips, mouth shapes, and a humanoid rig — and what you must do
to make it perform.

    python3 Tools/check_avatar.py path/to/avatar.vrm
    python3 Tools/check_avatar.py path/to/avatar.glb --json

Exit codes: 0 = can animate as-is, 1 = needs work (see remedy), 2 = unreadable.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

MOUTH_VRM = {"aa", "ih", "ou", "ee", "oh"}
MOUTH_ARKIT = {
    "jawOpen", "jawForward", "mouthClose", "mouthFunnel", "mouthPucker",
    "mouthLeft", "mouthRight", "mouthSmileLeft", "mouthSmileRight",
    "mouthStretchLeft", "mouthStretchRight", "mouthUpperUpLeft",
    "mouthUpperUpRight", "mouthLowerDownLeft", "mouthLowerDownRight",
}
BLINK = {"blink", "blinkLeft", "blinkRight", "eyeBlinkLeft", "eyeBlinkRight"}


def read_gltf_json(path: Path) -> dict:
    """Pull the JSON chunk out of a .gltf/.glb (binary or text)."""
    with path.open("rb") as f:
        head = f.read(4)
        if head == b"glTF":
            f.read(8)  # version + length
            while True:
                header = f.read(8)
                if len(header) < 8:
                    break
                length, ctype = struct.unpack("<II", header)
                data = f.read(length)
                if ctype == 0x4E4F534A:  # 'JSON'
                    return json.loads(data.decode("utf-8"))
                if ctype == 0:
                    continue
        f.seek(0)
        return json.loads(f.read().decode("utf-8", "ignore"))


def inspect(path: Path) -> dict:
    doc = read_gltf_json(path)
    ext = doc.get("extensions", {}) or {}
    vrm = ext.get("VRMC_vrm") or ext.get("VRM") or {}
    spec = vrm.get("specVersion") or ("1.0" if "VRMC_vrm" in ext else ("0.0" if "VRM" in ext else None))

    humanoid = (vrm.get("humanoid") or {}).get("humanBones") or []
    bone_count = len(humanoid)

    expressions = vrm.get("expressions") or {}
    preset = expressions.get("preset") or {}
    custom = expressions.get("custom") or {}

    # blendshape names from mesh extras (VRM0) or targets (glTF)
    shapes: set[str] = set()
    for mesh in doc.get("meshes", []):
        names = (mesh.get("extras") or {}).get("targetNames") or []
        shapes.update(names)
        for prim in mesh.get("primitives", []):
            count = prim.get("targets")
            if isinstance(count, list):
                shapes.update(f"target_{i}" for i in range(len(count)))
        # ARKit-style naming sometimes hides in extras
        for key in (mesh.get("extras") or {}):
            if "arkit" in key.lower() or "blendshape" in key.lower():
                shapes.add(key)

    mouth = {s for s in shapes if s in MOUTH_VRM or s in MOUTH_ARKIT}
    # VRM0 A/I/U/E/O live as single-letter target names
    if shapes & set("AIUEO"):
        mouth |= MOUTH_VRM
    blink = {s for s in shapes if s in BLINK}
    # Some exports (kuasa and friends) name shapes Fcl_MTH_A..O / Fcl_EYE_Close
    upper = {s.upper(): s for s in shapes}
    for viseme, letter in (("aa", "A"), ("ih", "I"), ("ou", "U"), ("ee", "E"), ("oh", "O")):
        for key in (f"FCL_MTH_{letter}", f"MTH_{letter}", f"FCL_{letter}"):
            if key in upper:
                mouth.add(upper[key])
    for key in ("FCL_EYE_CLOSE", "FCL_EYE_CLOSE_L", "FCL_EYE_CLOSE_R"):
        if key in upper:
            blink.add(upper[key])
    # VRM 1.0 keeps mouth/blink in the expression preset, not in mesh targets
    mouth |= {s for s in preset if s in MOUTH_VRM}
    blink |= {s for s in preset if s in BLINK}

    # plain glTF rigs (Ready Player Me, Mixamo, three.js samples) carry no VRM
    # metadata — detect the armature directly so we stop calling them unusable
    skins = doc.get("skins", []) or []
    joints = len(skins[0].get("joints", [])) if skins else 0

    morph_target_count = 0
    for mesh in doc.get("meshes", []):
        for prim in mesh.get("primitives", []):
            tgt = prim.get("targets")
            if isinstance(tgt, list):
                morph_target_count += len(tgt)

    clips = doc.get("animations", []) or []
    clip_names = [c.get("name", f"clip{i}") for i, c in enumerate(clips)]

    has_lookat = "lookAt" in vrm
    spring = any("spring" in k.lower() for k in ext)

    return {
        "file": str(path),
        "format": "VRM" if spec else "glTF/GLB",
        "vrm_spec": spec,
        "humanoid_bones": bone_count or joints,
        "skinned": bool(skins),
        "morph_targets": morph_target_count,
        "animation_clips": len(clips),
        "clip_names": clip_names,
        "mouth_shapes": sorted(mouth),
        "blink_shapes": sorted(blink),
        "expressions": sorted(list(preset) + list(custom)),
        "look_at": has_lookat,
        "spring_bones": spring,
    }


def verdict(info: dict) -> tuple[int, str]:
    can_talk = bool(info["mouth_shapes"])
    can_move = info["animation_clips"] > 0
    rigged = info["humanoid_bones"] > 0 or can_talk

    if can_move and not rigged:
        return 0, ("ANIMATES — no humanoid rig detected, but it carries "
                  f"{info['animation_clips']} animation clips, so it will move "
                  "when a clip is played. Usable as-is; mouth will not lip sync "
                  f"({info['morph_targets']} unnamed morph target(s) detected).")

    if rigged and can_talk:
        if can_move:
            return 0, ("GOOD — rigged, has mouth shapes and animation clips. "
                      "Drop it in Frontend/multigate/public/avatars/ and point "
                      "avatarUrl at it.")
        return 0, ("GOOD — rigged with mouth shapes; our procedural driver supplies "
                  "idle/body language, so animation clips are optional.")

    if rigged and can_move and not can_talk:
        return 0, ("MOVES (no lip sync) — rigged with " + str(info['animation_clips']) +
                   " animation clips, so it will animate when a clip plays, but it "
                   "has no mouth shapes. Good for testing the pipeline; not for "
                   "talking.")

    if rigged and not can_talk:
        remedy = []
        if info["humanoid_bones"] == 0 and not info["mouth_shapes"]:
            remedy.append("no rig and no mouth shapes — this is a static mesh, not an avatar")
        else:
            remedy.append("no mouth shapes — lip sync impossible on this file")
        if not can_move:
            remedy.append("no animation clips — nothing will move without procedural code")
        return 1, ("CANNOT ANIMATE AS-IS: " + "; ".join(remedy) +
                   ". Re-export as VRM 1.0 from VRoid Hub or Booth — those carry "
                   "the aa/ih/ou/ee/oh mouth shapes lip sync needs.")

    return 1, ("UNUSABLE — no humanoid rig detected. " +
               "Re-export as VRM 1.0 or GLB with an armature.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Will this avatar actually animate?")
    ap.add_argument("path", type=Path)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    if not args.path.exists():
        print(f"no such file: {args.path}", file=sys.stderr)
        return 2
    try:
        info = inspect(args.path)
    except Exception as e:
        print(f"could not read {args.path}: {e}", file=sys.stderr)
        return 2

    code, msg = verdict(info)
    if args.as_json:
        print(json.dumps({**info, "verdict": msg, "exit": code}, indent=2))
    else:
        print(f"\n  {info['file']}")
        print(f"    format            {info['format']}" + (f" (VRM {info['vrm_spec']})" if info['vrm_spec'] else ""))
        print(f"    humanoid bones    {info['humanoid_bones']}"
              + ("  (skinned rig)" if info.get('skinned') else ""))
        if info.get('morph_targets'):
            print(f"    morph targets     {info['morph_targets']}")
        print(f"    animation clips   {info['animation_clips']}"
              + (f"  {info['clip_names'][:4]}" if info["clip_names"] else ""))
        print(f"    mouth shapes      {len(info['mouth_shapes'])} {info['mouth_shapes'][:6]}")
        print(f"    blink shapes      {len(info['blink_shapes'])} {info['blink_shapes'][:4]}")
        print(f"    lookAt/spring     {info['look_at']} / {info['spring_bones']}")
        print(f"\n  → {msg}\n")
    return code


if __name__ == "__main__":
    sys.exit(main())