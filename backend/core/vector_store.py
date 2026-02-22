"""
ChromaDB vector store for message embeddings.
Used for context retrieval and similar message search.
"""
import logging
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ChromaDB client — connects to the ChromaDB service
_client: Optional[chromadb.HttpClient] = None
_collection = None


def get_chroma_client() -> chromadb.HttpClient:
    """Lazy-init ChromaDB HTTP client."""
    global _client
    if _client is None:
        _client = chromadb.HttpClient(
            host=settings.CHROMA_URL.replace("http://", "").split(":")[0],
            port=int(settings.CHROMA_URL.split(":")[-1]),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _client


def get_collection():
    """Get or create the message_history collection."""
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_or_create_collection(
            name="message_history",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


async def embed_message(
    message_id: str,
    content: str,
    user_id: str,
    platform: str,
    sender_id: str,
    timestamp: str,
) -> None:
    """Store a message embedding in ChromaDB."""
    try:
        collection = get_collection()
        collection.upsert(
            documents=[content],
            metadatas=[{
                "user_id": user_id,
                "platform": platform,
                "sender_id": sender_id,
                "timestamp": timestamp,
            }],
            ids=[message_id],
        )
    except Exception as e:
        logger.warning(f"Failed to embed message {message_id}: {e}")


async def get_similar_messages(
    query: str,
    user_id: str,
    n: int = 10,
    platform: Optional[str] = None,
) -> list[str]:
    """Retrieve similar messages for a user by content similarity."""
    try:
        collection = get_collection()
        where_filter = {"user_id": user_id}
        if platform:
            where_filter["platform"] = platform

        results = collection.query(
            query_texts=[query],
            n_results=n,
            where=where_filter,
        )
        return results["documents"][0] if results["documents"] else []
    except Exception as e:
        logger.warning(f"Failed to query similar messages: {e}")
        return []


async def get_sender_history(
    user_id: str,
    sender_id: str,
    n: int = 20,
) -> list[str]:
    """Retrieve recent messages from a specific sender."""
    try:
        collection = get_collection()
        results = collection.query(
            query_texts=[""],  # empty query to get all
            n_results=n,
            where={
                "$and": [
                    {"user_id": user_id},
                    {"sender_id": sender_id},
                ]
            },
        )
        return results["documents"][0] if results["documents"] else []
    except Exception as e:
        logger.warning(f"Failed to get sender history: {e}")
        return []
