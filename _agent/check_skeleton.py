import os

lines = open('repo-principia.md', 'r').readlines()
size_kb = os.path.getsize('repo-principia.md') / 1024
est_tokens = int(size_kb * 0.75)

print(f"Total lines: {len(lines)}")
print(f"Size: {size_kb:.1f} KB")
print(f"Estimated tokens: ~{est_tokens}")

# Count sections
sections = [l.strip() for l in lines if l.startswith('## ')]
print(f"\nSections ({len(sections)}):")
for s in sections:
    print(f"  {s}")

# Count skeleton files
skeletons = [l for l in lines if 'skeleton, level=deep)' in l]
print(f"\nSkeleton files: {len(skeletons)}")

# Count redundant header lines (the // filename + skeleton stats)
noise = [l for l in lines if l.strip().startswith('// ') and 'skeleton' in l]
print(f"Redundant header lines: {len(noise)}")

# Count directory tree lines
tree_start = next(i for i,l in enumerate(lines) if 'Directory Tree' in l)
tree_end = next(i for i,l in enumerate(lines) if 'Service Port Map' in l)
tree_lines = tree_end - tree_start
print(f"Directory tree lines: {tree_lines}")

# Count usage instruction lines
usage_start = next(i for i,l in enumerate(lines) if 'TokenSlayer Usage' in l)
usage_end = next(i for i,l in enumerate(lines) if 'Architecture Notes' in l)
usage_lines = usage_end - usage_start
print(f"TokenSlayer usage instruction lines: {usage_lines}")

# Count architecture notes lines
arch_start = next(i for i,l in enumerate(lines) if 'Architecture Notes' in l)
arch_lines = len(lines) - arch_start
print(f"Architecture notes lines: {arch_lines}")

# Count empty lines
empty = len([l for l in lines if l.strip() == ''])
print(f"Empty lines: {empty}")

# Count markdown code fences
fences = len([l for l in lines if l.strip().startswith('```')])
print(f"Code fences: {fences}")

# Actual token count using a rough estimate
print(f"\nBreakdown:")
print(f"  Directory tree: ~{tree_lines * 0.75:.0f} tokens")
print(f"  Service port map: ~{20 * 0.75:.0f} tokens")
print(f"  Backend skeletons: ~{len(skeletons) * 30:.0f} tokens (avg 30 lines each)")
print(f"  Usage instructions: ~{usage_lines * 0.75:.0f} tokens")
print(f"  Architecture notes: ~{arch_lines * 0.75:.0f} tokens")
print(f"  Empty/noise: ~{empty * 0.75:.0f} tokens")