"""
YouTube MCP CLI - Command-line interface for transcript extraction.

Usage:
    python -m youtube_mcp.cli                           # List available configs
    python -m youtube_mcp.cli <config_name>             # Extract from config
    python -m youtube_mcp.cli <config_name> --retry     # Retry failed only
    python -m youtube_mcp.cli --url <playlist_url>      # Extract from URL
    python -m youtube_mcp.cli --video <video_url>       # Single video
    python -m youtube_mcp.cli --all                     # Extract all configs

    # Unified YouTube Command
    python -m youtube_mcp.cli youtube @TJRTrades                    # Discover channel
    python -m youtube_mcp.cli youtube @TJRTrades --action p1        # Extract playlist 1
    python -m youtube_mcp.cli youtube @TJRTrades --action v1        # Extract video 1
    python -m youtube_mcp.cli youtube @TJRTrades --method playwright # Use Playwright
    python -m youtube_mcp.cli youtube @TJRTrades --action save      # Save config
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime

from url_parser import parse_youtube_url
from transcript import TranscriptExtractor
from playlist import PlaylistScraper, load_playlist_from_json
from output import OutputManager, ExtractionReport, ExtractionResult, sanitize_folder_name
from discovery import ChannelDiscoverer, create_config_from_discovery


# Default configuration
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "transcripts"
DEFAULT_CONFIGS_DIR = Path(__file__).parent.parent.parent / "tools" / "channels"
DEFAULT_LANGUAGE = "en"
DEFAULT_RATE_LIMIT = 3.0
ERROR_RATE_LIMIT = 10.0


class CLI:
    """Command-line interface for YouTube transcript extraction."""

    def __init__(
        self,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        configs_dir: Path = DEFAULT_CONFIGS_DIR,
        language: str = DEFAULT_LANGUAGE,
        rate_limit: float = DEFAULT_RATE_LIMIT,
    ):
        self.output_dir = Path(output_dir)
        self.configs_dir = Path(configs_dir)
        self.language = language
        self.rate_limit = rate_limit

        self.extractor = TranscriptExtractor(
            default_language=language,
            ssl_bypass=True,
        )
        self.scraper = PlaylistScraper(ssl_bypass=True)
        self.output_manager = OutputManager(base_dir=output_dir)

    def get_available_configs(self) -> dict[str, Path]:
        """Get all available channel configs."""
        configs = {}
        if not self.configs_dir.exists():
            return configs

        for json_file in self.configs_dir.glob("*.json"):
            try:
                playlist = load_playlist_from_json(json_file)
                if not playlist.error:
                    config_id = json_file.stem
                    configs[config_id] = json_file
            except Exception:
                continue

        return configs

    def list_configs(self):
        """Display available configurations."""
        configs = self.get_available_configs()

        print("=" * 60)
        print("Available Configurations")
        print("=" * 60)
        print()

        if not configs:
            print("No configurations found.")
            print()
            print(f"Add JSON config files to: {self.configs_dir}")
            print()
            print("Format:")
            print('  {"channel": {"name": "...", "playlist_name": "..."},')
            print('   "videos": [{"index": 1, "id": "VIDEO_ID", "title": "..."}]}')
            return

        for config_id, config_path in configs.items():
            playlist = load_playlist_from_json(config_path)
            print(f"  {config_id}")
            print(f"    Channel: {playlist.channel_name}")
            print(f"    Playlist: {playlist.title}")
            print(f"    Videos: {len(playlist.videos)}")
            print()

        print("-" * 60)
        print("Usage:")
        print(f"  python -m youtube_mcp.cli <config_id>           # Extract config")
        print(f"  python -m youtube_mcp.cli <config_id> --retry   # Retry failed only")
        print(f"  python -m youtube_mcp.cli --all                 # Extract all configs")
        print(f"  python -m youtube_mcp.cli --video <url>         # Single video")
        print()

    def extract_video(self, url: str) -> bool:
        """Extract transcript from a single video."""
        try:
            parsed = parse_youtube_url(url)
        except ValueError as e:
            print(f"Invalid URL: {e}")
            return False

        if not parsed.video_id:
            print("URL does not contain a video ID")
            return False

        print(f"Extracting transcript for: {parsed.video_id}")
        result = self.extractor.extract(parsed.video_id, self.language)

        if result.success:
            # Save to singles folder
            output_dir = self.output_manager.get_channel_dir("singles")
            filepath = self.output_manager.save_transcript_markdown(
                transcript=result,
                title=f"Video_{result.video_id}",
                channel_name="singles",
                output_dir=output_dir,
                video_url=url,
            )
            print(f"[OK] Saved to: {filepath}")
            print(f"     Segments: {result.segment_count}")
            print(f"     Length: {len(result.full_text)} characters")
            return True
        else:
            print(f"[FAIL] {result.error}")
            return False

    def extract_config(self, config_id: str, retry_only: bool = False) -> dict:
        """Extract transcripts from a configuration."""
        configs = self.get_available_configs()

        if config_id not in configs:
            print(f"Config not found: {config_id}")
            print()
            print("Available configs:")
            for cid in configs:
                print(f"  - {cid}")
            return {"successful": [], "failed": [], "skipped": []}

        config_path = configs[config_id]
        playlist = load_playlist_from_json(config_path)

        if playlist.error:
            print(f"Error loading config: {playlist.error}")
            return {"successful": [], "failed": [], "skipped": []}

        return self.extract_playlist(playlist, retry_only=retry_only)

    def extract_playlist(self, playlist, retry_only: bool = False) -> dict:
        """Extract transcripts from a playlist."""
        channel_name = playlist.channel_name or "unknown"
        playlist_name = playlist.title or "untitled"

        print("=" * 60)
        print(f"Extracting: {playlist_name}")
        print(f"Channel: {channel_name}")
        print("=" * 60)

        # Setup output directory
        output_dir = self.output_manager.get_playlist_dir(channel_name, playlist_name)
        print(f"Output: {output_dir}")
        print()

        # Get videos to process
        videos = list(playlist.videos)

        if retry_only:
            retry_videos = self.output_manager.get_retry_videos(
                output_dir,
                [{"video_id": v.video_id} for v in videos]
            )
            if not retry_videos:
                print("No failed videos to retry.")
                return {"successful": [], "failed": [], "skipped": []}

            retry_ids = {v.get('video_id') for v in retry_videos}
            videos = [v for v in videos if v.video_id in retry_ids]
            print(f"Retry mode: {len(videos)} failed videos to process")
        else:
            # Skip already extracted
            extracted_ids = self.output_manager.get_extracted_video_ids(output_dir)
            original_count = len(videos)
            videos = [v for v in videos if v.video_id not in extracted_ids]
            if len(videos) < original_count:
                print(f"Skipping {original_count - len(videos)} already extracted videos")

        print(f"Videos to process: {len(videos)}")
        print()

        # Save playlist info
        self.output_manager.save_playlist_info(playlist, output_dir)

        # Create report
        report = ExtractionReport(
            channel=channel_name,
            channel_id=sanitize_folder_name(channel_name),
            playlist=playlist.title,
            playlist_id=playlist.playlist_id,
            extraction_started=datetime.now().isoformat(),
            total_videos=playlist.video_count,
            accessible_videos=len(playlist.videos),
        )

        # Extract each video
        consecutive_failures = 0
        ip_blocked = False

        for i, video in enumerate(videos, 1):
            if ip_blocked:
                report.add_skipped(ExtractionResult(
                    index=video.index,
                    video_id=video.video_id,
                    title=video.title,
                    success=False,
                    error="Skipped due to IP block",
                ))
                continue

            print(f"[{i:2d}/{len(videos)}] {video.title}")
            print(f"         ID: {video.video_id}")

            result = self.extractor.extract(video.video_id, self.language)

            if result.success:
                filepath = self.output_manager.save_transcript_markdown(
                    transcript=result,
                    title=video.title or f"Video_{video.video_id}",
                    channel_name=channel_name,
                    output_dir=output_dir,
                    index=video.index,
                    playlist_name=playlist.title,
                )
                print(f"         [OK] Saved ({result.segment_count} segments)")
                report.add_success(ExtractionResult(
                    index=video.index,
                    video_id=video.video_id,
                    title=video.title,
                    success=True,
                    segments=result.segment_count,
                    file=filepath.name,
                ))
                consecutive_failures = 0
            else:
                print(f"         [FAIL] {result.error}")
                report.add_failure(ExtractionResult(
                    index=video.index,
                    video_id=video.video_id,
                    title=video.title,
                    success=False,
                    error=result.error,
                ))

                if result.error_type == "IpBlocked":
                    print()
                    print("!" * 60)
                    print("IP BLOCKED - Stopping extraction")
                    print("Try again later or use a VPN")
                    print("!" * 60)
                    ip_blocked = True
                    report.ip_blocked = True
                    continue

                consecutive_failures += 1

            print()

            # Adaptive rate limiting
            if i < len(videos) and not ip_blocked:
                if consecutive_failures >= 3:
                    print("         (Slowing down due to consecutive failures)")
                    time.sleep(ERROR_RATE_LIMIT)
                else:
                    time.sleep(self.rate_limit)

        # Finalize report
        report.extraction_completed = datetime.now().isoformat()
        self.output_manager.save_extraction_report(report, output_dir)

        return {
            "successful": report.successful,
            "failed": report.failed,
            "skipped": report.skipped,
            "ip_blocked": report.ip_blocked,
        }

    def print_summary(self, results: list[dict]):
        """Print extraction summary."""
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)

        total_success = 0
        total_failed = 0
        total_skipped = 0

        for result in results:
            success = len(result.get('successful', []))
            failed = len(result.get('failed', []))
            skipped = len(result.get('skipped', []))

            total_success += success
            total_failed += failed
            total_skipped += skipped

        print(f"Successful: {total_success}")
        print(f"Failed: {total_failed}")
        print(f"Skipped: {total_skipped}")
        print()

    async def youtube_discover(
        self,
        input_str: str,
        method: str = "auto",
        action: str = "discover",
        max_videos: int = 50,
        max_playlists: int = 20,
    ):
        """Unified YouTube command - discover, explore, and extract."""
        import os

        # Get API key from environment
        api_key = os.environ.get("YOUTUBE_API_KEY")

        discoverer = ChannelDiscoverer(
            api_key=api_key,
            ssl_bypass=True,
        )

        print("=" * 60)
        print(f"YouTube Discovery: {input_str}")
        print(f"Method: {method}")
        print("=" * 60)
        print()

        # Discover channel content
        discovery = await discoverer.discover(
            input_str,
            method=method,
            max_videos=max_videos,
            max_playlists=max_playlists,
        )

        if discovery.error and action == "discover":
            print(f"[FAIL] Discovery error: {discovery.error}")
            print()
            print("Tips:")
            print("  - Try --method playwright (requires: pip install playwright && playwright install chromium)")
            print("  - Try --method api (requires YOUTUBE_API_KEY environment variable)")
            return

        # Handle actions
        if action == "discover":
            self._print_discovery(discovery)

        elif action.startswith("p") and action[1:].isdigit():
            # Playlist shortcut
            idx = int(action[1:]) - 1
            if idx < 0 or idx >= len(discovery.playlists):
                print(f"[FAIL] Invalid playlist shortcut. Available: p1-p{len(discovery.playlists)}")
                return

            playlist_item = discovery.playlists[idx]
            print(f"Extracting playlist: {playlist_item.title}")
            print(f"Playlist ID: {playlist_item.playlist_id}")
            print()

            # Load playlist and extract
            playlist = self.scraper.get_playlist_info(playlist_item.playlist_id)
            if playlist.error or not playlist.videos:
                print(f"[FAIL] Could not load playlist: {playlist.error or 'No videos'}")
                print("TIP: Create a JSON config and use: python -m youtube_mcp.cli <config>")
                return

            result = self.extract_playlist(playlist)
            self.print_summary([result])

        elif action.startswith("v") and action[1:].isdigit():
            # Video shortcut
            idx = int(action[1:]) - 1
            if idx < 0 or idx >= len(discovery.videos):
                print(f"[FAIL] Invalid video shortcut. Available: v1-v{len(discovery.videos)}")
                return

            video = discovery.videos[idx]
            print(f"Extracting video: {video.title}")
            print(f"Video ID: {video.video_id}")
            print()

            result = self.extractor.extract(video.video_id, self.language)

            if result.success:
                output_dir = self.output_manager.get_channel_dir(discovery.channel_name or "unknown") / "singles"
                output_dir.mkdir(parents=True, exist_ok=True)

                filepath = self.output_manager.save_transcript_markdown(
                    transcript=result,
                    title=video.title,
                    channel_name=discovery.channel_name or "unknown",
                    output_dir=output_dir,
                    video_url=f"https://www.youtube.com/watch?v={video.video_id}",
                )
                print(f"[OK] Saved to: {filepath}")
                print(f"     Segments: {result.segment_count}")
                print(f"     Length: {len(result.full_text)} characters")
            else:
                print(f"[FAIL] {result.error}")

        elif action in ("save", "save_config"):
            # Save as JSON config
            config_name = discovery.channel_handle or discovery.channel_id or "channel"
            config_path = self.configs_dir / f"{config_name}.json"

            config = create_config_from_discovery(discovery, output_path=config_path)

            print(f"[OK] Config saved to: {config_path}")
            print(f"     Channel: {discovery.channel_name}")
            print(f"     Videos: {len(config['videos'])}")
            print()
            print(f"Usage: python -m youtube_mcp.cli {config_name}")

        elif action == "extract_all":
            # Extract all videos
            print(f"Extracting all {len(discovery.videos)} videos...")
            print()

            output_dir = self.output_manager.get_channel_dir(discovery.channel_name or "unknown") / "all_videos"
            output_dir.mkdir(parents=True, exist_ok=True)

            successful = 0
            failed = 0

            for i, video in enumerate(discovery.videos, 1):
                print(f"[{i:2d}/{len(discovery.videos)}] {video.title}")

                result = self.extractor.extract(video.video_id, self.language)

                if result.success:
                    filepath = self.output_manager.save_transcript_markdown(
                        transcript=result,
                        title=video.title,
                        channel_name=discovery.channel_name or "unknown",
                        output_dir=output_dir,
                        index=i,
                        video_url=f"https://www.youtube.com/watch?v={video.video_id}",
                    )
                    print(f"         [OK] ({result.segment_count} segments)")
                    successful += 1
                else:
                    print(f"         [FAIL] {result.error}")
                    failed += 1

                if i < len(discovery.videos):
                    time.sleep(self.rate_limit)

            print()
            print("=" * 60)
            print(f"Extracted: {successful}/{len(discovery.videos)}")
            print(f"Failed: {failed}")
            print(f"Output: {output_dir}")

        elif action == "list":
            self._print_discovery(discovery, verbose=True)

        else:
            print(f"[FAIL] Unknown action: {action}")
            print()
            print("Available actions:")
            print("  discover    - Show channel content (default)")
            print("  p1, p2, ... - Extract specific playlist")
            print("  v1, v2, ... - Extract specific video")
            print("  extract_all - Extract all videos")
            print("  save        - Save as JSON config")
            print("  list        - List all content verbosely")

    def _print_discovery(self, discovery, verbose: bool = False):
        """Print discovery results."""
        print(f"Channel: {discovery.channel_name}")
        if discovery.channel_handle:
            print(f"Handle: @{discovery.channel_handle}")
        if discovery.subscriber_count:
            subs = discovery.subscriber_count
            if subs >= 1_000_000:
                print(f"Subscribers: {subs/1_000_000:.1f}M")
            elif subs >= 1_000:
                print(f"Subscribers: {subs/1_000:.1f}K")
            else:
                print(f"Subscribers: {subs}")
        print(f"Method used: {discovery.method_used}")
        print()

        # Playlists
        if discovery.playlists:
            print("-" * 40)
            print(f"PLAYLISTS ({len(discovery.playlists)})")
            print("-" * 40)
            for i, p in enumerate(discovery.playlists, 1):
                print(f"  p{i:<3} {p.title}")
                if verbose:
                    print(f"       ID: {p.playlist_id}")
                    print(f"       Videos: {p.video_count}")
            print()

        # Videos
        if discovery.videos:
            print("-" * 40)
            display_count = len(discovery.videos) if verbose else min(20, len(discovery.videos))
            print(f"VIDEOS (showing {display_count} of {len(discovery.videos)})")
            print("-" * 40)
            for i, v in enumerate(discovery.videos[:display_count], 1):
                title = v.title[:50] + "..." if len(v.title) > 50 else v.title
                print(f"  v{i:<3} {title}")
                if verbose:
                    print(f"       ID: {v.video_id}")
                    if v.duration:
                        print(f"       Duration: {v.duration}")
            if not verbose and len(discovery.videos) > 20:
                print(f"  ... and {len(discovery.videos) - 20} more")
            print()

        # Usage hints
        print("-" * 40)
        print("QUICK ACTIONS")
        print("-" * 40)
        print(f"  youtube {discovery.channel_handle or discovery.channel_id} --action p1     # Extract first playlist")
        print(f"  youtube {discovery.channel_handle or discovery.channel_id} --action v1     # Extract first video")
        print(f"  youtube {discovery.channel_handle or discovery.channel_id} --action save   # Save config")
        print(f"  youtube {discovery.channel_handle or discovery.channel_id} --action list   # List all content")
        print()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="YouTube Transcript Extractor CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m youtube_mcp.cli                    # List configs
  python -m youtube_mcp.cli tjr                # Extract TJR config
  python -m youtube_mcp.cli tjr --retry        # Retry failed videos
  python -m youtube_mcp.cli --all              # Extract all configs
  python -m youtube_mcp.cli --video <url>      # Single video

  # Unified YouTube Command (use 'youtube' as first argument):
  python -m youtube_mcp.cli youtube @TJRTrades                    # Discover channel
  python -m youtube_mcp.cli youtube @TJRTrades --action p1        # Extract playlist 1
  python -m youtube_mcp.cli youtube @TJRTrades --action v1        # Extract video 1
  python -m youtube_mcp.cli youtube @TJRTrades --method playwright  # Use Playwright
  python -m youtube_mcp.cli youtube @TJRTrades --action save      # Save config
        """,
    )

    parser.add_argument(
        "config",
        nargs="?",
        help="Configuration ID to extract (e.g., 'tjr') OR 'youtube' for unified command",
    )
    parser.add_argument(
        "youtube_input",
        nargs="?",
        help="YouTube input for unified command (e.g., '@TJRTrades', channel URL)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Extract all available configurations",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Only retry previously failed videos",
    )
    parser.add_argument(
        "--video",
        "-v",
        type=str,
        help="Extract single video by URL",
    )
    parser.add_argument(
        "--url",
        "-u",
        type=str,
        help="Extract playlist by URL (may be blocked by YouTube)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--language",
        "-l",
        type=str,
        default=DEFAULT_LANGUAGE,
        help=f"Transcript language (default: {DEFAULT_LANGUAGE})",
    )
    parser.add_argument(
        "--delay",
        "-d",
        type=float,
        default=DEFAULT_RATE_LIMIT,
        help=f"Delay between requests in seconds (default: {DEFAULT_RATE_LIMIT})",
    )
    # YouTube unified command options
    parser.add_argument(
        "--action",
        "-a",
        type=str,
        default="discover",
        help="Action for youtube command: discover, p1-p99, v1-v99, extract_all, save, list",
    )
    parser.add_argument(
        "--method",
        "-m",
        type=str,
        choices=["auto", "api", "playwright", "scraping"],
        default="auto",
        help="Discovery method: auto (default), api, playwright, scraping",
    )
    parser.add_argument(
        "--max-videos",
        type=int,
        default=50,
        help="Max videos to discover (default: 50)",
    )
    parser.add_argument(
        "--max-playlists",
        type=int,
        default=20,
        help="Max playlists to discover (default: 20)",
    )

    args = parser.parse_args()

    # Initialize CLI
    cli = CLI(
        output_dir=Path(args.output),
        language=args.language,
        rate_limit=args.delay,
    )

    # Check for unified youtube command
    if args.config == "youtube":
        if not args.youtube_input:
            print("Usage: python -m youtube_mcp.cli youtube <input> [--action ACTION] [--method METHOD]")
            print()
            print("Input can be:")
            print("  @handle        - Channel handle (e.g., @TJRTrades)")
            print("  Channel URL    - https://www.youtube.com/@TJRTrades")
            print("  Channel ID     - UCxxxxxxxx")
            print()
            print("Actions:")
            print("  discover       - Show channel content (default)")
            print("  p1, p2, ...    - Extract specific playlist")
            print("  v1, v2, ...    - Extract specific video")
            print("  extract_all    - Extract all videos")
            print("  save           - Save as JSON config")
            print("  list           - List all content verbosely")
            print()
            print("Methods:")
            print("  auto           - Try API, then Playwright, then scraping (default)")
            print("  api            - Use YouTube Data API (requires YOUTUBE_API_KEY)")
            print("  playwright     - Use browser automation")
            print("  scraping       - Use HTTP scraping (fastest but may be blocked)")
            sys.exit(0)

        asyncio.run(cli.youtube_discover(
            input_str=args.youtube_input,
            method=args.method,
            action=args.action,
            max_videos=args.max_videos,
            max_playlists=args.max_playlists,
        ))

    # Handle different modes
    elif args.video:
        cli.extract_video(args.video)
    elif args.url:
        try:
            parsed = parse_youtube_url(args.url)
            if parsed.playlist_id:
                playlist = cli.scraper.get_playlist_info(parsed.playlist_id)
                if playlist.error or not playlist.videos:
                    print(f"Failed to scrape playlist: {playlist.error or 'No videos found'}")
                    print("Try using a JSON config file instead.")
                    sys.exit(1)
                results = [cli.extract_playlist(playlist, retry_only=args.retry)]
                cli.print_summary(results)
            elif parsed.video_id:
                cli.extract_video(args.url)
            else:
                print("URL must be a video or playlist")
                sys.exit(1)
        except ValueError as e:
            print(f"Invalid URL: {e}")
            sys.exit(1)
    elif args.all:
        configs = cli.get_available_configs()
        if not configs:
            print("No configurations found.")
            sys.exit(1)

        results = []
        for config_id in configs:
            result = cli.extract_config(config_id, retry_only=args.retry)
            results.append(result)

        cli.print_summary(results)
    elif args.config:
        result = cli.extract_config(args.config, retry_only=args.retry)
        cli.print_summary([result])
    else:
        cli.list_configs()


if __name__ == "__main__":
    main()
