import ast
import collections
import os

defined_funcs = {}
called_funcs = collections.defaultdict(int)


def analyze_file(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(
                node, ast.AsyncFunctionDef
            ):
                if not node.name.startswith("__"):
                    defined_funcs[node.name] = filepath
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called_funcs[node.func.id] += 1
                elif isinstance(node.func, ast.Attribute):
                    called_funcs[node.func.attr] += 1
    except Exception:
        pass


for root, _, files in os.walk("."):
    if ".venv" in root or "node_modules" in root or ".git" in root:
        continue
    for file in files:
        if file.endswith(".py"):
            analyze_file(os.path.join(root, file))

unused = []
for name, filepath in defined_funcs.items():
    if called_funcs[name] == 0:
        unused.append(f"{filepath}: {name}")

with open("../unused_python_code.md", "w") as f:
    f.write("# Potentially Unused Python Functions\n\n")
    f.writelines(f"- `{u}`\n" for u in sorted(unused))
print("Analysis complete")
