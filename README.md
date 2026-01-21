# YouTube MCP Server (Python)

A comprehensive Python-based MCP (Model Context Protocol) server for extracting YouTube transcripts from videos and playlists, with optional YouTube API integration.

## Features

- **Single Video Extraction**: Extract transcript from any YouTube video URL
- **Playlist Extraction**: Batch extract transcripts from entire playlists
- **Smart URL Parsing**: Accepts any YouTube URL format (watch, youtu.be, playlist, channel, etc.)
- **SSL Bypass**: Works in corporate environments with SSL inspection
- **Rate Limiting**: Built-in delays with adaptive slowdown after consecutive failures
- **Retry Mode**: Re-process only previously failed videos
- **Resume Support**: Skip already extracted videos
- **Structured Output**: Organized folder structure with markdown transcripts
- **CLI Interface**: Command-line tool matching original workflow
- **YouTube API Integration**: Optional video details, search, and channel info (requires API key)

## Installation

### From Source

```bash
cd youtube-mcp
pip install -e .
```

### Dependencies

```bash
pip install mcp youtube-transcript-api requests
```

## Usage

### CLI (Command Line)

```bash
# From the src directory
cd youtube-mcp/src

# List available configurations
python cli.py

# Extract from a config
python cli.py tjr

# Retry only failed videos
python cli.py tjr --retry

# Extract all configs
python cli.py --all

# Single video
python cli.py --video "https://www.youtube.com/watch?v=VIDEO_ID"

# Custom output directory
python cli.py tjr --output /path/to/output
```

### Unified YouTube Command (NEW!)

Discover and extract content from any YouTube channel with a single command:

```bash
# Discover channel content
python cli.py youtube @TJRTrades

# Extract specific playlist (p1, p2, ...)
python cli.py youtube @TJRTrades --action p1

# Extract specific video (v1, v2, ...)
python cli.py youtube @TJRTrades --action v1

# Extract all videos
python cli.py youtube @TJRTrades --action extract_all

# Save as JSON config for later
python cli.py youtube @TJRTrades --action save

# List all content verbosely
python cli.py youtube @TJRTrades --action list

# Choose discovery method
python cli.py youtube @TJRTrades --method playwright   # Browser automation
python cli.py youtube @TJRTrades --method api          # YouTube API (needs key)
python cli.py youtube @TJRTrades --method scraping     # HTTP scraping (fast)
```

**Input formats:**
- `@handle` - Channel handle (e.g., `@TJRTrades`, `@PixiesOfficialTV`)
- Channel URL - `https://www.youtube.com/@TJRTrades`
- Channel ID - `UCxxxxxxxx`

**Methods:**
- `auto` (default) - Try API, then Playwright, then scraping
- `api` - Requires `YOUTUBE_API_KEY` environment variable
- `playwright` - Requires `pip install playwright && playwright install chromium`
- `scraping` - Fastest but may be blocked by YouTube

### MCP Server (with Claude Code or Claude Desktop)

Add to your global Claude config (`~/.claude.json`) or Claude Desktop config:

```json
{
  "mcpServers": {
    "youtube": {
      "type": "stdio",
      "command": "python",
      "args": ["server.py"],
      "cwd": "C:/path/to/youtube-mcp/src",
      "env": {
        "YOUTUBE_MCP_OUTPUT_DIR": "C:/path/to/transcripts",
        "YOUTUBE_MCP_LANGUAGE": "en",
        "YOUTUBE_MCP_RATE_LIMIT": "3",
        "YOUTUBE_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### Direct Python Usage

```python
# Run from the src directory
from url_parser import parse_youtube_url
from transcript import TranscriptExtractor
from playlist import PlaylistScraper, load_playlist_from_json

# Extract single video transcript
extractor = TranscriptExtractor(ssl_bypass=True)
result = extractor.extract("VIDEO_ID")
print(result.full_text)

# Load playlist from JSON config
playlist = load_playlist_from_json("tools/channels/tjr.json")
for video in playlist.videos:
    print(f"{video.index}. {video.title}")
```

## MCP Tools

### Unified Tool (Recommended)

#### `youtube`

The unified YouTube tool - discover, explore, and extract content from any channel with a single input.

**Parameters:**
- `input` (required): Channel handle (@name), URL, channel ID, playlist URL, or video URL
- `action` (optional): Action to perform (default: "discover")
  - `discover` - Show channel content with shortcuts
  - `p1`, `p2`, ... `p99` - Extract specific playlist
  - `v1`, `v2`, ... `v99` - Extract specific video
  - `extract_all` - Extract all discovered videos
  - `save_config` - Save as JSON config file
  - `list_playlists` - List all playlists
  - `list_videos` - List all videos
- `method` (optional): Discovery method (default: "auto")
  - `auto` - Try API, then Playwright, then scraping
  - `api` - Use YouTube Data API (requires YOUTUBE_API_KEY)
  - `playwright` - Use browser automation
  - `scraping` - Use HTTP scraping
- `max_videos` (optional): Max videos to discover (default: 50)
- `max_playlists` (optional): Max playlists to discover (default: 20)
- `language` (optional): Transcript language (default: "en")

**Examples:**
```
youtube @TJRTrades                          # Discover channel
youtube @TJRTrades action=p1                # Extract first playlist
youtube @TJRTrades action=v3                # Extract third video
youtube @TJRTrades method=playwright        # Use Playwright
youtube @TJRTrades action=save_config       # Save for later
```

### Core Tools (No API Key Required)

#### `extract_transcript`

Extract transcript from a single YouTube video.

**Parameters:**
- `url` (required): YouTube video URL
- `language` (optional): Language code (default: "en")
- `save_file` (optional): Save to file (default: true)

#### `extract_playlist`

Extract transcripts from all videos in a playlist.

**Parameters:**
- `url` (optional): YouTube playlist URL
- `json_config` (optional): Path to JSON config file (more reliable)
- `language` (optional): Language code (default: "en")
- `skip_existing` (optional): Skip already extracted (default: true)
- `max_videos` (optional): Maximum videos to extract
- `retry_failed` (optional): Only retry previously failed videos (default: false)

#### `list_playlist`

List all videos in a playlist without extracting.

**Parameters:**
- `url` (required): YouTube playlist URL

#### `check_transcript`

Check if transcripts are available for a video.

**Parameters:**
- `url` (required): YouTube video URL

### YouTube API Tools (Requires YOUTUBE_API_KEY)

#### `get_video_info`

Get detailed information about a video (title, stats, etc.).

**Parameters:**
- `url` (required): YouTube video URL

#### `get_channel_info`

Get channel information (subscribers, video count, etc.).

**Parameters:**
- `url` (required): YouTube channel URL

#### `search_videos`

Search for videos on YouTube.

**Parameters:**
- `query` (required): Search query
- `max_results` (optional): Max results 1-50 (default: 10)

## JSON Config Format

Create config files in `tools/channels/` for reliable playlist extraction:

```json
{
  "channel": {
    "id": "channel-id",
    "name": "Channel Name",
    "url": "https://www.youtube.com/@handle",
    "playlist_id": "PLAYLIST_ID",
    "playlist_name": "Playlist Name"
  },
  "videos": [
    {"index": 1, "id": "VIDEO_ID", "title": "Video Title"},
    {"index": 2, "id": "VIDEO_ID2", "title": "Video Title 2"}
  ]
}
```

## Output Structure

```
transcripts/
├── channel_name/
│   ├── playlist_name/
│   │   ├── _playlist_info.json
│   │   ├── _extraction_report.json
│   │   ├── 01_video_title.md
│   │   ├── 02_video_title.md
│   │   └── ...
│   └── singles/
│       └── video_title.md
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_MCP_OUTPUT_DIR` | `transcripts` | Output directory for saved files |
| `YOUTUBE_MCP_LANGUAGE` | `en` | Default transcript language |
| `YOUTUBE_MCP_RATE_LIMIT` | `3` | Seconds between requests |
| `YOUTUBE_API_KEY` | - | YouTube Data API key (optional) |

### CLI Arguments

| Argument | Description |
|----------|-------------|
| `--output`, `-o` | Output directory |
| `--language`, `-l` | Transcript language |
| `--delay`, `-d` | Delay between requests |
| `--retry` | Only retry failed videos |
| `--all` | Process all configurations |
| `--video`, `-v` | Single video URL |
| `--url`, `-u` | Playlist URL |

## Features from Original Projects

### From `extract_transcripts.py`

- [x] SSL bypass for corporate environments
- [x] Batch extraction with rate limiting
- [x] JSON config loading
- [x] Markdown output format
- [x] Extraction reports
- [x] Skip existing videos
- [x] Retry failed videos only (`--retry`)
- [x] IP blocking detection
- [x] Adaptive rate limiting (slowdown after consecutive failures)
- [x] CLI interface

### From TypeScript `youtube-mcp-server`

- [x] Get transcript
- [x] List playlist videos
- [x] Check transcript availability
- [x] Get video details (requires API key)
- [x] Get channel info (requires API key)
- [x] Search videos (requires API key)

## Limitations

- **No API Key Required for Transcripts**: Uses web scraping, not YouTube API
- **Captions Required**: Only works for videos with captions/transcripts
- **Rate Limiting**: YouTube may block IP after many requests
- **Hidden Videos**: Cannot access private/deleted videos
- **Playlist Scraping**: HTTP scraping may hit consent pages; use JSON configs

## Error Handling

| Error | Description | Action |
|-------|-------------|--------|
| `TranscriptsDisabled` | Video has no captions | Skip |
| `NoTranscriptFound` | No transcript in language | Try other languages |
| `VideoUnavailable` | Private/deleted/locked | Skip |
| `IpBlocked` | Too many requests | Stop, wait, retry later |
| `SSLError` | Certificate issues | Auto-retry with bypass |

## License

MIT
