# graph-diff

Standalone, repo-agnostic command-line tool that renders the **change in a
codebase's import/dependency graph between two git refs** (e.g. a feature branch
vs its base). It extracts the module import graph at each ref, set-differences
them, and emits a colour-coded diagram plus machine- and human-readable
summaries:

- **added edges** render **green** (solid), **removed edges** **red** (dashed),
  **unchanged edges** **grey/dimmed** (thin) — colour reinforced with line style
  so the diagram stays legible for colour-blind viewers;
- **added nodes** get a green fill/outline, **removed nodes** a red dashed
  outline;
- a JSON edge-set dump and a Markdown summary enumerate every added/removed edge
  and node with exact counts.

It answers the structural question a line-diff cannot: *what new connections
between modules did this change introduce, and which did it sever.*

## Design guarantee

The tool is self-contained and carries **no** knowledge of any host project: no
import from a project package, no project-specific package name, no hardcoded
repository path. Everything repo-specific is a CLI argument, so it can be copied
into another repository and run unchanged.

## Install

Two dependency layers:

1. **The Graphviz system binary** (`dot`) — required only for SVG/PNG output
   (the `.dot`, JSON, and Markdown artifacts need nothing external):
   - Windows: `choco install graphviz`
   - macOS: `brew install graphviz`
   - Debian/Ubuntu: `apt-get install graphviz`
   - conda (any OS): `conda install -c conda-forge graphviz`

   If `dot` is not on PATH and you request `svg`/`png`, the tool raises a clear,
   actionable error (and still writes any `dot`/`json`/`md` you also requested).

2. **The Python packages** (`grimp` for extraction, the `graphviz` bindings for
   rendering):

   ```bash
   pip install -r tools/graph-diff/requirements.txt
   ```

## Usage

```bash
python tools/graph-diff/graph_diff.py \
  --package-path src/mypkg \      # required: filesystem path OR dotted package name
  --base-ref dev \               # required: the "before" ref (branch/tag/SHA)
  --head-ref my-feature \        # optional: the "after" ref (default: current branch)
  --repo-root . \                # optional: repo to analyse (default: git top-level of cwd)
  --depth 3 \                    # optional: collapse modules to their N-th package level
  --output graph-diff-out \      # optional: output directory (default: ./graph-diff-out)
  --format svg,png,dot,json,md \ # optional: subset to emit (default: all five)
  --exclude 'tests,__pycache__'  # optional: comma-separated name substrings to drop
```

### Flags

| Flag | Required | Default | Meaning |
|------|----------|---------|---------|
| `--package-path` | yes | — | Target package: a filesystem path (`src/mypkg`) or a dotted name (`mypkg.sub`), resolved inside each ref's checked-out tree. |
| `--base-ref` | yes | — | The base git ref — the "before" side of the diff. Any branch, tag, or SHA. |
| `--head-ref` | no | current branch | The head git ref — the "after" side. Defaults to `git rev-parse --abbrev-ref HEAD`. |
| `--repo-root` | no | git top-level of cwd | Repository to operate on. |
| `--depth` | no | full granularity | Collapse each module to its first N dotted components (e.g. `--depth 3` turns `a.b.c.d` into `a.b.c`); edges internal to a collapsed node are dropped. |
| `--output` | no | `./graph-diff-out` | Directory for the artifacts (created if absent). |
| `--format` | no | `svg,png,dot,json,md` | Comma-separated subset of the five static formats, **plus the opt-in `html`** (a self-contained interactive explorer — see below). `html` is not in the default set; request it explicitly (may combine with others) and it is **incompatible with `--depth`**. |
| `--exclude` | no | — | Comma-separated substrings; any module whose name contains one is dropped, along with every edge touching it. |

### How it works (safe by construction)

For each ref the tool creates a **throwaway detached `git worktree`** in a temp
directory, extracts the graph from it with **grimp** (exact *static* import
analysis — the target need not be installed or importable), then tears the
worktree down in a `finally` block. Your working tree, index, and current branch
are never touched, and a crash leaves no orphaned worktree behind. grimp caching
is disabled and `sys.modules`/`sys.path` are isolated per extraction, so two
same-named packages at different refs never contaminate each other.

## Output artifacts

Written into `--output` with fixed names:

| File | Format | Contents |
|------|--------|----------|
| `graph_delta.dot` | Graphviz source | The colour-coded delta digraph (no external binary needed to produce). |
| `graph_delta.svg` | Vector image | The rendered diagram — scalable, best for reading large graphs. |
| `graph_delta.png` | Raster image (300 dpi) | The rendered diagram for embedding in docs/PRs. |
| `graph_delta.json` | JSON | Full node/edge sets (`added`/`removed`/`unchanged`) plus a summary block — machine-readable. |
| `graph_delta.md` | Markdown | Counts table plus an explicit enumeration of every added/removed edge and node. |
| `graph_explorer.html` | Self-contained HTML | Opt-in (`--format html`) interactive explorer — see below. Only written when `html` is requested. |

All emitters are deterministic (everything sorted), so artifacts diff cleanly
between runs.

## Interactive HTML explorer (`--format html`)

`--format html` emits a single **`graph_explorer.html`** that is fully
**self-contained and offline**: all graph data, the module source at each ref, a
vanilla-JS force-directed renderer, and the CSS are inlined. There is **no
server, no CDN, no vendored library, and no external `src`/`href`** — open it by
double-click and copy it into any repo. (Module names appear only as embedded
runtime data, exactly as they do in the `.json`/`.md`; the tool's own source
stays repo-agnostic.)

```bash
python tools/graph-diff/graph_diff.py \
  --package-path src/mypkg \
  --base-ref dev \
  --head-ref my-feature \
  --format html \
  --output graph-diff-out
```

What you get:

- **The full import graph**, delta-highlighted — added nodes/edges green,
  removed red (dashed), unchanged grey. Drag the background to **pan**, wheel to
  **zoom**, drag a node to reposition it.
- **Click a node** → a right-hand **detail panel** showing:
  - a **status badge** (added / removed / unchanged),
  - **Signatures** — AST-extracted top-level `def`/`async def`/`class` and class
    methods (arg names + return annotation where present),
  - **Source** — the module's full text at the head ref (collapsible),
  - **Diff** — a colourised base→head unified diff (green added lines, red
    removed lines); an added module diffs against an empty base, a removed module
    against an empty head.

The explorer works at **full module granularity** (one node = one `.py` module)
so "click → this file's source" is unambiguous. It is therefore **incompatible
with `--depth`** (a collapsed node cannot map back to a single file); requesting
both fails loudly rather than silently misleading.

## Worked example

Diffing this repository's `dev` line against a feature branch, collapsed to four
package levels for legibility:

```bash
python tools/graph-diff/graph_diff.py \
  --package-path src/population_synthetic \
  --base-ref dev \
  --head-ref feature/persona-realism-judge \
  --output tools/graph-diff/out \
  --depth 4
```

Sample summary printed to stdout:

```
graph-diff: dev -> feature/persona-realism-judge
  nodes:  +15 added  -0 removed  (111 unchanged)
  edges:  +35 added  -0 removed  (188 unchanged)
  output: .../tools/graph-diff/out
    dot  -> graph_delta.dot
    json -> graph_delta.json
    md   -> graph_delta.md
    png  -> graph_delta.png
    svg  -> graph_delta.svg
```

Here the new `...analysis.persona_realism.*` modules and every import into them
appear as green nodes and green edges; nothing was removed, so there are no red
elements.

## Guidance for large graphs

A full module-level graph of a big package can be visually dense. Two levers keep
the **diagram** legible (the JSON/MD summaries are always readable regardless):

- `--depth N` collapses modules to their N-th-level package prefix, turning a
  wall of leaf modules into a handful of subpackage nodes. Start high (e.g.
  `--depth 3`/`4`) and lower it to zoom in.
- `--exclude` drops noise (`tests`, `__pycache__`, generated modules, a
  subpackage you don't care about) and every edge touching it.

The `.dot`/`svg`/`png` show the shape; the `.md`/`.json` give the exact,
grep-able list.

## Layout

```
tools/graph-diff/
├── README.md            # this file
├── requirements.txt     # grimp, graphviz (pinned)
├── conftest.py          # puts the tool root on sys.path for pytest
├── graph_diff.py        # CLI entrypoint (argparse) — orchestration only
├── graphdiff/
│   ├── __init__.py
│   ├── worktree.py      # temporary detached git-worktree context manager
│   ├── extract.py       # grimp → canonical (nodes, edges) Graph; path→module helper
│   ├── diff.py          # pure set-diff over two Graphs → Delta
│   ├── sources.py       # per-module source + AST signatures at one ref (for html)
│   ├── render.py        # Delta → dot / svg / png / json / md
│   └── explorer.py      # Delta + sources → one self-contained graph_explorer.html
└── tests/               # diff, extract, worktree, render, sources, explorer, CLI
```

## Running the tests

From the repository root:

```bash
python -m pytest tools/graph-diff/tests -q
```

The `.dot`-source tests need no external binary; the SVG/PNG tests skip cleanly
when `dot` is not on PATH.
