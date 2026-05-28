import json


async def test_cwds_endpoint(jp_fetch):
    response = await jp_fetch("jupyterlab-restore-terminals-fix", "cwds")
    assert response.code == 200
    payload = json.loads(response.body)
    assert "terminals" in payload
    assert isinstance(payload["terminals"], list)


async def test_cwd_not_found(jp_fetch):
    response = await jp_fetch(
        "jupyterlab-restore-terminals-fix", "cwd", "nonexistent",
        raise_error=False
    )
    assert response.code == 404
    payload = json.loads(response.body)
    assert "error" in payload
    assert payload["error"] == "not found"
