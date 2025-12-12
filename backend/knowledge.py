"""Knowledge extraction and semantic chunking."""

import re
import hashlib
from typing import List, Dict, Any
from .config import CHUNK_SIZE


def normalize_text(text: str) -> str:
    """
    Normalize text for consistent processing.
    
    Args:
        text: Raw text
        
    Returns:
        Normalized text
    """
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    text = text.lower()
    return text


def compute_text_hash(text: str) -> str:
    """
    Compute stable hash for text.
    
    Args:
        text: Text to hash
        
    Returns:
        SHA-256 hash as hex string
    """
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def chunk_by_sentences(text: str, target_words: int = CHUNK_SIZE) -> List[str]:
    """
    Chunk text into semantic units based on sentences.
    
    Strategy:
    - Split by sentence boundaries
    - Group sentences to reach target word count
    - Preserve semantic coherence
    
    Args:
        text: Text to chunk
        target_words: Target words per chunk (approximate)
        
    Returns:
        List of text chunks
    """
    sentence_endings = r'[.!?]\s+'
    sentences = re.split(sentence_endings, text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return []
    
    chunks = []
    current_chunk = []
    current_word_count = 0
    
    for sentence in sentences:
        word_count = len(sentence.split())
        
        if current_word_count + word_count > target_words and current_chunk:
            chunks.append(' '.join(current_chunk))
            current_chunk = [sentence]
            current_word_count = word_count
        else:
            current_chunk.append(sentence)
            current_word_count += word_count
    
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    return chunks


def chunk_by_paragraphs(text: str) -> List[str]:
    """
    Chunk text by paragraph boundaries.
    
    Args:
        text: Text to chunk
        
    Returns:
        List of paragraph chunks
    """
    paragraphs = text.split('\n\n')
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    return paragraphs


def extract_code_blocks(text: str) -> List[Dict[str, str]]:
    """
    Extract code blocks from markdown text.
    
    Args:
        text: Markdown text
        
    Returns:
        List of dicts with 'type' ('code') and 'content'
    """
    code_pattern = r'```[\w]*\n(.*?)```'
    matches = re.findall(code_pattern, text, re.DOTALL)
    return [{'type': 'code', 'content': match.strip()} for match in matches]


def smart_chunk(text: str, target_words: int = CHUNK_SIZE) -> List[Dict[str, Any]]:
    """
    Intelligently chunk text preserving semantic boundaries.
    
    Strategy:
    1. Extract code blocks separately (treat as atomic units)
    2. Split remaining text by paragraphs if large enough
    3. Otherwise, chunk by sentences
    
    Args:
        text: Text to chunk
        target_words: Target words per chunk
        
    Returns:
        List of chunk dicts with 'text', 'type', and 'metadata'
    """
    chunks = []
    
    code_blocks = extract_code_blocks(text)
    for code_block in code_blocks:
        chunks.append({
            'text': code_block['content'],
            'type': 'code',
            'metadata': {'is_code': True}
        })
    
    text_without_code = re.sub(r'```[\w]*\n.*?```', '', text, flags=re.DOTALL)
    
    paragraphs = chunk_by_paragraphs(text_without_code)
    
    for para in paragraphs:
        word_count = len(para.split())
        
        if word_count > target_words * 1.5:
            sentence_chunks = chunk_by_sentences(para, target_words)
            for chunk_text in sentence_chunks:
                if chunk_text.strip():
                    chunks.append({
                        'text': chunk_text.strip(),
                        'type': 'text',
                        'metadata': {}
                    })
        else:
            if para.strip():
                chunks.append({
                    'text': para.strip(),
                    'type': 'text',
                    'metadata': {}
                })
    
    return chunks


def extract_knowledge_units(
    model_responses: List[Dict[str, Any]],
    user_query: str,
    conversation_id: str
) -> List[Dict[str, Any]]:
    """
    Extract knowledge units from multiple model responses.
    
    Args:
        model_responses: List of model response dicts with 'model' and 'response'
        user_query: The original user query
        conversation_id: ID of the conversation
        
    Returns:
        List of knowledge unit dicts
    """
    knowledge_units = []
    
    for model_resp in model_responses:
        try:
            model_name = model_resp.get('model', 'unknown')
            response_text = model_resp.get('response', '')
            
            if not response_text or not response_text.strip():
                continue
            
            chunks = smart_chunk(response_text)
            
            for chunk in chunks:
                try:
                    chunk_text = chunk.get('text', '').strip()
                    
                    if len(chunk_text.split()) < 10:
                        continue
                    
                    text_hash = compute_text_hash(chunk_text)
                    
                    knowledge_units.append({
                        'text': chunk_text,
                        'normalized_text': normalize_text(chunk_text),
                        'hash': text_hash,
                        'source_model': model_name,
                        'query_context': user_query,
                        'conversation_id': conversation_id,
                        'chunk_type': chunk.get('type', 'text'),
                        'metadata': chunk.get('metadata', {})
                    })
                except Exception as e:
                    print(f"ERROR: Failed to extract chunk from response: {e}")
                    continue
        except Exception as e:
            print(f"ERROR: Failed to extract knowledge units from model {model_resp.get('model', 'unknown')}: {e}")
            continue
    
    return knowledge_units
