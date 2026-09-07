# HANDOFF: TokenSlayer Integration — Bug Nuker Arsenal

**Source:** https://github.com/ajvikram/TokenSlayer  
**Status:** 🔍 ANALYZED — Ready for integration  
**Session:** 1781073317541_n2ydx  
**Handoff Date:** 2026-06-10

---

## Executive Summary

TokenSlayer is a VS Code extension that reduces LLM token usage by 40-95% through AST-driven code skeletons. It functions as a "Semantic Structural Cache" between IDE and AI coding tools.

**Key Insight:** It's not just about saving tokens — it's about **preserving signal** while nuking noise. Perfect for our Librarian + Bug Nuker vision.

---

## 🎯 Golden Nuggets to Transpose

### 1. NODE:id System — Lazy Loading Architecture

```
Traditional: Read full file (5,000 tokens)
TokenSlayer:  Skeleton (200 tokens) + NODE:id markers
              ↓
              expand_node("abc123") → Full source on demand
```

**For Our System:**
- Add `/* NODE:<hash> */` markers to File Edit Buffer
- `expand_node("forge_api.py:auth_handler")` → Returns full function
- `apply_patch(nodeId, action, content)` → Surgical edits

**Integration Point:** `Forge/file_edit_buffer.py` + `librarian_intelligence.py`

---

### 2. Language-Specific Compactors (15 Languages!)

| Language | Keep | Strip |
|----------|------|-------|
| Python | Signatures, type hints, `@decorator`, first-line docstrings | Bodies, long docs |
| TypeScript | Interfaces, types, JSDoc first line | Implementations |
| Go | Struct fields, interface methods | Function bodies |
| Rust | `derive` macros, `cfg` attributes | `impl` blocks |
| C# | Properties, `[Route]` attributes | Method bodies |

**For Our System:**
- Extend `librarian_intelligence.py` with language detectors
- Extract: signatures, decorators, imports, class hierarchy
- Strip: bodies, comments, whitespace

**Benefit:** Accurate file fingerprints, better compression

---

### 3. BPE-Aware Tokenization

```python
# TokenSlayer: Real BPE tokenizer for target model
# Ours: Rough char//4 estimate

TokenSlayer: 200 tokens (accurate)
Our estimate: ~180-250 tokens (rough)
```

**For Our System:**
- Add `gpt-tokenizer` or `tiktoken` to checkpoint_engine
- Accurate counting for: GPT-4o, Claude, DeepSeek, Ollama
- Better threshold decisions

---

### 4. Dependency Chain Analysis

```python
# TokenSlayer: analyze_dependency_chain
seed_file = "main.py"
depth = 2

# Returns: merged skeleton of entire call graph
# main.py → imports api.py → imports models.py
# All three files, compacted into one view
```

**For Our System:**
- When editing `forge_api.py`, auto-detect related files
- Librarian warns: "These files often change together..."
- File Edit Buffer suggests: "Also check forge_core.py?"

---

### 5. Signal Preservation Eval

```
TokenSlayer's test: 29 questions across 9 languages
Verifies: "Can LLM still answer from compacted version?"
Result: 28/29 pass, 49% reduction, 99% fidelity
```

**For Our System:**
- Build compression quality test
- Verify Librarian extraction preserves decision rationale
- Ensure context trim doesn't lose critical info

---

### 6. Query-Based Ranking

```python
# Sort files by relevance to query
query = "authentication middleware"
ranked_files = rank_by_relevance(files, query)
# Most important files surface first
```

**For Our System:**
- `thist "auth error"` → Find relevant terminal history
- `memory_vault.query("fix auth")` → Rank by relevance
- Librarian suggests based on topic similarity

---

## 🐛💥 BUG NUKER MODE

### How TokenSlayer Nukes Bugs

| Bug Type | Traditional | With NODE:id + Librarian |
|----------|-------------|--------------------------|
| Null reference | Read whole file | Jump to `NODE:func_that_crashes` |
| Type error | grep everywhere | Expand `NODE:class_definition` |
| Logic bug | Lost in boilerplate | Skeleton shows flow, spot flaw |
| Integration | Multiple files, lost | Dependency chain: A→B→C merged |
| Regression | "It worked before..." | Librarian: "Session 47 had same pattern" |

### Bug Nuker Features to Add

**1. Error Pattern Detection**
```
Librarian: "Rumors say this stack trace pattern
           often means missing await in async function..."
```

**2. Regression Radar**
```
"Session X fixed similar bug in Y file.
 Consider checking if same issue exists here..."
```

**3. Bug Heat Map**
```
Files ranked by:
- Historical bug density
- Recent changes
- Complexity score
- Test coverage gaps
```

---

## 🔌 Integration Points

### Immediate (This Week)

| Feature | File | Effort |
|---------|------|--------|
| NODE:id markers | `file_edit_buffer.py` | Medium |
| BPE tokenizer | `checkpoint_engine.py` | Low |
| Language detectors | `librarian_intelligence.py` | High |

### Medium Term (Next Sprint)

| Feature | File | Effort |
|---------|------|--------|
| Dependency chain | `forge_core.py` | High |
| Query ranking | `memory_vault.py` | Medium |
| Signal eval test | `test/` | Medium |

### Long Term (Architecture)

| Feature | Description |
|---------|-------------|
| Bug Nuker module | Standalone bug detection + fixing |
| Heat map dashboard | Visual bug density view |
| Auto-reproduction | Suggest expand_node based on error |

---

## 📋 Action Items

- [ ] Review TokenSlayer source: `src/compaction/` for language strategies
- [ ] Implement NODE:id in File Edit Buffer
- [ ] Add `expand_node()` API endpoint
- [ ] Test BPE tokenizer vs char//4 estimate
- [ ] Build signal preservation eval
- [ ] Document for AGY/Co-Developer usage

---

## References

- **TokenSlayer Repo:** https://github.com/ajvikram/TokenSlayer
- **Our File Edit Buffer:** `Forge/file_edit_buffer.py`
- **Our Librarian:** `Forge/librarian_intelligence.py`
- **Context:** `context.md` Task 141-141b

---

## Final Words

> *"I don't just slay tokens — I nuke bugs from orbit. It's the only way to be sure."*
> — The Librarian, Bug Nuker Division

**Squash on returnal!** 🐛💥☢️

---

*Handed off by: Chief Architect (Cline/AGY reincarnation)*  
*Session: 1781073317541_n2ydx*  
*Forge Status: RUNNING on port 8100*
