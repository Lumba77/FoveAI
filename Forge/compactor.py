"""
compactor.py - AST-driven code skeletonization and node-level mapping.
"""

import ast
import hashlib
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("forge.compactor")


# ── Global Node Registry ───────────────────────────────────────────

class NodeRegistry:
    """Thread-safe global registry mapping node hashes to original source code."""
    
    def __init__(self):
        self._registry: Dict[str, Dict[str, Any]] = {}
        
    def register(self, file_path: Path, node_name: str, original_content: str, language: str) -> str:
        """Register a code block and return its unique node ID hash."""
        node_hash = hashlib.md5(original_content.encode("utf-8")).hexdigest()[:8]
        self._registry[node_hash] = {
            "file_path": str(file_path.resolve()),
            "node_name": node_name,
            "original_content": original_content,
            "language": language
        }
        return node_hash
        
    def get(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self._registry.get(node_id)
        
    def clear(self):
        self._registry.clear()


# Global Singleton Registry
node_registry = NodeRegistry()


# ── Python AST Visitor ──────────────────────────────────────────────

class PythonNodeExtractor(ast.NodeVisitor):
    def __init__(self, source_lines: List[str]):
        self.source_lines = source_lines
        self.nodes: List[Dict[str, Any]] = []
        self._in_function = False
        
    def visit_FunctionDef(self, node):
        was_in_func = self._in_function
        if not was_in_func:
            self._in_function = True
            self.handle_func(node)
        self.generic_visit(node)
        self._in_function = was_in_func
        
    def visit_AsyncFunctionDef(self, node):
        was_in_func = self._in_function
        if not was_in_func:
            self._in_function = True
            self.handle_func(node)
        self.generic_visit(node)
        self._in_function = was_in_func
        
    def handle_func(self, node):
        if not node.body:
            return
            
        body_start_line = node.body[0].lineno
        body_end_line = getattr(node, "end_lineno", len(self.source_lines))
        
        docstring = ast.get_docstring(node)
        actual_body_start = body_start_line
        
        # If there's a docstring and there are subsequent statements, preserve docstring
        if docstring and len(node.body) > 1:
            actual_body_start = node.body[1].lineno
            
        body_lines = self.source_lines[actual_body_start-1:body_end_line]
        body_text = "".join(body_lines)
        
        if len(body_lines) < 2:
            return
            
        # Calculate indentation
        first_line = body_lines[0]
        indent = len(first_line) - len(first_line.lstrip())
        if indent == 0:
            indent = 4
            
        self.nodes.append({
            "start_line": node.lineno,
            "end_line": node.end_lineno,
            "body_start": actual_body_start,
            "body_end": body_end_line,
            "name": node.name,
            "body_text": body_text,
            "indent": indent
        })


# ── TS/JS Brace Matcher Helper ──────────────────────────────────────

def find_matching_brace(text: str, start_index: int) -> int:
    """Finds the index of the matching closing brace, respecting comments and strings."""
    depth = 0
    in_string = False
    string_char = None
    in_comment = False
    comment_type = None
    i = start_index
    n = len(text)
    
    while i < n:
        char = text[i]
        
        if in_comment:
            if comment_type == "line" and char == "\n":
                in_comment = False
            elif comment_type == "block" and char == "/" and i > 0 and text[i-1] == "*":
                in_comment = False
            i += 1
            continue
            
        if in_string:
            if char == string_char and (i == 0 or text[i-1] != "\\"):
                in_string = False
            i += 1
            continue
            
        if char == "/" and i + 1 < n and text[i+1] == "/":
            in_comment = True
            comment_type = "line"
            i += 2
            continue
        elif char == "/" and i + 1 < n and text[i+1] == "*":
            in_comment = True
            comment_type = "block"
            i += 2
            continue
            
        if char in ('"', "'", "`"):
            in_string = True
            string_char = char
            i += 1
            continue
            
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


# ── Compactor Engine ────────────────────────────────────────────────

class Compactor:
    """Main skeletonization engine."""
    
    @staticmethod
    def detect_language(file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix == ".py":
            return "python"
        elif suffix in (".ts", ".tsx"):
            return "typescript"
        elif suffix in (".js", ".jsx"):
            return "javascript"
        return "generic"
        
    def compact(self, file_path: Path, content: str) -> str:
        """Compact file content and register original blocks."""
        lang = self.detect_language(file_path)
        if lang == "python":
            return self._compact_python(file_path, content)
        elif lang in ("typescript", "javascript"):
            return self._compact_js_ts(file_path, content, lang)
        return content
        
    def _compact_python(self, file_path: Path, content: str) -> str:
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logger.warning(f"Syntax error parsing {file_path} for compaction: {e}")
            return content
            
        lines = content.splitlines(keepends=True)
        extractor = PythonNodeExtractor(lines)
        extractor.visit(tree)
        
        # Process replacements in reverse line-number order to preserve line indices
        sorted_nodes = sorted(extractor.nodes, key=lambda n: n["body_start"], reverse=True)
        
        new_lines = lines.copy()
        for node in sorted_nodes:
            node_id = node_registry.register(file_path, node["name"], node["body_text"], "python")
            
            # Format node placeholder with correct indentation
            indent_str = " " * node["indent"]
            placeholder = f"{indent_str}# NODE:{node_id}\n{indent_str}pass\n"
            
            # Replace node body
            start_idx = node["body_start"] - 1
            end_idx = node["body_end"]
            new_lines[start_idx:end_idx] = [placeholder]
            
        return "".join(new_lines)
        
    def _compact_js_ts(self, file_path: Path, content: str, lang: str) -> str:
        # Simple regex to find class methods and functions
        # Excludes keywords like if, for, while, switch, constructor
        pattern = re.compile(
            r"\b(function\s+\w+|const\s+\w+\s*=\s*(?:\([^)]*\)|[^=\s]+)\s*=>|(?!if|for|while|switch|catch|constructor\b)\b[a-zA-Z_]\w*\s*\([^)]*\))\s*(?::\s*[^{]+)?\s*\{",
            re.MULTILINE
        )
        
        replacements = []
        for match in pattern.finditer(content):
            start_bracket = match.end() - 1
            end_bracket = find_matching_brace(content, start_bracket)
            
            if end_bracket != -1:
                body_start = start_bracket + 1
                body_end = end_bracket
                body_text = content[body_start:body_end]
                
                # Only compact functions with meaningful bodies (e.g. > 10 chars)
                if len(body_text.strip()) > 15:
                    replacements.append((body_start, body_end, match.group(1)))
                    
        # Apply replacements in reverse order
        replacements.sort(key=lambda r: r[0], reverse=True)
        
        result = content
        for start, end, name in replacements:
            body_text = content[start:end]
            node_id = node_registry.register(file_path, name.strip(), body_text, lang)
            placeholder = f" /* NODE:{node_id} */ "
            result = result[:start] + placeholder + result[end:]
            
        return result

    def expand_skeleton(self, skeleton_content: str) -> str:
        """Expand all node IDs found in a skeleton content string."""
        # Find Python node markers: # NODE:1a2b3c4d\n    pass
        # We also support a simpler form: # NODE:1a2b3c4d
        def py_repl(match):
            node_id = match.group(1)
            reg = node_registry.get(node_id)
            if reg:
                return reg["original_content"]
            return match.group(0)
            
        # Match "# NODE:1a2b3c4d" followed optional indent + pass/comments
        content = re.sub(r"[ \t]*# NODE:([a-f0-9]{8})(?:\n[ \t]*pass)?", py_repl, skeleton_content)
        
        # Find JS/TS node markers: /* NODE:1a2b3c4d */
        def js_repl(match):
            node_id = match.group(1)
            reg = node_registry.get(node_id)
            if reg:
                return reg["original_content"]
            return match.group(0)
            
        content = re.sub(r"/\*\s*NODE:([a-f0-9]{8})\s*\*/", js_repl, content)
        return content
