from ntrp.slices.projection import parse_open_loops

PROSE = """# O-1A

## What we know
Stuff.

## Open loops
- **Assess case strength** — determine whether evidence is enough (from chat).
- **Find the right counsel** — identify an attorney (from chat).

## Related
- [[United States]]
"""


def test_parse_open_loops_extracts_bullets_until_next_heading():
    loops = parse_open_loops(PROSE)
    assert len(loops) == 2
    assert loops[0].startswith("Assess case strength")
    assert "(from chat)" not in loops[0]  # provenance suffix stripped


def test_parse_open_loops_missing_section_is_empty():
    assert parse_open_loops("# T\n\n## What we know\nx\n") == []


def test_parse_open_loops_indented_heading_terminates_section():
    prose = "# T\n\n## Open loops\n- Loop one.\n  ## Indented heading\n- Not a loop.\n"
    assert parse_open_loops(prose) == ["Loop one."]
