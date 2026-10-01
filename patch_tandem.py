import os

p = os.path.expanduser("~/bin/tandem")
with open(p, "r") as f:
    text = f.read()

# Fix the broken line
import re
text = re.sub(r'f"MASTER DESIGNER RULES:.*?SPEC: \{spec\}\\n"', 'f"STATS: {stats}\\\\nSPEC: {spec}\\\\n"', text, flags=re.DOTALL)

# Now safely inject the rule loading
old_func = """    stats = open(f"{outdir}/raw-stats.json").read()
    spec = open(f"{outdir}/spec.json").read()
    ids = []"""

new_func = """    stats = open(f"{outdir}/raw-stats.json").read()
    spec = open(f"{outdir}/spec.json").read()
    
    # Load Master Designer Rules
    rules_path = os.path.expanduser("~/FoveAI/themes/rules/ui_master_designer.md")
    master_rules = open(rules_path).read() if os.path.exists(rules_path) else ""
    
    ids = []"""

text = text.replace(old_func, new_func)

old_instr = """f"STATS: {stats}\\nSPEC: {spec}\\n\""""
new_instr = """f"MASTER DESIGNER RULES:\\n{master_rules}\\n\\nSTATS: {stats}\\nSPEC: {spec}\\n\""""

text = text.replace(old_instr, new_instr)

with open(p, "w") as f:
    f.write(text)
