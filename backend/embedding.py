"""Embedding generation for RAG system."""

from sentence_transformers import SentenceTransformer
from typing import List, Union
import numpy as np
from .config import EMBEDDING_MODEL


class EmbeddingService:
    """Handles text embedding generation."""
    
    _instance = None
    _model = None
    
    def __new__(cls):
        """Singleton pattern to avoid reloading model."""
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize the embedding model (lazy loading)."""
        if self._model is None:
            try:
                print(f"Loading embedding model: {EMBEDDING_MODEL}")
                self._model = SentenceTransformer(EMBEDDING_MODEL)
                print("Embedding model loaded successfully")
            except Exception as e:
                print(f"ERROR: Failed to load embedding model: {e}")
                raise RuntimeError(f"Embedding service initialization failed: {e}") from e
    
    def embed(self, text: Union[str, List[str]]) -> Union[np.ndarray, List[np.ndarray]]:
        """
        Generate embeddings for text(s).
        
        Args:
            text: Single text string or list of strings
            
        Returns:
            Embedding(s) as numpy array(s)
        """
        if self._model is None:
            raise RuntimeError("Embedding model not initialized")
        
        try:
            if isinstance(text, str):
                return self._model.encode([text])[0]
            else:
                return self._model.encode(text)
        except Exception as e:
            print(f"ERROR: Failed to embed text: {e}")
            raise RuntimeError(f"Embedding failed: {e}") from e
    
    def similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Cosine similarity score (0-1)
        """
        dot_product = np.dot(embedding1, embedding2)
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0.0 or norm2 == 0.0:
            print("WARNING: Zero-norm embedding detected in similarity calculation")
            return 0.0
        
        return float(dot_product / (norm1 * norm2))


# Global instance
embedding_service = EmbeddingService()
