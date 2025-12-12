"""Deduplication logic for knowledge units."""

from typing import List, Dict, Any, Tuple
from .config import SEMANTIC_SIMILARITY_THRESHOLD
from .embedding import embedding_service
from .vectordb import vector_db


class DeduplicationMetrics:
    """Track deduplication metrics."""
    
    def __init__(self):
        self.total_generated = 0
        self.exact_duplicates = 0
        self.semantic_duplicates = 0
        self.stored_new = 0
    
    def deduplication_rate(self) -> float:
        """Calculate deduplication rate."""
        if self.total_generated == 0:
            return 0.0
        duplicates = self.exact_duplicates + self.semantic_duplicates
        return duplicates / self.total_generated
    
    def storage_rate(self) -> float:
        """Calculate storage rate (inverse of dedup rate)."""
        return 1.0 - self.deduplication_rate()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for API responses."""
        return {
            'total_generated': self.total_generated,
            'exact_duplicates': self.exact_duplicates,
            'semantic_duplicates': self.semantic_duplicates,
            'stored_new': self.stored_new,
            'deduplication_rate': self.deduplication_rate(),
            'storage_rate': self.storage_rate()
        }


async def deduplicate_and_store(
    knowledge_units: List[Dict[str, Any]]
) -> Tuple[DeduplicationMetrics, List[str]]:
    """
    Deduplicate knowledge units and store only unique ones.
    
    Process:
    1. Check exact duplicates (hash-based)
    2. Check semantic duplicates (embedding similarity)
    3. Store new knowledge or update consensus
    
    Args:
        knowledge_units: List of extracted knowledge units
        
    Returns:
        Tuple of (metrics, stored_ids)
    """
    metrics = DeduplicationMetrics()
    stored_ids = []
    
    for unit in knowledge_units:
        metrics.total_generated += 1
        
        if vector_db.check_exact_duplicate(unit['hash']):
            metrics.exact_duplicates += 1
            continue
        
        embedding = embedding_service.embed(unit['text'])
        
        semantic_match = vector_db.check_semantic_duplicate(
            embedding.tolist(),
            threshold=SEMANTIC_SIMILARITY_THRESHOLD
        )
        
        if semantic_match:
            metrics.semantic_duplicates += 1
            
            vector_db.update_knowledge_unit_consensus(
                semantic_match['id'],
                unit['source_model']
            )
            stored_ids.append(semantic_match['id'])
        else:
            unit_id = vector_db.add_knowledge_unit(unit, embedding.tolist())
            metrics.stored_new += 1
            stored_ids.append(unit_id)
    
    return metrics, stored_ids


def calculate_consensus_info(
    retrieved_units: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Calculate consensus statistics from retrieved knowledge units.
    
    Args:
        retrieved_units: Retrieved knowledge units from vector DB
        
    Returns:
        Consensus info dict
    """
    if not retrieved_units:
        return {
            'avg_consensus_score': 0.0,
            'avg_support_count': 0.0,
            'high_consensus_count': 0,
            'novel_count': 0
        }
    
    consensus_scores = [u['consensus_score'] for u in retrieved_units]
    support_counts = [u['support_count'] for u in retrieved_units]
    
    high_consensus = sum(1 for u in retrieved_units if u['consensus_score'] >= 0.75)
    novel = sum(1 for u in retrieved_units if u['support_count'] == 1)
    
    return {
        'avg_consensus_score': sum(consensus_scores) / len(consensus_scores),
        'avg_support_count': sum(support_counts) / len(support_counts),
        'high_consensus_count': high_consensus,
        'novel_count': novel
    }
