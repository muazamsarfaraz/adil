"""
Project Adil - Content Extraction Service

Extracts text content from URLs for downstream legal analysis.
Each platform follows a cascade pattern (try method A, fall back to B, ...):

Supported platforms:
    YouTube   - youtube-transcript-api + Shorts/Live support + manual fallback
    Facebook  - yt-dlp subtitles/description -> OG meta tags -> manual fallback
    Twitter/X - FXTwitter API -> yt-dlp -> manual fallback
    Instagram - OG meta tags -> yt-dlp -> manual fallback
    Webpages  - httpx + BeautifulSoup with Content-Type check

SSRF protection is applied to all outbound URL fetching (private/loopback
IP blocking via socket-level validation).
"""
import re
import logging
import asyncio
import socket
import ipaddress
from typing import List, Optional
from enum import Enum
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models for Content Extraction
# =============================================================================

class ContentType(str, Enum):
    """Type of extracted content"""
    TEXT = "text"
    WEBPAGE = "webpage"
    YOUTUBE = "youtube"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    UNKNOWN = "unknown"


class ExtractedContent(BaseModel):
    """Result of content extraction from a single source"""
    url: str = Field(..., description="Original URL")
    content_type: ContentType = Field(..., description="Type of content extracted")
    title: Optional[str] = Field(None, description="Page or video title")
    text: str = Field(..., description="Extracted text content")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    success: bool = Field(True, description="Whether extraction succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class ProcessedContent(BaseModel):
    """Combined result of processing a message"""
    original_text: str = Field(..., description="Original message text")
    extracted_urls: List[ExtractedContent] = Field(default_factory=list)
    combined_text: str = Field(..., description="All text combined for analysis")
    url_count: int = Field(0, description="Number of URLs processed")


# =============================================================================
# URL Patterns
# =============================================================================

URL_PATTERNS = {
    'youtube': re.compile(
        r'(?:https?://)?(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/|live/)|youtu\.be/)([a-zA-Z0-9_-]{11})',
        re.IGNORECASE
    ),
    'twitter': re.compile(
        r'(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/(\d+)',
        re.IGNORECASE
    ),
    'instagram': re.compile(
        r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|reels|tv)/[\w-]+',
        re.IGNORECASE
    ),
    'facebook': re.compile(
        r'(?:https?://)?(?:(?:www|m|web)\.)?(?:facebook\.com/(?:watch|reel|video|.+/videos/|story\.php)|fb\.watch)/.+',
        re.IGNORECASE
    ),
    'generic_url': re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+',
        re.IGNORECASE
    )
}


# =============================================================================
# SSRF Protection
# =============================================================================

def _is_safe_url(url: str) -> bool:
    """
    Validate that a URL does not point to private/internal IP ranges (SSRF protection).

    Returns True if the URL is safe to fetch, False otherwise.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Reject non-http(s) schemes
    if parsed.scheme not in ('http', 'https'):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    try:
        # Resolve hostname to IP address(es)
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False

    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False

        # Reject private / reserved ranges
        if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
            return False

    return True


# =============================================================================
# Content Extractor Service
# =============================================================================

class ContentExtractor:
    """
    Service for extracting content from URLs.
    Supports web pages, YouTube transcripts, Twitter/X posts (via FXTwitter),
    Instagram posts (OG meta + yt-dlp), and Facebook videos (yt-dlp + OG meta).
    Designed to work async and integrate with the RAG service.
    """

    def __init__(
        self,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        request_timeout: float = 30.0
    ):
        """
        Initialize ContentExtractor.

        Args:
            user_agent: User agent string for HTTP requests
            request_timeout: Timeout for HTTP requests in seconds
        """
        self.user_agent = user_agent
        self.request_timeout = request_timeout
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info("ContentExtractor initialized")

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=self.request_timeout,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            )
        return self._http_client

    async def close(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.close()

    # -------------------------------------------------------------------------
    # URL Detection
    # -------------------------------------------------------------------------

    def detect_urls(self, text: str) -> List[str]:
        """
        Detect all URLs in text.

        Args:
            text: Input text to scan for URLs

        Returns:
            List of detected URLs (deduplicated, order preserved)
        """
        urls = []
        seen = set()

        for match in URL_PATTERNS['generic_url'].finditer(text):
            url = match.group(0).rstrip('.,;:!?)')
            if url not in seen:
                seen.add(url)
                urls.append(url)

        logger.debug(f"Detected {len(urls)} URLs in text")
        return urls

    def _classify_url(self, url: str) -> ContentType:
        """Classify URL by content type"""
        if URL_PATTERNS['youtube'].search(url):
            return ContentType.YOUTUBE
        if URL_PATTERNS['twitter'].search(url):
            return ContentType.TWITTER
        if URL_PATTERNS['instagram'].search(url):
            return ContentType.INSTAGRAM
        if URL_PATTERNS['facebook'].search(url):
            return ContentType.FACEBOOK
        return ContentType.WEBPAGE

    def _extract_youtube_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from URL"""
        match = URL_PATTERNS['youtube'].search(url)
        return match.group(1) if match else None

    def _get_base_ytdlp_opts(self) -> dict:
        """Base yt-dlp options shared across all platform extractors."""
        return {
            'skip_download': True,
            'no_warnings': True,
            'quiet': True,
            'extract_flat': False,
            'socket_timeout': self.request_timeout,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'json3/vtt/srv3/srv2/srv1',
        }

    # -------------------------------------------------------------------------
    # Web Content Extraction
    # -------------------------------------------------------------------------

    async def extract_url_content(self, url: str) -> ExtractedContent:
        """
        Extract content from a URL based on its type.

        Args:
            url: The URL to extract content from

        Returns:
            ExtractedContent with extracted text and metadata
        """
        # SSRF protection: reject private/internal URLs
        if not _is_safe_url(url):
            return ExtractedContent(
                url=url,
                content_type=ContentType.UNKNOWN,
                text="",
                success=False,
                error_message="URL rejected: points to a private or internal network address."
            )

        content_type = self._classify_url(url)

        try:
            if content_type == ContentType.YOUTUBE:
                video_id = self._extract_youtube_id(url)
                try:
                    text = await self.extract_youtube_transcript(url)
                    return ExtractedContent(
                        url=url,
                        content_type=ContentType.YOUTUBE,
                        title=f"YouTube Video: {video_id}",
                        text=text,
                        metadata={"video_id": video_id}
                    )
                except Exception as yt_err:
                    logger.warning(f"YouTube transcript extraction failed for {url}: {yt_err}")
                    return ExtractedContent(
                        content_type=ContentType.YOUTUBE,
                        text="",
                        title=f"YouTube Video ({video_id})",
                        url=url,
                        success=True,
                        metadata={
                            "source": "manual_fallback",
                            "video_id": video_id,
                            "requires_manual_input": True,
                            "fallback_message": "Could not extract transcript automatically. Please paste the video transcript or describe the content."
                        }
                    )

            if content_type == ContentType.TWITTER:
                return await self._extract_twitter_content(url)

            if content_type == ContentType.INSTAGRAM:
                return await self._extract_instagram_content(url)

            if content_type == ContentType.FACEBOOK:
                return await self._extract_facebook_content(url)

            # Default: generic webpage extraction
            return await self._extract_webpage_content(url)

        except Exception as e:
            logger.error(f"Failed to extract content from {url}: {e}")
            return ExtractedContent(
                url=url,
                content_type=content_type,
                text="",
                success=False,
                error_message=str(e)
            )

    async def _extract_webpage_content(self, url: str) -> ExtractedContent:
        """Extract text content from a generic webpage"""
        if not _is_safe_url(url):
            return ExtractedContent(
                url=url,
                content_type=ContentType.WEBPAGE,
                text="",
                success=False,
                error_message="URL rejected: points to a private or internal network address."
            )

        client = self._get_http_client()
        response = await client.get(url)
        response.raise_for_status()

        # Check Content-Type — only parse HTML responses
        content_type_header = response.headers.get('content-type', '')
        if not any(ct in content_type_header for ct in ('text/html', 'application/xhtml+xml')):
            return ExtractedContent(
                url=url,
                content_type=ContentType.WEBPAGE,
                title=None,
                text="",
                metadata={"content_type_header": content_type_header},
                success=False,
                error_message=f"Non-HTML content type: {content_type_header}"
            )

        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script and style elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
            element.decompose()

        # Get title
        title = soup.title.string if soup.title else None

        # Extract main content (prefer article, main, or body)
        main_content = soup.find('article') or soup.find('main') or soup.body

        if main_content:
            # Get text with paragraph separation
            paragraphs = main_content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'])
            text = '\n\n'.join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        else:
            text = soup.get_text(separator='\n', strip=True)

        # Clean up excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)

        logger.info(f"Extracted {len(text)} characters from {url}")

        return ExtractedContent(
            url=url,
            content_type=ContentType.WEBPAGE,
            title=title,
            text=text,
            metadata={"content_length": len(text)}
        )

    # -------------------------------------------------------------------------
    # Twitter/X Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_tweet_id(url: str) -> Optional[str]:
        """Extract tweet ID from a Twitter/X URL."""
        match = URL_PATTERNS['twitter'].search(url)
        return match.group(1) if match else None

    async def _extract_twitter_via_fxtwitter(self, url: str) -> Optional[ExtractedContent]:
        """
        Extract tweet text via the FXTwitter API (free, no auth required).
        Returns None if the API cannot retrieve the tweet.
        """
        tweet_id = self._extract_tweet_id(url)
        if not tweet_id:
            return None

        try:
            client = self._get_http_client()
            response = await client.get(
                f"https://api.fxtwitter.com/status/{tweet_id}",
                headers={"Accept": "application/json"},
            )
            if response.status_code != 200:
                logger.warning(f"FXTwitter API returned {response.status_code} for tweet {tweet_id}")
                return None

            data = response.json()
            tweet = data.get('tweet')
            if not tweet:
                return None

            text = tweet.get('text', '')
            if not text:
                return None

            author = tweet.get('author', {})
            author_name = author.get('name', '')
            screen_name = author.get('screen_name', '')
            title = f"@{screen_name} ({author_name})" if screen_name else "Tweet"

            metadata = {
                "source": "fxtwitter",
                "author": author_name,
                "screen_name": screen_name,
                "tweet_id": tweet_id,
            }
            # Include engagement metrics if available
            for key in ('likes', 'retweets', 'replies', 'views'):
                val = tweet.get(key)
                if val is not None:
                    metadata[key] = val

            logger.info(f"FXTwitter extracted tweet ({len(text)} chars) from @{screen_name}")

            return ExtractedContent(
                url=url,
                content_type=ContentType.TWITTER,
                title=title,
                text=text,
                metadata=metadata,
            )

        except Exception as e:
            logger.warning(f"FXTwitter extraction failed for {url}: {e}")
            return None

    async def _extract_twitter_via_ytdlp(self, url: str) -> Optional[ExtractedContent]:
        """
        Extract Twitter/X video metadata via yt-dlp.
        Only works for tweets with video; returns None for text-only tweets.
        """
        def _run_ytdlp(target_url: str) -> Optional[dict]:
            import yt_dlp
            opts = self._get_base_ytdlp_opts()
            opts['subtitleslangs'] = ['en', 'en-US', 'en-GB']
            opts['user_agent'] = self.user_agent
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(target_url, download=False)
            except Exception as e:
                logger.debug(f"yt-dlp Twitter extraction failed for {target_url}: {e}")
                return None

        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, _run_ytdlp, url)

        if not info:
            return None

        description = info.get('description', '')
        title = info.get('title', '')
        uploader = info.get('uploader', '')
        subtitle_text = self._extract_subtitles_from_info(info)

        text_parts = []
        if subtitle_text:
            text_parts.append(f"[Video transcript]\n{subtitle_text}")
        if description:
            text_parts.append(f"[Tweet]\n{description}")
        if not text_parts:
            return None

        combined_text = '\n\n'.join(text_parts)

        metadata = {
            "source": "yt-dlp",
            "uploader": uploader,
            "has_video": True,
            "has_subtitles": bool(subtitle_text),
        }

        logger.info(f"yt-dlp extracted Twitter video ({len(combined_text)} chars) from {url}")

        return ExtractedContent(
            url=url,
            content_type=ContentType.TWITTER,
            title=(title or (f"Tweet by {uploader}" if uploader else "Tweet")),
            text=combined_text,
            metadata=metadata,
        )

    async def _extract_twitter_content(self, url: str) -> ExtractedContent:
        """
        Extract content from a Twitter/X post.

        Strategy (cascading):
        1. FXTwitter API  (free, no auth — gets tweet text for any public tweet)
        2. yt-dlp         (for video tweets — gets video metadata + subtitles)
        3. Manual-paste fallback
        """
        # Step 1: FXTwitter API (works for all public tweets, text + video)
        result = await self._extract_twitter_via_fxtwitter(url)
        if result:
            return result

        # Step 2: yt-dlp (bonus — may get video subtitles that FXTwitter doesn't)
        result = await self._extract_twitter_via_ytdlp(url)
        if result:
            return result

        # Step 3: fallback
        return ExtractedContent(
            url=url,
            content_type=ContentType.TWITTER,
            title="Tweet",
            text=(
                f"[Twitter/X content at {url} could not be extracted. "
                "Please paste the tweet text directly into the chat for legal analysis.]"
            ),
            metadata={"requires_manual_input": True, "source": "fallback"},
            success=True,
        )


    # -------------------------------------------------------------------------
    # Instagram Helpers
    # -------------------------------------------------------------------------

    async def _extract_instagram_via_og(self, url: str) -> Optional[ExtractedContent]:
        """Scrape og:description meta tag from Instagram's public page."""
        if not _is_safe_url(url):
            return None

        try:
            client = self._get_http_client()
            response = await client.get(url)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                og_desc = soup.find('meta', property='og:description')
                og_title = soup.find('meta', property='og:title')
                description = og_desc['content'] if og_desc and og_desc.get('content') else None
                title = og_title['content'] if og_title and og_title.get('content') else None
                if description and len(description) > 20:
                    logger.info(f"OG-meta extracted Instagram content ({len(description)} chars) from {url}")
                    return ExtractedContent(
                        url=url,
                        content_type=ContentType.INSTAGRAM,
                        title=title or "Instagram Post",
                        text=description,
                        metadata={"source": "og_meta_scrape"},
                    )
        except Exception as e:
            logger.warning(f"Instagram OG scrape failed for {url}: {e}")
        return None

    async def _extract_instagram_via_ytdlp(self, url: str) -> Optional[ExtractedContent]:
        """
        Extract Instagram video/reel metadata via yt-dlp.
        Works best when server has Instagram cookies configured.
        Returns None if yt-dlp cannot access the content.
        """
        def _run_ytdlp(target_url: str) -> Optional[dict]:
            import yt_dlp
            opts = self._get_base_ytdlp_opts()
            opts['subtitleslangs'] = ['en', 'en-US', 'en-GB']
            opts['user_agent'] = self.user_agent
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(target_url, download=False)
            except Exception as e:
                logger.debug(f"yt-dlp Instagram extraction failed for {target_url}: {e}")
                return None

        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, _run_ytdlp, url)

        if not info:
            return None

        title = info.get('title', '')
        description = info.get('description', '')
        uploader = info.get('uploader', '') or info.get('uploader_id', '')
        duration = info.get('duration')
        subtitle_text = self._extract_subtitles_from_info(info)

        text_parts = []
        if subtitle_text:
            text_parts.append(f"[Video transcript]\n{subtitle_text}")
        if description:
            text_parts.append(f"[Post caption]\n{description}")
        if not text_parts:
            if title:
                text_parts.append(f"[Instagram post: {title}]")
            else:
                return None

        combined_text = '\n\n'.join(text_parts)

        metadata = {
            "source": "yt-dlp",
            "uploader": uploader,
            "has_subtitles": bool(subtitle_text),
        }
        if duration:
            metadata["duration_seconds"] = duration

        logger.info(f"yt-dlp extracted Instagram content ({len(combined_text)} chars) from {url}")

        return ExtractedContent(
            url=url,
            content_type=ContentType.INSTAGRAM,
            title=title or "Instagram Post",
            text=combined_text,
            metadata=metadata,
        )

    async def _extract_instagram_content(self, url: str) -> ExtractedContent:
        """
        Extract content from an Instagram post/reel.

        Strategy (cascading):
        1. OG meta scrape  (works for some public posts without login)
        2. yt-dlp          (works if server has Instagram cookies configured)
        3. Manual-paste fallback
        """
        # Step 1: OG meta scrape (lightweight, no dependencies)
        result = await self._extract_instagram_via_og(url)
        if result:
            return result

        # Step 2: yt-dlp (may work with cookies, gets richer data for video posts)
        result = await self._extract_instagram_via_ytdlp(url)
        if result:
            return result

        # Step 3: fallback
        return ExtractedContent(
            url=url,
            content_type=ContentType.INSTAGRAM,
            title="Instagram Post",
            text=(
                f"[Instagram content at {url} could not be fully extracted. "
                "Instagram restricts automated access to post content. "
                "Please paste the post caption or screenshot text directly into the chat "
                "for legal analysis.]"
            ),
            metadata={"requires_manual_input": True, "source": "fallback"},
            success=True,
        )

    # -------------------------------------------------------------------------
    # Facebook Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _normalize_facebook_url(url: str) -> str:
        """Normalize Facebook URL: strip tracking params, fix subdomains."""
        # Remove common tracking parameters
        url = re.sub(r'[&?](fbclid|ref|source|__tn__|__cft__|hash)=[^&]*', '', url)
        url = re.sub(r'[&?]$', '', url)
        # Normalize subdomains for yt-dlp compatibility
        url = url.replace('web.facebook.com', 'www.facebook.com')
        url = url.replace('m.facebook.com', 'www.facebook.com')
        return url

    async def _resolve_fb_watch_url(self, url: str) -> str:
        """Resolve fb.watch short links by following redirect chain."""
        if 'fb.watch' not in url:
            return url

        try:
            client = self._get_http_client()
            current_url = url
            for _ in range(5):  # max 5 redirects
                response = await client.get(
                    current_url,
                    follow_redirects=False,
                )
                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_url = response.headers.get('Location', '')
                    if not redirect_url:
                        break
                    if redirect_url.startswith('/'):
                        redirect_url = urljoin(current_url, redirect_url)
                    if 'facebook.com' in redirect_url:
                        logger.info(f"Resolved fb.watch: {url} -> {redirect_url}")
                        return redirect_url
                    current_url = redirect_url
                else:
                    break
        except Exception as e:
            logger.warning(f"fb.watch resolution failed for {url}: {e}")

        return url

    async def _extract_facebook_via_ytdlp(self, url: str) -> Optional[ExtractedContent]:
        """
        Extract Facebook video metadata and subtitles using yt-dlp.
        Returns None if yt-dlp cannot handle this URL.
        """
        def _run_ytdlp(target_url: str) -> Optional[dict]:
            import yt_dlp
            opts = self._get_base_ytdlp_opts()
            opts['subtitleslangs'] = ['en', 'en-US', 'en-GB']
            opts['user_agent'] = self.user_agent
            opts['retries'] = 3
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(target_url, download=False)
                    return info
            except Exception as e:
                logger.warning(f"yt-dlp extraction failed for {target_url}: {e}")
                return None

        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, _run_ytdlp, url)

        if not info:
            return None

        title = info.get('title', '')
        description = info.get('description', '')
        uploader = info.get('uploader', '')
        duration = info.get('duration')

        # Try to get subtitles/captions text
        subtitle_text = self._extract_subtitles_from_info(info)

        # Build combined text: subtitles are the richest, then description
        text_parts = []
        if subtitle_text:
            text_parts.append(f"[Video transcript]\n{subtitle_text}")
        if description:
            text_parts.append(f"[Video description]\n{description}")
        if not text_parts:
            # yt-dlp succeeded but no useful text
            if title:
                text_parts.append(f"[Facebook video: {title}]")
            else:
                return None

        combined_text = '\n\n'.join(text_parts)

        metadata = {
            "source": "yt-dlp",
            "uploader": uploader,
            "has_subtitles": bool(subtitle_text),
        }
        if duration:
            metadata["duration_seconds"] = duration

        logger.info(
            f"yt-dlp extracted Facebook content ({len(combined_text)} chars, "
            f"subtitles={'yes' if subtitle_text else 'no'}) from {url}"
        )

        return ExtractedContent(
            url=url,
            content_type=ContentType.FACEBOOK,
            title=title or "Facebook Video",
            text=combined_text,
            metadata=metadata,
        )

    @staticmethod
    def _extract_subtitles_from_info(info: dict) -> Optional[str]:
        """Pull subtitle text from yt-dlp info dict if available."""
        # yt-dlp stores subtitles in requested_subtitles or subtitles
        for subs_key in ('requested_subtitles', 'subtitles', 'automatic_captions'):
            subs = info.get(subs_key)
            if not subs:
                continue
            # subs is a dict like {'en': [{'ext': 'json3', 'data': ...}, ...]}
            for lang in ('en', 'en-US', 'en-GB'):
                lang_subs = subs.get(lang)
                if not lang_subs:
                    continue
                for sub_entry in lang_subs:
                    # Some entries have inline data
                    data = sub_entry.get('data')
                    if data:
                        # json3 format has events with segs
                        if isinstance(data, dict) and 'events' in data:
                            segments = []
                            for event in data['events']:
                                for seg in event.get('segs', []):
                                    text = seg.get('utf8', '').strip()
                                    if text and text != '\n':
                                        segments.append(text)
                            if segments:
                                return ' '.join(segments)
                        elif isinstance(data, str):
                            return data
        return None

    async def _extract_facebook_via_og(self, url: str) -> Optional[ExtractedContent]:
        """Fallback: scrape og:description meta tag from the public page."""
        if not _is_safe_url(url):
            return None

        try:
            client = self._get_http_client()
            response = await client.get(url)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                og_desc = soup.find('meta', property='og:description')
                og_title = soup.find('meta', property='og:title')
                description = og_desc['content'] if og_desc and og_desc.get('content') else None
                title = og_title['content'] if og_title and og_title.get('content') else None
                if description and len(description) > 20:
                    logger.info(f"OG-meta extracted Facebook content ({len(description)} chars) from {url}")
                    return ExtractedContent(
                        url=url,
                        content_type=ContentType.FACEBOOK,
                        title=title or "Facebook Post",
                        text=description,
                        metadata={"source": "og_meta_scrape"},
                    )
        except Exception as e:
            logger.warning(f"Facebook OG scrape failed for {url}: {e}")
        return None

    async def _extract_facebook_content(self, url: str) -> ExtractedContent:
        """
        Extract content from a Facebook post/video/reel.

        Strategy (cascading):
        1. Normalize URL & resolve fb.watch short links
        2. yt-dlp metadata + subtitle extraction  (best for videos)
        3. OG meta scrape fallback               (best for text posts)
        4. Manual-paste prompt                   (last resort)
        """
        # Step 1: normalize & resolve short links
        normalized = self._normalize_facebook_url(url)
        normalized = await self._resolve_fb_watch_url(normalized)

        # Step 2: try yt-dlp (best for videos with subtitles/descriptions)
        result = await self._extract_facebook_via_ytdlp(normalized)
        if result:
            return result

        # Step 3: OG meta scrape (works for some public text posts)
        result = await self._extract_facebook_via_og(normalized)
        if result:
            return result

        # Step 4: fallback — ask user to paste content
        fallback_text = (
            f"[Facebook content at {url} could not be fully extracted. "
            "Facebook restricts automated access to post content. "
            "Please paste the post text directly into the chat for legal analysis.]"
        )
        return ExtractedContent(
            url=url,
            content_type=ContentType.FACEBOOK,
            title="Facebook Post",
            text=fallback_text,
            metadata={"requires_manual_input": True, "source": "fallback"},
            success=True,
        )

    # -------------------------------------------------------------------------
    # YouTube Transcript Extraction
    # -------------------------------------------------------------------------

    async def extract_youtube_transcript(self, youtube_url: str) -> str:
        """
        Extract transcript from a YouTube video.

        Args:
            youtube_url: YouTube video URL

        Returns:
            Video transcript as text

        Raises:
            ValueError: If video ID cannot be extracted
            Exception: If transcript is not available
        """
        video_id = self._extract_youtube_id(youtube_url)
        if not video_id:
            raise ValueError(f"Could not extract video ID from URL: {youtube_url}")

        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            # Create API instance (new API pattern in v1.2+)
            ytt_api = YouTubeTranscriptApi()

            # List available transcripts
            transcript_list = ytt_api.list(video_id)

            transcript = None
            try:
                # Try manually created English transcript first
                transcript = transcript_list.find_transcript(['en'])
            except Exception:
                try:
                    # Fall back to auto-generated English
                    transcript = transcript_list.find_generated_transcript(['en'])
                except Exception:
                    # Get any available transcript
                    for t in transcript_list:
                        transcript = t
                        break

            if transcript is None:
                raise Exception(f"No transcript available for video {video_id}")

            # Fetch and combine transcript segments (new API returns FetchedTranscript)
            fetched_transcript = transcript.fetch()
            # New API: FetchedTranscript is iterable with .text attribute on snippets
            text_segments = [snippet.text for snippet in fetched_transcript]
            full_text = ' '.join(text_segments)

            logger.info(f"Extracted transcript ({len(full_text)} chars) for YouTube video {video_id}")
            return full_text

        except ImportError:
            logger.error("youtube-transcript-api not installed")
            raise Exception("YouTube transcript extraction requires youtube-transcript-api package")
        except Exception as e:
            logger.error(f"Failed to extract YouTube transcript for {video_id}: {e}")
            raise

    # -------------------------------------------------------------------------
    # Combined Message Processing
    # -------------------------------------------------------------------------

    async def process_message(self, text: str) -> ProcessedContent:
        """
        Process a message for legal analysis.

        Detects URLs in text, extracts their content (including YouTube transcripts).
        Combines all content for RAG processing.

        Args:
            text: Message text that may contain URLs

        Returns:
            ProcessedContent with all extracted content
        """
        # Detect and extract URLs (limit to 10)
        urls = self.detect_urls(text)
        if len(urls) > 10:
            logger.warning(f"Detected {len(urls)} URLs, limiting to first 10")
            urls = urls[:10]

        async def _safe_extract(u: str) -> ExtractedContent:
            try:
                return await self.extract_url_content(u)
            except Exception as e:
                logger.error(f"Failed to process URL {u}: {e}")
                return ExtractedContent(
                    url=u,
                    content_type=ContentType.UNKNOWN,
                    text="",
                    success=False,
                    error_message=str(e)
                )

        extracted_urls: List[ExtractedContent] = list(
            await asyncio.gather(*[_safe_extract(u) for u in urls])
        )

        # Combine all text for analysis
        combined_parts = [text]

        for extracted in extracted_urls:
            if extracted.success and extracted.text:
                source_label = f"[Content from {extracted.url}]"
                combined_parts.append(f"\n\n{source_label}\n{extracted.text}")

        combined_text = ''.join(combined_parts)

        logger.info(f"Processed message: {len(urls)} URLs, {len(combined_text)} total characters")

        return ProcessedContent(
            original_text=text,
            extracted_urls=extracted_urls,
            combined_text=combined_text,
            url_count=len(urls)
        )

