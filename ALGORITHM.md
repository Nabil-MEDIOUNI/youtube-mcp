# YouTube MCP Python - Algorithm Design

## Overview

A Python-based MCP server for extracting YouTube transcripts from videos, playlists, and channels with a single URL input.

---

## Research Findings

### Playwright MCP Capabilities (Scraping)

| Capability | Status | Notes |
|------------|--------|-------|
| Load playlist page | ✅ Works | Gets metadata + videos |
| Extract video IDs | ✅ Works | From href attributes |
| Extract titles | ✅ Works | From video-title elements |
| Infinite scroll | ✅ Works | Needs multiple scroll iterations |
| Channel info | ✅ Works | Name, handle, URL |
| Hidden videos | ⚠️ Limited | Only shows publicly available videos |

**Key Finding**: Playlist page showed 56 total videos but only 5 accessible (51 hidden/unavailable).

### youtube-transcript-api Capabilities

| Capability | Status | Notes |
|------------|--------|-------|
| Extract transcript | ✅ Works | Returns segments with timestamps |
| SSL bypass | ✅ Works | Required for corporate environments |
| English transcripts | ✅ Works | Primary language |
| Auto-generated captions | ✅ Works | Falls back automatically |
| Videos without captions | ❌ Fails | TranscriptsDisabled error |
| Rate limiting | ⚠️ Needed | 2-3 seconds between requests |
| IP blocking | ⚠️ Risk | After many rapid requests |

### URL Format Support

| Format | Example | Supported |
|--------|---------|-----------|
| Standard video | `youtube.com/watch?v=ID` | ✅ |
| Short URL | `youtu.be/ID` | ✅ |
| Video in playlist | `watch?v=ID&list=PLID` | ✅ |
| Playlist | `playlist?list=PLID` | ✅ |
| Channel handle | `youtube.com/@handle` | ✅ |
| Channel ID | `youtube.com/channel/UCID` | ✅ |
| Legacy channel | `youtube.com/c/name` | ✅ |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     YouTube MCP Python                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
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
│  │  transcripts/{channel_name}/                             │   │
│  │  ├── _playlist_info.json                                 │   │
│  │  ├── 01_video_title.md                                   │   │
│  │  ├── 02_video_title.md                                   │   │
│  │  └── _extraction_report.json                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## MCP Tools Design

### Tool 1: `extract_transcript`

**Purpose**: Extract transcript from a single YouTube video

**Input**:
```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "language": "en",
  "output_format": "markdown|json|text"
}
```

**Output**:
```json
{
  "success": true,
  "video_id": "VIDEO_ID",
  "title": "Video Title",
  "channel": "Channel Name",
  "transcript": "Full text...",
  "segments": [...],
  "output_file": "path/to/file.md"
}
```

### Tool 2: `extract_playlist`

**Purpose**: Extract transcripts from all videos in a playlist

**Input**:
```json
{
  "url": "https://www.youtube.com/playlist?list=PLAYLIST_ID",
  "language": "en",
  "skip_existing": true,
  "rate_limit_seconds": 3
}
```

**Output**:
```json
{
  "success": true,
  "playlist_name": "Playlist Name",
  "channel": "Channel Name",
  "total_videos": 56,
  "accessible_videos": 5,
  "extracted": 4,
  "failed": 1,
  "output_folder": "transcripts/channel_name/",
  "report": {...}
}
```

### Tool 3: `list_playlist_videos`

**Purpose**: List all videos in a playlist without extracting (for preview)

**Input**:
```json
{
  "url": "https://www.youtube.com/playlist?list=PLAYLIST_ID"
}
```

**Output**:
```json
{
  "playlist_name": "Boot Camp",
  "channel": "TJR",
  "total_videos": 56,
  "accessible_videos": 5,
  "videos": [
    {"index": 1, "id": "VIDEO_ID", "title": "Title"},
    ...
  ]
}
```

### Tool 4: `check_transcript_availability`

**Purpose**: Check if a video has transcripts available

**Input**:
```json
{
  "url": "https://www.youtube.com/watch?v=VIDEO_ID"
}
```

**Output**:
```json
{
  "available": true,
  "languages": ["en", "en-US", "auto"],
  "video_id": "VIDEO_ID"
}
```

---

## Algorithm Flowcharts

### Main Extraction Flow

```
START
  │
  ▼
┌─────────────────────┐
│ Parse YouTube URL   │
└─────────────────────┘
  │
  ▼
┌─────────────────────┐
│ Detect URL Type     │
│ (video/playlist/    │
│  channel)           │
└─────────────────────┘
  │
  ├──► video ──────────────────────────────────────┐
  │                                                 │
  ├──► playlist ─────────┐                          │
  │                      ▼                          │
  │              ┌───────────────────┐              │
  │              │ Try YouTube API   │              │
  │              │ (if key available)│              │
  │              └───────────────────┘              │
  │                      │                          │
  │                      ├── success ──► video list │
  │                      │                          │
  │                      ├── fail/no key            │
  │                      ▼                          │
  │              ┌───────────────────┐              │
  │              │ Playwright Scrape │              │
  │              │ (scroll + extract)│              │
  │              └───────────────────┘              │
  │                      │                          │
  │                      ▼                          │
  │              ┌───────────────────┐              │
  │              │ For each video:   │◄─────────────┘
  │              │ Extract transcript│
  │              └───────────────────┘
  │                      │
  │                      ▼
  │              ┌───────────────────┐
  │              │ Save to output    │
  │              │ folder structure  │
  │              └───────────────────┘
  │                      │
  └──► channel ──────────┘
          │
          ▼
  ┌───────────────────┐
  │ Scrape channel    │
  │ videos page       │
  └───────────────────┘
          │
          ▼
        END
```

### Rate Limiting Strategy

```
┌─────────────────────────────────────────────┐
│           Rate Limiting Algorithm            │
├─────────────────────────────────────────────┤
│                                             │
│  BASE_DELAY = 3 seconds                     │
│  ERROR_DELAY = 10 seconds                   │
│  MAX_CONSECUTIVE_ERRORS = 5                 │
│  BACKOFF_MULTIPLIER = 2                     │
│                                             │
│  for each video:                            │
│    try:                                     │
│      extract_transcript()                   │
│      consecutive_errors = 0                 │
│      sleep(BASE_DELAY)                      │
│    except IPBlocked:                        │
│      STOP immediately                       │
│      mark remaining as skipped              │
│    except TransientError:                   │
│      consecutive_errors++                   │
│      if consecutive_errors > MAX:           │
│        delay = ERROR_DELAY * BACKOFF        │
│      retry with exponential backoff         │
│    except PermanentError:                   │
│      log error, continue to next            │
│                                             │
└─────────────────────────────────────────────┘
```

---

## Limitations & Edge Cases

### Hard Limitations (Cannot Overcome)

| Limitation | Reason | Workaround |
|------------|--------|------------|
| Videos without captions | Creator disabled or never added | None - skip video |
| Private videos | Not accessible | None - skip video |
| Age-restricted videos | Requires login | Would need authentication |
| Region-locked videos | Geographic restriction | VPN required |
| Live streams (ongoing) | No transcript until ended | Wait for stream to end |
| IP blocking | Too many requests | Wait 1-24 hours, use VPN |

### Soft Limitations (Can Mitigate)

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Rate limiting | Slow extraction | Configurable delays, parallel with caution |
| SSL errors | Corporate environments | SSL bypass session |
| Playlist infinite scroll | Miss videos | Multiple scroll iterations |
| Auto-generated captions quality | Poor accuracy | Prefer manual captions when available |
| Large playlists (500+ videos) | Very slow, IP risk | Batch processing, resume support |

### Error Types & Handling

```python
ERRORS = {
    'TranscriptsDisabled': {
        'recoverable': False,
        'action': 'skip',
        'message': 'Video has no captions enabled'
    },
    'NoTranscriptFound': {
        'recoverable': False,
        'action': 'skip',
        'message': 'No transcript in requested language'
    },
    'VideoUnavailable': {
        'recoverable': False,
        'action': 'skip',
        'message': 'Video is private, deleted, or restricted'
    },
    'IpBlocked': {
        'recoverable': False,
        'action': 'stop_all',
        'message': 'IP blocked by YouTube - wait and retry later'
    },
    'SSLError': {
        'recoverable': True,
        'action': 'retry_with_bypass',
        'max_retries': 3
    },
    'NetworkError': {
        'recoverable': True,
        'action': 'retry_with_backoff',
        'max_retries': 3
    }
}
```

---

## Output Structure

### Folder Organization

```
transcripts/
├── tjr/                              # Channel folder (sanitized name)
│   ├── _channel_info.json            # Channel metadata
│   ├── _extraction_report.json       # Extraction results & errors
│   ├── boot-camp/                    # Playlist subfolder
│   │   ├── _playlist_info.json       # Playlist metadata
│   │   ├── 01_boot_camp_day_1.md     # Indexed video transcripts
│   │   ├── 02_boot_camp_day_2.md
│   │   └── ...
│   └── other-playlist/
│       └── ...
└── another-channel/
    └── ...
```

### Transcript File Format (Markdown)

```markdown
# Video Title

## Video Info
- **Channel**: Channel Name
- **Playlist**: Playlist Name
- **Index**: 1
- **Video ID**: VIDEO_ID
- **URL**: https://www.youtube.com/watch?v=VIDEO_ID
- **Duration**: 15:28
- **Extracted**: 2026-01-21 16:30:00

---

## Full Text

Full transcript text here, wrapped at 80 characters for readability.
This is the continuous text without timestamps for easy reading and
processing by AI tools.
```

### Report File Format (JSON)

```json
{
  "channel": "TJR",
  "channel_id": "tjr",
  "playlist": "Boot Camp",
  "playlist_id": "PLKE_22Jx497twaT62Qv9DAiagynP4dAYV",
  "extraction_started": "2026-01-21T16:00:00",
  "extraction_completed": "2026-01-21T16:30:00",
  "total_videos": 56,
  "accessible_videos": 5,
  "successful": [
    {"index": 1, "video_id": "ID", "title": "Title", "segments": 368}
  ],
  "failed": [
    {"index": 3, "video_id": "ID", "title": "Title", "error": "TranscriptsDisabled"}
  ],
  "skipped": [
    {"index": 4, "video_id": "ID", "title": "Title", "reason": "IP blocked during extraction"}
  ],
  "ip_blocked": false
}
```

---

## Implementation Options

### Option A: Pure Python MCP Server

**Pros**:
- Simple, self-contained
- Matches existing Python workflow
- Easy to debug and extend

**Cons**:
- Need to implement MCP protocol
- Less integration with existing TypeScript MCP

### Option B: Extend Existing TypeScript MCP

**Pros**:
- Already has MCP infrastructure
- Existing tools for video/playlist info
- Claude Desktop integration ready

**Cons**:
- Need to add Playwright integration
- TypeScript complexity
- SSL bypass more complex in Node.js

### Option C: Hybrid (Recommended)

**Architecture**:
1. **TypeScript MCP** for Claude integration & API calls
2. **Python subprocess** for transcript extraction with your existing code
3. **Playwright MCP** for scraping when needed

**Flow**:
```
Claude ──► YouTube MCP (TS) ──► Python extractor ──► Output
                │
                └──► Playwright MCP (for scraping)
```

---

## Recommended Implementation Steps

1. **Phase 1**: Create Python YouTube Extractor module
   - URL parser
   - Transcript extractor with SSL bypass
   - Playlist scraper using Playwright
   - Output manager

2. **Phase 2**: Create Python MCP server
   - Implement MCP protocol
   - Expose 4 tools (extract_transcript, extract_playlist, list_playlist, check_availability)
   - Add to Claude Desktop config

3. **Phase 3**: Integration
   - Connect with Playwright MCP for scraping fallback
   - Add resume/retry support for interrupted extractions
   - Add progress reporting

---

## Usage Examples (Target UX)

```
User: Extract transcripts from https://www.youtube.com/playlist?list=PLKE_22Jx497twaT62Qv9DAiagynP4dAYV

Claude: I'll extract transcripts from this playlist.

[Uses youtube_mcp.extract_playlist]

Extracted 4/5 accessible videos from "Boot Camp" by TJR:
- ✅ Boot Camp Day 39: Calculating Lot Size (368 segments)
- ✅ Boot Camp Day 47: Back Testing CPI (449 segments)
- ❌ Boot Camp Day 48: Live Daily Bias Analysis (no captions)
- ✅ Boot Camp Day 48 Pt. 2 (312 segments)
- ✅ Boot Camp Day 53: Daily Bias (287 segments)

Files saved to: transcripts/tjr/boot-camp/
```

```
User: Get transcript from https://youtu.be/KSiWKfPOlh4

Claude: [Uses youtube_mcp.extract_transcript]

Extracted transcript from "Boot Camp Day 39: Calculating Lot Size":
- Channel: TJR
- Duration: 15:28
- Segments: 368
- File: transcripts/tjr/boot_camp_day_39.md
```
