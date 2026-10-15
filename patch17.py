import sys

with open("/home/lumba/FoveAI/theme/theme_engine.py", "r") as f:
    content = f.read()

old_block = """    if "functional_aspects" in theme_data:
        print(f"⚡ FUNCTIONAL     : {theme_data.get('functional_aspects', '')}")
        
    print("="*80 + "\\n")"""

new_block = """    if "functional_aspects" in theme_data:
        print(f"⚡ FUNCTIONAL     : {theme_data.get('functional_aspects', '')}")
        
    if "requested_assets" in theme_data:
        print("-" * 80)
        print("📦 REQUESTED ASSETS (BILL OF MATERIALS):")
        for asset in theme_data["requested_assets"]:
            print(f"   - {asset.get('name')}: {asset.get('prompt')} (Transparent: {asset.get('make_transparent')})")
            
    if "requested_scripts" in theme_data:
        print("-" * 80)
        print("📜 REQUESTED TACTILE SCRIPTS:")
        for script in theme_data["requested_scripts"]:
            print(f"   - {script.get('name')}: {script.get('description')}")
            
    print("="*80 + "\\n")"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("/home/lumba/FoveAI/theme/theme_engine.py", "w") as f:
        f.write(content)
    print("Patched stdout printing!")
else:
    print("Could not find block")
