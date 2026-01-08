"""
What this does:
1. Read a text file
2. Split into chunks
3. Generate embeddings (local model)
4. Store in ChromaDB (local, file-based)
5. Query and retrieve relevant chunks
6. Generate answer 
"""

import os
from pathlib import Path
from typing import List
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 512
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHROMA_DB_PATH = './chroma_db'

class MinimalRAG:
    """Minimal RAG system for learning."""

    def __init__(self):
        """Initialize components."""
        print("Initializing Minimal RAG System...")

        # 1. Embedding model (runs locally, no API neede)
        print(f" Loading embedding model: {EMBEDDING_MODEL}")
        self.embedder = SentenceTransformer(EMBEDDING_MODEL)

        # 2. Vector Database (ChromaDB - simple, local, no Docker)
        print(f" Setting up Chroma at: {CHROMA_DB_PATH}")
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

        # Get or create collection
        try:
            self.collection = self.chroma_client.get_collection("documents")
            print(f"   ✓ Found existing collection with {self.collection.count()} documents")
        except:
            self.collection = self.chroma_client.create_collection(
                name="documents",
                metadata={"hnsw:space": "cosine"}
            )
            print("Created new collection")
        
        # 3. Text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size = CHUNK_SIZE,
            chunk_overlap = CHUNK_OVERLAP,
            separators = ["\n\n","\n", ". ", " ", ""]
        )
        print("Initialization completed!\n")

    def ingest_file(self, filepath:str) -> int:
        """
        Ingest a text file into the RAG system.
        
        Args:
            filepath: Path to text file
            
        Returns:
            Number of chunks created
        """
        print(f"📄 Ingesting file: {filepath}")

        # 1. Read file
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        
        print(f" File size: {len(text)} characters")

        # 2. Split into chunks
        chunks = self.text_splitter.split_text(text)
        print(f"   Split into {len(chunks)} chunks")

        # 3. Generate embeddings
        print("Generating Embeddings")
        embeddings = self.embedder.encode(chunks).tolist()

        # 4. Store in ChromaDB
        filename = Path(filepath).name
        doc_id = filename.replace(".","_")

        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {"source": filename, "chunk_index": i} 
            for i in range(len(chunks))
        ]

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )

        print(f"✅ Ingested {len(chunks)} chunks from {filename}\n")
        return len(chunks)

    def query(self, question:str, top_k:int=3) -> dict:
        """
        Query the RAG system.
        
        Args:
            question: User question
            top_k: Number of chunks to retrieve
            
        Returns:
            Dictionary with answer and sources
        """
        print(f"❓ Query: {question}")

        # 1. Generate query embeddings
        query_embedding = self.embedder.encode([question])[0].tolist()

        # 2. Search similar chunks
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )

        # 3. Extract results
        chunks = results['documents'][0]
        metadatas = results['metadatas'][0]
        distances = results['distances'][0]

        print(f"   Found {len(chunks)} relevant chunks\n")

        # 4. Build content and simple answer
        context = "\n\n".join(chunks)

        # For now, just return the most relevant chunk as "answer"
        # We'll add LLM generation in Phase 2
        answer = f"Based on the documents, here's what I found:\n\n{chunks[0][:500]}..."
        
        return {
            "answer": answer,
            "context": context,
            "sources": [
                {
                    "chunk": chunk,
                    "source": meta["source"],
                    "chunk_index": meta["chunk_index"],
                    "similarity": 1 - dist
                }
                for chunk, meta, dist in zip(chunks, metadatas, distances)
            ]
        }

    def get_stats(self) -> dict:
        count = self.collection
        return {
            "total_chunks":count,
            "collection": "documents"
        }

def main():
    rag = MinimalRAG()

    sample_file = "sample_doc.txt"
    if not Path(sample_file).exists():
        print("📝 Creating sample document...\n")
        with open(sample_file, 'w') as f:
            f.write("""
            Introduction to Machine Learning

Machine learning is a subset of artificial intelligence (AI) that enables 
systems to learn and improve from experience without being explicitly programmed.

Key Concepts:

1. Supervised Learning
Supervised learning uses labeled training data. The algorithm learns from 
input-output pairs to predict outputs for new inputs. Common applications 
include image classification and spam detection.

2. Unsupervised Learning
Unsupervised learning works with unlabeled data. The algorithm finds hidden 
patterns and structures in the data. Clustering and dimensionality reduction 
are typical use cases.

3. Neural Networks
Neural networks are computing systems inspired by biological neural networks. 
They consist of layers of interconnected nodes (neurons) that process information 
and learn patterns from data.

4. Deep Learning
Deep learning is a subset of machine learning that uses neural networks with 
multiple layers (deep neural networks). It excels at processing unstructured 
data like images, text, and audio.

Applications of Machine Learning:

- Healthcare: Disease diagnosis, drug discovery
- Finance: Fraud detection, algorithmic trading
- Transportation: Autonomous vehicles, route optimization
- Retail: Recommendation systems, inventory management
- Natural Language Processing: Chatbots, translation services

Conclusion:

Machine learning continues to evolve rapidly, enabling increasingly sophisticated 
applications across various industries. Understanding its fundamentals is crucial 
for leveraging its capabilities effectively.
            """)

    # Ingest the document
    print("="*60)
    num_chunks = rag.ingest_file(sample_file)

    # Show Statistics
    stats = rag.get_stats()
    print("="*60)
    print(f"📊 Database Stats:")
    print(f"   Total chunks: {stats['total_chunks']}")
    print(f"   Collection: {stats['collection']}")
    print("="*60 + "\n")

    questions = [
        "What is Reinforcement machine learning?",
    ]
    for question in questions:
        print("="*60)
        result = rag.query(question, top_k=3)

        print(f"💡 Answer:\n{result['answer']}\n")
        
        print(f"📚 Sources ({len(result['sources'])} chunks):")
        for i, source in enumerate(result['sources'], 1):
            print(f"\n   {i}. {source['source']} (chunk {source['chunk_index']})")
            print(f"      Similarity: {source['similarity']:.3f}")
            print(f"      Text: {source['chunk'][:150]}...")
        
        print("\n")
    
    print("="*60)
    print("✅ Demo complete!")
    print("\nNext steps:")
    print("  1. Try adding your own .txt files")
    print("  2. Experiment with different questions")
    print("  3. Look at the ChromaDB storage in ./chroma_db/")
    print("="*60)


if __name__ == "__main__":
    main()