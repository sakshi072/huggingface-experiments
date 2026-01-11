"""
What this does:
1. Get a text file -> store in minIO
2. Split into chunks
3. Generate embeddings (local model)
4. Store in pgvector
5. Query and retrieve relevant chunks
6. Generate answer 
"""

import os
import asyncio
from typing import List, Dict, Optional
from uuid import UUID

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import db_manager
from models import Document, DocumentChunk
from storage_service import storage_service
from llm_service import LLMService
from adv_parser import DocumentParser
import hashlib

CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

class KnowledgeBase:
    """Minimal RAG system for learning."""

    def __init__(self):
        """Initialize components."""
        print("Initializing Minimal RAG System...")

        # Embedding model (runs locally, no API neede)
        print(f" Loading embedding model: {EMBEDDING_MODEL}")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)
        
        # Text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size = CHUNK_SIZE,
            chunk_overlap = CHUNK_OVERLAP,
            separators = ["\n\n","\n", ". ", " ", ""]
        )

        # print("   Initializing LLM service...")
        # try:
        #     self.llm = LLMService(model_name="llama")
        #     print("   ✓ LLM ready!")
        # except ValueError as e:
        #     print(f"{e}")
        
        # Initialize database
        db_manager.initialize()
        
        print("✅ Initialization complete!\n")

    def calculate_file_hash(self, file_data:bytes) -> str:
        return hashlib.sha256(file_data).hexdigest()

    async def ingest_file(
        self, 
        file_data:bytes,
        filename: str,
        file_type: str,
        metadata: Optional[Dict] = None
    ) -> UUID:
        """
        Ingest a document: upload to MinIO, parse, chunk, embed, and store in PostgreSQL
        
        Args:
            file_data: File content as bytes
            filename: Original filename
            file_type: File extension (pdf, docx, txt, md)
            metadata: Optional metadata (pages, author, etc.)
            
        Returns:
            Document UUID
        """
        print(f"\n📄 Ingesting document: {filename}")

        async with db_manager.session() as session:

            # Calculate hash
            file_hash = self.calculate_file_hash(file_data)

            # Check for duplicates
            existing = await session.execute(
                select(Document).where(Document.file_hash == file_hash) 
            )
            if existing_doc := existing.scalar_one_or_none():
                print(f"⚠️ Duplicate! Using existing doc {existing_doc.id}")
                return existing_doc.id, True

            try: 
                # 1. Upload File to MinIO
                print("   1/6 Uploading original file to MinIO...")
                object_key = storage_service.upload_file(file_data, filename)
                print(f"       Stored as: {object_key}")

                # Validate metadata parameter
                if metadata is not None and not isinstance(metadata, dict):
                    print(f"       ⚠️  Warning: metadata parameter is {type(metadata)}, expected dict")
                    metadata = None
                    
                # 2. Create document record
                print("   2/6 Creating document record...")
                document = Document(
                    filename=filename,
                    file_type=file_type,
                    file_size = len(file_data),
                    file_hash = file_hash,
                    minio_object_key = object_key,
                    status="processing",
                    metadata_ = metadata or {}
                )

                session.add(document)
                await session.flush() # Get document.id
                print(f"       Document ID: {document.id}")

                # 3. Parse the ORIGINAL file (not pre-parsed text)
                print("   3/6 Parsing document...")
                try:
                    parsed_result = DocumentParser.parse(file_data, file_type)
                    
                    # Validate parser result
                    if not isinstance(parsed_result, dict):
                        raise ValueError(f"Parser returned {type(parsed_result)} instead of dict")
                    
                    if "text" not in parsed_result:
                        raise ValueError("Parser result missing 'text' key")
                    
                    parsed_text = parsed_result["text"]
                    parse_metadata = parsed_result.get("metadata", {})
                    
                    # Validate metadata is a dict
                    if not isinstance(parse_metadata, dict):
                        parse_metadata = {"raw_metadata": str(parse_metadata)}
                    
                    # Check if extraction was successful
                    if len(parsed_text) < 10:
                        raise ValueError(
                            f"Extracted text is too short ({len(parsed_text)} chars). "
                            "PDF may be scanned/image-based (OCR not supported) or corrupted."
                        )
                    
                except Exception as parse_error:
                    print(f"       ❌ Parsing failed: {parse_error}")
                    raise ValueError(f"Failed to parse {file_type} file: {parse_error}")
                
                if parse_metadata:
                    try:
                        if not isinstance(parse_metadata, dict):
                            print(f"       ⚠️  Warning: parse_metadata is {type(parse_metadata)}, converting...")
                            parse_metadata = {"raw": str(parse_metadata)}
                        
                        combined_metadata = {**(metadata or {}), **parse_metadata}                        
                        document.metadata_ = combined_metadata

                    except Exception as meta_error:
                        print(f"       ❌ Metadata update failed: {meta_error}")
                        print(f"       metadata type: {type(metadata)}")
                        print(f"       parse_metadata type: {type(parse_metadata)}")
                        print(f"       document.metadata_ type: {type(document.metadata_)}")
                        raise

                # 4. Chunk text
                print("   4/6 Chunking text...")
                chunks = self.text_splitter.split_text(parsed_text)
                print(f"       Created {len(chunks)} chunks")
                
                # 5. Generate embeddings
                print("   5/6 Generating embeddings...")
                embeddings = self.embedder.encode(
                    chunks,
                    show_progress_bar=False,
                    convert_to_numpy=True
                )
                print(f"       Generated {len(embeddings)} embeddings")

                # 6. Store chunks with embeddings
                print("   6/6 Storing chunks in PostgreSQL...")
                for idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
                    chunk = DocumentChunk(
                        document_id = document.id,
                        chunk_index = idx,
                        text = chunk_text,
                        embedding=embedding.tolist(),
                        token_count = len(chunk_text.split()),
                        page_number=metadata.get('page_number') if metadata else None
                    )
                    session.add(chunk)
                
                # Update document status
                document.status = "completed"
                document.chunk_count = len(chunks)

                await session.flush()

                print(f"✅ Document ingested successfully!")
                print(f"   Document ID: {document.id}")
                print(f"   Chunks: {len(chunks)}")
                
                return document.id, False
            except Exception as e:
                # Mark document as failed
                if 'document' in locals():
                    document.status = "failed"
                    document.error_message = str(e)
                    await session.commit()
                
                print(f"❌ Ingestion failed: {e}")
                raise

    async def search(
        self, 
        query_text:str, 
        top_k:int=3,
    ) -> Dict:
        """
        Query the RAG system
        
        Args:
            query_text: User's question
            top_k: Number of chunks to retrieve
            
        Returns:
            Dictionary with sources
        """
        print(f"\n❓ Query: {query_text}")

        async with db_manager.session() as session:
            # 1. Generate query embedding
            print("   1/3 Generating query embedding...")
            query_embedding = self.embedder.encode(
                query_text,
                show_progress_bar=False,
                convert_to_numpy=True
            ).tolist()

            # 2. Search for similar chunks using pgvector
            print("   2/3 Searching vector database...")

            # Use pgvector's cosine distance operator
            similarity_col = (1 - DocumentChunk.embedding.cosine_distance(query_embedding)).label("similarity")

            stmt = (
                select(
                    DocumentChunk,
                    Document,
                    similarity_col
                )
                .join(Document)
                .where(Document.status == "completed")
                .order_by(similarity_col.desc())
                .limit(top_k)
            )

            result = await session.execute(stmt)
            results = result.all()

            if not results:
                return {
                    "answer": "No relevant documents found.",
                    "sources": []
                }
            
            print(f"       Found {len(results)} relevant chunks")

            # 3. Generate answer with LLM
            print("   3/3 Generating answer...")

            # Prepare context and sources
            sources = []

            for chunk, doc, similarity in results:
                try:
                    file_url = storage_service.get_presigned_url(doc.minio_object_key, expiray_seconds=3600)
                except Exception as e:
                    print(f"   ⚠️  Failed to generate URL for {doc.filename}: {e}")
                    file_url = None

                sources.append({
                    "document_id": str(doc.id),
                    "filename": doc.filename,
                    "chunk_index": chunk.chunk_index,
                    "similarity": float(similarity),
                    "text": chunk.text,
                    "file_url": file_url
                })

            # # Generate answer
            # print("   Generating answer with LLM...")
            # answer = self.llm.generate(
            #     query=query_text,
            #     context_chunks=context_chunks,
            #     max_tokens=max_tokens,
            #     temperature=temperature
            # )

            print(f"✅ Sources generated!")
            print(sources)

            return {
                "sources": sources,
                "query": query_text
            }
    
    async def get_document(self, document_id: UUID) -> Optional[Dict]:
        """Get document metadata"""
        async with db_manager.session() as session:
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return None
            
            return {
                "id": str(doc.id),
                "filename": doc.filename,
                "file_type": doc.file_type,
                "file_size": doc.file_size,
                "status": doc.status,
                "chunk_count": doc.chunk_count,
                "metadata": dict(doc.metadata_) if doc.metadata_ else {},
                "created_at": doc.created_at.isoformat()
            }

    async def list_documents(self, limit: int = 100) -> List[Dict]:
        """List all documents"""
        async with db_manager.session() as session:
            result = await session.execute(
                select(Document)
                .order_by(Document.created_at.desc())
                .limit(limit)
            )
            docs = result.scalars().all()

        return [
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "status": doc.status,
                "chunk_count": doc.chunk_count,
                "created_at": doc.created_at.isoformat()
            }
            for doc in docs
        ]

    async def delete_document(self, document_id: UUID) -> bool:
        """Delete document and all its chunks"""
        async with db_manager.session() as session:
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            doc = result.scalar_one_or_none()

            if not doc:
                return False
            
            # Delete from MinIO
            try:
                storage_service.delete_file(doc.minio_object_key)
            except Exception as e:
                print(f"⚠️  Failed to delete from MinIO: {e}")

            # Delete from database (cascades to chunks)
            await session.delete(doc)
            await session.commit()

            return True

    
    async def get_stats(self) -> Dict:
        """Get RAG system statistics"""
        async with db_manager.session() as session:
            # Count documents
            doc_result = await session.execute(
                select(func.count(Document.id))
            )
            total_docs = doc_result.scalar()

            # Count chunks
            chunk_result = await session.execute(
                select(func.count(DocumentChunk.id))
            )
            total_chunks = chunk_result.scalar()

            # Count by status
            status_result = await session.execute(
                select(Document.status, func.count(Document.id))
                .group_by(Document.status)
            )

            status_counts = {status: count for status, count in status_result.all()}

            return {
                "total_documents": total_docs,
                "total_chunks": total_chunks,
                "status_breakdown": status_counts
            }