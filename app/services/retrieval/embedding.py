"""Shared document/query embeddings using the configured local FastEmbed model."""
from functools import lru_cache
from app.config import EMBEDDING_MODEL

@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=EMBEDDING_MODEL)

def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:return []
    return [vector.tolist() for vector in _model().embed(texts)]

def embed_query(query: str) -> list[float]:return embed_texts([query])[0]
def get_embedding_dim() -> int:return len(embed_query('industrial knowledge vector dimension probe'))
