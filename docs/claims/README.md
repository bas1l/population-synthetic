# The claim DAG

The logical skeleton of the study's published results: which claim rests on which
finding, through which named inference rule, and what is assumed along the way.

Authored as YAML, rendered to four formats. The YAML is the source of truth; every
renderer is disposable.

```
docs/claims/
├── leaves.yaml          shared leaf layer -- findings, assumptions, contexts
├── results/*.yaml       one file per published result: laws, derived claims, defeaters
├── _style.yaml          the visual grammar (node classes, status overlays, edge kinds)
└── diagrams/            generated -- do not hand-edit
    ├── claim_{short}.png / .svg    the ancestor sub-DAG of that result
    ├── claim_{short}.dot           Graphviz source
    ├── claim_{short}.mmd           Mermaid source
    └── _index/impact.csv           every leaf and the results depending on it
        _index/ladder.csv           every node with rank, law, backing, qualifier
```

Render with:

```bash
python scripts/dev/render_claim_dag.py
```

## It is one DAG with many roots, not many trees

Results share leaves. The same reference population, the same score matrix, the same
validation gate and the same assumptions feed several published claims at once. Modelled
as separate trees that fact disappears; modelled as one DAG it is the first thing you
can see.

That is what `_index/impact.csv` is for. A per-result diagram answers *what does this
claim rest on*. The impact table answers the question that actually costs you something:
**if this leaf turns out to be wrong, which published claims must be withdrawn?** It is
the reverse-dependency query — `rdeps` in build-system terms — and no downward-facing
diagram can show it.

## Why the global view is a table and the per-result view is a picture

Ghoniem, Fekete & Castagliola (InfoVis 2004) found that above roughly twenty nodes, a
matrix or table beats a node-link diagram on every graph-reading task **except**
path-finding. The whole claim DAG is past that threshold. A single result's sub-DAG is
not — and tracing a path is exactly what it is for. So the per-result view is drawn and
the global view is tabulated. That is not a compromise; it is what the evidence says.

## The two checks the renderer runs

Both print to stdout on every render, and both are findings about the manuscript rather
than errors in the input, so neither raises.

**The Ladder Invariant.** Ascending a rung increases interpretive commitment and
decreases certainty, so no node may declare a qualifier stronger than the weakest of its
own premises. A ladder whose confidence grows as it climbs is defective — this turns
that from a matter of taste into arithmetic.

**Unbacked laws.** A law states a general rule; its *backing* is why that rule holds,
independent of these data. A law with no backing is an assumption wearing a rule's
clothes, and the renderer names them.

Malformed input — an unknown premise id, a defeater pointing at nothing, a cycle,
a duplicate node id — raises instead.

## Not an analysis process

No `analysis_registry.yaml` entry, no DAG node, no GUI workflow task. This consumes no
run data and produces no statistic; it is a documentation renderer that happens to live
next to the code whose outputs its leaves cite.

## Method

The technique is documented at
`~/.claude/knowledge/logic-and-argumentation/08-derivation-ladders.md`, and is assembled
from Goal Structuring Notation, Adelard's Claims-Arguments-Evidence blocks, SEI's
eliminative argumentation (the three defeater kinds, and "evidence supports a claim only
insofar as it eliminates doubt"), ASPIC⁺ (strict `→` vs defeasible `⇒`, and the
preference-free status of undercutting), and Wigmore/Schum evidence charts (the key list,
and the rule that evidence *about* evidence attaches to an arc, never to the main chain).
