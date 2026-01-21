"""
Test script for YouTube MCP components.
"""

import sys
sys.path.insert(0, 'src')

from youtube_mcp.url_parser import parse_youtube_url
from youtube_mcp.transcript import TranscriptExtractor
from youtube_mcp.playlist import PlaylistScraper


def test_url_parser():
    """Test URL parsing."""
    print("=" * 60)
    print("Testing URL Parser")
    print("=" * 60)

    test_urls = [
        "https://www.youtube.com/watch?v=KSiWKfPOlh4",
        "https://youtu.be/KSiWKfPOlh4",
        "https://www.youtube.com/playlist?list=PLKE_22Jx497twaT62Qv9DAiagynP4dAYV",
        "https://www.youtube.com/@TJRTrades",
    ]

    for url in test_urls:
        try:
            parsed = parse_youtube_url(url)
            print(f"\nURL: {url[:50]}...")
            print(f"  Type: {parsed.url_type}")
            if parsed.video_id:
                print(f"  Video ID: {parsed.video_id}")
            if parsed.playlist_id:
                print(f"  Playlist ID: {parsed.playlist_id}")
            if parsed.channel_handle:
                print(f"  Channel: @{parsed.channel_handle}")
        except ValueError as e:
            print(f"\nURL: {url}")
            print(f"  ERROR: {e}")

    print("\n[OK] URL Parser tests passed!")


def test_transcript_extractor():
    """Test transcript extraction."""
    print("\n" + "=" * 60)
    print("Testing Transcript Extractor")
    print("=" * 60)

    extractor = TranscriptExtractor(ssl_bypass=True)

    # Test with a known video
    video_id = "KSiWKfPOlh4"
    print(f"\nExtracting transcript for: {video_id}")

    result = extractor.extract(video_id)

    if result.success:
        print(f"  [OK] Success!")
        print(f"  Language: {result.language}")
        print(f"  Segments: {result.segment_count}")
        print(f"  Text length: {len(result.full_text)} chars")
        print(f"  Preview: {result.full_text[:100]}...")
    else:
        print(f"  [FAIL] Failed: {result.error}")

    # Test availability check
    print(f"\nChecking availability for: {video_id}")
    availability = extractor.check_availability(video_id)
    print(f"  Available: {availability['available']}")
    if availability.get('languages'):
        print(f"  Languages: {[l['language_code'] for l in availability['languages']]}")


def test_playlist_scraper():
    """Test playlist scraping."""
    print("\n" + "=" * 60)
    print("Testing Playlist Scraper")
    print("=" * 60)

    scraper = PlaylistScraper(ssl_bypass=True)

    playlist_id = "PLKE_22Jx497twaT62Qv9DAiagynP4dAYV"
    print(f"\nScraping playlist: {playlist_id}")

    playlist = scraper.get_playlist_info(playlist_id)

    if playlist.error:
        print(f"  [FAIL] Error: {playlist.error}")
    else:
        print(f"  [OK] Success!")
        print(f"  Title: {playlist.title}")
        print(f"  Channel: {playlist.channel_name}")
        print(f"  Total videos: {playlist.video_count}")
        print(f"  Accessible: {len(playlist.videos)}")
        if playlist.videos:
            print(f"  First video: {playlist.videos[0].title}")


def main():
    print("\n" + "#" * 60)
    print("# YouTube MCP Server - Component Tests")
    print("#" * 60)

    test_url_parser()
    test_transcript_extractor()
    test_playlist_scraper()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
