from ntrp.llm.openai import OpenAIClient


def test_native_openai_request_includes_prompt_cache_key():
    client = OpenAIClient(api_key="test")

    request = client._prepare(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-5.2",
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
        reasoning_effort=None,
        response_format=None,
        prompt_cache_key="session-1",
    )

    assert request["prompt_cache_key"] == "session-1"


def test_openai_compatible_request_omits_prompt_cache_key():
    client = OpenAIClient(api_key="test", base_url="https://example.test", native_openai=False)

    request = client._prepare(
        messages=[{"role": "user", "content": "hi"}],
        model="custom-model",
        tools=None,
        tool_choice=None,
        temperature=None,
        max_tokens=None,
        reasoning_effort=None,
        response_format=None,
        prompt_cache_key="session-1",
    )

    assert "prompt_cache_key" not in request
