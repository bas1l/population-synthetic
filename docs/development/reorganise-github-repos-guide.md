# Reorganising GitHub repos into thematic subfolders

## Context

You have 26+ repos under `F:\GitHub\` and want to group them into thematic subdirectories (e.g. `F:\GitHub\clinical\anxiety-synthetic`). The concern is whether GitHub, Claude Code, or local tooling will break.

---

## What is safe (nothing to do)

| Thing | Why safe |
|---|---|
| **GitHub remote / history** | Git remotes are URLs (`git@github.com:…`), not local paths. Moving the folder doesn't touch them. All history, branches, and remotes survive. |
| **Claude global settings** | `C:\Users\basil\.claude\settings.json` and `settings.local.json` contain no hardcoded local paths. |
| **CLAUDE.md** | It lives inside the repo and moves with it. |
| **All scripts** | Every script uses `Path(__file__).resolve().parent.parent` — they self-locate at runtime, so they work anywhere. |
| **Config YAMLs** | `seed_manifests_manager.yaml` uses relative paths. `db_location_registry.yaml` points to OneDrive (unaffected by repo move). |
| **Claude skills** | Skills are global (`~/.claude/`), not tied to any project path. |

---

## What breaks (and what to do about it)

### 1. Editable Python install — **must fix**

`pip install -e .` writes an absolute path into your conda environment. After moving, bare imports (`from utils import …`) will silently resolve to the old (now wrong) location or fail entirely.

**Fix**: after moving each Python package, reactivate the env and reinstall:
```powershell
conda activate persona_env
pip install -e .
```

### 2. Claude project memory — **optional migration**

Claude Code derives a project memory folder from the local path using a simple encoding:
`F:\GitHub\anxiety-synthetic` → `C:\Users\basil\.claude\projects\F--GitHub-anxiety-synthetic\`

Moving a repo to a subfolder creates a new (empty) memory folder on next access and orphans the old one. Your saved memories, feedback, and session state become invisible to Claude.

**Fix** (do this before or immediately after moving):
```powershell
# Example: moving anxiety-synthetic one level deeper
Rename-Item `
  "C:\Users\basil\.claude\projects\F--GitHub-anxiety-synthetic" `
  "F--GitHub-clinical-anxiety-synthetic"
```

Encoding rule: replace every `\` and `:` in the full path with `-`.
`F:\GitHub\<theme>\<repo>` → `F--GitHub-<theme>-<repo>`

Repeat for each repo you move that has accumulated Claude memory.

### 3. IDE workspaces / shell aliases — **check manually**

Any VS Code workspace files (`.code-workspace`), shell aliases, or scripts outside the repos that hardcode `F:\GitHub\<repo>` need to be updated manually. Scope depends on your personal setup.

---

## Migration procedure (per repo)

1. Close any running processes using the repo (pipeline, chatbot, etc.).
2. Move the folder in Explorer or PowerShell:
   ```powershell
   Move-Item "F:\GitHub\anxiety-synthetic" "F:\GitHub\clinical\anxiety-synthetic"
   ```
3. If the repo has a Python editable install, reinstall it from the new location.
4. If the repo has Claude project memory you want to keep, rename the folder under `C:\Users\basil\.claude\projects\` to match the new encoded path.
5. Verify Git is intact: `git -C "F:\GitHub\clinical\anxiety-synthetic" remote -v` — should still show the GitHub URL.

---

## Verification

- `git remote -v` from new location still shows `github.com` URLs — confirms GitHub connection intact.
- `python scripts/generate_persona_and_report.py` runs without import errors — confirms editable install is good.
- In Claude Code, open the moved repo and check that memories are visible — confirms memory migration worked.
