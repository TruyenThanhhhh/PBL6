from sentence_transformers import CrossEncoder
from typing import List, Dict, Any

class RerankerService:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        # Khởi tạo mô hình Cross-Encoder Reranker
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        if not documents:
            return []

        # Tạo cặp (Query, Document)
        pairs = [[query, doc["content"]] for doc in documents]
        
        # Chấm điểm Cross-Encoder
        scores = self.model.predict(pairs)
        
        for idx, score in enumerate(scores):
            documents[idx]["rerank_score"] = float(score)

        # Sắp xếp lại theo điểm Rerank giảm dần
        sorted_docs = sorted(documents, key=lambda x: x["rerank_score"], reverse=True)
        return sorted_docs[:top_k]

reranker_service = RerankerService()