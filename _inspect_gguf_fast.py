"""Fast GGUF-core inspector — reads metadata directly from the XRLF section (no disk write)."""

import os
import struct
import sys

_dev = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dev)
from formats.xrlf_parser import XRLFParser
from formats.xrlf_schema import SectionType


def parse_header(data):
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
        if vtype == 8:
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
            val = "<unhandled type %d>" % vtype
        kv[key] = val
    return {"version": version, "n_tensors": n_tensors, "kv": kv}


def inspect(xrlf_path):
    print("=" * 70)
    print("FILE: %s" % xrlf_path)
    print("=" * 70)
    with XRLFParser.open(xrlf_path) as p:
        hdr = p.manifest.header
        print("Manifest base_model_name : %s" % hdr.base_model_name)
        print("Manifest xrl_source_model: %s" % hdr.xrl_source_model)
        entry = p.manifest.section(SectionType.CORE_GGUF)
        if entry is None:
            print("No CORE_GGUF section!")
            return
        print("CORE_GGUF section size   : %.3f GB" % (entry.length / 1e9))
        head_len = min(entry.length, 16 * 1024 * 1024)
        head = bytes(p._mm[entry.offset : entry.offset + head_len])
        meta = parse_header(head)
        print("\n--- TRUE GGUF metadata (read directly from section) ---")
        print("GGUF version: %s" % meta.get("version"))
        print("N tensors   : %s" % meta.get("n_tensors"))
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
                print("  %s: %s" % (k, kv[k]))
        print("\nAll metadata keys (%d):" % len(kv))
        for k in sorted(kv.keys()):
            v = kv[k]
            if isinstance(v, list) and len(v) > 8:
                v = v[:8] + ["..."]
            print("  %s: %s" % (k, v))


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "qwen4b-concise-v1.0.xrlf"
    inspect(os.path.join(_dev, target))
