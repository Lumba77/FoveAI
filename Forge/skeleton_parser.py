import os
import ast
import json
from typing import Dict, List, Optional, Tuple

class SkeletonParser:
    """Parses python files into structural skeletons using AST."""
    
    def __init__(self):
        self.node_store: Dict[str, Dict] = {}
        self.node_counter = 0
    
    def _get_node_id(self) -> str:
        self.node_counter += 1
        return f"NODE_{self.node_counter:04d}"
    
    def parse_file(self, filepath: str) -> str:
        if not os.path.exists(filepath):
            return f"Error: File not found {filepath}"
            
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            
        if not filepath.endswith('.py'):
            # For non-python files, just return the first few lines
            lines = content.splitlines()
            return "\n".join(lines[:50]) + ("\n... [truncated]" if len(lines) > 50 else "")
            
        try:
            tree = ast.parse(content)
            lines = content.splitlines()
        except SyntaxError:
            return "Error: Syntax error in file."
            
        skeleton_lines = []
        
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                node_id = self._get_node_id()
                start_line = node.lineno - 1
                end_line = node.end_lineno
                
                # Extract the signature/header (up to the colon)
                sig_lines = []
                for i in range(start_line, end_line):
                    sig_lines.append(lines[i])
                    if lines[i].strip().endswith(':'):
                        break
                        
                sig = "\n".join(sig_lines)
                
                # Store the full body
                self.node_store[node_id] = {
                    "filepath": filepath,
                    "name": node.name,
                    "type": type(node).__name__,
                    "body": "\n".join(lines[start_line:end_line])
                }
                
                skeleton_lines.append(f"{sig}\n    # /* EXPAND:{node_id} */")
                
                # If it's a class, we might want its methods too, but for simplicity
                # we just show the class header. TokenSlayer prunes inner bodies.
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                skeleton_lines.append(lines[node.lineno - 1])
            elif isinstance(node, ast.Assign):
                # Just add top level assignments as they might be constants
                skeleton_lines.append(lines[node.lineno - 1])
                
        return "\n".join(skeleton_lines)
        
    def expand_node(self, node_id: str) -> str:
        if node_id in self.node_store:
            return self.node_store[node_id]["body"]
        return f"Error: Node {node_id} not found."

global_parser = SkeletonParser()
