"""
RAG (Retrieval Augmented Generation) system for YouTube MCP.
Indexes transcripts and summaries for semantic search.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict

# Check for optional dependencies
try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


@dataclass
class VideoDocument:
    """A document representing a video's content."""
    video_id: str
    title: str
    channel: str
    url: str
    content_type: str  # 'transcript', 'summary', 'algorithm'
    text: str
    file_path: str
    indexed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """A search result from the RAG system."""
    video_id: str
    title: str
    channel: str
    content_type: str
    chunk_text: str
    score: float
    file_path: str
    metadata: dict = field(default_factory=dict)


class YouTubeRAG:
    """
    RAG system for YouTube MCP content.

    Uses ChromaDB for vector storage and sentence-transformers for embeddings.
    Falls back to simple keyword search if dependencies aren't available.
    """

    def __init__(self, data_dir: str = None):
        """Initialize the RAG system."""
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "rag_data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.use_vectors = HAS_CHROMADB and HAS_SENTENCE_TRANSFORMERS

        if self.use_vectors:
            self._init_vector_store()
        else:
            self._init_simple_store()

    def _init_vector_store(self):
        """Initialize ChromaDB and sentence transformer."""
        # Use a local persistent ChromaDB
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.data_dir / "chroma_db"),
            settings=Settings(anonymized_telemetry=False)
        )

        # Get or create collection
        self.collection = self.chroma_client.get_or_create_collection(
            name="youtube_content",
            metadata={"description": "YouTube transcripts and summaries"}
        )

        # Load embedding model (small and fast)
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')

    def _init_simple_store(self):
        """Initialize simple JSON-based storage for keyword search."""
        self.index_file = self.data_dir / "simple_index.json"
        if self.index_file.exists():
            with open(self.index_file, 'r', encoding='utf-8') as f:
                self.simple_index = json.load(f)
        else:
            self.simple_index = {"documents": [], "chunks": []}

    def _save_simple_index(self):
        """Save simple index to disk."""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.simple_index, f, indent=2)

    def _chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]

            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk.rfind('. ')
                if last_period > chunk_size // 2:
                    chunk = chunk[:last_period + 1]
                    end = start + last_period + 1

            chunks.append(chunk.strip())
            start = end - overlap

        return [c for c in chunks if len(c) > 50]  # Filter tiny chunks

    def _generate_chunk_id(self, video_id: str, content_type: str, chunk_idx: int) -> str:
        """Generate unique ID for a chunk."""
        return f"{video_id}_{content_type}_{chunk_idx}"

    def index_video(
        self,
        video_id: str,
        title: str,
        channel: str,
        url: str,
        transcript: str = None,
        summary: str = None,
        algorithm: str = None,
        transcript_path: str = None,
        summary_path: str = None,
        algorithm_path: str = None,
    ) -> dict:
        """
        Index a video's content for RAG retrieval.

        Args:
            video_id: YouTube video ID
            title: Video title
            channel: Channel name
            url: Video URL
            transcript: Full transcript text
            summary: Summary text
            algorithm: Algorithm guide text
            *_path: File paths for each content type

        Returns:
            dict with indexing results
        """
        results = {"video_id": video_id, "indexed": [], "chunks": 0}

        content_items = [
            ("transcript", transcript, transcript_path),
            ("summary", summary, summary_path),
            ("algorithm", algorithm, algorithm_path),
        ]

        for content_type, text, file_path in content_items:
            if not text:
                continue

            chunks = self._chunk_text(text)
            results["chunks"] += len(chunks)
            results["indexed"].append(content_type)

            if self.use_vectors:
                self._index_chunks_vector(
                    video_id, title, channel, url,
                    content_type, chunks, file_path
                )
            else:
                self._index_chunks_simple(
                    video_id, title, channel, url,
                    content_type, chunks, file_path
                )

        return results

    def _index_chunks_vector(
        self,
        video_id: str,
        title: str,
        channel: str,
        url: str,
        content_type: str,
        chunks: list[str],
        file_path: str
    ):
        """Index chunks using ChromaDB vectors."""
        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = self._generate_chunk_id(video_id, content_type, i)
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "video_id": video_id,
                "title": title,
                "channel": channel,
                "url": url,
                "content_type": content_type,
                "file_path": file_path or "",
                "chunk_index": i,
                "indexed_at": datetime.now().isoformat(),
            })

        # Upsert to handle re-indexing
        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def _index_chunks_simple(
        self,
        video_id: str,
        title: str,
        channel: str,
        url: str,
        content_type: str,
        chunks: list[str],
        file_path: str
    ):
        """Index chunks using simple JSON storage."""
        # Remove existing chunks for this video/content_type
        self.simple_index["chunks"] = [
            c for c in self.simple_index["chunks"]
            if not (c["video_id"] == video_id and c["content_type"] == content_type)
        ]

        # Add new chunks
        for i, chunk in enumerate(chunks):
            self.simple_index["chunks"].append({
                "id": self._generate_chunk_id(video_id, content_type, i),
                "video_id": video_id,
                "title": title,
                "channel": channel,
                "url": url,
                "content_type": content_type,
                "text": chunk,
                "file_path": file_path or "",
                "chunk_index": i,
            })

        self._save_simple_index()

    def search(self, query: str, limit: int = 5, content_type: str = None) -> list[SearchResult]:
        """
        Search for relevant content.

        Args:
            query: Search query
            limit: Max results to return
            content_type: Filter by type ('transcript', 'summary', 'algorithm')

        Returns:
            List of SearchResult objects
        """
        if self.use_vectors:
            return self._search_vector(query, limit, content_type)
        else:
            return self._search_simple(query, limit, content_type)

    def _search_vector(self, query: str, limit: int, content_type: str = None) -> list[SearchResult]:
        """Search using ChromaDB vector similarity."""
        where_filter = None
        if content_type:
            where_filter = {"content_type": content_type}

        results = self.collection.query(
            query_texts=[query],
            n_results=limit,
            where=where_filter,
        )

        search_results = []
        if results and results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i] if results.get("distances") else 0

                search_results.append(SearchResult(
                    video_id=metadata["video_id"],
                    title=metadata["title"],
                    channel=metadata["channel"],
                    content_type=metadata["content_type"],
                    chunk_text=doc,
                    score=1 - distance,  # Convert distance to similarity
                    file_path=metadata.get("file_path", ""),
                    metadata=metadata,
                ))

        return search_results

    def _search_simple(self, query: str, limit: int, content_type: str = None) -> list[SearchResult]:
        """Search using simple keyword matching."""
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_results = []
        for chunk in self.simple_index.get("chunks", []):
            if content_type and chunk["content_type"] != content_type:
                continue

            text_lower = chunk["text"].lower()
            title_lower = chunk["title"].lower()

            # Score based on word matches
            score = 0
            for word in query_words:
                if word in text_lower:
                    score += text_lower.count(word)
                if word in title_lower:
                    score += 2  # Boost title matches

            if score > 0:
                scored_results.append((score, chunk))

        # Sort by score descending
        scored_results.sort(key=lambda x: x[0], reverse=True)

        return [
            SearchResult(
                video_id=chunk["video_id"],
                title=chunk["title"],
                channel=chunk["channel"],
                content_type=chunk["content_type"],
                chunk_text=chunk["text"],
                score=score,
                file_path=chunk.get("file_path", ""),
            )
            for score, chunk in scored_results[:limit]
        ]

    def get_context_for_query(self, query: str, limit: int = 5) -> str:
        """
        Get formatted context for a query (for use in prompts).

        Returns a string with relevant chunks that can be injected into a prompt.
        """
        results = self.search(query, limit=limit)

        if not results:
            return "No relevant content found in indexed videos."

        context_parts = [f"## Relevant Content from {len(results)} sources:\n"]

        for i, result in enumerate(results, 1):
            context_parts.append(f"### Source {i}: {result.title} ({result.channel})")
            context_parts.append(f"Type: {result.content_type} | Score: {result.score:.2f}")
            context_parts.append(f"```\n{result.chunk_text}\n```\n")

        return "\n".join(context_parts)

    def list_indexed_videos(self) -> list[dict]:
        """List all indexed videos."""
        if self.use_vectors:
            # Get unique videos from ChromaDB
            all_data = self.collection.get()
            videos = {}
            for metadata in all_data.get("metadatas", []):
                vid = metadata["video_id"]
                if vid not in videos:
                    videos[vid] = {
                        "video_id": vid,
                        "title": metadata["title"],
                        "channel": metadata["channel"],
                        "url": metadata.get("url", ""),
                        "content_types": set(),
                    }
                videos[vid]["content_types"].add(metadata["content_type"])

            return [
                {**v, "content_types": list(v["content_types"])}
                for v in videos.values()
            ]
        else:
            # Get from simple index
            videos = {}
            for chunk in self.simple_index.get("chunks", []):
                vid = chunk["video_id"]
                if vid not in videos:
                    videos[vid] = {
                        "video_id": vid,
                        "title": chunk["title"],
                        "channel": chunk["channel"],
                        "url": chunk.get("url", ""),
                        "content_types": set(),
                    }
                videos[vid]["content_types"].add(chunk["content_type"])

            return [
                {**v, "content_types": list(v["content_types"])}
                for v in videos.values()
            ]

    def get_stats(self) -> dict:
        """Get RAG system statistics."""
        if self.use_vectors:
            count = self.collection.count()
            return {
                "backend": "chromadb + sentence-transformers",
                "total_chunks": count,
                "videos": len(self.list_indexed_videos()),
                "embedding_model": "all-MiniLM-L6-v2",
            }
        else:
            return {
                "backend": "simple keyword search (install chromadb & sentence-transformers for vector search)",
                "total_chunks": len(self.simple_index.get("chunks", [])),
                "videos": len(self.list_indexed_videos()),
            }

    def delete_video(self, video_id: str):
        """Remove a video from the index."""
        if self.use_vectors:
            # Delete all chunks for this video
            self.collection.delete(where={"video_id": video_id})
        else:
            self.simple_index["chunks"] = [
                c for c in self.simple_index["chunks"]
                if c["video_id"] != video_id
            ]
            self._save_simple_index()

    def clear(self):
        """Clear all indexed data."""
        if self.use_vectors:
            self.chroma_client.delete_collection("youtube_content")
            self.collection = self.chroma_client.get_or_create_collection(
                name="youtube_content",
                metadata={"description": "YouTube transcripts and summaries"}
            )
        else:
            self.simple_index = {"documents": [], "chunks": []}
            self._save_simple_index()


# Singleton instance
_rag_instance = None

def get_rag() -> YouTubeRAG:
    """Get the global RAG instance."""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = YouTubeRAG()
    return _rag_instance
