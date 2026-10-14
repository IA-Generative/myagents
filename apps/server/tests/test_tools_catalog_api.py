async def test_list_tools_catalog(client):
    res = await client.get("/api/agents/tools")
    assert res.status_code == 200
    ids = [t["id"] for t in res.json()]
    assert "current_datetime" in ids
