# implement(spec, target?, depth?) — recon -> blueprint -> parallel builders -> adversarial review -> test gate.
spec = args.get("spec", "")
if not spec:
    raise ValueError("implement requires args['spec']: what to build, with constraints and non-goals.")
target = args.get("target", ".")
depth = args.get("depth", "normal")
recon_n = {"quick": 2, "normal": 4, "deep": 6}.get(depth, 4)
skeptics = {"quick": 1, "normal": 2, "deep": 3}.get(depth, 2)
recon_model = args.get("recon_model")
build_model = args.get("build_model")

phase("recon")
derived = await agent(
    f"A feature is about to be implemented in {target}. SPEC:\n{spec}\n\n"
    f"List the {recon_n} recon questions an implementer must have answered before writing code — "
    "existing patterns to follow, plumbing to reuse, conventions, how tests are written and run. "
    "Terse, one per item.",
    schema={"questions": ["str"]}, model=recon_model, agent_type="explorer",
)
questions = (derived or {}).get("questions") or [
    f"What existing code, conventions, and tests in {target} matter for: {spec}"
]
briefs = await parallel([
    agent(
        f"Read-only recon in {target}: {q}\nAnswer with exact file paths, names, and short verbatim "
        "excerpts of the key interfaces — implementers will code against your brief without re-reading.",
        model=recon_model, agent_type="explorer",
    )
    for q in questions
])

phase("blueprint")
plan = await agent(
    f"You are the architect for new work in {target}.\n\nSPEC:\n{spec}\n\nRECON BRIEFS:\n"
    + json.dumps([b for b in briefs if b])
    + "\n\nRead code to settle anything the briefs leave ambiguous — verify, don't guess. Write the "
    "definitive implementation blueprint: pin down EXACTLY every cross-file contract (names, shapes, "
    "endpoints, events), the file-by-file changes, and the test plan. Builders work in parallel from "
    "this text alone and cannot talk to each other. Split the work into 1-3 workstreams with disjoint "
    "files; assign any shared file to exactly one.",
    schema={"blueprint": "str", "workstreams": [{"name": "str", "scope": "str"}]},
    agent_type="planner",
)
blueprint = (plan or {}).get("blueprint") or ""
streams = (plan or {}).get("workstreams") or []
if not blueprint or not streams:
    raise RuntimeError("architect returned no blueprint/workstreams")

phase(f"build {len(streams)}")
REPORT = {"files_changed": ["str"], "deviations": "str", "tests_run": "str"}
built = await parallel([
    agent(
        f"Implement workstream '{w.get('name')}' in {target}. Scope: {w.get('scope')}.\n"
        "Follow the blueprint LITERALLY on every cross-boundary contract — counterparts build the other "
        "workstreams in parallel and you cannot talk to them; record any forced deviation in `deviations`. "
        "Match existing conventions, write the tests the blueprint assigns to your scope, and run the "
        "relevant test subset until green (commands + results in `tests_run`). Do NOT git commit.\n\n"
        f"BLUEPRINT:\n{blueprint}",
        schema=REPORT, model=build_model, agent_type="builder",
    )
    for w in streams
])
built = [b for b in built if b]
touched = sorted({f for b in built for f in (b.get("files_changed") or [])})
deviations = "; ".join(d for b in built if (d := b.get("deviations")))
log(f"{len(touched)} files changed" + (f"; deviations: {deviations}" if deviations else ""))

phase("review")
FINDING = {"title": "str", "where": "str", "issue": "str", "severity": "str"}
VERDICT = {"real": "bool", "why": "str"}
ctx = (
    f"Files changed (review ONLY these; ignore unrelated uncommitted work): {json.dumps(touched)}\n"
    f"Builder-reported deviations: {deviations or 'none'}\n\n"
    f"BLUEPRINT (contract source of truth):\n{blueprint}"
)
lenses = [
    "cross-boundary contracts: trace every shared name/shape/endpoint/event on BOTH its producer and consumer side",
    "correctness: bugs, races, leaks, unhandled failure paths, missing cleanup",
    "conventions: missed reuse of existing primitives, dead code, over-engineering vs the blueprint",
]


async def review_lens(lens):
    found = await agent(
        f"Review the fresh changes in {target} through ONE lens: {lens}.\n{ctx}\n"
        "Report up to 4 concrete issues traced to actual code — no nitpicks.",
        schema={"findings": [FINDING]}, agent_type="reviewer", phase="review",
    )
    survivors = []
    for f in ((found or {}).get("findings") or []):
        votes = await parallel([
            agent(
                f"Refute this review finding against the real code in {target}: quote the lines that "
                f"prove it real or already-handled. Finding: {f.get('title')} @ {f.get('where')} — "
                f"{f.get('issue')}",
                schema=VERDICT, agent_type="verifier", phase="review",
            )
            for _ in range(skeptics)
        ])
        if sum(1 for v in votes if v and v.get("real")) > skeptics / 2:
            survivors.append(f)
    return survivors


confirmed = [f for batch in await parallel([review_lens(l) for l in lenses]) for f in (batch or [])]
log(f"{len(confirmed)} confirmed finding(s)")

if confirmed:
    phase("fix")
    await agent(
        f"Fix these CONFIRMED review findings in {target} (uncommitted work; do not commit, do not touch "
        "unrelated files). Re-run the affected tests after. Honor the blueprint contracts:\n"
        f"{blueprint}\n\nFINDINGS:\n" + json.dumps(confirmed),
        model=build_model, agent_type="builder",
    )

phase("verify")
report = await agent(
    f"Final gate for the uncommitted feature work in {target} (files: {json.dumps(touched)}). Run the "
    "project's relevant test suites and typechecks. Distinguish pre-existing failures from failures in "
    "this work. Fix nothing; commit nothing. Report each command + outcome, then a verdict: does the "
    f"work satisfy the spec?\nSPEC:\n{spec}",
    agent_type="builder",
)
return {"files_changed": touched, "confirmed_findings": confirmed, "verification": report}
