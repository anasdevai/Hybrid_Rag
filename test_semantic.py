import os
import asyncio
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore
from embeddings.embedder import get_embedder

load_dotenv()

async def test_semantic_only():
    print("--- Initializing Pure Semantic (Dense) Search Test ---")
    
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

    # A query that relies on MEANING, not just keywords
    # Example: "tidy the workspace" vs "clean the environment"
    semantic_query = "What are the rules for maintaining a neat and orderly production area?"
    
    print(f"\n[QUERY]: '{semantic_query}'")
    print("-" * 50)

    # Perform pure semantic search (Dense retrieval only)
    results = vectorstore.similarity_search_with_score(
        query=semantic_query,
        k=3
    )

    if not results:
        print("No results found. Ensure your Qdrant collection is populated.")
        return

    for i, (doc, score) in enumerate(results):
        print(f"\n[Result {i+1}] (Distance Score: {score:.4f})")
        print(f"Content Snippet: {doc.page_content[:150]}...")
        print(f"Metadata: {doc.metadata}")

if __name__ == "__main__":
    asyncio.run(test_semantic_only())
