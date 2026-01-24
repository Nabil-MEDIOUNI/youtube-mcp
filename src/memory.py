"""
Simple RAG-style memory for YouTube MCP.
Stores and retrieves past extractions and summaries for context.
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict


@dataclass
class MemoryEntry:
    """A single memory entry."""
    id: str
    type: str  # 'video', 'playlist', 'channel'
    url: str
    title: str
    channel: str
    timestamp: str
    summary_preview: str = ""  # First 500 chars of summary
    file_paths: dict = None
    tags: list = None

    def __post_init__(self):
        if self.file_paths is None:
            self.file_paths = {}
        if self.tags is None:
            self.tags = []


class MCPMemory:
    """
    Simple file-based memory for the YouTube MCP.
    Stores metadata about processed videos for quick retrieval.
    """

    def __init__(self, memory_dir: str = None):
        if memory_dir is None:
            memory_dir = Path(__file__).parent.parent / "memory"
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.memory_dir / "index.json"
        self._load_index()

    def _load_index(self):
        """Load the memory index."""
        if self.index_file.exists():
            with open(self.index_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.entries = {k: MemoryEntry(**v) for k, v in data.items()}
        else:
            self.entries = {}

    def _save_index(self):
        """Save the memory index."""
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump({k: asdict(v) for k, v in self.entries.items()}, f, indent=2)

    def _generate_id(self, url: str) -> str:
        """Generate a unique ID for a URL."""
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def add(
        self,
        url: str,
        entry_type: str,
        title: str,
        channel: str,
        summary_preview: str = "",
        file_paths: dict = None,
        tags: list = None,
    ) -> MemoryEntry:
        """Add a new memory entry."""
        entry_id = self._generate_id(url)
        entry = MemoryEntry(
            id=entry_id,
            type=entry_type,
            url=url,
            title=title,
            channel=channel,
            timestamp=datetime.now().isoformat(),
            summary_preview=summary_preview[:500] if summary_preview else "",
            file_paths=file_paths or {},
            tags=tags or [],
        )
        self.entries[entry_id] = entry
        self._save_index()
        return entry

    def get(self, url: str) -> Optional[MemoryEntry]:
        """Get a memory entry by URL."""
        entry_id = self._generate_id(url)
        return self.entries.get(entry_id)

    def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Simple text search across titles and channels."""
        query_lower = query.lower()
        results = []
        for entry in self.entries.values():
            score = 0
            if query_lower in entry.title.lower():
                score += 2
            if query_lower in entry.channel.lower():
                score += 1
            if any(query_lower in tag.lower() for tag in entry.tags):
                score += 1
            if query_lower in entry.summary_preview.lower():
                score += 0.5
            if score > 0:
                results.append((score, entry))

        results.sort(key=lambda x: (-x[0], x[1].timestamp), reverse=False)
        return [entry for _, entry in results[:limit]]

    def get_by_channel(self, channel: str) -> list[MemoryEntry]:
        """Get all entries for a channel."""
        channel_lower = channel.lower()
        return [e for e in self.entries.values() if channel_lower in e.channel.lower()]

    def get_recent(self, limit: int = 10) -> list[MemoryEntry]:
        """Get most recent entries."""
        sorted_entries = sorted(
            self.entries.values(),
            key=lambda x: x.timestamp,
            reverse=True
        )
        return sorted_entries[:limit]

    def list_channels(self) -> list[str]:
        """List all unique channels."""
        channels = set(e.channel for e in self.entries.values())
        return sorted(channels)

    def get_context_prompt(self, limit: int = 5) -> str:
        """Generate a context prompt with recent memory for Claude."""
        recent = self.get_recent(limit)
        if not recent:
            return ""

        lines = ["## Recent YouTube Extractions (from memory):\n"]
        for entry in recent:
            lines.append(f"- **{entry.title}** ({entry.channel})")
            lines.append(f"  - Type: {entry.type}")
            lines.append(f"  - Files: {', '.join(entry.file_paths.values()) if entry.file_paths else 'N/A'}")
            if entry.tags:
                lines.append(f"  - Tags: {', '.join(entry.tags)}")

        return "\n".join(lines)

    def clear(self):
        """Clear all memory."""
        self.entries = {}
        self._save_index()


# Singleton instance
_memory_instance = None

def get_memory() -> MCPMemory:
    """Get the global memory instance."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = MCPMemory()
    return _memory_instance
