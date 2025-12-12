"""Vector database operations using ChromaDB."""

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from pathlib import Path

from .config import VECTOR_DB_DIR, TOP_K_RETRIEVAL, CONSENSUS_WEIGHT
from .embedding import embedding_service


class VectorDatabase:
    """Manages vector storage and retrieval using ChromaDB."""
    
    def __init__(self):
        """Initialize ChromaDB client."""
        Path(VECTOR_DB_DIR).mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=VECTOR_DB_DIR,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        self.collection = self.client.get_or_create_collection(
            name="knowledge_units",
            metadata={"hnsw:space": "cosine"}
        )
        
        print(f"Vector database initialized at {VECTOR_DB_DIR}")
        print(f"Current knowledge units: {self.collection.count()}")
    
    def check_exact_duplicate(self, text_hash: str) -> bool:
        """
        Check if exact duplicate exists by hash.
        
        Args:
            text_hash: SHA-256 hash of normalized text
            
        Returns:
            True if duplicate exists
        """
        results = self.collection.get(
            where={"hash": text_hash},
            limit=1
        )
        return len(results['ids']) > 0
    
    def check_semantic_duplicate(
        self,
        embedding: List[float],
        threshold: float = 0.98
    ) -> Optional[Dict[str, Any]]:
        """
        Check if semantic duplicate exists above threshold.
        
        Args:
            embedding: Query embedding
            threshold: Cosine similarity threshold
            
        Returns:
            Existing knowledge unit if duplicate found, else None
        """
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=1
        )
        
        if not results['ids'] or not results['ids'][0]:
            return None
        
        similarity = 1 - results['distances'][0][0]
        
        if similarity >= threshold:
            return {
                'id': results['ids'][0][0],
                'text': results['documents'][0][0],
                'metadata': results['metadatas'][0][0],
                'similarity': similarity
            }
        
        return None
    
    def add_knowledge_unit(
        self,
        knowledge_unit: Dict[str, Any],
        embedding: List[float]
    ) -> str:
        """
        Add new knowledge unit to vector database.
        
        Args:
            knowledge_unit: Knowledge unit dict
            embedding: Pre-computed embedding
            
        Returns:
            ID of stored knowledge unit
        """
        unit_id = f"{knowledge_unit['conversation_id']}_{knowledge_unit['hash'][:16]}"
        
        metadata = {
            'hash': knowledge_unit['hash'],
            'source_models': json.dumps([knowledge_unit['source_model']]),
            'support_count': 1,
            'consensus_score': 0.25,
            'query_context': knowledge_unit['query_context'],
            'conversation_id': knowledge_unit['conversation_id'],
            'chunk_type': knowledge_unit['chunk_type'],
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        self.collection.add(
            ids=[unit_id],
            documents=[knowledge_unit['text']],
            embeddings=[embedding],
            metadatas=[metadata]
        )
        
        return unit_id
    
    def update_knowledge_unit_consensus(
        self,
        unit_id: str,
        new_source_model: str
    ):
        """
        Update consensus metadata for existing knowledge unit.
        
        Args:
            unit_id: ID of knowledge unit
            new_source_model: Model contributing to consensus
        """
        existing = self.collection.get(ids=[unit_id])
        
        if not existing['ids']:
            return
        
        metadata = existing['metadatas'][0]
        source_models = json.loads(metadata['source_models'])
        
        if new_source_model not in source_models:
            source_models.append(new_source_model)
            support_count = len(source_models)
            
            consensus_score = min(support_count / 4.0, 1.0)
            
            metadata['source_models'] = json.dumps(source_models)
            metadata['support_count'] = support_count
            metadata['consensus_score'] = consensus_score
            metadata['updated_at'] = datetime.utcnow().isoformat()
            
            self.collection.update(
                ids=[unit_id],
                metadatas=[metadata]
            )
    
    def retrieve(
        self,
        query: str,
        top_k: int = TOP_K_RETRIEVAL
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant knowledge units for a query.
        
        Args:
            query: User query text
            top_k: Number of results to retrieve
            
        Returns:
            List of knowledge units with metadata
        """
        query_embedding = embedding_service.embed(query)
        
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k
        )
        
        if not results['ids'] or not results['ids'][0]:
            return []
        
        knowledge_units = []
        for i in range(len(results['ids'][0])):
            semantic_similarity = 1 - results['distances'][0][i]
            metadata = results['metadatas'][0][i]
            
            consensus_score = float(metadata.get('consensus_score', 0.0))
            
            combined_score = (
                (1 - CONSENSUS_WEIGHT) * semantic_similarity +
                CONSENSUS_WEIGHT * consensus_score
            )
            
            knowledge_units.append({
                'id': results['ids'][0][i],
                'text': results['documents'][0][i],
                'semantic_similarity': semantic_similarity,
                'consensus_score': consensus_score,
                'combined_score': combined_score,
                'support_count': metadata.get('support_count', 1),
                'source_models': json.loads(metadata.get('source_models', '[]')),
                'query_context': metadata.get('query_context', ''),
                'created_at': metadata.get('created_at', '')
            })
        
        knowledge_units.sort(key=lambda x: x['combined_score'], reverse=True)
        
        return knowledge_units
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get vector database statistics.
        
        Returns:
            Stats dict
        """
        total_count = self.collection.count()
        
        all_metadata = self.collection.get()
        
        consensus_counts = {
            'single_source': 0,
            'dual_source': 0,
            'majority': 0,
            'full_consensus': 0
        }
        
        for metadata in all_metadata.get('metadatas', []):
            support_count = metadata.get('support_count', 1)
            if support_count == 1:
                consensus_counts['single_source'] += 1
            elif support_count == 2:
                consensus_counts['dual_source'] += 1
            elif support_count == 3:
                consensus_counts['majority'] += 1
            elif support_count >= 4:
                consensus_counts['full_consensus'] += 1
        
        return {
            'total_knowledge_units': total_count,
            'consensus_distribution': consensus_counts
        }


vector_db = VectorDatabase()
