# Fix Context Window Overflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix context window overflow (131072 token limit) in the code implementation loop by capping KB size, trimming saved summaries to interface-only, and replacing full plan with compact file structure in concise messages.

**Architecture:** Three targeted changes to `workflows/agents/memory_agent_concise.py`. No new files, no new classes. Each change cuts a different token growth vector: KB accumulation, per-entry verbosity, and plan repetition.

**Tech Stack:** Python, existing project structure.

---

## Background

The context window blows up because `create_concise_messages()` constructs "clean" reset messages that are themselves too large:

- `self.initial_plan` — full YAML plan (10,000–50,000 tokens), passed verbatim every round
- `_read_code_knowledge_base()` — returns **all** accumulated summaries (~700 tokens × N files)
- Each summary entry includes 5 verbose sections when only 2 are needed downstream

By file 10–15, these together easily exceed 131,072 tokens.

## Files to Modify

- **Modify only:** `workflows/agents/memory_agent_concise.py`
  - Add `_extract_plan_skeleton()` method (~line 360, after `_extract_all_files_from_plan`)
  - `_read_code_knowledge_base()` line 1763 — cap to last 5 entries
  - `create_code_implementation_summary()` lines 1092–1102 — only save core_purpose + public_interface
  - `_create_code_summary_prompt()` line 1162 — use skeleton + truncate file content
  - `create_concise_messages()` line 1679 — use skeleton instead of full plan

---

## Task 1: Add `_extract_plan_skeleton()` helper method

**Files:**
- Modify: `workflows/agents/memory_agent_concise.py` (insert after line ~360)

This method is used by Tasks 2 and 3, so it must be added first. It extracts just the `file_structure:` YAML block from the plan—the only section the LLM needs to know what files to implement.

- [ ] **Step 1: Insert `_extract_plan_skeleton()` after `_extract_all_files_from_plan()`**

Find `def _extract_all_files_from_plan(self)` in the file. Insert the following new method immediately after that method's closing line (the line containing `return self._clean_and_validate_files(files)`):

```python
    def _extract_plan_skeleton(self) -> str:
        """
        Extract just the file_structure block from initial_plan.
        The LLM only needs the file list + purposes to decide what to implement next.
        Falls back to first 3000 chars if parsing fails.
        """
        try:
            lines = self.initial_plan.split("\n")
            skeleton_lines = []
            in_file_structure = False
            for line in lines:
                if line.startswith("file_structure:"):
                    in_file_structure = True
                    skeleton_lines.append(line)
                    continue
                if in_file_structure:
                    # Stop at the next top-level YAML key (no leading whitespace + has colon)
                    if line and not line.startswith(" ") and ":" in line:
                        break
                    skeleton_lines.append(line)
            if skeleton_lines:
                return "\n".join(skeleton_lines)
        except Exception:
            pass
        # Fallback: first 3000 chars
        suffix = "\n...(truncated)" if len(self.initial_plan) > 3000 else ""
        return self.initial_plan[:3000] + suffix
```

- [ ] **Step 2: Verify the method works on real plan files**

```bash
python3 -c "
import sys
sys.path.insert(0, '/home/kps_spark/workspace/paper2code')
from workflows.agents.memory_agent_concise import ConciseMemoryAgent

for task in ['paper_91fae459', 'paper_c777b1cf', 'paper_8352d45d']:
    task_dir = f'/home/kps_spark/workspace/paper2code/output/tasks/{task}'
    plan = open(f'{task_dir}/initial_plan.txt').read()
    agent = ConciseMemoryAgent(plan, target_directory=task_dir, code_directory=f'{task_dir}/generate_code')
    skeleton = agent._extract_plan_skeleton()
    print(f'{task}: plan={len(plan)} chars -> skeleton={len(skeleton)} chars ({100*(1-len(skeleton)/len(plan)):.0f}% reduction)')
    assert len(skeleton) > 0, 'Skeleton must not be empty'
print('All OK')
"
```

Expected output (approximate):
```
paper_91fae459: plan=3200 chars -> skeleton=280 chars (91% reduction)
paper_c777b1cf: plan=62000 chars -> skeleton=800 chars (99% reduction)
paper_8352d45d: plan=58000 chars -> skeleton=750 chars (99% reduction)
All OK
```

- [ ] **Step 3: Commit**

```bash
cd /home/kps_spark/workspace/paper2code
git add workflows/agents/memory_agent_concise.py
git commit -m "feat: add _extract_plan_skeleton() helper to ConciseMemoryAgent"
```

---

## Task 2: Cap KB to last 5 entries

**Files:**
- Modify: `workflows/agents/memory_agent_concise.py:1763-1786`

`_read_code_knowledge_base()` currently returns the entire `implement_code_summary.md`. For 20 files at ~700 tokens each that's 14,000 tokens. We only need the last 5 entries for dependency context—earlier files are less relevant for the next file being implemented.

- [ ] **Step 1: Replace `_read_code_knowledge_base()` body**

Replace the entire method body (everything inside the `try/except` block, lines 1771–1785) so the full method reads:

```python
    def _read_code_knowledge_base(self) -> Optional[str]:
        """Return at most the last 5 IMPLEMENTATION sections from implement_code_summary.md."""
        MAX_KB_ENTRIES = 5
        try:
            if not os.path.exists(self.code_summary_path):
                return None
            with open(self.code_summary_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return None

            import re
            section_pattern = r"={80}\s*\n## IMPLEMENTATION File .+?; ROUND \d+\s*\n={80}"
            boundaries = [m.start() for m in re.finditer(section_pattern, content)]
            if not boundaries:
                return content  # no sections found, return as-is (small file)

            start = boundaries[-MAX_KB_ENTRIES] if len(boundaries) >= MAX_KB_ENTRIES else boundaries[0]
            return content[start:].strip()

        except Exception as e:
            self.logger.error(f"Failed to read code knowledge base: {e}")
            return None
```

- [ ] **Step 2: Verify KB truncation on a real summary file**

```bash
python3 -c "
import re
content = open('/home/kps_spark/workspace/paper2code/output/tasks/paper_c777b1cf/implement_code_summary.md').read()
pattern = r'={80}\s*\n## IMPLEMENTATION File .+?; ROUND \d+\s*\n={80}'
boundaries = [m.start() for m in re.finditer(pattern, content)]
print(f'Total sections: {len(boundaries)}')
MAX = 5
start = boundaries[-MAX] if len(boundaries) >= MAX else boundaries[0]
trimmed = content[start:].strip()
print(f'Full KB: {len(content)} chars (~{len(content)//4} tokens)')
print(f'Capped KB: {len(trimmed)} chars (~{len(trimmed)//4} tokens)')
print(f'Reduction: {100*(1-len(trimmed)/len(content)):.0f}%')
"
```

Expected: Total sections >= 10, Reduction >= 60%.

- [ ] **Step 3: Commit**

```bash
cd /home/kps_spark/workspace/paper2code
git add workflows/agents/memory_agent_concise.py
git commit -m "fix: cap knowledge base to last 5 entries to prevent context overflow"
```

---

## Task 3: Trim KB entries to interface-only + use skeleton in summary prompt

**Files:**
- Modify: `workflows/agents/memory_agent_concise.py:1092-1102` and `1162-1166`

Each saved KB entry currently includes 5 sections. We only need `core_purpose` (1-2 sentences) + `public_interface` (function signatures). The other 3 sections are not needed by the LLM to implement the next file. Also, the summary-generation prompt passes the full plan with no truncation—replace it with the skeleton.

- [ ] **Step 1: In `create_code_implementation_summary()`, drop 3 verbose sections from saved content**

At lines 1092–1102, replace the block that builds `file_summary_content`:

```python
            # Format summary with only Implementation Progress and Dependencies for file saving
            file_summary_content = ""
            if sections.get("core_purpose"):
                file_summary_content += sections["core_purpose"] + "\n\n"
            if sections.get("public_interface"):
                file_summary_content += sections["public_interface"] + "\n\n"
            if sections.get("internal_dependencies"):
                file_summary_content += sections["internal_dependencies"] + "\n\n"
            if sections.get("external_dependencies"):
                file_summary_content += sections["external_dependencies"] + "\n\n"
            if sections.get("implementation_notes"):
                file_summary_content += sections["implementation_notes"] + "\n\n"
```

With:

```python
            # Keep only what downstream files need: purpose + public API signatures.
            # internal_dependencies, external_dependencies, implementation_notes are dropped
            # to keep KB entries compact (~150 tokens each vs ~700 tokens before).
            file_summary_content = ""
            if sections.get("core_purpose"):
                file_summary_content += sections["core_purpose"] + "\n\n"
            if sections.get("public_interface"):
                file_summary_content += sections["public_interface"] + "\n\n"
```

- [ ] **Step 2: In `_create_code_summary_prompt()`, use skeleton and truncate file content**

At lines 1161–1167 (the `**Initial Plan Reference:**` block), replace:

```python
**Initial Plan Reference:**
{self.initial_plan[:]}

**Implemented Code Content:**
```
{implementation_content[:]}
```
```

With:

```python
**File Structure Reference:**
{self._extract_plan_skeleton()}

**Implemented Code Content (truncated to 8000 chars):**
```
{implementation_content[:8000]}
```
```

- [ ] **Step 3: Commit**

```bash
cd /home/kps_spark/workspace/paper2code
git add workflows/agents/memory_agent_concise.py
git commit -m "fix: trim KB entries to public interface only, truncate summary prompt inputs"
```

---

## Task 4: Replace full plan with compact skeleton in concise messages

**Files:**
- Modify: `workflows/agents/memory_agent_concise.py:1676-1679`

This is the largest single token consumer. The `initial_plan_message` in `create_concise_messages()` embeds `self.initial_plan` verbatim. For complex papers this alone is 10,000–50,000 tokens. Replace it with the skeleton (file list + purposes only).

- [ ] **Step 1: In `create_concise_messages()`, replace `self.initial_plan` with skeleton**

At line 1676–1679, replace:

```python
        initial_plan_message = {
            "role": "user",
            "content": f"""**Task: Implement code based on the following reproduction plan**

**Code Reproduction Plan:**
{self.initial_plan}
```

With:

```python
        initial_plan_message = {
            "role": "user",
            "content": f"""**Task: Implement code based on the following reproduction plan**

**File Structure to Implement:**
{self._extract_plan_skeleton()}
```

- [ ] **Step 2: Estimate total input size for previously-failing paper**

```bash
python3 -c "
import sys
sys.path.insert(0, '/home/kps_spark/workspace/paper2code')
from workflows.agents.memory_agent_concise import ConciseMemoryAgent

task_dir = '/home/kps_spark/workspace/paper2code/output/tasks/paper_8352d45d'
plan = open(f'{task_dir}/initial_plan.txt').read()
agent = ConciseMemoryAgent(plan, target_directory=task_dir, code_directory=f'{task_dir}/generate_code')

skeleton = agent._extract_plan_skeleton()
kb = agent._read_code_knowledge_base() or ''
system_prompt_estimate = 5000  # tokens

total_chars = len(skeleton) + len(kb)
total_tokens_estimate = total_chars // 4 + system_prompt_estimate
print(f'Skeleton: {len(skeleton)} chars (~{len(skeleton)//4} tokens)')
print(f'KB (capped): {len(kb)} chars (~{len(kb)//4} tokens)')
print(f'Estimated total: ~{total_tokens_estimate} tokens')
print(f'Limit: 131072 tokens')
print(f'Headroom: {131072 - total_tokens_estimate} tokens remaining for file content + output')
"
```

Expected: total estimated tokens < 20,000, headroom > 100,000.

- [ ] **Step 3: Commit**

```bash
cd /home/kps_spark/workspace/paper2code
git add workflows/agents/memory_agent_concise.py
git commit -m "fix: use compact plan skeleton in concise messages instead of full plan"
```

---

## Summary of Token Budget After All Fixes

| Component | Before | After |
|-----------|--------|-------|
| Plan in reset messages | 10,000–50,000 tokens | ~200 tokens (skeleton) |
| Plan in summary prompt | 10,000–50,000 tokens | ~200 tokens (skeleton) |
| KB total (20 files, all sections) | ~14,000 tokens | ~750 tokens (last 5 × 2 sections) |
| File content in summary prompt | uncapped | capped at 8,000 chars (~2,000 tokens) |
| **Estimated total per reset** | **>122,000 tokens** | **~10,000 tokens** |
