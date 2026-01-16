# Implementation Plan - Windows Support & Safety Fixes

## Goal
Address critical flaws identified during the codebase review:
1.  **OS Compatibility**: Replace Linux-specific `grep` command with Python-native search for Windows support.
2.  **Safety**: Prevent `apply_fix` from destroying files by implementing code block extraction and file backups.
3.  **Correctness**: Remove hardcoded values in the context gathering logic.

## User Review Required
> [!IMPORTANT]
> **Code Extraction Strategy**: Use a regex to extract content between triple backticks (```python ... ```). If no backticks are found, we will treat the entire response as the code (fallback), but this might still be risky.

## Proposed Changes

### `context.py`
#### [MODIFY] [context.py](file:///d:/Projects/mistral-cli/context.py)
- **Replace `grep`**: Rewrite `search_in_file` to read the file line-by-line in Python and find matches. This ensures it works on Windows, macOS, and Linux.
- **Fix Hardcoded Logic**: Remove `search_in_file(file_path, "calculate_total")` and use the dynamic `function_name` derived from the `bug_description`.

### `main.py`
#### [MODIFY] [main.py](file:///d:/Projects/mistral-cli/main.py)
- **Add Backup**: Before writing to the file, copy the original to `filename.bak`.
- **Extract Code**: Implement a helper function to strip Markdown formatting (e.g., `Here is the fix: \n \`\`\`python ... \`\`\` `) and only write the code inside the block.

---

## Verification Plan

### Automated Tests
- Create a dummy file and test the new `search_in_file` function to ensure it finds lines correctly without `grep`.
- Test the `extract_code` logic with a sample mock LLM response string.

### Manual Verification
- Run the CLI on the provided `test_bug.py` (which contains the bug) on Windows.
- **Expected Result**: 
    1. It runs without `grep` errors.
    2. It creates `test_bug.py.bak`.
    3. `test_bug.py` is updated with *valid Python code*, not Markdown text.
