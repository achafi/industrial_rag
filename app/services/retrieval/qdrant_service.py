"""Qdrant client helpers; local persistent mode is the default."""
from qdrant_client import QdrantClient,models
from app.config import QDRANT_API_KEY,QDRANT_COLLECTION,QDRANT_PATH,QDRANT_URL
from app.services.retrieval.embedding import embed_query,get_embedding_dim

if QDRANT_URL:
    client=QdrantClient(url=QDRANT_URL,api_key=QDRANT_API_KEY or None)
else:
    QDRANT_PATH.mkdir(parents=True,exist_ok=True)
    client=QdrantClient(path=str(QDRANT_PATH))

def ensure_collection():
    if not client.collection_exists(QDRANT_COLLECTION):
        client.create_collection(collection_name=QDRANT_COLLECTION,
            vectors_config=models.VectorParams(size=get_embedding_dim(),distance=models.Distance.COSINE))

def search_enterprise_knowledge(query: str,limit: int=8,source_type: str|None=None):
    ensure_collection(); query_filter=None
    if source_type:
        query_filter=models.Filter(must=[models.FieldCondition(key='source_type',match=models.MatchValue(value=source_type))])
    response=client.query_points(collection_name=QDRANT_COLLECTION,query=embed_query(query),limit=limit,
        with_payload=True,query_filter=query_filter)
    return [{'content':point.payload.get('text',''),'source':point.payload.get('source','Unknown'),
        'source_type':point.payload.get('source_type','unknown'),'score':point.score,
        'chunk_index':point.payload.get('chunk_index',0)} for point in response.points]

def collection_stats():
    if not client.collection_exists(QDRANT_COLLECTION):
        return {'collection':QDRANT_COLLECTION,'points':0,'backend':'remote' if QDRANT_URL else 'local'}
    info=client.get_collection(QDRANT_COLLECTION)
    return {'collection':QDRANT_COLLECTION,'points':info.points_count or 0,'backend':'remote' if QDRANT_URL else 'local'}

def list_documents():
    if not client.collection_exists(QDRANT_COLLECTION):return []
    records,_=client.scroll(collection_name=QDRANT_COLLECTION,limit=10000,
        with_payload=['source','source_type'],with_vectors=False)
    counts={}
    for record in records:
        payload=record.payload or {}; key=(payload.get('source','Unknown'),payload.get('source_type','unknown'))
        counts[key]=counts.get(key,0)+1
    return [{'source':source,'source_type':kind,'chunks':count} for (source,kind),count in sorted(counts.items())]
