import os
import asyncio
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore
from embeddings.embedder import get_embedder
from retrieval.hybrid_retriever import HybridRetriever
from chain.rag_chain import HybridRAGChain
from retrieval.reranker import CrossEncoderReranker

load_dotenv()

async def test_search():
    client = QdrantClient(
        url=os.getenv("QDRANT_URL"),
        api_key=os.getenv("QDRANT_API_KEY")
    )
    collection_name = os.getenv("COLLECTION_NAME")
    embedder = get_embedder()
    
    vectorstore = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=embedder,
    )
    
    retriever = HybridRetriever(
        vectorstore=vectorstore,
        client=client,
        collection_name=collection_name,
        dense_top_k=5,
        bm25_top_k=5,
        final_top_k=3
    )

    query = "Based on the text that mentions 'fuga et accusamus dolorum perferendis illo voluptas', what happens next according to the document?"
    
    print(f"\n--- Testing Raw Hybrid Retrieval for: '{query}' ---")
    docs = retriever.invoke(query)
    for i, doc in enumerate(docs):
        print(f"\n[Hybrid Result {i+1}] (Chunk ID: {doc.metadata.get('chunk_id')})")
        print(f"Content: {doc.page_content}")

    print(f"\n--- Testing RAG Chain Output ---")
    reranker = CrossEncoderReranker(top_n=2)
    chain = HybridRAGChain(retriever, reranker)
    
    res = chain.invoke(query)
    print(f"\nFinal Answer:\n{res['answer']}")
    print(f"\nCitations Used: {len(res['citations'])}")

if __name__ == "__main__":
    asyncio.run(test_search())
