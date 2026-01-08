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
from llm_service import LLMService

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

        print("   Initializing LLM service...")
        try:
            self.llm = LLMService(model_name="llama")
            print("   ✓ LLM ready!")
        except ValueError as e:
            print(f"{e}")
        
        print("✅ Initialization complete!\n")

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

        print(f"   Retrieved {len(chunks)} relevant chunks")

        if not chunks:
            return {
                "answer": "I cannot find relevant information to answer your question.",
                "context": "",
                "sources": []
            }

        # Prepare context chunks for LLM
        context_chunks = [
                {
                    "chunk": chunk,
                    "source": meta["source"],
                    "chunk_index": meta["chunk_index"],
                    "similarity": 1 - dist
                }
                for chunk, meta, dist in zip(chunks, metadatas, distances)
            ]

        # 5. Generate answer
        print("   Generating answer with LLM...")
        answer = self.llm.generate(
            query=question,
            context_chunks=context_chunks,
            max_tokens=100,
            temperature=0.1
        )

        # 6. Build content and simple answer
        context = "\n\n".join(chunks)
        
        return {
            "answer": answer,
            "context": context,
            "sources": context_chunks,
        }

    def get_stats(self) -> dict:
        count = self.collection
        return {
            "total_chunks":self.collection.count(),
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

Introduction to Machine Learning

Machine learning is a subset of artificial intelligence (AI) that enables 
systems to learn and improve from experience without being explicitly programmed.
It focuses on developing computer programs that can access data and use it to 
learn for themselves.

Key Concepts:

1. Supervised Learning
Supervised learning uses labeled training data. The algorithm learns from 
input-output pairs to predict outputs for new inputs. Common applications 
include image classification, spam detection, and price prediction.

2. Unsupervised Learning
Unsupervised learning works with unlabeled data. The algorithm finds hidden 
patterns and structures in the data without predefined categories. Clustering 
and dimensionality reduction are typical use cases.

3. Neural Networks
Neural networks are computing systems inspired by biological neural networks. 
They consist of layers of interconnected nodes (neurons) that process information 
and learn patterns from data. Each connection has a weight that adjusts during 
training.

4. Deep Learning
Deep learning is a subset of machine learning that uses neural networks with 
multiple layers (deep neural networks). It excels at processing unstructured 
data like images, text, and audio. Popular architectures include CNNs for images 
and RNNs for sequences.

Applications of Machine Learning:

Healthcare: Machine learning assists in disease diagnosis, drug discovery, and 
personalized treatment plans. Models can analyze medical images and predict 
patient outcomes.

Finance: Financial institutions use ML for fraud detection, algorithmic trading, 
credit scoring, and risk assessment. Models analyze transaction patterns to 
identify anomalies.

Transportation: Autonomous vehicles rely heavily on machine learning for object 
detection, path planning, and decision making. ML also optimizes route planning 
and traffic prediction.

Retail: Recommendation systems suggest products based on user behavior. ML also 
powers inventory management, demand forecasting, and dynamic pricing.

Natural Language Processing: Chatbots, virtual assistants, machine translation, 
and sentiment analysis all leverage ML. Modern language models can understand 
and generate human-like text.

Conclusion:

Machine learning continues to evolve rapidly, enabling increasingly sophisticated 
applications across various industries. Understanding its fundamentals - from 
basic algorithms to deep learning - is crucial for leveraging its capabilities 
effectively in real-world problems.
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
        "What is machine learning?",
        "Explain the difference between supervised and unsupervised learning.",
        "What are the applications of machine learning in healthcare?"
    ]

    for question in questions:
        print("="*60)
        result = rag.query(question, top_k=3)

        print(f"💡 Answer LLM generated:\n{result['answer']}\n")
        
        print(f"📚 Sources ({len(result['sources'])} chunks):")
        for i, source in enumerate(result['sources'], 1):
            print(f"\n   {i}. {source['source']} (chunk {source['chunk_index']})")
            print(f"      Similarity: {source['similarity']:.3f}")
            print(f"      Text: {source['chunk'][:150]}...")
        
        print("\n")
    
    print("="*60)
    print("✅ Phase 2 Demo Complete!")
    print("\n🎓 What You Learned:")
    print("   ✓ LLM integration with HuggingFace")
    print("   ✓ Prompt engineering for RAG")
    print("   ✓ Context building from retrieved chunks")
    print("   ✓ Generating coherent answers from multiple sources")
    print("\n🚀 Next: Phase 3 - Add FastAPI for REST endpoints!")
    print("="*60)


if __name__ == "__main__":
    main()