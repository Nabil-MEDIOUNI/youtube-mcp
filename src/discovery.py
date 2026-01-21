"""
YouTube Discovery - Auto-discover channel content, playlists, and videos.

Supports multiple methods:
- playwright: Browser automation (most reliable, no API key)
- api: YouTube Data API (fast, requires API key)
- scraping: HTTP scraping (fastest, may be blocked)
"""

import re
import json
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from requests.adapters import HTTPAdapter

from url_parser import parse_youtube_url, YouTubeURL


DiscoveryMethod = Literal["playwright", "api", "scraping", "auto"]


@dataclass
class VideoItem:
    """A discovered video."""
    video_id: str
    title: str
    duration: Optional[str] = None
    view_count: Optional[int] = None
    published_at: Optional[str] = None


@dataclass
class PlaylistItem:
    """A discovered playlist."""
    playlist_id: str
    title: str
    video_count: int = 0
    thumbnail_url: Optional[str] = None


@dataclass
class ChannelDiscovery:
    """Complete discovery results for a channel."""

    # Channel info
    channel_id: str = ""
    channel_handle: str = ""
    channel_name: str = ""
    channel_url: str = ""
    subscriber_count: int = 0
    video_count: int = 0

    # Discovered content
    playlists: list[PlaylistItem] = field(default_factory=list)
    videos: list[VideoItem] = field(default_factory=list)

    # Metadata
    method_used: str = ""
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "channel": {
                "id": self.channel_id,
                "handle": self.channel_handle,
                "name": self.channel_name,
                "url": self.channel_url,
                "subscribers": self.subscriber_count,
                "video_count": self.video_count,
            },
            "playlists": [
                {"id": p.playlist_id, "title": p.title, "videos": p.video_count}
                for p in self.playlists
            ],
            "videos": [
                {"id": v.video_id, "title": v.title, "duration": v.duration}
                for v in self.videos
            ],
            "method": self.method_used,
            "error": self.error,
        }

    def get_shortcuts(self) -> dict:
        """Generate shortcuts for all discovered content."""
        shortcuts = {
            "channel": f"@{self.channel_handle}" if self.channel_handle else self.channel_id,
            "playlists": {},
            "videos": {},
            "actions": {
                "extract_all": f"Extract all {len(self.videos)} videos",
                "extract_playlist": "Extract specific playlist by number",
                "list_playlists": f"List all {len(self.playlists)} playlists",
                "list_videos": f"List all {len(self.videos)} videos",
                "save_config": "Save as JSON config for later use",
            }
        }

        # Playlist shortcuts
        for i, p in enumerate(self.playlists, 1):
            shortcuts["playlists"][f"p{i}"] = {
                "id": p.playlist_id,
                "title": p.title,
                "videos": p.video_count,
                "command": f"extract_playlist:{p.playlist_id}",
            }

        # Video shortcuts (first 20)
        for i, v in enumerate(self.videos[:20], 1):
            shortcuts["videos"][f"v{i}"] = {
                "id": v.video_id,
                "title": v.title,
                "command": f"extract_transcript:{v.video_id}",
            }

        return shortcuts


class ChannelDiscoverer:
    """
    Discover all content from a YouTube channel.

    Supports multiple methods:
    - playwright: Uses browser automation (most reliable)
    - api: Uses YouTube Data API (requires key)
    - scraping: Uses HTTP requests (may be blocked)
    - auto: Tries methods in order until one works
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        ssl_bypass: bool = True,
    ):
        self.api_key = api_key
        self.ssl_bypass = ssl_bypass
        self._session = None

    @property
    def session(self) -> requests.Session:
        """Lazy session initialization."""
        if self._session is None:
            self._session = requests.Session()
            if self.ssl_bypass:
                self._session.verify = False
            self._session.mount('http://', HTTPAdapter(max_retries=3))
            self._session.mount('https://', HTTPAdapter(max_retries=3))
            self._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            self._session.cookies.set('CONSENT', 'YES+1', domain='.youtube.com')
        return self._session

    async def discover(
        self,
        input_str: str,
        method: DiscoveryMethod = "auto",
        max_videos: int = 50,
        max_playlists: int = 20,
    ) -> ChannelDiscovery:
        """
        Discover channel content from any YouTube input.

        Args:
            input_str: Channel handle (@name), URL, or channel ID
            method: Discovery method to use
            max_videos: Maximum videos to fetch
            max_playlists: Maximum playlists to fetch

        Returns:
            ChannelDiscovery with all found content
        """
        # Normalize input
        channel_handle = None
        channel_id = None

        # Check if it's a handle
        if input_str.startswith("@"):
            channel_handle = input_str[1:]
        elif input_str.startswith("UC"):
            channel_id = input_str
        else:
            # Try to parse as URL
            try:
                parsed = parse_youtube_url(input_str)
                channel_handle = parsed.channel_handle
                channel_id = parsed.channel_id
            except ValueError:
                # Assume it's a handle without @
                channel_handle = input_str

        if not channel_handle and not channel_id:
            return ChannelDiscovery(error="Could not determine channel from input")

        # Try methods based on selection
        if method == "auto":
            # Try API first if key available, then playwright, then scraping
            if self.api_key:
                result = await self._discover_via_api(channel_handle, channel_id, max_videos, max_playlists)
                if not result.error:
                    return result

            # Try playwright
            result = await self._discover_via_playwright(channel_handle, channel_id, max_videos, max_playlists)
            if not result.error:
                return result

            # Fall back to scraping
            return await self._discover_via_scraping(channel_handle, channel_id, max_videos, max_playlists)

        elif method == "api":
            if not self.api_key:
                return ChannelDiscovery(error="API method requires YOUTUBE_API_KEY")
            return await self._discover_via_api(channel_handle, channel_id, max_videos, max_playlists)

        elif method == "playwright":
            return await self._discover_via_playwright(channel_handle, channel_id, max_videos, max_playlists)

        elif method == "scraping":
            return await self._discover_via_scraping(channel_handle, channel_id, max_videos, max_playlists)

        return ChannelDiscovery(error=f"Unknown method: {method}")

    async def _discover_via_api(
        self,
        handle: Optional[str],
        channel_id: Optional[str],
        max_videos: int,
        max_playlists: int,
    ) -> ChannelDiscovery:
        """Discover using YouTube Data API."""
        result = ChannelDiscovery(method_used="api")

        try:
            # Get channel info
            if handle:
                url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics,contentDetails&forHandle={handle}&key={self.api_key}"
            else:
                url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics,contentDetails&id={channel_id}&key={self.api_key}"

            resp = self.session.get(url, timeout=30)
            data = resp.json()

            if "error" in data:
                result.error = data["error"].get("message", "API error")
                return result

            items = data.get("items", [])
            if not items:
                result.error = "Channel not found"
                return result

            channel = items[0]
            snippet = channel.get("snippet", {})
            stats = channel.get("statistics", {})
            content = channel.get("contentDetails", {})

            result.channel_id = channel.get("id", "")
            result.channel_name = snippet.get("title", "")
            result.channel_handle = snippet.get("customUrl", "").lstrip("@")
            result.channel_url = f"https://www.youtube.com/@{result.channel_handle}" if result.channel_handle else ""
            result.subscriber_count = int(stats.get("subscriberCount", 0))
            result.video_count = int(stats.get("videoCount", 0))

            uploads_playlist = content.get("relatedPlaylists", {}).get("uploads", "")

            # Get playlists
            playlists_url = f"https://www.googleapis.com/youtube/v3/playlists?part=snippet,contentDetails&channelId={result.channel_id}&maxResults={max_playlists}&key={self.api_key}"
            playlists_resp = self.session.get(playlists_url, timeout=30)
            playlists_data = playlists_resp.json()

            for item in playlists_data.get("items", []):
                result.playlists.append(PlaylistItem(
                    playlist_id=item.get("id", ""),
                    title=item.get("snippet", {}).get("title", ""),
                    video_count=item.get("contentDetails", {}).get("itemCount", 0),
                ))

            # Get recent videos from uploads playlist
            if uploads_playlist:
                videos_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,contentDetails&playlistId={uploads_playlist}&maxResults={max_videos}&key={self.api_key}"
                videos_resp = self.session.get(videos_url, timeout=30)
                videos_data = videos_resp.json()

                for item in videos_data.get("items", []):
                    snippet = item.get("snippet", {})
                    result.videos.append(VideoItem(
                        video_id=item.get("contentDetails", {}).get("videoId", ""),
                        title=snippet.get("title", ""),
                        published_at=snippet.get("publishedAt", ""),
                    ))

            return result

        except Exception as e:
            result.error = str(e)
            return result

    async def _discover_via_playwright(
        self,
        handle: Optional[str],
        channel_id: Optional[str],
        max_videos: int,
        max_playlists: int,
    ) -> ChannelDiscovery:
        """Discover using Playwright browser automation."""
        result = ChannelDiscovery(method_used="playwright")

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            result.error = "Playwright not installed. Run: pip install playwright && playwright install chromium"
            return result

        channel_url = f"https://www.youtube.com/@{handle}" if handle else f"https://www.youtube.com/channel/{channel_id}"

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                # Get channel page
                await page.goto(channel_url, wait_until='networkidle')
                await page.wait_for_timeout(2000)

                # Extract channel info
                channel_data = await page.evaluate('''
                    () => {
                        const name = document.querySelector('yt-formatted-string#text.ytd-channel-name')?.textContent?.trim() ||
                                    document.querySelector('#channel-name')?.textContent?.trim() || '';
                        const subsText = document.querySelector('#subscriber-count')?.textContent?.trim() || '';
                        const handle = window.location.pathname.replace('/', '');

                        return { name, subsText, handle };
                    }
                ''')

                result.channel_name = channel_data.get('name', '')
                result.channel_handle = channel_data.get('handle', '').lstrip('@')
                result.channel_url = channel_url

                # Parse subscriber count
                subs_text = channel_data.get('subsText', '')
                if 'M' in subs_text:
                    result.subscriber_count = int(float(re.sub(r'[^\d.]', '', subs_text)) * 1_000_000)
                elif 'K' in subs_text:
                    result.subscriber_count = int(float(re.sub(r'[^\d.]', '', subs_text)) * 1_000)

                # Go to playlists tab
                await page.goto(f"{channel_url}/playlists", wait_until='networkidle')
                await page.wait_for_timeout(2000)

                # Extract playlists
                playlists_data = await page.evaluate('''
                    () => {
                        const playlists = [];
                        const items = document.querySelectorAll('ytd-grid-playlist-renderer, ytd-playlist-renderer');
                        items.forEach(item => {
                            const link = item.querySelector('a#video-title, a.ytd-playlist-renderer');
                            const href = link?.href || '';
                            const match = href.match(/list=([^&]+)/);
                            if (match) {
                                const title = link?.textContent?.trim() || '';
                                const countEl = item.querySelector('#video-count-text, .ytd-playlist-renderer #overlays');
                                const countText = countEl?.textContent?.trim() || '0';
                                const count = parseInt(countText.replace(/[^\d]/g, '')) || 0;
                                playlists.push({ id: match[1], title, count });
                            }
                        });
                        return playlists;
                    }
                ''')

                for p in playlists_data[:max_playlists]:
                    result.playlists.append(PlaylistItem(
                        playlist_id=p.get('id', ''),
                        title=p.get('title', ''),
                        video_count=p.get('count', 0),
                    ))

                # Go to videos tab
                await page.goto(f"{channel_url}/videos", wait_until='networkidle')
                await page.wait_for_timeout(2000)

                # Scroll to load more videos
                for _ in range(3):
                    await page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
                    await page.wait_for_timeout(1000)

                # Extract videos
                videos_data = await page.evaluate('''
                    () => {
                        const videos = [];
                        const items = document.querySelectorAll('ytd-rich-item-renderer, ytd-grid-video-renderer');
                        items.forEach(item => {
                            const link = item.querySelector('a#video-title-link, a#video-title');
                            const href = link?.href || '';
                            const match = href.match(/v=([^&]+)/);
                            if (match) {
                                const title = link?.textContent?.trim() || '';
                                const duration = item.querySelector('span.ytd-thumbnail-overlay-time-status-renderer')?.textContent?.trim() || '';
                                videos.push({ id: match[1], title, duration });
                            }
                        });
                        return videos;
                    }
                ''')

                for v in videos_data[:max_videos]:
                    result.videos.append(VideoItem(
                        video_id=v.get('id', ''),
                        title=v.get('title', ''),
                        duration=v.get('duration', ''),
                    ))

                result.video_count = len(result.videos)

                await browser.close()

            return result

        except Exception as e:
            result.error = str(e)
            return result

    async def _discover_via_scraping(
        self,
        handle: Optional[str],
        channel_id: Optional[str],
        max_videos: int,
        max_playlists: int,
    ) -> ChannelDiscovery:
        """Discover using HTTP scraping (may be blocked)."""
        result = ChannelDiscovery(method_used="scraping")

        channel_url = f"https://www.youtube.com/@{handle}" if handle else f"https://www.youtube.com/channel/{channel_id}"

        try:
            resp = self.session.get(channel_url, timeout=30)
            html = resp.text

            # Check for consent page
            if "Before you continue" in html or "consent" in html.lower():
                result.error = "Blocked by consent page. Use 'playwright' or 'api' method instead."
                return result

            # Try to find ytInitialData
            match = re.search(r'var ytInitialData = ({.*?});', html, re.DOTALL)
            if not match:
                result.error = "Could not parse page data. Use 'playwright' or 'api' method."
                return result

            data = json.loads(match.group(1))

            # Extract channel metadata
            header = data.get('header', {}).get('c4TabbedHeaderRenderer', {})
            result.channel_name = header.get('title', '')
            result.channel_id = header.get('channelId', '')
            result.channel_handle = handle or ''
            result.channel_url = channel_url

            # Extract subscriber count
            subs_text = header.get('subscriberCountText', {}).get('simpleText', '')
            if 'M' in subs_text:
                result.subscriber_count = int(float(re.sub(r'[^\d.]', '', subs_text)) * 1_000_000)
            elif 'K' in subs_text:
                result.subscriber_count = int(float(re.sub(r'[^\d.]', '', subs_text)) * 1_000)

            result.error = "Scraping limited. For full results, use 'playwright' or 'api' method."
            return result

        except Exception as e:
            result.error = str(e)
            return result


def create_config_from_discovery(
    discovery: ChannelDiscovery,
    playlist_id: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> dict:
    """
    Create a JSON config from discovery results.

    Args:
        discovery: ChannelDiscovery results
        playlist_id: Specific playlist to include (or None for all videos)
        output_path: Optional path to save config

    Returns:
        Config dict
    """
    config = {
        "channel": {
            "id": discovery.channel_handle or discovery.channel_id,
            "name": discovery.channel_name,
            "url": discovery.channel_url,
        },
        "videos": []
    }

    if playlist_id:
        # Find the playlist
        playlist = next((p for p in discovery.playlists if p.playlist_id == playlist_id), None)
        if playlist:
            config["channel"]["playlist_id"] = playlist_id
            config["channel"]["playlist_name"] = playlist.title

    # Add videos
    for i, v in enumerate(discovery.videos, 1):
        config["videos"].append({
            "index": i,
            "id": v.video_id,
            "title": v.title,
        })

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    return config
