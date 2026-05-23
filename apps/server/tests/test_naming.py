from ntrp.core.naming import agent_name, conversation_name


def test_conversation_name_removes_request_filler():
    assert conversation_name("please research the replay animation root cause in desktop") == (
        "Replay Animation Root Cause"
    )


def test_conversation_name_handles_images():
    assert conversation_name("", has_images=True) == "Image Conversation"


def test_agent_name_prefixes_role_without_prompt_dump():
    assert agent_name("research", "inspect current eval/test harness opportunities") == (
        "Research Eval Test Harness"
    )
