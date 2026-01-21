"""
YouTube Transcript Extractor - Extract transcripts with SSL bypass and error handling.
"""

import time
from dataclasses import dataclass, field
from typing import Optional
import ssl
import urllib3

# Disable SSL warnings for corporate environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests
from requests.adapters import HTTPAdapter

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
    CouldNotRetrieveTranscript,
    FailedToCreateConsentCookie,
    YouTubeRequestFailed,
)

# Try to import additional error types if available
try:
    from youtube_transcript_api._errors import IpBlocked, RequestBlocked
    HAS_IP_BLOCK_ERRORS = True
except ImportError:
    HAS_IP_BLOCK_ERRORS = False


@dataclass
class TranscriptSegment:
    """A single segment of a transcript."""

    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class TranscriptResult:
    """Result of a transcript extraction."""

    success: bool
    video_id: str
    language: Optional[str] = None
    segments: list[TranscriptSegment] = field(default_factory=list)
    full_text: str = ""
    error: Optional[str] = None
    error_type: Optional[str] = None

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    @property
    def total_duration(self) -> float:
        if not self.segments:
            return 0.0
        return self.segments[-1].end


class TranscriptExtractor:
    """
    Extract transcripts from YouTube videos with SSL bypass and retry logic.
    """

    def __init__(
        self,
        default_language: str = "en",
        max_retries: int = 3,
        ssl_bypass: bool = True,
    ):
        self.default_language = default_language
        self.max_retries = max_retries
        self.ssl_bypass = ssl_bypass
        self._api = None

    @property
    def api(self) -> YouTubeTranscriptApi:
        """Lazy initialization of API with SSL bypass session."""
        if self._api is None:
            if self.ssl_bypass:
                session = self._create_ssl_bypass_session()
                self._api = YouTubeTranscriptApi(http_client=session)
            else:
                self._api = YouTubeTranscriptApi()
        return self._api

    def _create_ssl_bypass_session(self) -> requests.Session:
        """Create a requests session that bypasses SSL certificate verification."""
        session = requests.Session()
        session.verify = False

        adapter = HTTPAdapter(max_retries=3)
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        return session

    def extract(
        self,
        video_id: str,
        language: Optional[str] = None,
    ) -> TranscriptResult:
        """
        Extract transcript from a YouTube video.

        Args:
            video_id: YouTube video ID (11 characters)
            language: Preferred language code (e.g., 'en', 'es', 'fr')

        Returns:
            TranscriptResult with success status, segments, and full text
        """
        lang = language or self.default_language
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # Try with specified language first
                transcript = self.api.fetch(video_id, languages=[lang])
                segments = [
                    TranscriptSegment(
                        text=seg.text,
                        start=seg.start,
                        duration=seg.duration
                    )
                    for seg in transcript
                ]

                full_text = " ".join(seg.text.strip() for seg in segments)

                return TranscriptResult(
                    success=True,
                    video_id=video_id,
                    language=lang,
                    segments=segments,
                    full_text=full_text,
                )

            except TranscriptsDisabled:
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    error="Transcripts are disabled for this video",
                    error_type="TranscriptsDisabled",
                )

            except NoTranscriptFound:
                # Try without language filter
                try:
                    transcript = self.api.fetch(video_id)
                    segments = [
                        TranscriptSegment(
                            text=seg.text,
                            start=seg.start,
                            duration=seg.duration
                        )
                        for seg in transcript
                    ]

                    full_text = " ".join(seg.text.strip() for seg in segments)

                    return TranscriptResult(
                        success=True,
                        video_id=video_id,
                        language="auto",
                        segments=segments,
                        full_text=full_text,
                    )
                except Exception:
                    return TranscriptResult(
                        success=False,
                        video_id=video_id,
                        error=f"No transcript found for language '{lang}' or any other language",
                        error_type="NoTranscriptFound",
                    )

            except VideoUnavailable:
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    error="Video is unavailable (private, deleted, or region-locked)",
                    error_type="VideoUnavailable",
                )

            except (FailedToCreateConsentCookie, YouTubeRequestFailed) as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    error=f"YouTube request failed after {self.max_retries} attempts: {last_error}",
                    error_type="YouTubeRequestFailed",
                )

            except CouldNotRetrieveTranscript as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    error=f"Could not retrieve transcript after {self.max_retries} attempts: {last_error}",
                    error_type="CouldNotRetrieveTranscript",
                )

            except requests.exceptions.SSLError as e:
                last_error = "SSL Certificate Error"
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    error=f"SSL error after {self.max_retries} attempts",
                    error_type="SSLError",
                )

            except Exception as e:
                error_name = type(e).__name__
                error_str = str(e).upper()

                # Check for IP blocking errors
                if (HAS_IP_BLOCK_ERRORS and error_name in ('IpBlocked', 'RequestBlocked')) or \
                   "IP" in error_str or "BLOCKED" in error_str or "TOO MANY" in error_str:
                    return TranscriptResult(
                        success=False,
                        video_id=video_id,
                        error="IP blocked by YouTube - wait and retry later",
                        error_type="IpBlocked",
                    )

                last_error = str(e)
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue

                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    error=f"Error: {last_error}",
                    error_type=error_name,
                )

        return TranscriptResult(
            success=False,
            video_id=video_id,
            error=f"Unknown error after {self.max_retries} attempts",
            error_type="UnknownError",
        )

    def list_available_languages(self, video_id: str) -> list[dict]:
        """
        List available transcript languages for a video.

        Returns:
            List of dicts with 'language_code' and 'is_generated' keys
        """
        try:
            transcript_list = self.api.list(video_id)
            return [
                {
                    "language_code": t.language_code,
                    "language": t.language,
                    "is_generated": t.is_generated,
                }
                for t in transcript_list
            ]
        except Exception as e:
            return []

    def check_availability(self, video_id: str) -> dict:
        """
        Check if transcripts are available for a video.

        Returns:
            Dict with 'available', 'languages', and optional 'error' keys
        """
        try:
            languages = self.list_available_languages(video_id)
            return {
                "available": len(languages) > 0,
                "video_id": video_id,
                "languages": languages,
            }
        except TranscriptsDisabled:
            return {
                "available": False,
                "video_id": video_id,
                "languages": [],
                "error": "Transcripts disabled",
            }
        except VideoUnavailable:
            return {
                "available": False,
                "video_id": video_id,
                "languages": [],
                "error": "Video unavailable",
            }
        except Exception as e:
            return {
                "available": False,
                "video_id": video_id,
                "languages": [],
                "error": str(e),
            }
