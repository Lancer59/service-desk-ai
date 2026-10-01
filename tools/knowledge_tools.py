"""
tools/knowledge_tools.py — Knowledge Base search and article retrieval.

Uses FAISS vector search when KB_INDEX_PATH is set and faiss-cpu is installed.
Falls back to a placeholder response when the index is not available.
"""

import os
from langchain.tools import tool
from pydantic import BaseModel, Field


class SearchKBInput(BaseModel):
    query: str = Field(description="Search query or problem description")
    top_k: int = Field(default=3, description="Number of results to return (1-10)")


class GetArticleDetailInput(BaseModel):
    article_id: str = Field(description="KB article identifier from search results")


def _faiss_search(query: str, top_k: int) -> list[dict]:
    """
    FAISS similarity search. Requires:
      KB_INDEX_PATH env var pointing to the FAISS index directory
      pip install faiss-cpu langchain-community sentence-transformers
    """
    index_path = os.environ.get("KB_INDEX_PATH", "")
    if not index_path:
        raise RuntimeError("KB_INDEX_PATH not set")

    # TODO: swap embeddings model to match whatever was used to build the index
    from langchain_community.vectorstores import FAISS
    from langchain_openai import AzureOpenAIEmbeddings
    from config import get_azure_credentials

    creds = get_azure_credentials()
    embeddings = AzureOpenAIEmbeddings(
        azure_deployment=os.environ.get("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"),
        azure_endpoint=creds["azure_endpoint"],
        api_key=creds["api_key"],
        api_version=creds["api_version"],
    )

    db = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
    docs = db.similarity_search(query, k=top_k)

    return [
        {
            "article_id": doc.metadata.get("id", doc.metadata.get("source", f"doc_{i}")),
            "title": doc.metadata.get("title", "Untitled"),
            "summary": doc.page_content[:400],
            "relevance_score": round(1 - (i * 0.1), 2),  # approximate rank-based score
        }
        for i, doc in enumerate(docs)
    ]


@tool("search_knowledge_base", args_schema=SearchKBInput)
def search_knowledge_base(query: str, top_k: int = 3) -> dict:
    """
    Search the internal knowledge base for articles relevant to the user's query.
    Returns article titles, IDs, and summaries. Always search before answering
    any IT how-to or troubleshooting question.
    """
    try:
        top_k = max(1, min(top_k, 10))
        results = _faiss_search(query, top_k)
        return {"success": True, "query": query, "results": results}
    except RuntimeError as e:
        # FAISS not configured — return informative placeholder
        return {
            "success": True,
            "query": query,
            "results": [
                {
                    "article_id": "KB_NOT_CONFIGURED",
                    "title": "Knowledge Base not configured",
                    "summary": (
                        "The KB index is not yet configured (KB_INDEX_PATH not set). "
                        "Set KB_INDEX_PATH to the FAISS index directory to enable real KB search."
                    ),
                    "relevance_score": 0.0,
                }
            ],
            "note": str(e),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool("get_article_detail", args_schema=GetArticleDetailInput)
def get_article_detail(article_id: str) -> dict:
    """
    Retrieve the full content of a specific KB article by its ID.
    Use when the user wants complete step-by-step instructions.
    """
    try:
        index_path = os.environ.get("KB_INDEX_PATH", "")
        if not index_path:
            return {
                "success": False,
                # TODO: set KB_INDEX_PATH env var and implement article detail
                # retrieval from FAISS metadata or a KB REST API.
                "error": "TODO: KB_INDEX_PATH not set. Configure KB_INDEX_PATH to enable article detail retrieval.",
            }

        # TODO: For FAISS-backed KB, article full content is in the document's
        # page_content field. Re-run similarity_search with article_id as a
        # metadata filter, or store a separate id→content lookup at index build time.
        # For an API-backed KB, call the appropriate article endpoint here.
        return {
            "success": False,
            "error": f"TODO: implement article detail retrieval for article_id={article_id}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
