"""
Advanced semantic-aware chunking strategies
"""

import re
from typing import List, Dict, Tuple
from dataclasses import dataclass
import numpy as np
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

@dataclass
class SemanticChunk:
    """Enhanced chunk with semantic metadata"""
    text:str
    chunk_index:int
    chunk_type:str # 'paragraph', 'heading', 'list', 'table', 'code'
    section_title:str = None
    page_number:int = None
    keywords: List[str] = None
    semantic_density:float = None
    quality_score: float = None

class SemanticChunker:
    """Advanced chunking with semantic awareness"""

    def __init__(
        self,
        embedder: SentenceTransformer,
        chunk_size: int = 512,
        chunk_overlap: int = 50
    ):
        self.embedder = embedder
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Standar splitter for fallback
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

    def chunk_document(
        self,
        text:str,
        file_type:str = 'txt',
        metadata: Dict = None  
    ) -> List[SemanticChunk]:
        """
        Chunk document with semantic awareness
        
        Strategies:
        1. Preserve semantic boundaries (sections, paragraphs)
        2. Detect chunk types (headings, lists, code blocks)
        3. Calculate quality metrics
        4. Extract keywords
        """

        if file_type == 'md':
            return self._chunk_markdown(text, metadata)
        elif file_type == 'pdf':
            return self._chunk_pdf(text, metadata)
        else:
            return self._chunk_generic(text, metadata)
        
    def _chunk_markdown(self, text:str, metadata:Dict) -> List[SemanticChunk]:
        """Markdown-aware chunking preserving structure"""
        chunks = []
        current_section = None

        # Split by headers while preserving hierarchy
        sections = re.split(r'(^#{1,6}\s+.+$)', text, flags=re.MULTILINE)

        buffer = []
        chunk_index = 0

        for i, section in enumerate(sections):
            if not section.strip():
                continue

            # Detect header
            header_match = re.match(r'^(#{1,6})\s+(.+)$', section)
            if header_match:
                current_section = header_match.group(2).strip()
                buffer.append(current_section)
            else:
                # Content under header
                buffer.append(section)

                # Check if buffer exceeds chunk size
                buffer_text = '\n\n'.join(buffer)
                if len(buffer_text) > self.chunk_size:
                    # Create chunk
                    chunk = self._create_semantic_chunk(
                        buffer_text,
                        chunk_index,
                        'section',
                        current_section,
                        metadata
                    )
                    chunks.append(chunk)
                    chunk_index +=1

                    # Keep last part for overlap
                    overlap_text = buffer_text[-self.chunk_overlap:]
                    buffer = [overlap_text]

        # Remaining buffer
        if buffer:
            buffer_text = '\n\n'.join(buffer)
            chunk = self._create_semantic_chunk(
                buffer_text,
                chunk_index,
                'section',
                current_section,
                metadata
            )
            chunks.append(chunk)

        return chunks

    def _chunk_pdf(self, text:str, metadata:Dict) -> List[SemanticChunk]:
        """PDF-aware chunking with page markers"""
        chunks = []
        chunk_index = 0

        page_pattern = r'\[Page (\d+)\]'
        pages = re.split(page_pattern, text)

        current_page = None
        for i in range(1, len(pages), 2):
            page_num = int(pages[i])
            page_text = pages[i+1] if i+1 < len(pages) else ''

            # Chunk page content
            page_chunks = self.text_splitter.split_text(page_text)

            for page_chunk in page_chunks:
                chunk = self._create_semantic_chunk(
                    page_chunk,
                    chunk_index,
                    'paragraph',
                    None,
                    metadata,
                    page_number=page_num
                )
                chunks.append(chunk)
                chunk_index +=1
        
        return chunks
    
    def _chunk_generic(self, text:str, metadata:Dict) -> List[SemanticChunk]:
        """Generic semantic chunking"""
        
        # Use standard splitter
        text_chunks = self.text_splitter.split_text(text)

        chunks = []
        for i, chunk_text in enumerate(text_chunks):
            chunk_type = self._detect_chunk_type(chunk_text)
            chunk = self._create_semantic_chunk(
                chunk_text,
                i,
                chunk_type,
                None,
                metadata
            )
            chunks.append(chunk)
       
        return chunks

    def _create_semantic_chunk(
        self,
        text: str,
        index:int,
        chunk_type:str,
        section_title:str,
        metadata:Dict,
        page_number:int = None
    ) -> SemanticChunk:
        """Create chunk with semantic metadata"""

        # Extract keywords
        keywords = self._extract_keywords(text)

        # Calculate semantic density
        density = self._calculate_semantic_denstiy(text)

        # Calculate quality score
        quality = self._calculate_quality_score(text, keywords, density)

        return SemanticChunk(
            text=text,
            chunk_index=index,
            chunk_type=chunk_type,
            section_title=section_title,
            page_number=page_number,
            keywords=keywords,
            semantic_density=density,
            quality_score=quality
        )
    
    def _detect_chunk_type(self, text:str) -> str:
        """Detect semantic type of chunk"""
        text_lower = text.lower().strip()

        # Code blocks
        if '```' in text or text.count('\n   ') > 2:
            return 'code'
        
        # Lists
        if re.search(r'^[\s]*[-*•]\s', text, re.MULTILINE):
            return 'list'
        
        # Tables
        if text.count('|') > 3:
            return 'table'

        # Headings
        if re.match(r'^#{1,6}\s+', text) or len(text) < 100:
            return 'heading'
        
        return 'paragraph'
    
    def _extract_keywords(self, text:str, top_k:int=5) -> List[str]:
        """Extract key terms using simple TF-IDF-like approach"""

        # Remove common words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this',
            'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }

        # Extract words
        words = re.findall(r'\b[a-z]{3,}\b', text.lower())

        # Count frequencies
        word_freq = {}
        for word in words:
            if word not in stop_words:
                word_freq[word] = 1 + word_freq.get(word, 0)
            
        # Get top-k
        sorted_words = sorted(word_freq.items(), key=lambda x:x[1], reverse=True)
        return [word for word, freq in sorted_words[:top_k]]

    def _calculate_semantic_denstiy(self, text:str) -> float:
        """
        Calculate information density
        Higher = more informative content
        """

        # Metrics:
        #1. Unique word ratio
        words = text.lower().split()
        unique_ratio = len(set(words)) / max(len(words), 1)

        # 2. Average word length
        avg_word_len = sum(len(w) for w in words) / max(len(words), 1)

        # 3. Sentence complexity
        sentences = re.split(r'[.!?]+', text)
        avg_sentence_len = len(words) / max(len(sentences), 1)

        # Combine metrics (normalized)
        density = (
            unique_ratio * 0.4 +
            min(avg_word_len / 10, 1.0) * 0.3 +
            min(avg_sentence_len / 20, 1.0) * 0.3
        )

        return min(density, 1.0)
    
    def _calculate_quality_score(self, text:str, keywords:List[str], density:float) -> float:
        """
        Calculate chunk quality score (0-1)
        Higher = better quality chunk
        """

        # Length score (prefer medium-length chunks)
        text_len = len(text)
        if text_len < 100:
            len_score = text_len/100
        elif text_len > 1000:
            len_score = max(0, 1 - (text_len - 1000)/1000)
        else:
            len_score = 1.0
    
        # Keyword richness
        keyword_score = min(len(keywords)/5, 1.0)

        # Structure score (complete sentences)
        sentence_endings = len(re.findall(r'[.!?]', text))
        structure_score = min(sentence_endings/3, 1.0)

        # Combine
        quality = (
            len_score * 0.3 + 
            keyword_score * 0.3 +
            density * 0.2 +
            structure_score * 0.2
        )

        return quality
    
class HybridChunker:
    """
    Hybrid chunking strategy combining:
    1. Semantic boundaries
    2. Sliding windows
    3. Parent-child relationships
    """

    def __init__(self, embedder:SentenceTransformer):
        self.embedder = embedder
        self.semantic_chunker = SemanticChunker(
            embedder,
            chunk_size=512,
            chunk_overlap=50
        )

    def chunk_with_context(
        self,
        text:str,
        file_type:str = 'txt'
    ) -> Tuple[List[SemanticChunk], List[str]]:
        """
        Create chunks with parent context
        
        Returns:
        - child_chunks: Small chunks for precise retrieval
        - parent_chunks: Larger context chunks
        """

        # Create semantic chunks (children)
        child_chunks = self.semantic_chunker.chunk_document(text, file_type)

        # Create parent chunks 
        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1024,
            chunk_overlap=100,
            separators=["\n\n", "\n", ". ", " "]
        )
        parent_chunks = parent_splitter.split_text(text)

        return child_chunks, parent_chunks
