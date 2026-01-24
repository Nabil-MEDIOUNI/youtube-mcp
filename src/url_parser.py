"""
YouTube URL Parser - Parse any YouTube URL format and extract IDs.
"""

import re
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass
from typing import Optional


@dataclass
class YouTubeURL:
    """Parsed YouTube URL with extracted components."""

    original_url: str
    url_type: str  # 'video', 'playlist', 'channel', 'video_in_playlist'
    video_id: Optional[str] = None
    playlist_id: Optional[str] = None
    channel_id: Optional[str] = None
    channel_handle: Optional[str] = None

    @property
    def is_video(self) -> bool:
        return self.url_type in ('video', 'video_in_playlist')

    @property
    def is_playlist(self) -> bool:
        return self.url_type in ('playlist', 'video_in_playlist')

    @property
    def is_channel(self) -> bool:
        return self.url_type == 'channel'

    def get_video_url(self) -> Optional[str]:
        if self.video_id:
            return f"https://www.youtube.com/watch?v={self.video_id}"
        return None

    def get_playlist_url(self) -> Optional[str]:
        if self.playlist_id:
            return f"https://www.youtube.com/playlist?list={self.playlist_id}"
        return None

    def get_channel_url(self) -> Optional[str]:
        if self.channel_handle:
            return f"https://www.youtube.com/@{self.channel_handle}"
        elif self.channel_id:
            return f"https://www.youtube.com/channel/{self.channel_id}"
        return None


def parse_youtube_url(url: str) -> YouTubeURL:
    """
    Parse any YouTube URL and extract video_id, playlist_id, or channel info.

    Supported formats:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID
    - https://www.youtube.com/playlist?list=PLAYLIST_ID
    - https://www.youtube.com/@channel_handle
    - https://www.youtube.com/channel/CHANNEL_ID
    - https://www.youtube.com/c/channel_name

    Returns:
        YouTubeURL dataclass with parsed components

    Raises:
        ValueError: If URL is not a valid YouTube URL
    """
    url = url.strip()

    # Validate it's a YouTube URL
    if not any(domain in url.lower() for domain in ['youtube.com', 'youtu.be']):
        raise ValueError(f"Not a YouTube URL: {url}")

    video_id = None
    playlist_id = None
    channel_id = None
    channel_handle = None
    url_type = None

    # Handle youtu.be short URLs
    if 'youtu.be/' in url:
        match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url)
        if match:
            video_id = match.group(1)
            url_type = 'video'

            # Check for playlist in query params
            if '?' in url:
                query = parse_qs(urlparse(url).query)
                if 'list' in query:
                    playlist_id = query['list'][0]
                    url_type = 'video_in_playlist'

            return YouTubeURL(
                original_url=url,
                url_type=url_type,
                video_id=video_id,
                playlist_id=playlist_id
            )

    # Parse standard YouTube URLs
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    path = parsed.path

    # Extract video ID from query params
    if 'v' in query:
        video_id = query['v'][0]

    # Extract playlist ID from query params
    if 'list' in query:
        playlist_id = query['list'][0]

    # Determine URL type based on path
    if '/playlist' in path:
        url_type = 'playlist'
    elif '/watch' in path:
        url_type = 'video_in_playlist' if playlist_id else 'video'
    elif '/@' in path:
        match = re.search(r'/@([^/?]+)', path)
        if match:
            url_type = 'channel'
            channel_handle = match.group(1)
    elif '/channel/' in path:
        match = re.search(r'/channel/([^/?]+)', path)
        if match:
            url_type = 'channel'
            channel_id = match.group(1)
    elif '/c/' in path:
        match = re.search(r'/c/([^/?]+)', path)
        if match:
            url_type = 'channel'
            channel_handle = match.group(1)
    elif '/user/' in path:
        match = re.search(r'/user/([^/?]+)', path)
        if match:
            url_type = 'channel'
            channel_handle = match.group(1)

    # Fallback: if we have video_id but no type determined
    if video_id and not url_type:
        url_type = 'video_in_playlist' if playlist_id else 'video'

    if not url_type:
        raise ValueError(f"Could not determine URL type: {url}")

    return YouTubeURL(
        original_url=url,
        url_type=url_type,
        video_id=video_id,
        playlist_id=playlist_id,
        channel_id=channel_id,
        channel_handle=channel_handle
    )


def extract_video_id(url: str) -> Optional[str]:
    """Quick helper to extract just the video ID from any YouTube URL."""
    try:
        parsed = parse_youtube_url(url)
        return parsed.video_id
    except ValueError:
        return None


def extract_playlist_id(url: str) -> Optional[str]:
    """Quick helper to extract just the playlist ID from any YouTube URL."""
    try:
        parsed = parse_youtube_url(url)
        return parsed.playlist_id
    except ValueError:
        return None


def fetch_video_info(video_id: str) -> dict:
    """
    Fetch video title and channel name using YouTube oEmbed API.
    No API key required.

    Returns:
        dict with 'title', 'channel', 'success' keys
    """
    import requests

    # Use YouTube oEmbed API - reliable and doesn't require auth
    oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"

    try:
        response = requests.get(oembed_url, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()

        title = data.get('title', f"Video {video_id}")
        channel = data.get('author_name', 'unknown')

        return {
            'success': True,
            'video_id': video_id,
            'title': title,
            'channel': channel,
        }

    except Exception as e:
        return {
            'success': False,
            'video_id': video_id,
            'title': f"Video {video_id}",
            'channel': "unknown",
            'error': str(e),
        }
