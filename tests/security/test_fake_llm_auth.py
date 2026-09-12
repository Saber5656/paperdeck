from tests.security.fake_llm import FakeLLM, assert_auth


def test_fake_llm_requires_auth_by_default(fake_llm: FakeLLM) -> None:
    assert assert_auth(fake_llm, key=None) == 401
    assert assert_auth(fake_llm, key="dummy") == 200
    import httpx

    malformed = httpx.post(
        fake_llm.base_url + "/chat/completions",
        headers={"Authorization": "Basic dummy"},
        json={},
    )
    assert malformed.status_code == 401


def test_fake_llm_can_cover_local_no_key_path() -> None:
    with FakeLLM(require_auth=False) as server:
        assert assert_auth(server, key=None) == 200


def test_fake_llm_supports_scriptable_failures() -> None:
    responses = [
        (429, {"error": "rate limited"}, {"Retry-After": "0"}),
        (400, {"error": "json_schema unsupported"}),
        (200, "{\"choices\":["),
    ]

    def plan(_request: dict[str, object]):
        return responses.pop(0)

    with FakeLLM(plan=plan) as server:
        import httpx

        first = httpx.post(
            server.base_url + "/chat/completions",
            headers={"Authorization": "Bearer dummy"},
            json={},
        )
        second = httpx.post(
            server.base_url + "/chat/completions",
            headers={"Authorization": "Bearer dummy"},
            json={},
        )
        third = httpx.post(
            server.base_url + "/chat/completions",
            headers={"Authorization": "Bearer dummy"},
            json={},
        )
    assert first.status_code == 429 and first.headers["Retry-After"] == "0"
    assert second.status_code == 400
    assert third.status_code == 200 and third.text == '{"choices":['
