"""
Output Manager - Save transcripts, summaries, and reports in structured format.
"""

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from transcript import TranscriptResult
from playlist import PlaylistInfo

if TYPE_CHECKING:
    from summarizer import SummaryResult


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Convert a string to a safe filename."""
    # Remove invalid characters
    safe = re.sub(r'[<>:"/\\|?*]', '', name)
    # Replace spaces and multiple underscores
    safe = re.sub(r'\s+', '_', safe)
    safe = re.sub(r'_+', '_', safe)
    # Strip leading/trailing underscores
    safe = safe.strip('_')
    # Truncate
    return safe[:max_length] if safe else "untitled"


def sanitize_folder_name(name: str) -> str:
    """Convert a string to a safe folder name."""
    safe = sanitize_filename(name, max_length=50)
    return safe.lower()


@dataclass
class ExtractionResult:
    """Result of a single video extraction."""

    index: int
    video_id: str
    title: str
    success: bool
    segments: int = 0
    file: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ExtractionReport:
    """Report of a batch extraction."""

    channel: str
    channel_id: str
    playlist: Optional[str] = None
    playlist_id: Optional[str] = None
    extraction_started: str = ""
    extraction_completed: str = ""
    total_videos: int = 0
    accessible_videos: int = 0
    successful: list = None
    failed: list = None
    skipped: list = None
    ip_blocked: bool = False

    def __post_init__(self):
        if self.successful is None:
            self.successful = []
        if self.failed is None:
            self.failed = []
        if self.skipped is None:
            self.skipped = []

    def add_success(self, result: ExtractionResult):
        self.successful.append(asdict(result))

    def add_failure(self, result: ExtractionResult):
        self.failed.append(asdict(result))

    def add_skipped(self, result: ExtractionResult):
        self.skipped.append(asdict(result))

    def to_dict(self) -> dict:
        return asdict(self)


class OutputManager:
    """
    Manage output files for transcript extraction.

    Directory structure:
        transcripts/
        ├── {channel_name}/
        │   ├── _channel_info.json
        │   ├── {playlist_name}/
        │   │   ├── _playlist_info.json
        │   │   ├── _extraction_report.json
        │   │   ├── 01_video_title.md
        │   │   └── ...
        │   └── singles/
        │       └── video_title.md
    """

    def __init__(self, base_dir: str | Path = "transcripts"):
        self.base_dir = Path(base_dir)

    def get_channel_dir(self, channel_name: str) -> Path:
        """Get or create channel directory."""
        dir_name = sanitize_folder_name(channel_name) or "unknown_channel"
        channel_dir = self.base_dir / dir_name
        channel_dir.mkdir(parents=True, exist_ok=True)
        return channel_dir

    def get_playlist_dir(self, channel_name: str, playlist_name: str) -> Path:
        """Get or create playlist directory within channel."""
        channel_dir = self.get_channel_dir(channel_name)
        dir_name = sanitize_folder_name(playlist_name) or "untitled_playlist"
        playlist_dir = channel_dir / dir_name
        playlist_dir.mkdir(parents=True, exist_ok=True)
        return playlist_dir

    def save_transcript_markdown(
        self,
        transcript: TranscriptResult,
        title: str,
        channel_name: str,
        output_dir: Path,
        index: Optional[int] = None,
        playlist_name: Optional[str] = None,
        video_url: Optional[str] = None,
    ) -> Path:
        """
        Save a transcript as a Markdown file.

        Args:
            transcript: TranscriptResult object
            title: Video title
            channel_name: Channel name
            output_dir: Directory to save to
            index: Optional playlist index for numbered filename
            playlist_name: Optional playlist name for metadata
            video_url: Optional video URL

        Returns:
            Path to saved file
        """
        # Create filename
        safe_title = sanitize_filename(title)
        if index is not None and index > 0:
            filename = f"{index:02d}_{safe_title}.md"
        else:
            filename = f"{safe_title}.md"

        filepath = output_dir / filename

        # Build markdown content
        lines = [
            f"# {title}",
            "",
            "## Video Info",
            f"- **Channel**: {channel_name}",
        ]

        if playlist_name:
            lines.append(f"- **Playlist**: {playlist_name}")

        if index is not None and index > 0:
            lines.append(f"- **Index**: {index}")

        lines.extend([
            f"- **Video ID**: {transcript.video_id}",
            f"- **URL**: {video_url or f'https://www.youtube.com/watch?v={transcript.video_id}'}",
            f"- **Language**: {transcript.language or 'unknown'}",
            f"- **Segments**: {transcript.segment_count}",
            f"- **Extracted**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
            "## Full Text",
            "",
        ])

        # Wrap text at ~80 characters
        words = transcript.full_text.split()
        current_line = []
        for word in words:
            current_line.append(word)
            if len(" ".join(current_line)) > 80:
                lines.append(" ".join(current_line))
                current_line = []
        if current_line:
            lines.append(" ".join(current_line))

        # Write file
        filepath.write_text("\n".join(lines), encoding='utf-8')
        return filepath

    def save_transcript_json(
        self,
        transcript: TranscriptResult,
        title: str,
        output_dir: Path,
        index: Optional[int] = None,
    ) -> Path:
        """Save transcript as JSON with full segment data."""
        safe_title = sanitize_filename(title)
        if index is not None and index > 0:
            filename = f"{index:02d}_{safe_title}.json"
        else:
            filename = f"{safe_title}.json"

        filepath = output_dir / filename

        data = {
            "video_id": transcript.video_id,
            "title": title,
            "language": transcript.language,
            "extracted_at": datetime.now().isoformat(),
            "segment_count": transcript.segment_count,
            "full_text": transcript.full_text,
            "segments": [
                {
                    "text": seg.text,
                    "start": seg.start,
                    "duration": seg.duration,
                }
                for seg in transcript.segments
            ],
        }

        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        return filepath

    def save_playlist_info(self, playlist: PlaylistInfo, output_dir: Path) -> Path:
        """Save playlist metadata as JSON."""
        filepath = output_dir / "_playlist_info.json"

        data = {
            "playlist_id": playlist.playlist_id,
            "title": playlist.title,
            "channel": playlist.channel_name,
            "channel_handle": playlist.channel_handle,
            "channel_url": playlist.channel_url,
            "total_videos": playlist.video_count,
            "accessible_videos": playlist.accessible_count,
            "videos": [
                {
                    "index": v.index,
                    "id": v.video_id,
                    "title": v.title,
                    "duration": v.duration,
                }
                for v in playlist.videos
            ],
            "extracted_at": datetime.now().isoformat(),
        }

        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        return filepath

    def save_extraction_report(self, report: ExtractionReport, output_dir: Path) -> Path:
        """Save extraction report as JSON."""
        filepath = output_dir / "_extraction_report.json"
        filepath.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        return filepath

    def load_extraction_report(self, output_dir: Path) -> Optional[ExtractionReport]:
        """Load existing extraction report if present."""
        filepath = output_dir / "_extraction_report.json"
        if not filepath.exists():
            return None

        try:
            data = json.loads(filepath.read_text(encoding='utf-8'))
            return ExtractionReport(**data)
        except (json.JSONDecodeError, TypeError):
            return None

    def get_extracted_video_ids(self, output_dir: Path) -> set[str]:
        """Get set of video IDs that have already been extracted."""
        report = self.load_extraction_report(output_dir)
        if report is None:
            return set()

        extracted = set()
        for item in report.successful:
            extracted.add(item.get('video_id', ''))
        return extracted

    def transcript_exists(self, output_dir: Path, video_id: str) -> bool:
        """Check if a transcript file already exists for a video."""
        # Check in report
        report = self.load_extraction_report(output_dir)
        if report:
            for item in report.successful:
                if item.get('video_id') == video_id:
                    return True

        # Also check for actual files
        for md_file in output_dir.glob("*.md"):
            content = md_file.read_text(encoding='utf-8')
            if f"**Video ID**: {video_id}" in content:
                return True

        return False

    def get_failed_video_ids(self, output_dir: Path) -> set[str]:
        """
        Get set of video IDs that failed in the previous extraction.
        Used for retry mode.
        """
        report = self.load_extraction_report(output_dir)
        if report is None:
            return set()

        failed_ids = set()

        # Get failed videos
        for item in report.failed:
            video_id = item.get('video_id', '')
            if video_id:
                failed_ids.add(video_id)

        # Get skipped videos (e.g., due to IP block)
        for item in report.skipped:
            video_id = item.get('video_id', '')
            if video_id:
                failed_ids.add(video_id)

        return failed_ids

    def get_retry_videos(self, output_dir: Path, all_videos: list) -> list:
        """
        Filter video list to only include previously failed videos.

        Args:
            output_dir: Directory with extraction report
            all_videos: Full list of videos (dicts with 'video_id' or 'id' key)

        Returns:
            Filtered list of videos to retry
        """
        failed_ids = self.get_failed_video_ids(output_dir)
        if not failed_ids:
            return []

        retry_videos = []
        for video in all_videos:
            video_id = video.get('video_id') or video.get('id', '')
            if video_id in failed_ids:
                retry_videos.append(video)

        return retry_videos

    def get_summaries_dir(self, channel_name: Optional[str] = None) -> Path:
        """Get or create summaries directory."""
        summaries_base = self.base_dir.parent / "summaries"
        if channel_name:
            dir_name = sanitize_folder_name(channel_name) or "unknown_channel"
            summaries_dir = summaries_base / dir_name
        else:
            summaries_dir = summaries_base
        summaries_dir.mkdir(parents=True, exist_ok=True)
        return summaries_dir

    def save_summary_markdown(
        self,
        summary: "SummaryResult",
        title: str,
        video_url: str,
        channel_name: Optional[str] = None,
        playlist_name: Optional[str] = None,
        index: Optional[int] = None,
        include_algorithm: bool = True,
    ) -> dict:
        """
        Save summary as Markdown files (video summary + algorithm summary).

        Args:
            summary: SummaryResult object
            title: Video title
            video_url: YouTube video URL
            channel_name: Channel name for folder organization
            playlist_name: Playlist name for subfolder
            index: Video index in playlist
            include_algorithm: Whether to save algorithm-focused summary

        Returns:
            Dict with paths to saved files
        """
        # Determine output directory
        if playlist_name:
            summaries_dir = self.get_summaries_dir(channel_name) / sanitize_folder_name(playlist_name)
        else:
            summaries_dir = self.get_summaries_dir(channel_name) / "singles"
        summaries_dir.mkdir(parents=True, exist_ok=True)

        # Create filename
        safe_title = sanitize_filename(title or f"video_{summary.video_id}")
        if index is not None and index > 0:
            base_filename = f"{index:02d}_{safe_title}"
        else:
            base_filename = safe_title

        saved_files = {}

        # Save video summary
        summary_filepath = summaries_dir / f"{base_filename}_summary.md"
        summary_content = self._build_summary_markdown(
            summary=summary,
            title=title,
            video_url=video_url,
            channel_name=channel_name,
            playlist_name=playlist_name,
            index=index,
            summary_type="video",
        )
        summary_filepath.write_text(summary_content, encoding='utf-8')
        saved_files["summary"] = str(summary_filepath)

        # Save algorithm/indicator summary if trading insights exist
        if include_algorithm and summary.trading_insights:
            algo_filepath = summaries_dir / f"{base_filename}_algorithm.md"
            algo_content = self._build_algorithm_markdown(
                summary=summary,
                title=title,
                video_url=video_url,
            )
            algo_filepath.write_text(algo_content, encoding='utf-8')
            saved_files["algorithm"] = str(algo_filepath)

        return saved_files

    def _build_summary_markdown(
        self,
        summary: "SummaryResult",
        title: str,
        video_url: str,
        channel_name: Optional[str] = None,
        playlist_name: Optional[str] = None,
        index: Optional[int] = None,
        summary_type: str = "video",
    ) -> str:
        """Build markdown content for video summary."""
        lines = [
            f"# {title or 'Video Summary'}",
            "",
            "## Video Info",
            f"- **Video ID**: {summary.video_id}",
            f"- **URL**: {video_url}",
        ]

        if channel_name:
            lines.append(f"- **Channel**: {channel_name}")
        if playlist_name:
            lines.append(f"- **Playlist**: {playlist_name}")
        if index is not None and index > 0:
            lines.append(f"- **Index**: {index}")

        lines.extend([
            f"- **Transcript Length**: {summary.transcript_length:,} characters",
            f"- **Summary Style**: {summary.summary_style}",
            f"- **Summary Length**: {summary.summary_length}",
            f"- **Word Count**: {summary.word_count}",
            f"- **Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "---",
            "",
        ])

        # Key topics
        if summary.key_topics:
            lines.append("## Key Topics")
            for topic in summary.key_topics:
                lines.append(f"- {topic}")
            lines.append("")
            lines.append("---")
            lines.append("")

        # Main summary
        lines.append("## Summary")
        lines.append("")
        lines.append(summary.summary_text)

        return "\n".join(lines)

    def _build_algorithm_markdown(
        self,
        summary: "SummaryResult",
        title: str,
        video_url: str,
    ) -> str:
        """Build markdown content for algorithm/indicator building summary."""
        lines = [
            f"# Algorithm & Indicator Guide: {title or 'Trading Strategy'}",
            "",
            "## Source",
            f"- **Video**: [{title}]({video_url})",
            f"- **Video ID**: {summary.video_id}",
            f"- **Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "> This document extracts algorithmic rules and indicator-building information from the video.",
            "",
            "---",
            "",
        ]

        insights = summary.trading_insights or {}

        # Strategy Overview
        if insights.get("strategy_overview"):
            lines.extend([
                "## Strategy Overview",
                "",
                insights["strategy_overview"],
                "",
            ])

        # Entry Conditions - formatted for coding
        if insights.get("entry_conditions"):
            lines.extend([
                "## Entry Conditions (Indicator Logic)",
                "",
                "```",
                "// Entry conditions to implement:",
            ])
            for i, condition in enumerate(insights["entry_conditions"], 1):
                lines.append(f"// {i}. {condition}")
            lines.extend([
                "```",
                "",
                "### Detailed Entry Rules",
                "",
            ])
            for condition in insights["entry_conditions"]:
                lines.append(f"- {condition}")
            lines.append("")

        # Exit Conditions
        if insights.get("exit_conditions"):
            lines.extend([
                "## Exit Conditions",
                "",
                "```",
                "// Exit conditions to implement:",
            ])
            for i, condition in enumerate(insights["exit_conditions"], 1):
                lines.append(f"// {i}. {condition}")
            lines.extend([
                "```",
                "",
            ])
            for condition in insights["exit_conditions"]:
                lines.append(f"- {condition}")
            lines.append("")

        # Risk Management
        if insights.get("risk_management"):
            lines.extend([
                "## Risk Management Parameters",
                "",
            ])
            for rule in insights["risk_management"]:
                lines.append(f"- {rule}")
            lines.append("")

        # Indicators/Tools
        if insights.get("indicators"):
            lines.extend([
                "## Indicators & Tools to Use",
                "",
            ])
            for indicator in insights["indicators"]:
                lines.append(f"- {indicator}")
            lines.append("")

        # Trading Rules - numbered for implementation
        if insights.get("trading_rules"):
            lines.extend([
                "## Trading Rules (Implementation Checklist)",
                "",
            ])
            for i, rule in enumerate(insights["trading_rules"], 1):
                lines.append(f"{i}. {rule}")
            lines.append("")

        # Notes/Warnings
        if insights.get("notes"):
            lines.extend([
                "## Important Notes & Warnings",
                "",
            ])
            for note in insights["notes"]:
                lines.append(f"- {note}")
            lines.append("")

        # Pine Script template
        lines.extend([
            "---",
            "",
            "## Pine Script Template",
            "",
            "```pine",
            "//@version=6",
            f"indicator('{title or 'Strategy'} Indicator', overlay=true)",
            "",
            "// TODO: Implement entry conditions from above",
            "// TODO: Implement exit conditions",
            "// TODO: Add risk management logic",
            "```",
        ])

        return "\n".join(lines)
