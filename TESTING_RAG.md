# Testing the RAG System

## Quick Start

### 1. Install Dependencies

```bash
uv sync
```

This will install the new dependencies:
- `chromadb` - Vector database
- `sentence-transformers` - Embedding generation
- `numpy` - Numerical operations

**First run:** The embedding model (~100MB) will be downloaded automatically.

### 2. Start the Backend

```bash
uv run python -m backend.main
```

**Expected output:**
```
Loading embedding model: sentence-transformers/all-MiniLM-L6-v2
Embedding model loaded successfully
Vector database initialized at data/vectordb
Current knowledge units: 0
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### 3. Verify RAG is Enabled

```bash
curl http://localhost:8001/ | jq
```

**Expected:**
```json
{
  "status": "ok",
  "service": "LLM Council API",
  "rag_enabled": true
}
```

### 4. Check RAG Stats

```bash
curl http://localhost:8001/api/rag/stats | jq
```

**Expected (empty DB):**
```json
{
  "enabled": true,
  "total_knowledge_units": 0,
  "consensus_distribution": {
    "single_source": 0,
    "dual_source": 0,
    "majority": 0,
    "full_consensus": 0
  }
}
```

---

## Manual Testing Scenarios

### Scenario 1: First Query (Knowledge Creation)

**Objective:** Verify knowledge extraction and storage

**Steps:**
1. Start frontend: `cd frontend && npm run dev`
2. Open http://localhost:5173
3. Create new conversation
4. Ask: "What is quantum computing?"
5. Wait for all 3 stages to complete

**What to verify:**

**In Browser DevTools (Network tab):**
- Look for SSE events:
  - `rag_retrieval_start`
  - `rag_retrieval_complete` with `retrieved_count: 0` (empty DB)
  - `rag_storage_start`
  - `rag_storage_complete` with dedup metrics

**In Backend Logs:**
- No errors during embedding
- Knowledge units extracted
- New vectors stored

**Via API:**
```bash
curl http://localhost:8001/api/rag/stats | jq
```

**Expected:**
```json
{
  "total_knowledge_units": 15-30,  // Depends on response length
  "consensus_distribution": {
    "single_source": 15-30,  // All single-source (first time)
    "dual_source": 0,
    "majority": 0,
    "full_consensus": 0
  }
}
```

**Success criteria:**
- ✅ Knowledge units stored
- ✅ Dedup rate: 0-20% (mostly new content)
- ✅ No errors

---

### Scenario 2: Related Follow-up (Partial Deduplication)

**Objective:** Verify RAG retrieval and semantic deduplication

**Steps:**
1. Same conversation as Scenario 1
2. Ask: "How do qubits work?"
3. Wait for completion

**What to verify:**

**In SSE events:**
- `rag_retrieval_complete` with `retrieved_count: 5-10` (relevant chunks)
- `consensus_info` showing avg_consensus_score: 0.25-0.50

**In Stage 1 responses:**
- Models should reference previous knowledge
- Look for phrases like "As mentioned..." or "Building on..."

**Dedup metrics:**
```json
{
  "deduplication_rate": 0.40-0.60,
  "semantic_duplicates": 8-15,
  "stored_new": 10-15
}
```

**Database growth:**
```bash
curl http://localhost:8001/api/rag/stats | jq '.total_knowledge_units'
# Should be ~25-50 (not 30-60 due to dedup)
```

**Success criteria:**
- ✅ RAG context retrieved
- ✅ Dedup rate: 40-60%
- ✅ Database growth sub-linear
- ✅ Some consensus updates (dual_source count increases)

---

### Scenario 3: Repeat Query (High Deduplication)

**Objective:** Verify exact and semantic dedup on repeated content

**Steps:**
1. New conversation
2. Ask: "What is quantum computing?" (same as Scenario 1)
3. Wait for completion

**What to verify:**

**RAG retrieval:**
- `retrieved_count: 10` (high-quality chunks available)
- `avg_consensus_score: 0.25-0.50` (if previous query had 1-2 models)

**Dedup metrics:**
```json
{
  "deduplication_rate": 0.70-0.90,
  "exact_duplicates": 5-10,
  "semantic_duplicates": 10-20,
  "stored_new": 2-5
}
```

**Consensus distribution:**
```bash
curl http://localhost:8001/api/rag/stats | jq '.consensus_distribution'
```

**Expected:**
- `dual_source` or `majority` counts increase
- Some chunks now have higher consensus scores

**Success criteria:**
- ✅ High dedup rate (70-90%)
- ✅ Minimal storage growth
- ✅ Consensus scores increasing
- ✅ Answers similar to first query (consistency)

---

### Scenario 4: Unrelated Topic (Low Deduplication)

**Objective:** Verify system handles diverse topics

**Steps:**
1. New conversation
2. Ask: "How do I make chocolate chip cookies?"
3. Wait for completion

**What to verify:**

**RAG retrieval:**
- `retrieved_count: 0-3` (quantum computing knowledge not relevant)
- Low semantic similarity scores

**Dedup metrics:**
```json
{
  "deduplication_rate": 0.05-0.20,
  "semantic_duplicates": 1-5,
  "stored_new": 20-25
}
```

**Database:**
- New domain, mostly single-source chunks

**Success criteria:**
- ✅ Low retrieval from unrelated domain
- ✅ Low dedup rate (new content)
- ✅ System handles domain shift gracefully

---

## Automated Tests

### Test 1: Deduplication Rate

```python
import httpx
import asyncio

async def test_deduplication():
    async with httpx.AsyncClient() as client:
        # First query
        response1 = await client.post(
            "http://localhost:8001/api/conversations",
            json={}
        )
        conv_id = response1.json()['id']
        
        # Send message
        response2 = await client.post(
            f"http://localhost:8001/api/conversations/{conv_id}/message",
            json={"content": "What is machine learning?"}
        )
        
        rag_metrics = response2.json()['metadata']['rag']
        dedup_rate = rag_metrics['deduplication']['deduplication_rate']
        
        print(f"First query dedup rate: {dedup_rate:.2%}")
        assert dedup_rate < 0.30, "First query should have low dedup"
        
        # Repeat query
        response3 = await client.post(
            f"http://localhost:8001/api/conversations/{conv_id}/message",
            json={"content": "What is machine learning?"}
        )
        
        rag_metrics2 = response3.json()['metadata']['rag']
        dedup_rate2 = rag_metrics2['deduplication']['deduplication_rate']
        
        print(f"Repeat query dedup rate: {dedup_rate2:.2%}")
        assert dedup_rate2 > 0.60, "Repeat should have high dedup"

asyncio.run(test_deduplication())
```

**Expected output:**
```
First query dedup rate: 15%
Repeat query dedup rate: 82%
```

---

### Test 2: Consensus Evolution

```python
async def test_consensus():
    async with httpx.AsyncClient() as client:
        # Check initial state
        stats1 = await client.get("http://localhost:8001/api/rag/stats")
        initial = stats1.json()['consensus_distribution']
        
        # Create conversation and ask question
        conv = await client.post("http://localhost:8001/api/conversations", json={})
        conv_id = conv.json()['id']
        
        await client.post(
            f"http://localhost:8001/api/conversations/{conv_id}/message",
            json={"content": "Explain neural networks"}
        )
        
        stats2 = await client.get("http://localhost:8001/api/rag/stats")
        after_first = stats2.json()['consensus_distribution']
        
        # Ask same question again
        await client.post(
            f"http://localhost:8001/api/conversations/{conv_id}/message",
            json={"content": "Explain neural networks"}
        )
        
        stats3 = await client.get("http://localhost:8001/api/rag/stats")
        after_second = stats3.json()['consensus_distribution']
        
        print("Consensus evolution:")
        print(f"Initial: {initial}")
        print(f"After first: {after_first}")
        print(f"After second: {after_second}")
        
        # Verify consensus increased
        assert after_second['dual_source'] > after_first['dual_source']

asyncio.run(test_consensus())
```

---

## Performance Testing

### Benchmark: RAG Overhead

```python
import time
import httpx
import asyncio

async def benchmark_overhead():
    async with httpx.AsyncClient(timeout=300.0) as client:
        conv = await client.post("http://localhost:8001/api/conversations", json={})
        conv_id = conv.json()['id']
        
        # Time with RAG
        start = time.time()
        response = await client.post(
            f"http://localhost:8001/api/conversations/{conv_id}/message",
            json={"content": "Explain photosynthesis"}
        )
        with_rag = time.time() - start
        
        rag_metrics = response.json()['metadata']['rag']
        
        print(f"Total time with RAG: {with_rag:.2f}s")
        print(f"Retrieved: {rag_metrics['retrieved_count']} chunks")
        print(f"Stored: {rag_metrics['deduplication']['stored_new']} new chunks")
        print(f"Dedup rate: {rag_metrics['deduplication']['deduplication_rate']:.1%}")

asyncio.run(benchmark_overhead())
```

**Expected:**
- Total time: Similar to baseline (RAG overhead ~100-200ms)
- Retrieved: 0-10 chunks (depends on DB state)
- Stored: 15-30 chunks
- Dedup rate: Varies by query

---

## Troubleshooting

### Issue: "Model download failed"

**Symptoms:**
```
OSError: Can't load tokenizer for 'sentence-transformers/all-MiniLM-L6-v2'
```

**Fix:**
```bash
# Manually download model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

---

### Issue: ChromaDB errors

**Symptoms:**
```
sqlite3.OperationalError: database is locked
```

**Fix:**
```bash
# Stop all backend instances
pkill -f "backend.main"

# Remove lock files
rm -rf data/vectordb/*.lock

# Restart
uv run python -m backend.main
```

---

### Issue: High memory usage

**Symptoms:**
- Backend using >2GB RAM

**Causes:**
- Large vector database
- Embedding model in memory

**Fixes:**
1. **Reduce embedding model size:**
   ```python
   # In config.py, change to smaller model:
   EMBEDDING_MODEL = "sentence-transformers/paraphrase-MiniLM-L3-v2"  # 61MB
   ```

2. **Disable RAG temporarily:**
   ```bash
   # .env
   RAG_ENABLED=false
   ```

---

### Issue: Poor deduplication

**Symptoms:**
- Dedup rate always < 10%

**Diagnosis:**
```python
# Test semantic similarity
from backend.embedding import embedding_service

text1 = "Quantum computing uses qubits"
text2 = "Qubits are used in quantum computing"

emb1 = embedding_service.embed(text1)
emb2 = embedding_service.embed(text2)

similarity = embedding_service.similarity(emb1, emb2)
print(f"Similarity: {similarity:.3f}")  # Should be >0.85
```

**Fixes:**
- Lower threshold to 0.95-0.96
- Verify embedding model loaded correctly

---

## Success Checklist

After testing, verify:

- [ ] Backend starts without errors
- [ ] Embedding model loads successfully
- [ ] RAG stats endpoint returns data
- [ ] First query stores knowledge (dedup < 30%)
- [ ] Repeat query deduplicates (dedup > 60%)
- [ ] Consensus scores increase over time
- [ ] Database growth is sub-linear
- [ ] Retrieval returns relevant chunks
- [ ] No memory leaks over 10+ queries
- [ ] SSE events include RAG data

---

## Next Steps

1. **Monitor production:**
   - Track dedup rates over time
   - Monitor database growth
   - Analyze consensus distribution

2. **Tune parameters:**
   - Adjust threshold based on domain
   - Optimize CONSENSUS_WEIGHT
   - Fine-tune CHUNK_SIZE

3. **Iterate:**
   - Collect user feedback on answer quality
   - Add telemetry for retrieval relevance
   - Implement A/B testing (RAG on/off)

---

## Reference

**Config file:** `backend/config.py`
**Main changes:** `backend/council.py`, `backend/main.py`
**New modules:** `backend/embedding.py`, `backend/knowledge.py`, `backend/vectordb.py`, `backend/deduplication.py`

**Documentation:** See `RAG_SYSTEM.md` for comprehensive details.
