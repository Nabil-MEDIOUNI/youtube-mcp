"""
YouTube Playlist Scraper - Extract video list from playlists without API key.

Note: HTTP-based scraping may be blocked by YouTube consent pages in some regions.
For reliable scraping, use the PlaywrightPlaylistScraper or provide a JSON config.
"""

import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from requests.adapters import HTTPAdapter


@dataclass
class PlaylistVideo:
    """A video in a playlist."""

    index: int
    video_id: str
    title: str
    duration: Optional[str] = None
    channel: Optional[str] = None


@dataclass
class PlaylistInfo:
    """Information about a YouTube playlist."""

    playlist_id: str
    title: str
    channel_name: str
    channel_handle: Optional[str] = None
    channel_url: Optional[str] = None
    video_count: int = 0
    videos: list[PlaylistVideo] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def accessible_count(self) -> int:
        return len(self.videos)


class PlaylistScraper:
    """
    Scrape YouTube playlists to extract video information without API key.

    Uses HTML parsing by default. Can optionally use Playwright for
    better reliability with dynamic content.
    """

    def __init__(self, ssl_bypass: bool = True):
        self.ssl_bypass = ssl_bypass
        self._session = None

    @property
    def session(self) -> requests.Session:
        """Lazy initialization of requests session."""
        if self._session is None:
            self._session = requests.Session()
            if self.ssl_bypass:
                self._session.verify = False
            adapter = HTTPAdapter(max_retries=3)
            self._session.mount('http://', adapter)
            self._session.mount('https://', adapter)
            self._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            })
            # Set consent cookie to bypass YouTube consent page
            self._session.cookies.set('CONSENT', 'YES+cb', domain='.youtube.com')
        return self._session

    def get_playlist_info(self, playlist_id: str) -> PlaylistInfo:
        """
        Get playlist information and video list.

        Args:
            playlist_id: YouTube playlist ID

        Returns:
            PlaylistInfo with videos list
        """
        url = f"https://www.youtube.com/playlist?list={playlist_id}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            html = response.text

            return self._parse_playlist_html(playlist_id, html)

        except requests.RequestException as e:
            return PlaylistInfo(
                playlist_id=playlist_id,
                title="",
                channel_name="",
                error=f"Failed to fetch playlist: {str(e)}",
            )

    def _parse_playlist_html(self, playlist_id: str, html: str) -> PlaylistInfo:
        """Parse playlist HTML to extract video information."""

        # Try to find the initial data JSON
        # YouTube embeds playlist data in a script tag
        json_match = re.search(
            r'var ytInitialData = ({.*?});',
            html,
            re.DOTALL
        )

        if not json_match:
            # Try alternative pattern
            json_match = re.search(
                r'window\["ytInitialData"\] = ({.*?});',
                html,
                re.DOTALL
            )

        if json_match:
            try:
                data = json.loads(json_match.group(1))
                return self._parse_initial_data(playlist_id, data)
            except json.JSONDecodeError:
                pass

        # Fallback: Parse HTML directly
        return self._parse_html_fallback(playlist_id, html)

    def _parse_initial_data(self, playlist_id: str, data: dict) -> PlaylistInfo:
        """Parse ytInitialData JSON structure."""

        videos = []
        title = ""
        channel_name = ""
        channel_handle = None
        channel_url = None
        video_count = 0

        try:
            # Navigate to playlist contents
            contents = (
                data.get('contents', {})
                .get('twoColumnBrowseResultsRenderer', {})
                .get('tabs', [{}])[0]
                .get('tabRenderer', {})
                .get('content', {})
                .get('sectionListRenderer', {})
                .get('contents', [{}])[0]
                .get('itemSectionRenderer', {})
                .get('contents', [{}])[0]
                .get('playlistVideoListRenderer', {})
            )

            # Get playlist header info
            header = (
                data.get('header', {})
                .get('playlistHeaderRenderer', {})
            )

            if header:
                title = header.get('title', {}).get('simpleText', '')

                # Get video count
                stats = header.get('stats', [])
                for stat in stats:
                    text = stat.get('simpleText', '') or stat.get('runs', [{}])[0].get('text', '')
                    if 'video' in text.lower():
                        count_match = re.search(r'(\d+)', text.replace(',', ''))
                        if count_match:
                            video_count = int(count_match.group(1))
                            break

                # Get channel info
                owner = header.get('ownerText', {}).get('runs', [{}])[0]
                channel_name = owner.get('text', '')
                nav_endpoint = owner.get('navigationEndpoint', {})
                browse_endpoint = nav_endpoint.get('browseEndpoint', {})
                channel_url = browse_endpoint.get('canonicalBaseUrl', '')
                if channel_url and channel_url.startswith('/@'):
                    channel_handle = channel_url[2:]

            # Parse video items
            video_items = contents.get('contents', [])
            for idx, item in enumerate(video_items, 1):
                video_renderer = item.get('playlistVideoRenderer', {})
                if not video_renderer:
                    continue

                video_id = video_renderer.get('videoId', '')
                if not video_id:
                    continue

                video_title = video_renderer.get('title', {}).get('runs', [{}])[0].get('text', '')
                duration = video_renderer.get('lengthText', {}).get('simpleText', '')

                # Get index from playlist position
                index_text = video_renderer.get('index', {}).get('simpleText', str(idx))
                try:
                    index = int(index_text)
                except ValueError:
                    index = idx

                videos.append(PlaylistVideo(
                    index=index,
                    video_id=video_id,
                    title=video_title,
                    duration=duration,
                    channel=channel_name,
                ))

        except (KeyError, IndexError, TypeError) as e:
            # Structure changed or parsing failed
            pass

        return PlaylistInfo(
            playlist_id=playlist_id,
            title=title,
            channel_name=channel_name,
            channel_handle=channel_handle,
            channel_url=channel_url,
            video_count=video_count or len(videos),
            videos=videos,
        )

    def _parse_html_fallback(self, playlist_id: str, html: str) -> PlaylistInfo:
        """Fallback HTML parsing when JSON extraction fails."""

        videos = []

        # Extract video IDs and titles using regex
        # Pattern for video links in playlist
        video_pattern = re.compile(
            r'/watch\?v=([a-zA-Z0-9_-]{11})&list=' + re.escape(playlist_id)
        )

        # Find all video IDs
        video_ids = list(dict.fromkeys(video_pattern.findall(html)))  # Unique, preserve order

        for idx, video_id in enumerate(video_ids, 1):
            videos.append(PlaylistVideo(
                index=idx,
                video_id=video_id,
                title="",  # Can't reliably extract from HTML fallback
            ))

        # Try to extract playlist title
        title_match = re.search(r'<title>([^<]+)</title>', html)
        title = ""
        if title_match:
            title = title_match.group(1).replace(' - YouTube', '').strip()

        return PlaylistInfo(
            playlist_id=playlist_id,
            title=title,
            channel_name="",
            video_count=len(videos),
            videos=videos,
        )

    def get_video_list(self, playlist_id: str) -> list[dict]:
        """
        Get simplified video list from playlist.

        Returns:
            List of dicts with 'index', 'id', 'title' keys
        """
        info = self.get_playlist_info(playlist_id)
        return [
            {
                "index": v.index,
                "id": v.video_id,
                "title": v.title,
            }
            for v in info.videos
        ]


class PlaywrightPlaylistScraper:
    """
    Scrape YouTube playlists using Playwright for better reliability.

    This handles infinite scroll and dynamic content loading.
    Requires playwright to be installed: pip install playwright
    """

    def __init__(self):
        self._browser = None
        self._playwright = None

    async def _ensure_browser(self):
        """Ensure browser is initialized."""
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)

    async def close(self):
        """Close browser and cleanup."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def get_playlist_info(self, playlist_id: str) -> PlaylistInfo:
        """
        Get playlist information using Playwright.

        Handles infinite scroll to load all videos.
        """
        await self._ensure_browser()

        page = await self._browser.new_page()
        url = f"https://www.youtube.com/playlist?list={playlist_id}"

        try:
            await page.goto(url, wait_until='networkidle')

            # Scroll to load all videos
            previous_count = 0
            scroll_attempts = 0
            max_attempts = 50

            while scroll_attempts < max_attempts:
                # Count current videos
                current_count = await page.evaluate('''
                    () => document.querySelectorAll('ytd-playlist-video-renderer').length
                ''')

                if current_count == previous_count:
                    break

                previous_count = current_count
                scroll_attempts += 1

                # Scroll down
                await page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
                await page.wait_for_timeout(1000)

            # Extract playlist data
            data = await page.evaluate('''
                () => {
                    const playlist = document.querySelector('yt-formatted-string.ytd-playlist-header-renderer')?.textContent?.trim() ||
                                    document.querySelector('h1 yt-formatted-string')?.textContent?.trim() ||
                                    document.title.replace(' - YouTube', '');

                    const channelEl = document.querySelector('a.yt-simple-endpoint[href*="/@"]');
                    const channel = channelEl?.textContent?.trim() || '';
                    const channelHandle = channelEl?.href?.match(/@([^/]+)/)?.[1] || '';

                    const videoRenderers = document.querySelectorAll('ytd-playlist-video-renderer');
                    const videos = [];

                    videoRenderers.forEach((renderer, i) => {
                        const link = renderer.querySelector('a#video-title');
                        const href = link?.href || '';
                        const videoId = href.match(/v=([a-zA-Z0-9_-]{11})/)?.[1];
                        const title = link?.textContent?.trim() || '';
                        const indexEl = renderer.querySelector('#index');
                        const index = parseInt(indexEl?.textContent?.trim()) || (i + 1);
                        const duration = renderer.querySelector('span.ytd-thumbnail-overlay-time-status-renderer')?.textContent?.trim() || '';

                        if (videoId) {
                            videos.push({
                                index,
                                video_id: videoId,
                                title,
                                duration
                            });
                        }
                    });

                    return {
                        title: playlist,
                        channel_name: channel,
                        channel_handle: channelHandle,
                        videos
                    };
                }
            ''')

            videos = [
                PlaylistVideo(
                    index=v['index'],
                    video_id=v['video_id'],
                    title=v['title'],
                    duration=v.get('duration'),
                )
                for v in data['videos']
            ]

            return PlaylistInfo(
                playlist_id=playlist_id,
                title=data['title'],
                channel_name=data['channel_name'],
                channel_handle=data.get('channel_handle'),
                video_count=len(videos),
                videos=videos,
            )

        finally:
            await page.close()


def load_playlist_from_json(json_path: Union[str, Path]) -> PlaylistInfo:
    """
    Load playlist information from a JSON config file.

    Expected JSON format:
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
            ...
        ]
    }

    Args:
        json_path: Path to the JSON config file

    Returns:
        PlaylistInfo with videos from the config
    """
    json_path = Path(json_path)

    if not json_path.exists():
        return PlaylistInfo(
            playlist_id="",
            title="",
            channel_name="",
            error=f"Config file not found: {json_path}",
        )

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return PlaylistInfo(
            playlist_id="",
            title="",
            channel_name="",
            error=f"Invalid JSON: {e}",
        )

    channel_info = data.get('channel', {})
    videos_data = data.get('videos', [])

    videos = [
        PlaylistVideo(
            index=v.get('index', i + 1),
            video_id=v.get('id', ''),
            title=v.get('title', ''),
        )
        for i, v in enumerate(videos_data)
        if v.get('id')
    ]

    # Extract channel handle from URL if available
    channel_url = channel_info.get('url', '')
    channel_handle = None
    if '/@' in channel_url:
        match = re.search(r'/@([^/]+)', channel_url)
        if match:
            channel_handle = match.group(1)

    return PlaylistInfo(
        playlist_id=channel_info.get('playlist_id', ''),
        title=channel_info.get('playlist_name', ''),
        channel_name=channel_info.get('name', ''),
        channel_handle=channel_handle,
        channel_url=channel_url,
        video_count=len(videos),
        videos=videos,
    )


def create_playlist_json(
    playlist_info: PlaylistInfo,
    output_path: Union[str, Path],
) -> Path:
    """
    Create a JSON config file from PlaylistInfo.

    Useful for saving scraped playlist data for later use.
    """
    output_path = Path(output_path)

    data = {
        "channel": {
            "id": playlist_info.channel_handle or "",
            "name": playlist_info.channel_name,
            "url": playlist_info.channel_url or "",
            "playlist_id": playlist_info.playlist_id,
            "playlist_name": playlist_info.title,
        },
        "videos": [
            {
                "index": v.index,
                "id": v.video_id,
                "title": v.title,
            }
            for v in playlist_info.videos
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_path
