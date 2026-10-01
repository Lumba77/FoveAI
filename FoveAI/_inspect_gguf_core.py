"""
_inspect_gguf_core.py — Read the TRUE GGUF metadata from inside an XRLF file.
Extracts the CORE_GGUF section and parses its GGUF header to reveal the REAL
model architecture, parameter count, and quantization — not the manifest label.
"""

import os
import shutil
import struct
import sys
import tempfile

_dev = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dev)
from formats.xrlf_parser import XRLFParser
from formats.xrlf_schema import SectionType


def parse_gguf_metadata_from_bytes(data):
    """Parse GGUF metadata from an in-memory bytes buffer (no disk write)."""
    magic = data[:4]
    if magic != b"GGUF":
        return {"magic": magic, "error": "Not a GGUF file"}
    off = 4
    version = struct.unpack_from("<I", data, off)[0]
    off += 4
    n_tensors = struct.unpack_from("<Q", data, off)[0]
    off += 8
    n_kv = struct.unpack_from("<Q", data, off)[0]
    off += 8
    kv = {}
    for _ in range(n_kv):
        klen = struct.unpack_from("<Q", data, off)[0]
        off += 8
        key = data[off : off + klen].decode("utf-8", "replace")
        off += klen
        vtype = struct.unpack_from("<I", data, off)[0]
        off += 4
        if vtype == 8:  # string
            slen = struct.unpack_from("<Q", data, off)[0]
            off += 8
            val = data[off : off + slen].decode("utf-8", "replace")
            off += slen
        elif vtype == 5:
            val = struct.unpack_from("<i", data, off)[0]
            off += 4
        elif vtype == 11:
            val = struct.unpack_from("<q", data, off)[0]
            off += 8
        elif vtype == 6:
            val = struct.unpack_from("<f", data, off)[0]
            off += 4
        elif vtype == 7:
            val = struct.unpack_from("<?", data, off)[0]
            off += 1
        elif vtype == 4:
            val = struct.unpack_from("<I", data, off)[0]
            off += 4
        elif vtype == 10:
            val = struct.unpack_from("<Q", data, off)[0]
            off += 8
        elif vtype == 9:
            atype = struct.unpack_from("<I", data, off)[0]
            off += 4
            alen = struct.unpack_from("<Q", data, off)[0]
            off += 8
            arr = []
            for _ in range(alen):
                if atype == 8:
                    sl = struct.unpack_from("<Q", data, off)[0]
                    off += 8
                    arr.append(data[off : off + sl].decode("utf-8", "replace"))
                    off += sl
                elif atype == 5:
                    arr.append(struct.unpack_from("<i", data, off)[0])
                    off += 4
                elif atype == 11:
                    arr.append(struct.unpack_from("<q", data, off)[0])
                    off += 8
                elif atype == 6:
                    arr.append(struct.unpack_from("<f", data, off)[0])
                    off += 4
                else:
                    arr.append(None)
            val = arr
        else:
            val = f"<unhandled type {vtype}>"
        kv[key] = val
    return {
        "magic": magic.decode("latin1", "replace"),
        "version": version,
        "n_tensors": n_tensors,
        "kv": kv,
    }


def parse_gguf_metadata(path):
    """Parse a GGUF file header and return key metadata (name, arch, params)."""
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic != b"GGUF":
            return {"magic": magic, "error": "Not a GGUF file"}
        version = struct.unpack("<I", f.read(4))[0]
        n_tensors = struct.unpack("<Q", f.read(8))[0]
        n_kv = struct.unpack("<Q", f.read(8))[0]
        kv = {}
        for _ in range(n_kv):
            klen = struct.unpack("<Q", f.read(8))[0]
            key = f.read(klen).decode("utf-8", "replace")
            vtype = struct.unpack("<I", f.read(4))[0]
            # GGUF value types: 0=uint8,1=int8,2=uint16,3=int16,4=uint32,
            # 5=int32,6=float32,7=bool,8=string,9=array,10=uint64,11=int64,12=float64
            if vtype == 8:  # string
                slen = struct.unpack("<Q", f.read(8))[0]
                val = f.read(slen).decode("utf-8", "replace")
            elif vtype == 5:  # int32
                val = struct.unpack("<i", f.read(4))[0]
            elif vtype == 11:  # int64
                val = struct.unpack("<q", f.read(8))[0]
            elif vtype == 6:  # float32
                val = struct.unpack("<f", f.read(4))[0]
            elif vtype == 7:  # bool
                val = struct.unpack("<?", f.read(1))[0]
            elif vtype == 4:  # uint32
                val = struct.unpack("<I", f.read(4))[0]
            elif vtype == 10:  # uint64
                val = struct.unpack("<Q", f.read(8))[0]
            elif vtype == 9:  # array
                atype = struct.unpack("<I", f.read(4))[0]
                alen = struct.unpack("<Q", f.read(8))[0]
                arr = []
                for _ in range(alen):
                    if atype == 8:  # string array
                        sl = struct.unpack("<Q", f.read(8))[0]
                        arr.append(f.read(sl).decode("utf-8", "replace"))
                    elif atype == 5:
                        arr.append(struct.unpack("<i", f.read(4))[0])
                    elif atype == 11:
                        arr.append(struct.unpack("<q", f.read(8))[0])
                    elif atype == 6:
                        arr.append(struct.unpack("<f", f.read(4))[0])
                    else:
                        arr.append(None)
                val = arr
            else:
                val = f"<unhandled type {vtype}>"
            kv[key] = val
        return {
            "magic": magic.decode("latin1"),
            "version": version,
            "n_tensors": n_tensors,
            "kv": kv,
        }


def inspect(xrlf_path):
    print("=" * 70)
    print(f"FILE: {xrlf_path}")
    print("=" * 70)
    with XRLFParser.open(xrlf_path) as p:
        hdr = p.manifest.header
        print(f"Manifest base_model_name : {hdr.base_model_name}")
        print(f"Manifest xrl_source_model: {hdr.xrl_source_model}")
        entry = p.manifest.section(SectionType.CORE_GGUF)
        if entry is None:
            print("No CORE_GGUF section!")
            return
        print(f"CORE_GGUF section size   : {entry.length / 1e9:.3f} GB")
        # Extract to temp
        tmp = tempfile.mkdtemp(prefix="gguf_core_")
        try:
            gguf = p.extract_gguf(os.path.join(tmp, "core.gguf"), show_progress=False)
            meta = parse_gguf_metadata(gguf)
            print("\n--- TRUE GGUF metadata ---")
            print(f"GGUF version: {meta.get('version')}")
            print(f"N tensors   : {meta.get('n_tensors')}")
            kv = meta.get("kv", {})
            for k in [
                "general.name",
                "general.architecture",
                "general.file_type",
                "general.size_label",
                "general.finetune",
                "general.base_model",
                "gemma.context_length",
                "qwen2.context_length",
                "qwen2moe.context_length",
                "llama.context_length",
                "gemma.block_count",
                "qwen2.block_count",
                "llama.block_count",
                "gemma.embedding_length",
                "qwen2.embedding_length",
                "llama.embedding_length",
                "gemma.attention.head_count",
                "general.quantization_version",
                "general.alignment",
            ]:
                if k in kv:
                    print(f"  {k}: {kv[k]}")
            print(f"\nAll metadata keys ({len(kv)}):")
            for k in sorted(kv.keys()):
                v = kv[k]
                if isinstance(v, list) and len(v) > 8:
                    v = v[:8] + ["..."]
                print(f"  {k}: {v}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "qwen4b-concise-v1.0.xrlf"
    inspect(os.path.join(_dev, target))
