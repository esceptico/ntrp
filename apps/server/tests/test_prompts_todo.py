from ntrp.core.prompts import build_system_blocks


def _text(blocks: list[dict]) -> str:
    return "\n".join(b["text"] for b in blocks if b.get("type") == "text")


def test_build_system_blocks_injects_todo_override():
    blocks = build_system_blocks(
        source_details={},
        todo_override={
            "items": [
                {"content": "buy milk", "status": "pending"},
                {"content": "ship it", "status": "in_progress"},
            ],
            "explanation": None,
        },
    )
    text = _text(blocks)
    assert "TODO LIST (edited by the user)" in text
    assert "[pending] buy milk" in text
    assert "[in_progress] ship it" in text


def test_build_system_blocks_omits_todo_block_when_no_override():
    assert "TODO LIST (edited by the user)" not in _text(build_system_blocks(source_details={}))
    assert "TODO LIST (edited by the user)" not in _text(
        build_system_blocks(source_details={}, todo_override={"items": []})
    )
