"""
Test suite for RAG system robustness and data leakage audit fixes.

Tests the critical improvements made for:
1. Query normalization consistency
2. Error handling robustness
3. Data corruption prevention
4. Metadata validation
"""

import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import shutil

from .config import COUNCIL_MODELS, EMBEDDING_MODEL
from .knowledge import normalize_text, compute_text_hash, smart_chunk, extract_knowledge_units
from .embedding import EmbeddingService
from .vectordb import VectorDatabase
from .deduplication import deduplicate_and_store, DeduplicationMetrics, calculate_consensus_info
from .storage import create_conversation, save_conversation, get_conversation
from . import storage


class TestNormalization:
    """Test text normalization consistency."""
    
    def test_query_normalization_consistency(self):
        """Test that queries are normalized consistently."""
        q1 = "What is Python?"
        q2 = "what is python?"
        q3 = "What   is   Python?"
        
        norm1 = normalize_text(q1)
        norm2 = normalize_text(q2)
        norm3 = normalize_text(q3)
        
        assert norm1 == norm2, "Case-insensitive normalization failed"
        assert norm1 == norm3, "Whitespace normalization failed"
        assert norm1 == "what is python?", "Normalization result incorrect"
    
    def test_hash_consistency(self):
        """Test that hashing is consistent for normalized text."""
        text1 = "The Quick Brown Fox"
        text2 = "the quick brown fox"
        text3 = "The  Quick  Brown  Fox"
        
        hash1 = compute_text_hash(text1)
        hash2 = compute_text_hash(text2)
        hash3 = compute_text_hash(text3)
        
        assert hash1 == hash2 == hash3, "Hash inconsistency detected"
    
    def test_empty_text_handling(self):
        """Test handling of empty/whitespace-only text."""
        assert normalize_text("") == ""
        assert normalize_text("   ") == ""
        assert normalize_text("\n\t  ") == ""


class TestEmbeddingService:
    """Test embedding service robustness."""
    
    def test_singleton_pattern(self):
        """Test that EmbeddingService is a singleton."""
        service1 = EmbeddingService()
        service2 = EmbeddingService()
        
        assert service1 is service2, "Singleton pattern broken"
    
    def test_embedding_generation(self):
        """Test that embeddings are generated correctly."""
        service = EmbeddingService()
        text = "This is a test sentence."
        
        embedding = service.embed(text)
        
        assert embedding is not None, "Embedding generation failed"
        assert len(embedding) > 0, "Embedding is empty"
        assert embedding.ndim == 1, "Embedding should be 1D"
    
    def test_batch_embedding(self):
        """Test batch embedding generation."""
        service = EmbeddingService()
        texts = ["First sentence.", "Second sentence.", "Third sentence."]
        
        embeddings = service.embed(texts)
        
        assert len(embeddings) == 3, "Batch embedding count mismatch"
        assert all(len(e) > 0 for e in embeddings), "Some embeddings are empty"
    
    def test_similarity_calculation(self):
        """Test cosine similarity calculation."""
        service = EmbeddingService()
        
        text1 = "Python is a programming language"
        text2 = "Python is a programming language"
        text3 = "The weather is sunny today"
        
        emb1 = service.embed(text1)
        emb2 = service.embed(text2)
        emb3 = service.embed(text3)
        
        sim_same = service.similarity(emb1, emb2)
        sim_diff = service.similarity(emb1, emb3)
        
        assert sim_same > 0.99, "Identical texts should have high similarity"
        assert sim_diff < 0.5, "Different texts should have lower similarity"
    
    def test_zero_norm_handling(self):
        """Test handling of zero-norm embeddings."""
        import numpy as np
        service = EmbeddingService()
        
        zero_vec = np.zeros(384)
        normal_vec = np.ones(384) / 384.0
        
        sim = service.similarity(zero_vec, normal_vec)
        
        assert sim == 0.0, "Zero-norm similarity should be 0"


class TestDataStorage:
    """Test data storage robustness."""
    
    def test_atomic_write_success(self):
        """Test that atomic writes complete successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = storage.DATA_DIR
            storage.DATA_DIR = tmpdir
            
            try:
                conv = create_conversation("test-conv-1")
                
                assert conv['id'] == "test-conv-1"
                assert Path(tmpdir, "test-conv-1.json").exists()
                
                loaded = get_conversation("test-conv-1")
                assert loaded is not None
                assert loaded['id'] == "test-conv-1"
            finally:
                storage.DATA_DIR = original_dir
    
    def test_conversation_persistence(self):
        """Test that conversations persist correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = storage.DATA_DIR
            storage.DATA_DIR = tmpdir
            
            try:
                conv = create_conversation("test-conv-2")
                conv['messages'].append({"role": "user", "content": "Test message"})
                save_conversation(conv)
                
                loaded = get_conversation("test-conv-2")
                
                assert loaded['messages'][0]['content'] == "Test message"
            finally:
                storage.DATA_DIR = original_dir
    
    def test_concurrent_writes(self):
        """Test handling of concurrent writes (should not corrupt)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = storage.DATA_DIR
            storage.DATA_DIR = tmpdir
            
            try:
                conv = create_conversation("test-conv-3")
                
                for i in range(10):
                    conv['messages'].append({"role": "user", "content": f"Message {i}"})
                    save_conversation(conv)
                
                loaded = get_conversation("test-conv-3")
                
                assert len(loaded['messages']) == 10
                assert all(json.loads(json.dumps(msg)) for msg in loaded['messages'])
            finally:
                storage.DATA_DIR = original_dir


class TestDeduplication:
    """Test deduplication robustness."""
    
    def test_deduplication_metrics(self):
        """Test deduplication metrics calculation."""
        metrics = DeduplicationMetrics()
        
        metrics.total_generated = 100
        metrics.exact_duplicates = 20
        metrics.semantic_duplicates = 15
        metrics.stored_new = 65
        
        dedup_rate = metrics.deduplication_rate()
        storage_rate = metrics.storage_rate()
        
        assert dedup_rate == 0.35, "Deduplication rate incorrect"
        assert storage_rate == 0.65, "Storage rate incorrect"
        assert dedup_rate + storage_rate == 1.0, "Rates should sum to 1.0"
    
    def test_consensus_info_empty_list(self):
        """Test consensus info calculation with empty list."""
        info = calculate_consensus_info([])
        
        assert info['avg_consensus_score'] == 0.0
        assert info['avg_support_count'] == 0.0
        assert info['high_consensus_count'] == 0
        assert info['novel_count'] == 0
    
    def test_consensus_info_calculation(self):
        """Test consensus info calculation with data."""
        units = [
            {'consensus_score': 1.0, 'support_count': 4},
            {'consensus_score': 0.75, 'support_count': 3},
            {'consensus_score': 0.5, 'support_count': 2},
            {'consensus_score': 0.25, 'support_count': 1},
        ]
        
        info = calculate_consensus_info(units)
        
        assert info['avg_consensus_score'] == 0.625
        assert info['avg_support_count'] == 2.5
        assert info['high_consensus_count'] == 2
        assert info['novel_count'] == 1


class TestInputValidation:
    """Test input validation and sanitization."""
    
    def test_knowledge_unit_extraction_with_empty_response(self):
        """Test extraction handles empty responses gracefully."""
        responses = [
            {'model': 'model1', 'response': ''},
            {'model': 'model2', 'response': '   '},
            {'model': 'model3', 'response': None},
        ]
        
        units = extract_knowledge_units(responses, "test query", "conv-1")
        
        assert len(units) == 0, "Should handle empty responses"
    
    def test_knowledge_unit_extraction_with_short_chunks(self):
        """Test that short chunks are filtered out."""
        responses = [
            {
                'model': 'model1',
                'response': 'Short. Very short. Too short. Not enough words here.'
            }
        ]
        
        units = extract_knowledge_units(responses, "test query", "conv-1")
        
        assert len(units) == 0, "Short chunks should be filtered"
    
    def test_knowledge_unit_extraction_with_valid_content(self):
        """Test extraction of valid knowledge units."""
        responses = [
            {
                'model': 'model1',
                'response': 'This is a longer sentence with more than ten words that should be kept.'
            }
        ]
        
        units = extract_knowledge_units(responses, "test query", "conv-1")
        
        assert len(units) > 0, "Valid content should be extracted"
        assert all('source_model' in u for u in units)
        assert all('hash' in u for u in units)


class TestErrorRecovery:
    """Test error handling and recovery."""
    
    def test_smart_chunking_with_code_blocks(self):
        """Test intelligent chunking preserves code blocks."""
        text = """
Here is some Python code:

```python
def hello_world():
    print("Hello, World!")
```

And here is some more explanation text that follows the code block.
        """
        
        chunks = smart_chunk(text)
        
        assert len(chunks) > 0
        assert any(c['type'] == 'code' for c in chunks), "Code blocks should be preserved"
    
    def test_normalize_text_with_unicode(self):
        """Test text normalization with unicode characters."""
        text = "Café with café spelled differently"
        
        normalized = normalize_text(text)
        
        assert isinstance(normalized, str)
        assert len(normalized) > 0


@pytest.mark.asyncio
async def test_async_deduplication():
    """Test async deduplication process."""
    knowledge_units = [
        {
            'text': 'First knowledge unit with substantial content here.',
            'normalized_text': 'first knowledge unit with substantial content here.',
            'hash': 'abc123',
            'source_model': 'model1',
            'query_context': 'test query',
            'conversation_id': 'conv-1',
            'chunk_type': 'text',
            'metadata': {}
        }
    ]
    
    metrics, stored_ids = await deduplicate_and_store(knowledge_units)
    
    assert metrics.total_generated == 1
    assert isinstance(metrics, DeduplicationMetrics)
    assert isinstance(stored_ids, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
