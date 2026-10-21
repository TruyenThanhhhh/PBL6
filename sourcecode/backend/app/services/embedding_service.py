import torch
from sentence_transformers import SentenceTransformer
from typing import List, Union
from app.config import settings

class EmbeddingService:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # Load mô hình BGE-M3
        self.model = SentenceTransformer(model_name, device=self.device)

    def generate_embeddings(self, texts: Union[str, List[str]]) -> List[List[float]]:
        """
        Sinh Vector Embeddings (Dense) cho văn bản hoặc danh sách văn bản.
        """
        if isinstance(texts, str):
            texts = [texts]
        
        # BGE-M3 khuyến nghị normalize_embeddings=True cho cos_sim
        embeddings = self.model.encode(
            texts, 
            batch_size=16, 
            show_progress_bar=False, 
            normalize_embeddings=True
        )
        return embeddings.tolist()

embedding_service = EmbeddingService()