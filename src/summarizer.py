"""
YouTube Transcript Summarizer - AI-powered video summarization using Claude CLI.
"""

import subprocess
import json
import os
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class SummaryStyle(str, Enum):
    """Summary output styles."""
    BULLET_POINTS = "bullet-points"
    PARAGRAPH = "paragraph"
    KEY_TAKEAWAYS = "key-takeaways"
    TRADING_STRATEGY = "trading-strategy"


class SummaryLength(str, Enum):
    """Summary length options."""
    SHORT = "short"      # ~200 words
    MEDIUM = "medium"    # ~500 words
    LONG = "long"        # ~1000 words
    DETAILED = "detailed"  # ~2000 words


@dataclass
class SummaryResult:
    """Result of a transcript summarization."""

    success: bool
    video_id: str
    title: Optional[str] = None
    transcript_length: int = 0
    summary_style: str = "bullet-points"
    summary_length: str = "medium"
    summary_text: str = ""
    key_topics: list[str] = field(default_factory=list)
    trading_insights: Optional[dict] = None  # For trading-strategy style
    model_used: str = "claude-cli"
    error: Optional[str] = None

    @property
    def word_count(self) -> int:
        return len(self.summary_text.split())


class TranscriptSummarizer:
    """
    Summarize YouTube transcripts using Claude CLI.
    Uses subprocess to call the claude command-line tool.
    """

    def __init__(self):
        """Initialize the summarizer."""
        self._claude_path = self._find_claude_cli()

    def _find_claude_cli(self) -> Optional[str]:
        """Find the Claude CLI executable."""
        # Check environment variable first
        env_path = os.environ.get("CLAUDE_CLI_PATH")
        if env_path and Path(env_path).exists():
            return env_path

        # First try: check if it's in PATH
        claude_in_path = shutil.which("claude")
        if claude_in_path:
            return claude_in_path

        # Common locations to check on Windows
        home = Path.home()

        # Most common Windows npm location - check this first
        npm_claude = home / "AppData" / "Roaming" / "npm" / "claude.cmd"
        if npm_claude.exists():
            return str(npm_claude)

        possible_paths = [
            # npm global installs
            home / "AppData" / "Roaming" / "npm" / "claude.cmd",
            home / "AppData" / "Roaming" / "npm" / "claude",
            # Local npm
            home / ".npm-global" / "bin" / "claude",
            home / ".npm-global" / "bin" / "claude.cmd",
            # nvm installations
            home / "AppData" / "Roaming" / "nvm" / "current" / "claude.cmd",
            # Scoop
            home / "scoop" / "shims" / "claude.cmd",
            # Direct install locations
            Path("C:/Program Files/nodejs/claude.cmd"),
            Path("C:/Program Files (x86)/nodejs/claude.cmd"),
            # Also check common Unix paths (for WSL or Git Bash)
            Path("/usr/local/bin/claude"),
            Path("/usr/bin/claude"),
            home / ".local" / "bin" / "claude",
        ]

        for path in possible_paths:
            if path.exists():
                return str(path)

        # Try to find via npm root
        try:
            result = subprocess.run(
                ["npm", "root", "-g"],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True,
            )
            if result.returncode == 0:
                npm_root = Path(result.stdout.strip())
                claude_bin = npm_root.parent / "claude.cmd"
                if claude_bin.exists():
                    return str(claude_bin)
                claude_bin = npm_root.parent / "claude"
                if claude_bin.exists():
                    return str(claude_bin)
        except Exception:
            pass

        return None

    def _check_claude_cli(self) -> bool:
        """Check if Claude CLI is available."""
        return self._claude_path is not None

    def _get_prompt(
        self,
        transcript: str,
        style: SummaryStyle,
        length: SummaryLength,
        title: Optional[str] = None,
        custom_instructions: Optional[str] = None,
    ) -> str:
        """Build the full prompt for summarization."""

        length_guide = {
            SummaryLength.SHORT: "Keep it brief, around 200 words.",
            SummaryLength.MEDIUM: "Aim for around 500 words.",
            SummaryLength.LONG: "Be thorough, around 1000 words.",
            SummaryLength.DETAILED: "Be comprehensive, around 2000 words. Include all important details.",
        }

        style_instructions = {
            SummaryStyle.BULLET_POINTS: """Create a summary using bullet points:
- Start with a one-sentence overview
- Use hierarchical bullets for main points and sub-points
- Keep each bullet concise (1-2 sentences max)
- Group related points together
- End with key takeaways""",

            SummaryStyle.PARAGRAPH: """Create a flowing paragraph summary:
- Start with a strong topic sentence
- Use clear transitions between ideas
- Maintain logical flow
- Conclude with main insights""",

            SummaryStyle.KEY_TAKEAWAYS: """Extract and present key takeaways:
- Identify the most important insights
- Number each takeaway
- Explain why each point matters
- Focus on actionable information
- Prioritize by importance""",

            SummaryStyle.TRADING_STRATEGY: """Extract trading strategy information with this structure:

## Strategy Overview
Brief description of the trading approach

## Entry Conditions
- List specific entry criteria
- Include any indicators or patterns mentioned

## Exit Conditions
- Take profit levels/methods
- Stop loss placement
- Trailing stop rules if mentioned

## Risk Management
- Position sizing guidelines
- Risk per trade
- Max drawdown rules

## Key Indicators/Tools
- List all technical indicators mentioned
- Include timeframes if specified

## Trading Rules
- Numbered list of specific rules
- Include any filters or confirmations

## Important Notes
- Warnings or caveats mentioned
- Market conditions when strategy works best

If any section has no information in the transcript, write "Not specified in video"."""
        }

        prompt = f"""Summarize this YouTube video transcript.

{f'Video Title: {title}' if title else ''}

STYLE: {style_instructions.get(style, style_instructions[SummaryStyle.BULLET_POINTS])}

LENGTH: {length_guide.get(length, length_guide[SummaryLength.MEDIUM])}

{f'ADDITIONAL INSTRUCTIONS: {custom_instructions}' if custom_instructions else ''}

TRANSCRIPT:
---
{transcript}
---

Provide your summary now (output ONLY the summary, no preamble):"""

        return prompt

    def _call_claude_cli(self, prompt: str) -> tuple[bool, str]:
        """
        Call Claude CLI with the given prompt.

        Returns:
            Tuple of (success, response_text)
        """
        if not self._claude_path:
            return False, "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"

        try:
            # Pass prompt via stdin using subprocess.PIPE
            # This avoids shell escaping issues with special characters
            result = subprocess.run(
                [self._claude_path, "-p", "-", "--output-format", "text"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
                encoding='utf-8',
            )

            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                error_msg = result.stderr.strip() if result.stderr else result.stdout.strip() if result.stdout else "Unknown error"
                if "ANTHROPIC_API_KEY" in error_msg or "API key" in error_msg.lower():
                    return False, "Claude CLI requires authentication. Run 'claude' manually first to log in."
                return False, f"Claude CLI error (code {result.returncode}): {error_msg[:500]}"

        except subprocess.TimeoutExpired:
            return False, "Claude CLI timed out (5 min limit). Try a shorter video."
        except FileNotFoundError:
            return False, f"Claude CLI not found at: {self._claude_path}"
        except Exception as e:
            return False, f"Error calling Claude CLI: {str(e)}"

    def summarize(
        self,
        transcript: str,
        video_id: str,
        title: Optional[str] = None,
        style: str = "bullet-points",
        length: str = "medium",
        custom_instructions: Optional[str] = None,
    ) -> SummaryResult:
        """
        Summarize a transcript using Claude CLI.

        Args:
            transcript: Full transcript text
            video_id: YouTube video ID
            title: Video title (optional, helps with context)
            style: Summary style (bullet-points, paragraph, key-takeaways, trading-strategy)
            length: Summary length (short, medium, long, detailed)
            custom_instructions: Additional instructions for the summary

        Returns:
            SummaryResult with the summary and metadata
        """
        # Parse style and length
        try:
            style_enum = SummaryStyle(style)
        except ValueError:
            style_enum = SummaryStyle.BULLET_POINTS

        try:
            length_enum = SummaryLength(length)
        except ValueError:
            length_enum = SummaryLength.MEDIUM

        # Validate transcript
        if not transcript or len(transcript.strip()) < 100:
            return SummaryResult(
                success=False,
                video_id=video_id,
                title=title,
                transcript_length=len(transcript) if transcript else 0,
                error="Transcript too short to summarize (minimum 100 characters)",
            )

        # Truncate very long transcripts to avoid CLI issues
        max_chars = 50000  # ~12k tokens
        if len(transcript) > max_chars:
            transcript = transcript[:max_chars] + "\n\n[... transcript truncated for length ...]"

        # Build prompt
        prompt = self._get_prompt(
            transcript=transcript,
            style=style_enum,
            length=length_enum,
            title=title,
            custom_instructions=custom_instructions,
        )

        # Call Claude CLI
        success, response = self._call_claude_cli(prompt)

        if not success:
            return SummaryResult(
                success=False,
                video_id=video_id,
                title=title,
                transcript_length=len(transcript),
                summary_style=style,
                summary_length=length,
                error=response,
            )

        # Extract key topics
        key_topics = self._extract_topics(response)

        # For trading strategy, parse structured content
        trading_insights = None
        if style_enum == SummaryStyle.TRADING_STRATEGY:
            trading_insights = self._parse_trading_insights(response)

        return SummaryResult(
            success=True,
            video_id=video_id,
            title=title,
            transcript_length=len(transcript),
            summary_style=style,
            summary_length=length,
            summary_text=response,
            key_topics=key_topics,
            trading_insights=trading_insights,
            model_used="claude-cli",
        )

    def _extract_topics(self, summary: str) -> list[str]:
        """Extract key topics from summary text."""
        topics = []
        lines = summary.split('\n')

        for line in lines:
            line = line.strip()
            # Headers (## Topic)
            if line.startswith('##'):
                topic = line.lstrip('#').strip()
                if topic and len(topic) < 100:
                    topics.append(topic)
            # Numbered items at start (1. Topic)
            elif line and line[0].isdigit() and '.' in line[:3]:
                topic = line.split('.', 1)[1].strip()
                if ':' in topic:
                    topic = topic.split(':')[0].strip()
                if topic and len(topic) < 100:
                    topics.append(topic[:80])

        return topics[:10]

    def _parse_trading_insights(self, summary: str) -> dict:
        """Parse trading strategy summary into structured data."""
        sections = {
            "strategy_overview": "",
            "entry_conditions": [],
            "exit_conditions": [],
            "risk_management": [],
            "indicators": [],
            "trading_rules": [],
            "notes": [],
        }

        current_section = None
        section_map = {
            "strategy overview": "strategy_overview",
            "entry conditions": "entry_conditions",
            "entry criteria": "entry_conditions",
            "exit conditions": "exit_conditions",
            "exit criteria": "exit_conditions",
            "risk management": "risk_management",
            "indicators": "indicators",
            "key indicators": "indicators",
            "trading rules": "trading_rules",
            "rules": "trading_rules",
            "important notes": "notes",
            "notes": "notes",
        }

        lines = summary.split('\n')

        for line in lines:
            line = line.strip()

            # Check for section headers
            if line.startswith('##'):
                header = line.lstrip('#').strip().lower()
                for key, section in section_map.items():
                    if key in header:
                        current_section = section
                        break
                continue

            # Add content to current section
            if current_section and line:
                if current_section == "strategy_overview":
                    sections[current_section] += line + " "
                elif line.startswith(('-', '*', '•')) or (line[0].isdigit() if line else False):
                    item = line.lstrip('-*•0123456789. ').strip()
                    if item:
                        sections[current_section].append(item)

        sections["strategy_overview"] = sections["strategy_overview"].strip()
        return sections

    def summarize_for_indicator(
        self,
        transcript: str,
        video_id: str,
        title: Optional[str] = None,
        indicator_type: Optional[str] = None,
    ) -> SummaryResult:
        """
        Specialized summarization for building trading indicators.

        Args:
            transcript: Full transcript text
            video_id: YouTube video ID
            title: Video title
            indicator_type: Type of indicator being built (e.g., "SMC", "ICT", "price-action")

        Returns:
            SummaryResult with trading-focused summary
        """
        custom_instructions = f"""
Focus on extracting information useful for building a Pine Script trading indicator:
- Mathematical formulas or calculations mentioned
- Specific price levels, percentages, or ratios (exact numbers!)
- Entry/exit conditions with precise rules
- Indicator parameters and settings
- Candlestick patterns or chart formations
- Timeframe recommendations
- Any lookback periods or bar counts mentioned
{f'- Specifically look for {indicator_type} concepts and rules' if indicator_type else ''}

Be VERY specific about numbers, levels, conditions, and logic.
If the speaker mentions code or pseudocode, include it."""

        return self.summarize(
            transcript=transcript,
            video_id=video_id,
            title=title,
            style="trading-strategy",
            length="detailed",
            custom_instructions=custom_instructions,
        )
