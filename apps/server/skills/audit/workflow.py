# audit(target, dimensions?, depth?) — find -> adversarially verify -> rank.
target = args.get("target", ".")
dimensions = args.get("dimensions") or [
    "correctness / bugs",
    "security",
    "performance",
    "error handling / edge cases",
]
depth = args.get("depth", "normal")
skeptics = {"quick": 1, "normal": 2, "deep": 3}.get(depth, 2)
max_rounds = {"quick": 1, "normal": 2, "deep": 3}.get(depth, 2)
finder_model = args.get("finder_model")
synth_model = args.get("synth_model")

FINDING = {"title": "str", "where": "str", "issue": "str", "severity": "str"}
VERDICT = {"real": "bool", "why": "str"}

seen, confirmed, dry, rnd = set(), [], 0, 0
while dry < 2 and rnd < max_rounds:
    rnd += 1
    phase(f"round {rnd}: find")
    batches = await parallel([
        agent(
            f"Audit {target} for {d} issues. Use targeted search/reads and cite exact file:line — "
            f"do NOT dump whole files. Return up to 3 concrete, real issues (no style nits).",
            schema={"findings": [FINDING]}, model=finder_model, agent_type="reviewer",
        )
        for d in dimensions
    ])
    fresh = []
    for b in batches:
        for f in ((b or {}).get("findings") or []):
            key = (f.get("where"), f.get("title"))
            if key[0] and key not in seen:
                seen.add(key)
                fresh.append(f)
    if not fresh:
        dry += 1
        log(f"round {rnd}: nothing new")
        continue
    dry = 0
    phase(f"round {rnd}: verify {len(fresh)}")
    judged = await parallel([
        parallel([
            agent(
                f"Refute this finding against the real code in {target}: quote the lines that prove it "
                f"REAL or already-handled. Finding: {f.get('title')} @ {f.get('where')} — {f.get('issue')}.",
                schema=VERDICT, model=finder_model, agent_type="verifier",
            )
            for _ in range(skeptics)
        ])
        for f in fresh
    ])
    for f, votes in zip(fresh, judged):
        if sum(1 for v in (votes or []) if v and v.get("real")) > skeptics / 2:
            confirmed.append(f)

phase("synthesize")
log(f"{len(confirmed)} confirmed over {rnd} round(s)")
return await agent(
    "Write a short prioritized audit report: one-line summary, then the confirmed issues ordered by "
    "severity, each with file:line and the fix. Direct, no padding. Findings: " + json.dumps(confirmed),
    model=synth_model, agent_type="reviewer",
)
