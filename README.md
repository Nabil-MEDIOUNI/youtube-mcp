# YouTube MCP Server (Python)

A Python-based MCP (Model Context Protocol) server for extracting YouTube transcripts, generating AI-powered summaries, and extracting trading indicator algorithms from videos and playlists.

## Features

### Core Features
- **Single Video Extraction**: Extract transcript from any YouTube video URL
- **Playlist Extraction**: Batch extract transcripts from entire playlists
- **Channel Discovery**: Discover and extract content from any YouTube channel
- **Smart URL Parsing**: Accepts any YouTube URL format (watch, youtu.be, playlist, channel, etc.)

### AI-Powered Summarization
- **Video Summarization**: Generate comprehensive summaries using Claude CLI
- **Trading Strategy Extraction**: Extract entry/exit conditions, risk management, indicators
- **Algorithm Guide Generation**: Create indicator-building guides with Pine Script templates
- **Playlist Batch Summarization**: Summarize entire playlists with organized output
- **Auto Video Metadata**: Fetches video title and channel name automatically via YouTube oEmbed API (no API key required)

### Output Organization
- **Transcripts**: Saved to `transcripts/{channel}/{playlist}/`
- **Summaries**: Saved to `summaries/{channel}/{playlist}/`
- **Algorithm Guides**: Saved alongside summaries with `_algorithm.md` suffix

### Infrastructure
- **Multiple Discovery Methods**: API, Playwright browser automation, or HTTP scraping
- **SSL Bypass**: Works in corporate environments with SSL inspection
- **Rate Limiting**: Built-in delays with adaptive slowdown
- **Resume Support**: Skip already extracted/summarized videos

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
│  │               AI Summarizer (Claude CLI)                 │   │
│  │  ┌─────────────────┐    ┌───────────────────────────┐   │   │
│  │  │ Video Summary   │    │ Algorithm/Indicator Guide │   │   │
│  │  └─────────────────┘    └───────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Output Manager                        │   │
│  │  transcripts/{channel}/{playlist}/                       │   │
│  │  summaries/{channel}/{playlist}/                         │   │
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

# Required for summarization: Claude CLI
npm install -g @anthropic-ai/claude-code
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
        "YOUTUBE_MCP_OUTPUT_DIR": "C:/path/to/youtube-mcp/transcripts",
        "YOUTUBE_MCP_LANGUAGE": "en",
        "YOUTUBE_MCP_RATE_LIMIT": "3"
      }
    }
  }
}
```

> **Note**: `YOUTUBE_API_KEY` is optional. Transcript extraction and summarization work without it. The API key is only needed for extended metadata tools (`get_video_info`, `get_channel_info`, `search_videos`).

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

## MCP Tools

### Summarization Tools

#### `summarize_video`

Summarize a single YouTube video with transcript and algorithm extraction. Automatically fetches video title and channel name for proper file naming (no API key required).

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | Yes | - | YouTube video URL |
| `style` | No | `trading-strategy` | Summary style: `bullet-points`, `paragraph`, `key-takeaways`, `trading-strategy` |
| `length` | No | `detailed` | Length: `short`, `medium`, `long`, `detailed` |
| `language` | No | `en` | Transcript language code |
| `custom_instructions` | No | - | Additional instructions for the summary |

**Output files:**
- `transcripts/{channel}/singles/{title}.md` - Full transcript
- `summaries/{channel}/singles/{title}_summary.md` - Video summary
- `summaries/{channel}/singles/{title}_algorithm.md` - Indicator building guide

#### `summarize_for_indicator`

Specialized summarization optimized for building trading indicators.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | Yes | - | YouTube video URL |
| `indicator_type` | No | - | Type: `SMC`, `ICT`, `price-action`, `support-resistance` |
| `language` | No | `en` | Transcript language code |

**Extracts:**
- Mathematical formulas and calculations
- Specific price levels, percentages, ratios
- Entry/exit conditions with precise rules
- Indicator parameters and settings
- Candlestick patterns and formations
- Timeframe recommendations

#### `summarize_playlist`

Batch summarize all videos in a playlist.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | Yes | - | YouTube playlist URL |
| `style` | No | `trading-strategy` | Summary style |
| `length` | No | `detailed` | Summary length |
| `language` | No | `en` | Transcript language code |
| `max_videos` | No | all | Maximum videos to process |
| `skip_existing` | No | `true` | Skip already summarized videos |

**Output structure:**
```
transcripts/{channel}/{playlist}/
├── 01_video_title.md
├── 02_video_title.md
└── ...

summaries/{channel}/{playlist}/
├── 01_video_title_summary.md
├── 01_video_title_algorithm.md
├── 02_video_title_summary.md
├── 02_video_title_algorithm.md
└── ...
```

### Discovery & Extraction Tools

#### `youtube` (Unified Tool)

Discover, explore, and extract content from any channel with a single input.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `input` | Yes | - | Channel handle (@name), URL, channel ID, playlist URL, or video URL |
| `action` | No | `discover` | `discover`, `p1`-`p99`, `v1`-`v99`, `extract_all`, `save_config` |
| `method` | No | `auto` | `auto`, `api`, `playwright`, `scraping` |
| `max_videos` | No | 50 | Max videos to discover |
| `language` | No | `en` | Transcript language |

#### `extract_transcript`

Extract transcript from a single YouTube video.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | Yes | - | YouTube video URL |
| `language` | No | `en` | Language code |
| `save_file` | No | `true` | Save to file |

#### `extract_playlist`

Extract transcripts from all videos in a playlist.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | No | - | YouTube playlist URL |
| `json_config` | No | - | Path to JSON config file |
| `skip_existing` | No | `true` | Skip already extracted |
| `retry_failed` | No | `false` | Only retry previously failed |

#### `list_playlist` / `check_transcript`

List videos in a playlist or check transcript availability.

### API Tools (Requires `YOUTUBE_API_KEY`)

- `get_video_info` - Video details (title, description, stats, etc.)
- `get_channel_info` - Channel info (subscribers, video count)
- `search_videos` - Search YouTube

> **Note**: Basic video metadata (title, channel name) for summarization is fetched via YouTube's oEmbed API and does NOT require an API key. The API tools above are for extended metadata only.

## Summary Styles

| Style | Best For | Output |
|-------|----------|--------|
| `bullet-points` | Quick reference | Hierarchical bullets with key points |
| `paragraph` | Reading | Flowing prose summary |
| `key-takeaways` | Action items | Numbered insights |
| `trading-strategy` | Indicators | Structured: entry/exit/risk/indicators/rules |

## Algorithm Guide Format

When using `trading-strategy` style, an algorithm guide is generated with:

```markdown
# Algorithm & Indicator Guide: Video Title

## Strategy Overview
Brief description...

## Entry Conditions (Indicator Logic)
```
// Entry conditions to implement:
// 1. Condition one
// 2. Condition two
```

## Exit Conditions
- Take profit rules
- Stop loss rules

## Risk Management Parameters
- Position sizing
- Risk per trade

## Indicators & Tools to Use
- List of indicators
- Timeframes

## Trading Rules (Implementation Checklist)
1. Rule one
2. Rule two

## Pine Script Template
```pine
//@version=6
indicator('Strategy Indicator', overlay=true)
// TODO: Implement conditions
```
```

## Output Structure

```
youtube-mcp/
├── transcripts/
│   ├── channel_name/
│   │   ├── playlist_name/
│   │   │   ├── _playlist_info.json
│   │   │   ├── _extraction_report.json
│   │   │   ├── 01_video_title.md
│   │   │   └── 02_video_title.md
│   │   └── singles/
│   │       └── video_title.md
│
├── summaries/
│   ├── channel_name/
│   │   ├── playlist_name/
│   │   │   ├── 01_video_title_summary.md
│   │   │   ├── 01_video_title_algorithm.md
│   │   │   ├── 02_video_title_summary.md
│   │   │   └── 02_video_title_algorithm.md
│   │   └── singles/
│   │       ├── video_title_summary.md
│   │       └── video_title_algorithm.md
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_MCP_OUTPUT_DIR` | `transcripts` | Output directory for transcripts |
| `YOUTUBE_MCP_LANGUAGE` | `en` | Default language |
| `YOUTUBE_MCP_RATE_LIMIT` | `3` | Seconds between requests |
| `YOUTUBE_API_KEY` | - | YouTube API key (optional, only needed for `get_video_info`, `get_channel_info`, `search_videos`) |

## Requirements

### For Basic Extraction
- Python 3.10+
- `mcp` >= 1.0.0
- `youtube-transcript-api` >= 0.6.0
- `requests` >= 2.31.0

### For Browser-Based Discovery
- `playwright` >= 1.40.0
- Chromium browser

### For AI Summarization
- **Claude CLI** - Install with: `npm install -g @anthropic-ai/claude-code`
- Must be logged in to Claude CLI (run `claude` once to authenticate)

## Error Handling

| Error | Action |
|-------|--------|
| `TranscriptsDisabled` | Skip video |
| `NoTranscriptFound` | Try other languages |
| `VideoUnavailable` | Skip video |
| `IpBlocked` | Stop, wait, retry later |
| `SSLError` | Auto-retry with bypass |
| `Claude CLI not found` | Install Claude CLI |

## Project Structure

```
youtube-mcp/
├── src/
│   ├── server.py        # MCP server implementation
│   ├── cli.py           # Command-line interface
│   ├── discovery.py     # Channel/playlist discovery
│   ├── transcript.py    # Transcript extraction
│   ├── playlist.py      # Playlist handling
│   ├── summarizer.py    # AI summarization (Claude CLI)
│   ├── url_parser.py    # URL parsing + oEmbed metadata fetching
│   ├── youtube_api.py   # YouTube API integration
│   └── output.py        # Output file management
├── transcripts/         # Default transcript output
├── summaries/           # Default summary output
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Examples

### Summarize a Trading Video
```
summarize_video https://youtube.com/watch?v=1F7rFzRSsqY
```

**Output files:**
```
transcripts/the_trading_geek/singles/How_to_Start_Day_Trading_in_2025_(Full_10-Hour_BEGINNER_Course).md
summaries/the_trading_geek/singles/How_to_Start_Day_Trading_in_2025_(Full_10-Hour_BEGINNER_Course)_summary.md
summaries/the_trading_geek/singles/How_to_Start_Day_Trading_in_2025_(Full_10-Hour_BEGINNER_Course)_algorithm.md
```

### Extract Trading Strategy for Indicator Building
```
summarize_for_indicator https://youtube.com/watch?v=VIDEO_ID indicator_type=SMC
```

### Batch Summarize a Trading Course Playlist
```
summarize_playlist https://youtube.com/playlist?list=PLAYLIST_ID
```

### Discover and Summarize Channel Content
```
youtube @TradingChannel action=discover
youtube @TradingChannel action=p1  # Extract first playlist
```

## License

MIT
