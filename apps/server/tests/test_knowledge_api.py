"""API tests for knowledge base CRUD and document ingestion (RAG side mocked)."""

from unittest.mock import patch

from app.llm import rag


async def _create_kb(client, name="Base RH"):
    res = await client.post("/api/knowledge", json={"name": name})
    assert res.status_code == 200, res.text
    return res.json()


async def test_create_and_list_knowledge_base(client):
    created = await _create_kb(client)
    assert created["name"] == "Base RH"
    assert created["documents"] == []

    res = await client.get("/api/knowledge")
    assert res.status_code == 200
    assert len(res.json()) == 1


async def test_upload_document_indexes_it(client):
    kb = await _create_kb(client)

    with patch.object(rag, "ingest_text", return_value=3) as mocked_ingest:
        res = await client.post(
            f"/api/knowledge/{kb['id']}/documents",
            files={
                "file": ("notes.txt", b"Contenu utile pour les agents.", "text/plain")
            },
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "indexed"
    assert body["filename"] == "notes.txt"
    mocked_ingest.assert_called_once()


async def test_upload_document_rejects_unsupported_extension(client):
    kb = await _create_kb(client)
    res = await client.post(
        f"/api/knowledge/{kb['id']}/documents",
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert res.status_code == 422


async def test_delete_knowledge_base_purges_vectors(client):
    kb = await _create_kb(client)
    with patch.object(rag, "delete_knowledge_base") as mocked_delete:
        res = await client.delete(f"/api/knowledge/{kb['id']}")
    assert res.status_code == 200
    mocked_delete.assert_called_once_with(kb["id"])

    res = await client.get("/api/knowledge")
    assert res.json() == []
