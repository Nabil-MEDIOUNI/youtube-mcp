# YouTube MCP Server (Python)

A Python-based MCP (Model Context Protocol) server for extracting YouTube transcripts from videos, playlists, and channels with smart URL parsing and optional YouTube API integration.

## Features

- **Single Video Extraction**: Extract transcript from any YouTube video URL
- **Playlist Extraction**: Batch extract transcripts from entire playlists
- **Channel Discovery**: Discover and extract content from any YouTube channel
- **Smart URL Parsing**: Accepts any YouTube URL format (watch, youtu.be, playlist, channel, etc.)
- **Multiple Discovery Methods**: API, Playwright browser automation, or HTTP scraping
- **SSL Bypass**: Works in corporate environments with SSL inspection
- **Rate Limiting**: Built-in delays with adaptive slowdown after consecutive failures
- **Retry Mode**: Re-process only previously failed videos
- **Resume Support**: Skip already extracted videos
- **Structured Output**: Organized folder structure with markdown transcripts

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     YouTube MCP Python                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐     ┌──────────────┐     ┌─────────────────┐  │
│  │ URL Parser  │────▶│ Type Router  │────▶│ Extraction Mode │  │
│  └─────────────┘     └──────────────┘     └─────────────────┘  │
│         │                   │                      │            │
│         ▼                   ▼                      ▼            │
│  ┌─────────────┐     ┌──────────────┐     ┌─────────────────┐  │
│  │ video_id    │     │ video        │     │ Single Video    │  │
│  │ playlist_id │     │ playlist     │     │ Batch Playlist  │  │
│  │ channel_id  │     │ channel      │     │ Channel Scan    │  │
│  └─────────────┘     └──────────────┘     └─────────────────┘  │
│                                                    │            │
│                      ┌─────────────────────────────┘            │
│                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               Transcript Extractor                       │   │
│  │  ┌─────────────────┐    ┌───────────────────────────┐   │   │
│  │  │ youtube-        │    │ Playwright Fallback       │   │   │
│  │  │ transcript-api  │    │ (for video list scraping) │   │   │
│  │  └─────────────────┘    └───────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Output Manager                        │   │
│  │  transcripts/{channel_name}/{playlist_name}/             │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
cd youtube-mcp
pip install -e .
```

### Dependencies

```bash
pip install mcp youtube-transcript-api requests
# Optional: for browser-based discovery
pip install playwright && playwright install chromium
```

## Usage

### MCP Server (Claude Code / Claude Desktop)

Add to your Claude config (`~/.claude.json` or Claude Desktop config):

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

### CLI (Command Line)

```bash
cd youtube-mcp/src

# Unified YouTube command - discover channel content
python cli.py youtube @TJRTrades

# Extract specific playlist (p1, p2, ...)
python cli.py youtube @TJRTrades --action p1

# Extract specific video (v1, v2, ...)
python cli.py youtube @TJRTrades --action v1

# Single video
python cli.py --video "https://www.youtube.com/watch?v=VIDEO_ID"

# From JSON config
python cli.py tjr

# Retry only failed videos
python cli.py tjr --retry
```

### Direct Python Usage

```python
from url_parser import parse_youtube_url
from transcript import TranscriptExtractor
from playlist import load_playlist_from_json

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

### `youtube` (Unified Tool)

Discover, explore, and extract content from any channel with a single input.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `input` | Yes | - | Channel handle (@name), URL, channel ID, playlist URL, or video URL |
| `action` | No | `discover` | `discover`, `p1`-`p99`, `v1`-`v99`, `extract_all`, `save_config` |
| `method` | No | `auto` | `auto`, `api`, `playwright`, `scraping` |
| `max_videos` | No | 50 | Max videos to discover |
| `language` | No | `en` | Transcript language |

### `extract_transcript`

Extract transcript from a single YouTube video.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | Yes | - | YouTube video URL |
| `language` | No | `en` | Language code |
| `save_file` | No | `true` | Save to file |

### `extract_playlist`

Extract transcripts from all videos in a playlist.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | No | - | YouTube playlist URL |
| `json_config` | No | - | Path to JSON config file |
| `skip_existing` | No | `true` | Skip already extracted |
| `retry_failed` | No | `false` | Only retry previously failed |

### `list_playlist` / `check_transcript`

List videos in a playlist or check transcript availability.

### API Tools (Requires `YOUTUBE_API_KEY`)

- `get_video_info` - Video details (title, stats)
- `get_channel_info` - Channel info (subscribers, video count)
- `search_videos` - Search YouTube

## Algorithm

### Extraction Flow

```
Parse URL → Detect Type (video/playlist/channel)
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
  video     playlist     channel
    │           │           │
    │     ┌─────┴─────┐     │
    │     ▼           ▼     │
    │   API?    Playwright  │
    │     │     Scraping    │
    │     └─────┬─────┘     │
    │           ▼           │
    └────► Extract ◄────────┘
           Transcript
              │
              ▼
         Save Output
```

### Rate Limiting Strategy

```
BASE_DELAY = 3 seconds
ERROR_DELAY = 10 seconds
MAX_CONSECUTIVE_ERRORS = 5

for each video:
  try:
    extract_transcript()
    sleep(BASE_DELAY)
  except IPBlocked:
    STOP immediately
  except TransientError:
    retry with exponential backoff
  except PermanentError:
    log error, continue
```

## Output Structure

```
transcripts/
├── channel_name/
│   ├── playlist_name/
│   │   ├── _playlist_info.json
│   │   ├── _extraction_report.json
│   │   ├── 01_video_title.md
│   │   └── 02_video_title.md
│   └── singles/
│       └── video_title.md
```

### Transcript Format (Markdown)

```markdown
# Video Title

## Video Info
- **Channel**: Channel Name
- **Video ID**: VIDEO_ID
- **URL**: https://www.youtube.com/watch?v=VIDEO_ID
- **Extracted**: 2026-01-21

---

## Full Text

Transcript content here...
```

## URL Format Support

| Format | Example | Supported |
|--------|---------|-----------|
| Standard video | `youtube.com/watch?v=ID` | Yes |
| Short URL | `youtu.be/ID` | Yes |
| Playlist | `playlist?list=PLID` | Yes |
| Channel handle | `youtube.com/@handle` | Yes |
| Channel ID | `youtube.com/channel/UCID` | Yes |

## Limitations

### Hard Limitations

| Limitation | Reason |
|------------|--------|
| Videos without captions | Creator disabled or never added |
| Private/deleted videos | Not accessible |
| Age-restricted videos | Requires login |
| IP blocking | Too many requests - wait and retry |

### Soft Limitations

| Limitation | Mitigation |
|------------|------------|
| Rate limiting | Configurable delays, adaptive backoff |
| SSL errors | Auto-retry with bypass |
| Large playlists | Batch processing, resume support |

## Error Handling

| Error | Action |
|-------|--------|
| `TranscriptsDisabled` | Skip video |
| `NoTranscriptFound` | Try other languages |
| `VideoUnavailable` | Skip video |
| `IpBlocked` | Stop, wait, retry later |
| `SSLError` | Auto-retry with bypass |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_MCP_OUTPUT_DIR` | `transcripts` | Output directory |
| `YOUTUBE_MCP_LANGUAGE` | `en` | Default language |
| `YOUTUBE_MCP_RATE_LIMIT` | `3` | Seconds between requests |
| `YOUTUBE_API_KEY` | - | YouTube API key (optional) |

## Project Structure

```
youtube-mcp/
├── src/
│   ├── server.py        # MCP server implementation
│   ├── cli.py           # Command-line interface
│   ├── discovery.py     # Channel/playlist discovery
│   ├── transcript.py    # Transcript extraction
│   ├── playlist.py      # Playlist handling
│   ├── url_parser.py    # URL parsing utilities
│   ├── youtube_api.py   # YouTube API integration
│   └── output.py        # Output file management
├── transcripts/         # Default output directory
├── pyproject.toml
├── requirements.txt
└── README.md
```

## License

MIT
