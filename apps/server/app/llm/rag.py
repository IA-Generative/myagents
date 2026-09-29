"""RAG ingestion and retrieval for agent knowledge bases, backed by a single
Qdrant collection filtered by `knowledge_base_id` (avoids one collection per
knowledge base).
"""

import logging

from langchain_core.tools import BaseTool, tool
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny

from app.core.config import get_settings
from app.llm.client import LlmClient

logger = logging.getLogger(__name__)

COLLECTION_NAME = "agent_knowledge"

_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)


def _knowledge_base_filter(knowledge_ids: list[str]) -> Filter:
    return Filter(
        must=[
            FieldCondition(
                key="metadata.knowledge_base_id", match=MatchAny(any=knowledge_ids)
            )
        ]
    )


def ingest_text(knowledge_base_id: str, filename: str, text: str) -> int:
    """Split, embed and store a document's chunks. Returns the number of chunks stored."""
    chunks = _splitter.split_text(text)
    if not chunks:
        return 0
    settings = get_settings()
    QdrantVectorStore.from_texts(
        chunks,
        embedding=LlmClient().embeddings(),
        metadatas=[{"knowledge_base_id": knowledge_base_id, "filename": filename}]
        * len(chunks),
        collection_name=COLLECTION_NAME,
        url=settings.qdrant_url,
        force_recreate=False,
    )
    return len(chunks)


def delete_knowledge_base(knowledge_base_id: str) -> None:
    """Purge all vector points belonging to a knowledge base (called on KB deletion)."""
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url)
    if not client.collection_exists(COLLECTION_NAME):
        return
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=_knowledge_base_filter([knowledge_base_id]),
    )


def build_retriever_tool(knowledge_ids: list[str]) -> BaseTool:
    """A tool the agent can call to search the selected knowledge bases."""
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url)

    @tool
    async def knowledge_search(query: str) -> str:
        """Recherche des informations pertinentes dans les bases de connaissances de l'agent."""
        if not client.collection_exists(COLLECTION_NAME):
            return "Aucun document indexé pour l'instant."
        store = QdrantVectorStore(
            client=client,
            collection_name=COLLECTION_NAME,
            embedding=LlmClient().embeddings(),
        )
        docs = await store.asimilarity_search(
            query, k=4, filter=_knowledge_base_filter(knowledge_ids)
        )
        if not docs:
            return "Aucun document pertinent trouvé."
        return "\n\n---\n\n".join(d.page_content for d in docs)

    return knowledge_search
