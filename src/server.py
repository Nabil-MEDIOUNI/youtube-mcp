"""
YouTube MCP Server - Main server implementation.

Exposes tools for extracting YouTube transcripts via MCP protocol.
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

from url_parser import parse_youtube_url, YouTubeURL, fetch_video_info
from transcript import TranscriptExtractor, TranscriptResult
from playlist import PlaylistScraper, PlaylistInfo, load_playlist_from_json
from output import (
    OutputManager,
    ExtractionReport,
    ExtractionResult,
    sanitize_folder_name,
    sanitize_filename,
)

# Optional YouTube API import
try:
    from youtube_api import YouTubeAPI
    HAS_YOUTUBE_API = True
except ImportError:
    HAS_YOUTUBE_API = False

# Import discovery module
from discovery import ChannelDiscoverer, ChannelDiscovery, create_config_from_discovery

# Optional summarizer import
try:
    from summarizer import TranscriptSummarizer, SummaryStyle, SummaryLength
    HAS_SUMMARIZER = True
except ImportError:
    HAS_SUMMARIZER = False


# Default configuration
DEFAULT_OUTPUT_DIR = "transcripts"
DEFAULT_LANGUAGE = "en"
DEFAULT_RATE_LIMIT = 3.0  # seconds between requests


class YouTubeMCPServer:
    """YouTube MCP Server with transcript extraction tools."""

    def __init__(
        self,
        output_dir: str = DEFAULT_OUTPUT_DIR,
        default_language: str = DEFAULT_LANGUAGE,
        rate_limit: float = DEFAULT_RATE_LIMIT,
        api_key: str = None,
    ):
        self.output_dir = Path(output_dir)
        self.default_language = default_language
        self.rate_limit = rate_limit

        # Initialize components
        self.extractor = TranscriptExtractor(
            default_language=default_language,
            ssl_bypass=True,
        )
        self.scraper = PlaylistScraper(ssl_bypass=True)
        self.output_manager = OutputManager(base_dir=output_dir)

        # Initialize YouTube API if key provided
        self.youtube_api = None
        if api_key and HAS_YOUTUBE_API:
            try:
                self.youtube_api = YouTubeAPI(api_key=api_key, ssl_bypass=True)
            except ValueError:
                pass  # No API key, API features disabled

        # Initialize summarizer if available
        self.summarizer = None
        if HAS_SUMMARIZER:
            try:
                self.summarizer = TranscriptSummarizer()
            except Exception:
                pass  # No API key or import error, summarization disabled

        # MCP Server
        self.server = Server("youtube-mcp")
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup MCP tool handlers."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="extract_transcript",
                    description="Extract transcript from a single YouTube video. Returns the full transcript text and saves to a markdown file.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "YouTube video URL (any format: youtube.com/watch?v=, youtu.be/, etc.)",
                            },
                            "language": {
                                "type": "string",
                                "description": "Preferred transcript language code (e.g., 'en', 'es', 'fr'). Defaults to 'en'.",
                                "default": "en",
                            },
                            "save_file": {
                                "type": "boolean",
                                "description": "Whether to save transcript to file. Defaults to true.",
                                "default": True,
                            },
                        },
                        "required": ["url"],
                    },
                ),
                Tool(
                    name="extract_playlist",
                    description="Extract transcripts from all videos in a YouTube playlist or from a JSON config file. Saves each transcript to a separate file in a folder structure. Use json_config for reliable extraction when URL scraping fails.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "YouTube playlist URL (optional if json_config is provided)",
                            },
                            "json_config": {
                                "type": "string",
                                "description": "Path to a JSON config file with playlist/video info. Use this for reliable extraction. Format: {channel: {name, playlist_id, playlist_name}, videos: [{index, id, title}]}",
                            },
                            "language": {
                                "type": "string",
                                "description": "Preferred transcript language code. Defaults to 'en'.",
                                "default": "en",
                            },
                            "skip_existing": {
                                "type": "boolean",
                                "description": "Skip videos that already have transcripts extracted. Defaults to true.",
                                "default": True,
                            },
                            "max_videos": {
                                "type": "integer",
                                "description": "Maximum number of videos to extract. Defaults to all.",
                            },
                            "retry_failed": {
                                "type": "boolean",
                                "description": "Only retry videos that failed in the previous extraction. Defaults to false.",
                                "default": False,
                            },
                        },
                        "required": [],
                    },
                ),
                Tool(
                    name="list_playlist",
                    description="List all videos in a YouTube playlist without extracting transcripts. Useful for previewing what will be extracted.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "YouTube playlist URL",
                            },
                        },
                        "required": ["url"],
                    },
                ),
                Tool(
                    name="check_transcript",
                    description="Check if a YouTube video has transcripts available and list available languages.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "YouTube video URL",
                            },
                        },
                        "required": ["url"],
                    },
                ),
                Tool(
                    name="get_video_info",
                    description="Get detailed information about a YouTube video (title, description, stats, etc.). Requires YOUTUBE_API_KEY.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "YouTube video URL",
                            },
                        },
                        "required": ["url"],
                    },
                ),
                Tool(
                    name="get_channel_info",
                    description="Get information about a YouTube channel (subscribers, video count, etc.). Requires YOUTUBE_API_KEY.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "YouTube channel URL (e.g., youtube.com/@handle or youtube.com/channel/ID)",
                            },
                        },
                        "required": ["url"],
                    },
                ),
                Tool(
                    name="search_videos",
                    description="Search for videos on YouTube. Requires YOUTUBE_API_KEY.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query",
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results (1-50). Defaults to 10.",
                                "default": 10,
                            },
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="youtube",
                    description="""Unified YouTube tool - discover, explore, and extract content from any channel with a single input.

USAGE: youtube <input> [action] [options]

INPUT FORMATS:
- @handle (e.g., "@TJRTrades", "@PixiesOfficialTV")
- Channel URL (e.g., "https://www.youtube.com/@TJRTrades")
- Channel ID (e.g., "UCxxxxxxxx")
- Playlist URL
- Video URL

ACTIONS:
- discover: Find all playlists and videos from a channel (default)
- p1, p2, p3...: Extract specific playlist by number
- v1, v2, v3...: Extract specific video by number
- extract_all: Extract all discovered videos
- save_config: Save discovery as JSON config file

METHODS:
- auto: Try API (if key), then playwright, then scraping (default)
- api: Use YouTube Data API (requires YOUTUBE_API_KEY)
- playwright: Use browser automation (most reliable)
- scraping: Use HTTP scraping (fastest but may be blocked)

EXAMPLES:
- youtube @TJRTrades -> Discover channel content
- youtube @TJRTrades action=p1 -> Extract first playlist
- youtube @TJRTrades action=v1 -> Extract first video
- youtube @TJRTrades method=playwright -> Use Playwright for discovery
- youtube @TJRTrades action=save_config -> Save config to tools/channels/""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "input": {
                                "type": "string",
                                "description": "Channel handle (@name), URL, channel ID, playlist URL, or video URL",
                            },
                            "action": {
                                "type": "string",
                                "description": "Action to perform: 'discover' (default), 'p1'-'p99' (playlist shortcut), 'v1'-'v99' (video shortcut), 'extract_all', 'save_config', 'list_playlists', 'list_videos'",
                                "default": "discover",
                            },
                            "method": {
                                "type": "string",
                                "description": "Discovery method: 'auto' (default), 'api', 'playwright', 'scraping'",
                                "enum": ["auto", "api", "playwright", "scraping"],
                                "default": "auto",
                            },
                            "max_videos": {
                                "type": "integer",
                                "description": "Max videos to discover (default 50)",
                                "default": 50,
                            },
                            "max_playlists": {
                                "type": "integer",
                                "description": "Max playlists to discover (default 20)",
                                "default": 20,
                            },
                            "language": {
                                "type": "string",
                                "description": "Transcript language for extraction (default 'en')",
                                "default": "en",
                            },
                        },
                        "required": ["input"],
                    },
                ),
                Tool(
                    name="summarize_video",
                    description="""Summarize a YouTube video using Claude CLI. Extracts the transcript and generates a summary.

STYLES:
- bullet-points: Hierarchical bullet point summary (default)
- paragraph: Flowing paragraph summary
- key-takeaways: Numbered key insights
- trading-strategy: Extract trading rules, entry/exit conditions, risk management (best for trading videos)

LENGTHS:
- short: ~200 words
- medium: ~500 words (default)
- long: ~1000 words
- detailed: ~2000 words

Requires Claude CLI (claude command) to be installed and accessible.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "YouTube video URL",
                            },
                            "style": {
                                "type": "string",
                                "description": "Summary style",
                                "enum": ["bullet-points", "paragraph", "key-takeaways", "trading-strategy"],
                                "default": "bullet-points",
                            },
                            "length": {
                                "type": "string",
                                "description": "Summary length",
                                "enum": ["short", "medium", "long", "detailed"],
                                "default": "medium",
                            },
                            "language": {
                                "type": "string",
                                "description": "Transcript language code",
                                "default": "en",
                            },
                            "custom_instructions": {
                                "type": "string",
                                "description": "Additional instructions for the summary (e.g., 'focus on risk management')",
                            },
                        },
                        "required": ["url"],
                    },
                ),
                Tool(
                    name="summarize_for_indicator",
                    description="""Specialized summarization for building trading indicators from YouTube videos.

Extracts:
- Mathematical formulas and calculations
- Specific price levels, percentages, ratios
- Entry/exit conditions and rules
- Indicator settings and parameters
- Candlestick patterns and formations
- Timeframe recommendations

Best for ICT, SMC, price action, and technical analysis videos.

Requires Claude CLI (claude command) to be installed and accessible.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "YouTube video URL",
                            },
                            "indicator_type": {
                                "type": "string",
                                "description": "Type of indicator (e.g., 'SMC', 'ICT', 'price-action', 'support-resistance')",
                            },
                            "language": {
                                "type": "string",
                                "description": "Transcript language code",
                                "default": "en",
                            },
                        },
                        "required": ["url"],
                    },
                ),
                Tool(
                    name="summarize_playlist",
                    description="""Batch summarize all videos in a YouTube playlist.

For each video:
1. Extracts transcript → saves to transcripts/{channel}/{playlist}/
2. Generates video summary → saves to summaries/{channel}/{playlist}/
3. Generates algorithm/indicator guide → saves to summaries/{channel}/{playlist}/

Supports:
- Skip already processed videos
- Limit number of videos to process
- Rate limiting between videos

Output structure:
- transcripts/{channel}/{playlist}/01_title.md
- summaries/{channel}/{playlist}/01_title_summary.md
- summaries/{channel}/{playlist}/01_title_algorithm.md

Requires Claude CLI (claude command) to be installed and accessible.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "YouTube playlist URL",
                            },
                            "style": {
                                "type": "string",
                                "description": "Summary style (trading-strategy recommended for indicators)",
                                "enum": ["bullet-points", "paragraph", "key-takeaways", "trading-strategy"],
                                "default": "trading-strategy",
                            },
                            "length": {
                                "type": "string",
                                "description": "Summary length",
                                "enum": ["short", "medium", "long", "detailed"],
                                "default": "detailed",
                            },
                            "language": {
                                "type": "string",
                                "description": "Transcript language code",
                                "default": "en",
                            },
                            "max_videos": {
                                "type": "integer",
                                "description": "Maximum number of videos to process (default: all)",
                            },
                            "skip_existing": {
                                "type": "boolean",
                                "description": "Skip videos that already have summaries",
                                "default": True,
                            },
                        },
                        "required": ["url"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
            try:
                if name == "extract_transcript":
                    return await self._extract_transcript(arguments)
                elif name == "extract_playlist":
                    return await self._extract_playlist(arguments)
                elif name == "list_playlist":
                    return await self._list_playlist(arguments)
                elif name == "check_transcript":
                    return await self._check_transcript(arguments)
                elif name == "get_video_info":
                    return await self._get_video_info(arguments)
                elif name == "get_channel_info":
                    return await self._get_channel_info(arguments)
                elif name == "search_videos":
                    return await self._search_videos(arguments)
                elif name == "youtube":
                    return await self._youtube(arguments)
                elif name == "summarize_video":
                    return await self._summarize_video(arguments)
                elif name == "summarize_for_indicator":
                    return await self._summarize_for_indicator(arguments)
                elif name == "summarize_playlist":
                    return await self._summarize_playlist(arguments)
                else:
                    return CallToolResult(
                        content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                        isError=True,
                    )
            except Exception as e:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Error: {str(e)}")],
                    isError=True,
                )

    async def _extract_transcript(self, args: dict[str, Any]) -> CallToolResult:
        """Handle extract_transcript tool call."""
        url = args.get("url", "")
        language = args.get("language", self.default_language)
        save_file = args.get("save_file", True)

        # Parse URL
        try:
            parsed = parse_youtube_url(url)
        except ValueError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Invalid URL: {e}")],
                isError=True,
            )

        if not parsed.video_id:
            return CallToolResult(
                content=[TextContent(type="text", text="URL does not contain a video ID")],
                isError=True,
            )

        # Extract transcript
        result = self.extractor.extract(parsed.video_id, language)

        if not result.success:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Failed to extract transcript: {result.error}"
                )],
                isError=True,
            )

        # Build response
        response = {
            "success": True,
            "video_id": result.video_id,
            "language": result.language,
            "segments": result.segment_count,
            "text_length": len(result.full_text),
        }

        # Save file if requested
        if save_file:
            # Try to get video title (use video_id as fallback)
            title = f"Video {result.video_id}"
            channel_name = "unknown"

            output_dir = self.output_manager.get_channel_dir(channel_name) / "singles"
            output_dir.mkdir(parents=True, exist_ok=True)

            filepath = self.output_manager.save_transcript_markdown(
                transcript=result,
                title=title,
                channel_name=channel_name,
                output_dir=output_dir,
                video_url=parsed.get_video_url(),
            )
            response["file"] = str(filepath)

        # Include transcript text (truncated for display)
        text_preview = result.full_text[:2000]
        if len(result.full_text) > 2000:
            text_preview += f"\n\n... [truncated, {len(result.full_text)} total characters]"

        response["transcript"] = text_preview

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response, indent=2))]
        )

    async def _extract_playlist(self, args: dict[str, Any]) -> CallToolResult:
        """Handle extract_playlist tool call."""
        url = args.get("url", "")
        json_config = args.get("json_config", "")
        language = args.get("language", self.default_language)
        skip_existing = args.get("skip_existing", True)
        max_videos = args.get("max_videos")
        retry_failed = args.get("retry_failed", False)

        playlist = None
        playlist_id = ""

        # Option 1: Load from JSON config (most reliable)
        if json_config:
            playlist = load_playlist_from_json(json_config)
            if playlist.error:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Failed to load config: {playlist.error}")],
                    isError=True,
                )
            playlist_id = playlist.playlist_id

        # Option 2: Scrape from URL
        elif url:
            try:
                parsed = parse_youtube_url(url)
            except ValueError as e:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Invalid URL: {e}")],
                    isError=True,
                )

            if not parsed.playlist_id:
                return CallToolResult(
                    content=[TextContent(type="text", text="URL does not contain a playlist ID")],
                    isError=True,
                )

            playlist_id = parsed.playlist_id
            playlist = self.scraper.get_playlist_info(playlist_id)

            if playlist.error or not playlist.videos:
                # Provide helpful message about using JSON config
                error_msg = playlist.error or "No videos found"
                return CallToolResult(
                    content=[TextContent(type="text", text=(
                        f"Failed to scrape playlist: {error_msg}\n\n"
                        "TIP: YouTube may be blocking scraping. Try using a JSON config file instead:\n"
                        "1. Use the Playwright MCP to scrape the playlist\n"
                        "2. Or create a JSON file with format:\n"
                        '   {"channel": {"name": "...", "playlist_name": "..."}, '
                        '"videos": [{"index": 1, "id": "VIDEO_ID", "title": "..."}]}\n'
                        "3. Then call extract_playlist with json_config parameter"
                    ))],
                    isError=True,
                )
        else:
            return CallToolResult(
                content=[TextContent(type="text", text="Either 'url' or 'json_config' must be provided")],
                isError=True,
            )

        # Setup output directory
        channel_name = playlist.channel_name or "unknown"
        playlist_name = playlist.title or f"playlist_{playlist_id}"
        output_dir = self.output_manager.get_playlist_dir(channel_name, playlist_name)

        # Save playlist info
        self.output_manager.save_playlist_info(playlist, output_dir)

        # Get already extracted videos if skip_existing
        extracted_ids = set()
        if skip_existing and not retry_failed:
            extracted_ids = self.output_manager.get_extracted_video_ids(output_dir)

        # Create extraction report
        report = ExtractionReport(
            channel=channel_name,
            channel_id=sanitize_folder_name(channel_name),
            playlist=playlist.title,
            playlist_id=playlist_id,
            extraction_started=datetime.now().isoformat(),
            total_videos=playlist.video_count,
            accessible_videos=len(playlist.videos),
        )

        # Filter videos
        videos_to_extract = list(playlist.videos)

        # Retry mode: only process previously failed videos
        if retry_failed:
            retry_videos = self.output_manager.get_retry_videos(
                output_dir,
                [{"video_id": v.video_id, "index": v.index, "title": v.title} for v in videos_to_extract]
            )
            if not retry_videos:
                return CallToolResult(
                    content=[TextContent(type="text", text="No failed videos to retry. Previous extraction was successful or no report found.")],
                )
            # Filter to only retry videos
            retry_ids = {v.get('video_id') for v in retry_videos}
            videos_to_extract = [v for v in videos_to_extract if v.video_id in retry_ids]

        if max_videos:
            videos_to_extract = videos_to_extract[:max_videos]

        # Extract each video with adaptive rate limiting
        successful = 0
        failed = 0
        skipped = 0
        ip_blocked = False
        consecutive_failures = 0
        base_delay = self.rate_limit
        error_delay = self.rate_limit * 3  # Longer delay after errors

        for i, video in enumerate(videos_to_extract):
            # Skip if already extracted (and not in retry mode)
            if video.video_id in extracted_ids:
                report.add_skipped(ExtractionResult(
                    index=video.index,
                    video_id=video.video_id,
                    title=video.title,
                    success=False,
                    error="Already extracted",
                ))
                skipped += 1
                continue

            # Skip remaining if IP blocked
            if ip_blocked:
                report.add_skipped(ExtractionResult(
                    index=video.index,
                    video_id=video.video_id,
                    title=video.title,
                    success=False,
                    error="Skipped due to IP block",
                ))
                skipped += 1
                continue

            # Extract transcript
            result = self.extractor.extract(video.video_id, language)

            if result.success:
                # Save transcript
                filepath = self.output_manager.save_transcript_markdown(
                    transcript=result,
                    title=video.title or f"Video {video.video_id}",
                    channel_name=channel_name,
                    output_dir=output_dir,
                    index=video.index,
                    playlist_name=playlist.title,
                )

                report.add_success(ExtractionResult(
                    index=video.index,
                    video_id=video.video_id,
                    title=video.title,
                    success=True,
                    segments=result.segment_count,
                    file=filepath.name,
                ))
                successful += 1
                consecutive_failures = 0  # Reset on success
            else:
                # Check for IP block
                if result.error_type == "IpBlocked":
                    ip_blocked = True
                    report.ip_blocked = True

                report.add_failure(ExtractionResult(
                    index=video.index,
                    video_id=video.video_id,
                    title=video.title,
                    success=False,
                    error=result.error,
                ))
                failed += 1
                consecutive_failures += 1

            # Adaptive rate limiting
            if i < len(videos_to_extract) - 1 and not ip_blocked:
                if consecutive_failures >= 3:
                    # Slow down after multiple consecutive failures
                    await asyncio.sleep(error_delay)
                else:
                    await asyncio.sleep(base_delay)

        # Finalize report
        report.extraction_completed = datetime.now().isoformat()
        self.output_manager.save_extraction_report(report, output_dir)

        # Build response
        response = {
            "success": True,
            "playlist": playlist.title,
            "channel": channel_name,
            "total_videos": playlist.video_count,
            "accessible_videos": len(playlist.videos),
            "retry_mode": retry_failed,
            "extracted": successful,
            "failed": failed,
            "skipped": skipped,
            "ip_blocked": ip_blocked,
            "output_folder": str(output_dir),
            "results": {
                "successful": [
                    {"title": s["title"], "video_id": s["video_id"]}
                    for s in report.successful
                ],
                "failed": [
                    {"title": f["title"], "video_id": f["video_id"], "error": f["error"]}
                    for f in report.failed
                ],
            },
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response, indent=2))]
        )

    async def _list_playlist(self, args: dict[str, Any]) -> CallToolResult:
        """Handle list_playlist tool call."""
        url = args.get("url", "")

        # Parse URL
        try:
            parsed = parse_youtube_url(url)
        except ValueError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Invalid URL: {e}")],
                isError=True,
            )

        if not parsed.playlist_id:
            return CallToolResult(
                content=[TextContent(type="text", text="URL does not contain a playlist ID")],
                isError=True,
            )

        # Get playlist info
        playlist = self.scraper.get_playlist_info(parsed.playlist_id)

        if playlist.error:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Failed to get playlist: {playlist.error}")],
                isError=True,
            )

        response = {
            "playlist_id": playlist.playlist_id,
            "title": playlist.title,
            "channel": playlist.channel_name,
            "channel_handle": playlist.channel_handle,
            "total_videos": playlist.video_count,
            "accessible_videos": len(playlist.videos),
            "videos": [
                {
                    "index": v.index,
                    "video_id": v.video_id,
                    "title": v.title,
                    "duration": v.duration,
                }
                for v in playlist.videos
            ],
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response, indent=2))]
        )

    async def _check_transcript(self, args: dict[str, Any]) -> CallToolResult:
        """Handle check_transcript tool call."""
        url = args.get("url", "")

        # Parse URL
        try:
            parsed = parse_youtube_url(url)
        except ValueError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Invalid URL: {e}")],
                isError=True,
            )

        if not parsed.video_id:
            return CallToolResult(
                content=[TextContent(type="text", text="URL does not contain a video ID")],
                isError=True,
            )

        # Check availability
        availability = self.extractor.check_availability(parsed.video_id)

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(availability, indent=2))]
        )

    async def _get_video_info(self, args: dict[str, Any]) -> CallToolResult:
        """Handle get_video_info tool call."""
        if not self.youtube_api:
            return CallToolResult(
                content=[TextContent(type="text", text="YouTube API not available. Set YOUTUBE_API_KEY environment variable.")],
                isError=True,
            )

        url = args.get("url", "")

        try:
            parsed = parse_youtube_url(url)
        except ValueError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Invalid URL: {e}")],
                isError=True,
            )

        if not parsed.video_id:
            return CallToolResult(
                content=[TextContent(type="text", text="URL does not contain a video ID")],
                isError=True,
            )

        video = self.youtube_api.get_video(parsed.video_id)

        if video.error:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {video.error}")],
                isError=True,
            )

        response = {
            "video_id": video.video_id,
            "title": video.title,
            "description": video.description[:500] + "..." if len(video.description) > 500 else video.description,
            "channel_id": video.channel_id,
            "channel_title": video.channel_title,
            "published_at": video.published_at,
            "duration": video.duration,
            "view_count": video.view_count,
            "like_count": video.like_count,
            "comment_count": video.comment_count,
            "tags": video.tags[:10] if video.tags else [],
            "thumbnail_url": video.thumbnail_url,
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response, indent=2))]
        )

    async def _get_channel_info(self, args: dict[str, Any]) -> CallToolResult:
        """Handle get_channel_info tool call."""
        if not self.youtube_api:
            return CallToolResult(
                content=[TextContent(type="text", text="YouTube API not available. Set YOUTUBE_API_KEY environment variable.")],
                isError=True,
            )

        url = args.get("url", "")

        try:
            parsed = parse_youtube_url(url)
        except ValueError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Invalid URL: {e}")],
                isError=True,
            )

        channel = None
        if parsed.channel_handle:
            channel = self.youtube_api.get_channel_by_handle(parsed.channel_handle)
        elif parsed.channel_id:
            channel = self.youtube_api.get_channel(parsed.channel_id)
        else:
            return CallToolResult(
                content=[TextContent(type="text", text="URL does not contain a channel ID or handle")],
                isError=True,
            )

        if channel.error:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {channel.error}")],
                isError=True,
            )

        response = {
            "channel_id": channel.channel_id,
            "title": channel.title,
            "description": channel.description[:500] + "..." if len(channel.description) > 500 else channel.description,
            "custom_url": channel.custom_url,
            "published_at": channel.published_at,
            "subscriber_count": channel.subscriber_count,
            "video_count": channel.video_count,
            "view_count": channel.view_count,
            "thumbnail_url": channel.thumbnail_url,
            "uploads_playlist_id": channel.uploads_playlist_id,
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response, indent=2))]
        )

    async def _search_videos(self, args: dict[str, Any]) -> CallToolResult:
        """Handle search_videos tool call."""
        if not self.youtube_api:
            return CallToolResult(
                content=[TextContent(type="text", text="YouTube API not available. Set YOUTUBE_API_KEY environment variable.")],
                isError=True,
            )

        query = args.get("query", "")
        max_results = args.get("max_results", 10)

        if not query:
            return CallToolResult(
                content=[TextContent(type="text", text="Search query is required")],
                isError=True,
            )

        results = self.youtube_api.search_videos(query, max_results=max_results)

        if results.error:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {results.error}")],
                isError=True,
            )

        response = {
            "query": results.query,
            "total_results": results.total_results,
            "results": [
                {
                    "video_id": r.video_id,
                    "title": r.title,
                    "channel_title": r.channel_title,
                    "published_at": r.published_at,
                    "url": f"https://www.youtube.com/watch?v={r.video_id}",
                }
                for r in results.results
            ],
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response, indent=2))]
        )

    async def _youtube(self, args: dict[str, Any]) -> CallToolResult:
        """Handle unified youtube tool call."""
        input_str = args.get("input", "")
        action = args.get("action", "discover")
        method = args.get("method", "auto")
        max_videos = args.get("max_videos", 50)
        max_playlists = args.get("max_playlists", 20)
        language = args.get("language", self.default_language)

        if not input_str:
            return CallToolResult(
                content=[TextContent(type="text", text="Input is required. Use @handle, URL, or channel ID.")],
                isError=True,
            )

        # Check if it's a direct video URL - extract immediately
        try:
            parsed = parse_youtube_url(input_str)
            if parsed.video_id and not parsed.channel_handle and not parsed.channel_id and not parsed.playlist_id:
                # Direct video URL - extract transcript
                result = self.extractor.extract(parsed.video_id, language)
                if result.success:
                    response = {
                        "action": "extract_video",
                        "video_id": result.video_id,
                        "language": result.language,
                        "segments": result.segment_count,
                        "text_length": len(result.full_text),
                        "transcript_preview": result.full_text[:1000] + "..." if len(result.full_text) > 1000 else result.full_text,
                    }
                    return CallToolResult(
                        content=[TextContent(type="text", text=json.dumps(response, indent=2))]
                    )
                else:
                    return CallToolResult(
                        content=[TextContent(type="text", text=f"Failed to extract: {result.error}")],
                        isError=True,
                    )
        except ValueError:
            pass  # Not a valid URL, continue

        # Initialize discoverer
        discoverer = ChannelDiscoverer(
            api_key=self.youtube_api.api_key if self.youtube_api else None,
            ssl_bypass=True,
        )

        # Discover channel content
        discovery = await discoverer.discover(
            input_str,
            method=method,
            max_videos=max_videos,
            max_playlists=max_playlists,
        )

        if discovery.error and action == "discover":
            return CallToolResult(
                content=[TextContent(type="text", text=f"Discovery error: {discovery.error}\n\nTip: Try method='playwright' or method='api' (requires YOUTUBE_API_KEY)")],
                isError=True,
            )

        # Handle different actions
        if action == "discover":
            # Return discovery results with shortcuts
            shortcuts = discovery.get_shortcuts()
            response = {
                "action": "discover",
                "channel": {
                    "name": discovery.channel_name,
                    "handle": f"@{discovery.channel_handle}" if discovery.channel_handle else discovery.channel_id,
                    "url": discovery.channel_url,
                    "subscribers": discovery.subscriber_count,
                    "video_count": discovery.video_count,
                },
                "method_used": discovery.method_used,
                "playlists": [
                    {
                        "shortcut": f"p{i}",
                        "id": p.playlist_id,
                        "title": p.title,
                        "videos": p.video_count,
                    }
                    for i, p in enumerate(discovery.playlists, 1)
                ],
                "videos": [
                    {
                        "shortcut": f"v{i}",
                        "id": v.video_id,
                        "title": v.title,
                        "duration": v.duration,
                    }
                    for i, v in enumerate(discovery.videos[:20], 1)
                ],
                "shortcuts_help": {
                    "p1, p2, ...": "Extract specific playlist",
                    "v1, v2, ...": "Extract specific video",
                    "extract_all": "Extract all videos",
                    "save_config": "Save as JSON config",
                    "list_playlists": "List all playlists",
                    "list_videos": "List all videos",
                },
                "next_steps": [
                    f"youtube {input_str} action=p1  # Extract playlist '{discovery.playlists[0].title if discovery.playlists else 'N/A'}'",
                    f"youtube {input_str} action=v1  # Extract video '{discovery.videos[0].title[:40] if discovery.videos else 'N/A'}...'",
                    f"youtube {input_str} action=save_config  # Save for later use",
                ],
            }
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(response, indent=2))]
            )

        elif action.startswith("p") and action[1:].isdigit():
            # Playlist shortcut (p1, p2, etc.)
            idx = int(action[1:]) - 1
            if idx < 0 or idx >= len(discovery.playlists):
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Invalid playlist shortcut. Available: p1-p{len(discovery.playlists)}")],
                    isError=True,
                )

            playlist = discovery.playlists[idx]
            # Use extract_playlist with the playlist ID
            return await self._extract_playlist({
                "url": f"https://www.youtube.com/playlist?list={playlist.playlist_id}",
                "language": language,
            })

        elif action.startswith("v") and action[1:].isdigit():
            # Video shortcut (v1, v2, etc.)
            idx = int(action[1:]) - 1
            if idx < 0 or idx >= len(discovery.videos):
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Invalid video shortcut. Available: v1-v{len(discovery.videos)}")],
                    isError=True,
                )

            video = discovery.videos[idx]
            result = self.extractor.extract(video.video_id, language)

            if result.success:
                # Save transcript
                output_dir = self.output_manager.get_channel_dir(discovery.channel_name or "unknown") / "singles"
                output_dir.mkdir(parents=True, exist_ok=True)

                filepath = self.output_manager.save_transcript_markdown(
                    transcript=result,
                    title=video.title,
                    channel_name=discovery.channel_name or "unknown",
                    output_dir=output_dir,
                    video_url=f"https://www.youtube.com/watch?v={video.video_id}",
                )

                response = {
                    "action": f"extract_video:{action}",
                    "video": {
                        "id": video.video_id,
                        "title": video.title,
                    },
                    "success": True,
                    "language": result.language,
                    "segments": result.segment_count,
                    "file": str(filepath),
                    "transcript_preview": result.full_text[:1000] + "..." if len(result.full_text) > 1000 else result.full_text,
                }
            else:
                response = {
                    "action": f"extract_video:{action}",
                    "video": {
                        "id": video.video_id,
                        "title": video.title,
                    },
                    "success": False,
                    "error": result.error,
                }

            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(response, indent=2))]
            )

        elif action == "extract_all":
            # Extract all discovered videos
            results = {"successful": [], "failed": []}
            output_dir = self.output_manager.get_channel_dir(discovery.channel_name or "unknown") / "all_videos"
            output_dir.mkdir(parents=True, exist_ok=True)

            for i, video in enumerate(discovery.videos):
                result = self.extractor.extract(video.video_id, language)

                if result.success:
                    filepath = self.output_manager.save_transcript_markdown(
                        transcript=result,
                        title=video.title,
                        channel_name=discovery.channel_name or "unknown",
                        output_dir=output_dir,
                        index=i + 1,
                        video_url=f"https://www.youtube.com/watch?v={video.video_id}",
                    )
                    results["successful"].append({"title": video.title, "file": filepath.name})
                else:
                    results["failed"].append({"title": video.title, "error": result.error})

                # Rate limit
                if i < len(discovery.videos) - 1:
                    await asyncio.sleep(self.rate_limit)

            response = {
                "action": "extract_all",
                "channel": discovery.channel_name,
                "total": len(discovery.videos),
                "successful": len(results["successful"]),
                "failed": len(results["failed"]),
                "output_folder": str(output_dir),
                "results": results,
            }
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(response, indent=2))]
            )

        elif action == "save_config":
            # Save as JSON config
            config_dir = Path("tools/channels")
            config_dir.mkdir(parents=True, exist_ok=True)

            config_name = discovery.channel_handle or discovery.channel_id or "channel"
            config_path = config_dir / f"{config_name}.json"

            config = create_config_from_discovery(discovery, output_path=config_path)

            response = {
                "action": "save_config",
                "channel": discovery.channel_name,
                "config_file": str(config_path),
                "playlists_count": len(discovery.playlists),
                "videos_count": len(config["videos"]),
                "usage": f"python -m youtube_mcp.cli {config_name}",
            }
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(response, indent=2))]
            )

        elif action == "list_playlists":
            response = {
                "action": "list_playlists",
                "channel": discovery.channel_name,
                "count": len(discovery.playlists),
                "playlists": [
                    {
                        "shortcut": f"p{i}",
                        "id": p.playlist_id,
                        "title": p.title,
                        "videos": p.video_count,
                        "url": f"https://www.youtube.com/playlist?list={p.playlist_id}",
                    }
                    for i, p in enumerate(discovery.playlists, 1)
                ],
            }
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(response, indent=2))]
            )

        elif action == "list_videos":
            response = {
                "action": "list_videos",
                "channel": discovery.channel_name,
                "count": len(discovery.videos),
                "videos": [
                    {
                        "shortcut": f"v{i}",
                        "id": v.video_id,
                        "title": v.title,
                        "duration": v.duration,
                        "url": f"https://www.youtube.com/watch?v={v.video_id}",
                    }
                    for i, v in enumerate(discovery.videos, 1)
                ],
            }
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(response, indent=2))]
            )

        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown action: {action}\n\nAvailable actions: discover, p1-p99, v1-v99, extract_all, save_config, list_playlists, list_videos")],
                isError=True,
            )

    async def _summarize_video(self, args: dict[str, Any]) -> CallToolResult:
        """Handle summarize_video tool call - extracts transcript, summarizes, and saves files."""
        if not self.summarizer:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text="Summarization not available. Make sure Claude CLI is installed and accessible."
                )],
                isError=True,
            )

        url = args.get("url", "")
        style = args.get("style", "trading-strategy")  # Default to trading-strategy
        length = args.get("length", "detailed")  # Default to detailed
        language = args.get("language", self.default_language)
        custom_instructions = args.get("custom_instructions")

        # Parse URL
        try:
            parsed = parse_youtube_url(url)
        except ValueError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Invalid URL: {e}")],
                isError=True,
            )

        if not parsed.video_id:
            return CallToolResult(
                content=[TextContent(type="text", text="URL does not contain a video ID")],
                isError=True,
            )

        # Extract transcript first
        transcript_result = self.extractor.extract(parsed.video_id, language)

        if not transcript_result.success:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Failed to extract transcript: {transcript_result.error}"
                )],
                isError=True,
            )

        # Get video title and channel by scraping YouTube page (no API key needed)
        video_info = fetch_video_info(parsed.video_id)
        title = video_info.get("title", f"Video {parsed.video_id}")
        channel_name = video_info.get("channel", "unknown")

        # Save transcript to file
        transcript_dir = self.output_manager.get_channel_dir(channel_name) / "singles"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = self.output_manager.save_transcript_markdown(
            transcript=transcript_result,
            title=title,
            channel_name=channel_name,
            output_dir=transcript_dir,
            video_url=parsed.get_video_url(),
        )

        # Summarize
        summary_result = self.summarizer.summarize(
            transcript=transcript_result.full_text,
            video_id=parsed.video_id,
            title=title,
            style=style,
            length=length,
            custom_instructions=custom_instructions,
        )

        if not summary_result.success:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Transcript saved but failed to summarize: {summary_result.error}\nTranscript: {transcript_path}"
                )],
                isError=True,
            )

        # Save summary files
        saved_files = self.output_manager.save_summary_markdown(
            summary=summary_result,
            title=title,
            video_url=parsed.get_video_url(),
            channel_name=channel_name,
            include_algorithm=(style == "trading-strategy"),
        )

        # Build response
        response = {
            "success": True,
            "video_id": summary_result.video_id,
            "title": title,
            "files": {
                "transcript": str(transcript_path),
                **saved_files,
            },
            "transcript_length": summary_result.transcript_length,
            "summary_style": summary_result.summary_style,
            "summary_length": summary_result.summary_length,
            "word_count": summary_result.word_count,
            "key_topics": summary_result.key_topics,
            "summary": summary_result.summary_text,
        }

        if summary_result.trading_insights:
            response["trading_insights"] = summary_result.trading_insights

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response, indent=2))]
        )

    async def _summarize_for_indicator(self, args: dict[str, Any]) -> CallToolResult:
        """Handle summarize_for_indicator tool call - specialized for indicator building."""
        if not self.summarizer:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text="Summarization not available. Make sure Claude CLI is installed and accessible."
                )],
                isError=True,
            )

        url = args.get("url", "")
        indicator_type = args.get("indicator_type")
        language = args.get("language", self.default_language)

        # Parse URL
        try:
            parsed = parse_youtube_url(url)
        except ValueError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Invalid URL: {e}")],
                isError=True,
            )

        if not parsed.video_id:
            return CallToolResult(
                content=[TextContent(type="text", text="URL does not contain a video ID")],
                isError=True,
            )

        # Extract transcript first
        transcript_result = self.extractor.extract(parsed.video_id, language)

        if not transcript_result.success:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Failed to extract transcript: {transcript_result.error}"
                )],
                isError=True,
            )

        # Get video title and channel by scraping YouTube page (no API key needed)
        video_info = fetch_video_info(parsed.video_id)
        title = video_info.get("title", f"Video {parsed.video_id}")
        channel_name = video_info.get("channel", "unknown")

        # Save transcript to file
        transcript_dir = self.output_manager.get_channel_dir(channel_name) / "singles"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = self.output_manager.save_transcript_markdown(
            transcript=transcript_result,
            title=title,
            channel_name=channel_name,
            output_dir=transcript_dir,
            video_url=parsed.get_video_url(),
        )

        # Summarize with indicator focus
        summary_result = self.summarizer.summarize_for_indicator(
            transcript=transcript_result.full_text,
            video_id=parsed.video_id,
            title=title,
            indicator_type=indicator_type,
        )

        if not summary_result.success:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Transcript saved but failed to summarize: {summary_result.error}\nTranscript: {transcript_path}"
                )],
                isError=True,
            )

        # Save summary files (always include algorithm for indicator mode)
        saved_files = self.output_manager.save_summary_markdown(
            summary=summary_result,
            title=title,
            video_url=parsed.get_video_url(),
            channel_name=channel_name,
            include_algorithm=True,
        )

        # Build response with trading-focused structure
        response = {
            "success": True,
            "video_id": summary_result.video_id,
            "title": title,
            "indicator_type": indicator_type,
            "files": {
                "transcript": str(transcript_path),
                **saved_files,
            },
            "transcript_length": summary_result.transcript_length,
            "word_count": summary_result.word_count,
            "key_topics": summary_result.key_topics,
            "trading_insights": summary_result.trading_insights,
            "full_summary": summary_result.summary_text,
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response, indent=2))]
        )

    async def _summarize_playlist(self, args: dict[str, Any]) -> CallToolResult:
        """Handle summarize_playlist tool call - batch summarize all videos in a playlist."""
        if not self.summarizer:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text="Summarization not available. Make sure Claude CLI is installed and accessible."
                )],
                isError=True,
            )

        url = args.get("url", "")
        style = args.get("style", "trading-strategy")
        length = args.get("length", "detailed")
        language = args.get("language", self.default_language)
        max_videos = args.get("max_videos")
        skip_existing = args.get("skip_existing", True)

        # Parse URL
        try:
            parsed = parse_youtube_url(url)
        except ValueError as e:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Invalid URL: {e}")],
                isError=True,
            )

        if not parsed.playlist_id:
            return CallToolResult(
                content=[TextContent(type="text", text="URL does not contain a playlist ID")],
                isError=True,
            )

        # Get playlist info
        playlist_info = self.scraper.get_playlist_info(parsed.playlist_id)
        if not playlist_info or playlist_info.error:
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Failed to get playlist info: {playlist_info.error if playlist_info else 'Unknown error'}"
                )],
                isError=True,
            )

        channel_name = playlist_info.channel_name or "unknown"
        playlist_name = playlist_info.title or f"playlist_{parsed.playlist_id}"

        # Determine videos to process
        videos = playlist_info.videos
        if max_videos and max_videos > 0:
            videos = videos[:max_videos]

        results = {
            "successful": [],
            "failed": [],
            "skipped": [],
        }

        # Process each video
        for i, video in enumerate(videos, 1):
            video_id = video.video_id
            video_title = video.title or f"Video {video_id}"
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            # Check if already processed
            if skip_existing:
                summaries_dir = self.output_manager.get_summaries_dir(channel_name) / sanitize_folder_name(playlist_name)
                if summaries_dir.exists():
                    existing = list(summaries_dir.glob(f"*{sanitize_filename(video_title)[:30]}*_summary.md"))
                    if existing:
                        results["skipped"].append({"index": i, "title": video_title, "reason": "already exists"})
                        continue

            # Extract transcript
            transcript_result = self.extractor.extract(video_id, language)
            if not transcript_result.success:
                results["failed"].append({"index": i, "title": video_title, "error": transcript_result.error})
                continue

            # Save transcript
            transcript_dir = self.output_manager.get_playlist_dir(channel_name, playlist_name)
            transcript_path = self.output_manager.save_transcript_markdown(
                transcript=transcript_result,
                title=video_title,
                channel_name=channel_name,
                output_dir=transcript_dir,
                index=i,
                playlist_name=playlist_name,
                video_url=video_url,
            )

            # Summarize
            summary_result = self.summarizer.summarize(
                transcript=transcript_result.full_text,
                video_id=video_id,
                title=video_title,
                style=style,
                length=length,
            )

            if not summary_result.success:
                results["failed"].append({
                    "index": i,
                    "title": video_title,
                    "error": f"Summarization failed: {summary_result.error}",
                    "transcript": str(transcript_path),
                })
                continue

            # Save summaries
            saved_files = self.output_manager.save_summary_markdown(
                summary=summary_result,
                title=video_title,
                video_url=video_url,
                channel_name=channel_name,
                playlist_name=playlist_name,
                index=i,
                include_algorithm=(style == "trading-strategy"),
            )

            results["successful"].append({
                "index": i,
                "title": video_title,
                "files": {
                    "transcript": str(transcript_path),
                    **saved_files,
                },
            })

            # Rate limit between videos
            if i < len(videos):
                await asyncio.sleep(self.rate_limit)

        # Build response
        response = {
            "success": True,
            "playlist_id": parsed.playlist_id,
            "playlist_title": playlist_name,
            "channel": channel_name,
            "total_videos": len(videos),
            "successful": len(results["successful"]),
            "failed": len(results["failed"]),
            "skipped": len(results["skipped"]),
            "output_folders": {
                "transcripts": str(self.output_manager.get_playlist_dir(channel_name, playlist_name)),
                "summaries": str(self.output_manager.get_summaries_dir(channel_name) / sanitize_folder_name(playlist_name)),
            },
            "results": results,
        }

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response, indent=2))]
        )

    async def run(self):
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


def main():
    """Main entry point."""
    import os

    # Get configuration from environment
    output_dir = os.environ.get("YOUTUBE_MCP_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
    language = os.environ.get("YOUTUBE_MCP_LANGUAGE", DEFAULT_LANGUAGE)
    rate_limit = float(os.environ.get("YOUTUBE_MCP_RATE_LIMIT", str(DEFAULT_RATE_LIMIT)))
    api_key = os.environ.get("YOUTUBE_API_KEY")

    # Create and run server
    server = YouTubeMCPServer(
        output_dir=output_dir,
        default_language=language,
        rate_limit=rate_limit,
        api_key=api_key,
    )

    asyncio.run(server.run())


if __name__ == "__main__":
    main()
