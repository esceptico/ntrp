---
name: implement
description: Implement a spec end-to-end — recon readers map the codebase, an architect pins every cross-file contract in a blueprint, parallel builders implement disjoint workstreams from it, adversarial review, then a final test gate. Use for multi-file feature work. Run via the workflow tool by name.
kind: workflow
source: builtin
---

# implement — recon, blueprint, build, review, verify

A workflow preset. Run it with the `workflow` tool:

```
workflow(name="implement", args={"spec": "Add a render_html tool: <requirements, contracts, non-goals>", "target": "apps", "depth": "normal"})
```

Recon readers answer the questions an implementer would otherwise have to
ask; an architect reads the briefs (and code) and writes the definitive
blueprint — every cross-file contract pinned exactly, the work split into
1-3 workstreams with disjoint files; builders implement them in parallel
from the blueprint alone (it is their only shared context); review lenses
(contracts / correctness / conventions) feed skeptics who try to refute
each finding; survivors get fixed; a final gate runs the tests and judges
the work against the spec.

**args**
- `spec` (str, required) — what to build: requirements, constraints, non-goals. The richer, the better.
- `target` (str, default ".") — the dir/repo to work in.
- `depth` ("quick" | "normal" | "deep", default "normal") — scales recon breadth and skeptics-per-finding.
- `recon_model` / `build_model` (str, optional) — model overrides for readers / builders; omit to inherit the run's model.
