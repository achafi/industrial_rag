from app.services.retrieval.qdrant_service import search_enterprise_knowledge
from app.services.retrieval.ranking_service import rerank_documents

class RetrievalService:
    def search(self,query,limit=8,source_type=None):
        results=search_enterprise_knowledge(query,limit=max(limit,20),source_type=source_type)
        reranked=rerank_documents(query,[item['content'] for item in results],top_n=limit)
        by_text={item['content']:item for item in results}
        return [by_text[text] for text in reranked if text in by_text]
    def answer_with_evidence(self,query,limit=6):
        results=self.search(query,limit)
        answer=('I could not find relevant evidence in the indexed corpus.' if not results else
                'Retrieved evidence (not an approved operating instruction):\n\n'+'\n\n'.join(
                    f"[{row['source']}]\n{row['content'][:700]}" for row in results[:4]))
        if any(word in query.lower() for word in ('repair','isolation','cavitation','leak','noise','maintenance')):
            answer+='\n\nFor operational action, follow current site-approved procedures and involve authorized personnel.'
        return {'question':query,'answer':answer,'status':'evidence_found' if results else 'no_evidence',
                'sources':[{'source':row['source'],'source_type':row['source_type'],'score':row['score']} for row in results]}
