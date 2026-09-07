# File Edit Buffer — Quick Reference for Agents

## When to Use

| Scenario | Use Buffer? |
|----------|-------------|
| Multi-file refactor | ✅ YES |
| Risky/destructive edit | ✅ YES |
| Single line change | ❌ No (overhead) |
| Emergency fix | ❌ No (direct edit) |

## Python Usage (AGY/Soul)

```python
from file_edit_buffer import staging_area

# Stage changes
staging_area.stage_file(
    file_path="Forge/mesh_bus.py",
    content="# new content",
    edit_type="MODIFY"
)

# Get Librarian review
review = staging_area.librarian_review()
if review.warnings:
    print(f"Librarian warns: {review.warnings[0].message}")

# Preview
print(staging_area.preview_changes())

# Commit (with backup + rollback on failure)
results = staging_area.commit_all()
```

## API Usage (Dashboard/External)

```bash
# Stage
POST /edit/stage
{"file_path": "X", "content": "Y", "edit_type": "MODIFY"}

# Review
GET /edit/librarian-review

# Preview
GET /edit/preview

# Commit
POST /edit/commit
```

## Librarian Warnings You Might See

- `"Rumors say these files often conflict when edited together..."`
- `"Session X had similar edits, resulted in circular import..."`
- `"Missing related file Z that depends on X..."`
- `"Beware: Y is deprecated, consider Z instead..."`

## Integration Points

- **mesh_bus**: Emits `file_edits_committed` event
- **Librarian**: Auto-validates before commit
- **memory_vault**: Preserves "why" of changes

---
*See full docs in ARCHITECTURE.md Section 10*
