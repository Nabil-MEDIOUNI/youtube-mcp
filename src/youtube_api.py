"""
YouTube Data API Integration - Video details, search, and channel info.

Requires a YouTube Data API v3 key from Google Cloud Console.
Set the YOUTUBE_API_KEY environment variable or pass to constructor.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from requests.adapters import HTTPAdapter


@dataclass
class VideoDetails:
    """Detailed information about a YouTube video."""

    video_id: str
    title: str
    description: str
    channel_id: str
    channel_title: str
    published_at: str
    duration: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    tags: list[str] = field(default_factory=list)
    thumbnail_url: str = ""
    error: Optional[str] = None


@dataclass
class ChannelInfo:
    """Information about a YouTube channel."""

    channel_id: str
    title: str
    description: str
    custom_url: str = ""
    published_at: str = ""
    subscriber_count: int = 0
    video_count: int = 0
    view_count: int = 0
    thumbnail_url: str = ""
    uploads_playlist_id: str = ""
    error: Optional[str] = None


@dataclass
class SearchResult:
    """A single search result."""

    video_id: str
    title: str
    description: str
    channel_id: str
    channel_title: str
    published_at: str
    thumbnail_url: str = ""


@dataclass
class SearchResults:
    """Search results from YouTube."""

    query: str
    total_results: int = 0
    results: list[SearchResult] = field(default_factory=list)
    next_page_token: Optional[str] = None
    error: Optional[str] = None


class YouTubeAPI:
    """
    YouTube Data API v3 client.

    Provides access to video details, channel info, and search.
    Requires a YouTube API key.
    """

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(
        self,
        api_key: Optional[str] = None,
        ssl_bypass: bool = True,
    ):
        """
        Initialize YouTube API client.

        Args:
            api_key: YouTube Data API key. If not provided, reads from YOUTUBE_API_KEY env var.
            ssl_bypass: Bypass SSL certificate verification (for corporate environments)
        """
        self.api_key = api_key or os.environ.get("YOUTUBE_API_KEY")
        self.ssl_bypass = ssl_bypass
        self._session = None

        if not self.api_key:
            raise ValueError(
                "YouTube API key required. Set YOUTUBE_API_KEY environment variable "
                "or pass api_key parameter."
            )

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
        return self._session

    def _request(self, endpoint: str, params: dict) -> dict:
        """Make API request."""
        params["key"] = self.api_key
        url = f"{self.BASE_URL}/{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": str(e)}

    def get_video(self, video_id: str) -> VideoDetails:
        """
        Get detailed information about a video.

        Args:
            video_id: YouTube video ID

        Returns:
            VideoDetails with video information
        """
        params = {
            "part": "snippet,contentDetails,statistics",
            "id": video_id,
        }

        data = self._request("videos", params)

        if "error" in data:
            return VideoDetails(
                video_id=video_id,
                title="",
                description="",
                channel_id="",
                channel_title="",
                published_at="",
                error=data["error"],
            )

        items = data.get("items", [])
        if not items:
            return VideoDetails(
                video_id=video_id,
                title="",
                description="",
                channel_id="",
                channel_title="",
                published_at="",
                error="Video not found",
            )

        item = items[0]
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        stats = item.get("statistics", {})

        return VideoDetails(
            video_id=video_id,
            title=snippet.get("title", ""),
            description=snippet.get("description", ""),
            channel_id=snippet.get("channelId", ""),
            channel_title=snippet.get("channelTitle", ""),
            published_at=snippet.get("publishedAt", ""),
            duration=content.get("duration", ""),
            view_count=int(stats.get("viewCount", 0)),
            like_count=int(stats.get("likeCount", 0)),
            comment_count=int(stats.get("commentCount", 0)),
            tags=snippet.get("tags", []),
            thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
        )

    def get_channel(self, channel_id: str) -> ChannelInfo:
        """
        Get information about a channel.

        Args:
            channel_id: YouTube channel ID (starts with UC)

        Returns:
            ChannelInfo with channel information
        """
        params = {
            "part": "snippet,contentDetails,statistics",
            "id": channel_id,
        }

        data = self._request("channels", params)

        if "error" in data:
            return ChannelInfo(
                channel_id=channel_id,
                title="",
                description="",
                error=data["error"],
            )

        items = data.get("items", [])
        if not items:
            return ChannelInfo(
                channel_id=channel_id,
                title="",
                description="",
                error="Channel not found",
            )

        item = items[0]
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        stats = item.get("statistics", {})

        return ChannelInfo(
            channel_id=channel_id,
            title=snippet.get("title", ""),
            description=snippet.get("description", ""),
            custom_url=snippet.get("customUrl", ""),
            published_at=snippet.get("publishedAt", ""),
            subscriber_count=int(stats.get("subscriberCount", 0)),
            video_count=int(stats.get("videoCount", 0)),
            view_count=int(stats.get("viewCount", 0)),
            thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            uploads_playlist_id=content.get("relatedPlaylists", {}).get("uploads", ""),
        )

    def get_channel_by_handle(self, handle: str) -> ChannelInfo:
        """
        Get channel information by handle (e.g., @TJRTrades).

        Args:
            handle: YouTube channel handle (with or without @)

        Returns:
            ChannelInfo with channel information
        """
        if handle.startswith("@"):
            handle = handle[1:]

        params = {
            "part": "snippet,contentDetails,statistics",
            "forHandle": handle,
        }

        data = self._request("channels", params)

        if "error" in data:
            return ChannelInfo(
                channel_id="",
                title="",
                description="",
                error=data["error"],
            )

        items = data.get("items", [])
        if not items:
            return ChannelInfo(
                channel_id="",
                title="",
                description="",
                error=f"Channel not found for handle: @{handle}",
            )

        item = items[0]
        channel_id = item.get("id", "")
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        stats = item.get("statistics", {})

        return ChannelInfo(
            channel_id=channel_id,
            title=snippet.get("title", ""),
            description=snippet.get("description", ""),
            custom_url=snippet.get("customUrl", ""),
            published_at=snippet.get("publishedAt", ""),
            subscriber_count=int(stats.get("subscriberCount", 0)),
            video_count=int(stats.get("videoCount", 0)),
            view_count=int(stats.get("viewCount", 0)),
            thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            uploads_playlist_id=content.get("relatedPlaylists", {}).get("uploads", ""),
        )

    def search_videos(
        self,
        query: str,
        max_results: int = 10,
        page_token: Optional[str] = None,
    ) -> SearchResults:
        """
        Search for videos on YouTube.

        Args:
            query: Search query
            max_results: Maximum number of results (1-50)
            page_token: Page token for pagination

        Returns:
            SearchResults with matching videos
        """
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
        }

        if page_token:
            params["pageToken"] = page_token

        data = self._request("search", params)

        if "error" in data:
            return SearchResults(
                query=query,
                error=data["error"],
            )

        results = []
        for item in data.get("items", []):
            video_id = item.get("id", {}).get("videoId", "")
            snippet = item.get("snippet", {})

            if video_id:
                results.append(SearchResult(
                    video_id=video_id,
                    title=snippet.get("title", ""),
                    description=snippet.get("description", ""),
                    channel_id=snippet.get("channelId", ""),
                    channel_title=snippet.get("channelTitle", ""),
                    published_at=snippet.get("publishedAt", ""),
                    thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                ))

        page_info = data.get("pageInfo", {})

        return SearchResults(
            query=query,
            total_results=page_info.get("totalResults", len(results)),
            results=results,
            next_page_token=data.get("nextPageToken"),
        )

    def list_channel_videos(
        self,
        channel_id: str,
        max_results: int = 50,
        page_token: Optional[str] = None,
    ) -> SearchResults:
        """
        List videos from a channel.

        Args:
            channel_id: YouTube channel ID
            max_results: Maximum number of results (1-50)
            page_token: Page token for pagination

        Returns:
            SearchResults with channel videos
        """
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "type": "video",
            "order": "date",
            "maxResults": min(max_results, 50),
        }

        if page_token:
            params["pageToken"] = page_token

        data = self._request("search", params)

        if "error" in data:
            return SearchResults(
                query=f"channel:{channel_id}",
                error=data["error"],
            )

        results = []
        for item in data.get("items", []):
            video_id = item.get("id", {}).get("videoId", "")
            snippet = item.get("snippet", {})

            if video_id:
                results.append(SearchResult(
                    video_id=video_id,
                    title=snippet.get("title", ""),
                    description=snippet.get("description", ""),
                    channel_id=snippet.get("channelId", ""),
                    channel_title=snippet.get("channelTitle", ""),
                    published_at=snippet.get("publishedAt", ""),
                    thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                ))

        page_info = data.get("pageInfo", {})

        return SearchResults(
            query=f"channel:{channel_id}",
            total_results=page_info.get("totalResults", len(results)),
            results=results,
            next_page_token=data.get("nextPageToken"),
        )

    def get_playlist_items(
        self,
        playlist_id: str,
        max_results: int = 50,
        page_token: Optional[str] = None,
    ) -> list[dict]:
        """
        Get all videos in a playlist.

        Args:
            playlist_id: YouTube playlist ID
            max_results: Maximum number of results per page (1-50)
            page_token: Page token for pagination

        Returns:
            List of video dicts with id, title, description
        """
        all_items = []
        current_token = page_token

        while True:
            params = {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(max_results, 50),
            }

            if current_token:
                params["pageToken"] = current_token

            data = self._request("playlistItems", params)

            if "error" in data:
                break

            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                content = item.get("contentDetails", {})

                all_items.append({
                    "index": snippet.get("position", len(all_items)) + 1,
                    "id": content.get("videoId", ""),
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": snippet.get("channelTitle", ""),
                })

            current_token = data.get("nextPageToken")
            if not current_token:
                break

        return all_items
