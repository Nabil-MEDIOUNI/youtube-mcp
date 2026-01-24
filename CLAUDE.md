# YouTube MCP - Complete Reference

A Python MCP server for extracting YouTube transcripts and generating AI-powered summaries for trading indicator development.

## Architecture

```
URL Input → URL Parser → Transcript Extractor → AI Summarizer (Claude CLI) → Output Manager
                ↓
         oEmbed API (fetches title/channel automatically, no API key needed)
```

## MCP Tools Reference

### Summarization Tools

#### `summarize_video`
Extracts transcript, generates summary + algorithm guide.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | Yes | - | YouTube video URL |
| `style` | No | `trading-strategy` | `bullet-points`, `paragraph`, `key-takeaways`, `trading-strategy` |
| `length` | No | `detailed` | `short` (~200w), `medium` (~500w), `long` (~1000w), `detailed` (~2000w) |
| `language` | No | `en` | Transcript language code |
| `custom_instructions` | No | - | Additional prompt instructions |

**Example:** `summarize_video https://youtube.com/watch?v=1F7rFzRSsqY`

#### `summarize_for_indicator`
Specialized for Pine Script indicator building. Extracts formulas, price levels, entry/exit rules.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | Yes | - | YouTube video URL |
| `indicator_type` | No | - | `SMC`, `ICT`, `price-action`, `support-resistance` |
| `language` | No | `en` | Transcript language code |

#### `summarize_playlist`
Batch summarize all videos in a playlist.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `url` | Yes | - | YouTube playlist URL |
| `style` | No | `trading-strategy` | Summary style |
| `length` | No | `detailed` | Summary length |
| `max_videos` | No | all | Limit videos to process |
| `skip_existing` | No | `true` | Skip already summarized |

### Discovery & Extraction Tools

#### `youtube` (Unified Tool)
Discover channel content, extract playlists/videos.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `input` | Yes | - | `@handle`, channel URL, playlist URL, or video URL |
| `action` | No | `discover` | `discover`, `p1`-`p99`, `v1`-`v99`, `extract_all`, `save_config` |
| `method` | No | `auto` | `auto`, `api`, `playwright`, `scraping` |
| `max_videos` | No | 50 | Max videos to discover |

**Examples:**
- `youtube @TradingChannel` → Discover channel
- `youtube @TradingChannel action=p1` → Extract first playlist
- `youtube @TradingChannel action=v3` → Extract third video

#### `extract_transcript`
Extract transcript only (no summarization).

| Parameter | Required | Default |
|-----------|----------|---------|
| `url` | Yes | - |
| `language` | No | `en` |
| `save_file` | No | `true` |

#### `extract_playlist`
Batch extract transcripts from playlist.

| Parameter | Required | Default |
|-----------|----------|---------|
| `url` | No | - |
| `json_config` | No | - |
| `skip_existing` | No | `true` |
| `retry_failed` | No | `false` |

#### `list_playlist`
List videos in playlist without extracting.

#### `check_transcript`
Check if transcript is available and list languages.

### API Tools (Requires YOUTUBE_API_KEY)
- `get_video_info` - Extended video metadata
- `get_channel_info` - Channel stats
- `search_videos` - Search YouTube

> Note: Basic metadata (title, channel) for summarization uses oEmbed API - NO API key needed.

## Output Structure

```
youtube-mcp/
├── transcripts/
│   └── {channel_name}/
│       ├── singles/
│       │   └── {Video_Title}.md
│       └── {playlist_name}/
│           ├── _playlist_info.json
│           ├── _extraction_report.json
│           ├── 01_{video_title}.md
│           └── 02_{video_title}.md
│
├── summaries/
│   └── {channel_name}/
│       ├── singles/
│       │   ├── {Video_Title}_summary.md
│       │   └── {Video_Title}_algorithm.md
│       └── {playlist_name}/
│           ├── 01_{video_title}_summary.md
│           ├── 01_{video_title}_algorithm.md
│           └── ...
```

## Summary Styles

| Style | Best For | Output Structure |
|-------|----------|------------------|
| `bullet-points` | Quick reference | Hierarchical bullets |
| `paragraph` | Reading | Flowing prose |
| `key-takeaways` | Action items | Numbered insights |
| `trading-strategy` | Indicators | Entry/Exit/Risk/Indicators/Rules sections |

## Algorithm Guide Format (trading-strategy style)

Generated `_algorithm.md` files contain:
- Strategy Overview
- Entry Conditions (with pseudocode)
- Exit Conditions (TP/SL rules)
- Risk Management Parameters
- Indicators & Tools
- Trading Rules Checklist
- Pine Script Template stub

## Key Implementation Details

### Video Metadata Fetching
- Uses YouTube oEmbed API: `https://www.youtube.com/oembed?url=...&format=json`
- Returns `title` and `author_name` (channel)
- No API key required
- Implemented in `url_parser.py` → `fetch_video_info()`

### Transcript Extraction
- Uses `youtube-transcript-api` library
- Handles multiple languages, auto-generated captions
- SSL bypass for corporate environments
- Implemented in `transcript.py`

### Summarization
- Calls Claude CLI via subprocess: `claude -p - --output-format text`
- Prompt passed via stdin to avoid shell escaping issues
- 5-minute timeout for long videos
- Implemented in `summarizer.py`

### File Naming
- Titles sanitized: spaces → `_`, special chars removed
- Channel names lowercase with underscores
- Playlist videos prefixed with index: `01_`, `02_`, etc.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_MCP_OUTPUT_DIR` | `transcripts` | Base output directory |
| `YOUTUBE_MCP_LANGUAGE` | `en` | Default transcript language |
| `YOUTUBE_MCP_RATE_LIMIT` | `3` | Seconds between requests |
| `YOUTUBE_API_KEY` | - | Optional, for extended API tools only |

## Source Files

```
src/
├── server.py        # MCP server, tool handlers
├── summarizer.py    # Claude CLI integration
├── transcript.py    # youtube-transcript-api wrapper
├── playlist.py      # Playlist scraping
├── discovery.py     # Channel discovery
├── url_parser.py    # URL parsing + oEmbed metadata
├── output.py        # File saving, directory management
├── youtube_api.py   # YouTube Data API (optional)
└── cli.py           # Command-line interface
```

## Common Workflows

### Single Video Summary
```
summarize_video https://youtube.com/watch?v=VIDEO_ID
```

### Indicator-Focused Extraction
```
summarize_for_indicator https://youtube.com/watch?v=VIDEO_ID indicator_type=SMC
```

### Full Playlist Processing
```
summarize_playlist https://youtube.com/playlist?list=PLAYLIST_ID
```

### Channel Exploration
```
youtube @ChannelHandle                    # Discover
youtube @ChannelHandle action=p1          # First playlist
youtube @ChannelHandle action=save_config # Save for CLI
```

## Error Handling

| Error | Meaning | Action |
|-------|---------|--------|
| `TranscriptsDisabled` | Video has no captions | Skip |
| `NoTranscriptFound` | Language not available | Try other language |
| `VideoUnavailable` | Private/deleted | Skip |
| `IpBlocked` | Rate limited by YouTube | Wait and retry |
| `Claude CLI not found` | CLI not installed | Run `npm install -g @anthropic-ai/claude-code` |

## Dependencies

**Required:**
- Python 3.10+
- `mcp`, `youtube-transcript-api`, `requests`
- Claude CLI (`npm install -g @anthropic-ai/claude-code`)

**Optional:**
- `playwright` (browser-based discovery)
- `YOUTUBE_API_KEY` (extended metadata)
