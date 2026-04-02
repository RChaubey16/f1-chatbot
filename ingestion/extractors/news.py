"""Motorsport.com F1 news scraper.

Designed to fail gracefully — if the site changes its HTML structure the
scraper logs a warning and yields 0 documents rather than crashing the
scheduler.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from ingestion.core.config import settings
from ingestion.core.logging import get_logger
from ingestion.core.models import (
    ContentType,
    KBPartition,
    RawDocument,
    SourceType,
)
from ingestion.extractors.base import BaseExtractor

log = get_logger(__name__)

INDEX_URL = "https://www.motorsport.com/f1/news/"
# 2 seconds between article fetches — news sites are not APIs
NEWS_DELAY = 2.0


class NewsExtractor(BaseExtractor):
    """Scrape recent F1 news articles from Motorsport.com."""

    def __init__(
        self,
        max_articles: int = 50,
        since: datetime | None = None,
        url_exists_fn: object = None,
    ) -> None:
        self.max_articles = max_articles
        self.since = since
        # Injected callable: async (url: str) -> bool
        # Used by the pipeline to skip already-ingested URLs.
        self._url_exists_fn = url_exists_fn
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": settings.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    async def extract(self) -> AsyncIterator[RawDocument]:  # type: ignore[override]
        log.info("news.start", max_articles=self.max_articles)

        urls = await self._fetch_article_urls()
        if not urls:
            log.warning("news.no_urls_found", hint="Motorsport.com layout may have changed")
            await self._client.aclose()
            return

        log.info("news.urls_found", count=len(urls))
        yielded = 0

        for url in urls:
            if yielded >= self.max_articles:
                break

            # Skip if already in DB
            if self._url_exists_fn is not None:
                try:
                    exists = await self._url_exists_fn(url)
                    if exists:
                        log.debug("news.skip_existing", url=url)
                        continue
                except Exception as exc:
                    log.warning("news.url_check_fail", url=url, error=str(exc))

            article = await self._fetch_article(url)
            if article is None:
                continue

            # Filter by publication date if since is set
            if self.since and article.get("published_at"):
                try:
                    pub = datetime.fromisoformat(article["published_at"])
                    if pub.tzinfo is None:
                        pub = pub.replace(tzinfo=timezone.utc)
                    if pub < self.since:
                        continue
                except ValueError:
                    pass

            body = article.get("body", "")
            if not body or len(body) < 100:
                log.debug("news.skip_empty_body", url=url)
                continue

            raw = f"{article.get('headline', '')}\n\n{body}"
            yield RawDocument(
                source=SourceType.NEWS,
                content_type=ContentType.NARRATIVE,
                partition=KBPartition.LIVE,
                raw_content=raw,
                metadata={
                    "headline": article.get("headline", ""),
                    "url": url,
                    "published_at": article.get("published_at", ""),
                    "author": article.get("author", ""),
                    "tags": article.get("tags", []),
                },
            )
            yielded += 1
            await asyncio.sleep(NEWS_DELAY)

        await self._client.aclose()
        log.info("news.done", yielded=yielded)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _fetch_article_urls(self) -> list[str]:
        """Fetch the F1 news index and extract article URLs."""
        try:
            resp = await self._client.get(INDEX_URL, timeout=20.0)
            resp.raise_for_status()
        except Exception as exc:
            log.error("news.index_fetch_fail", error=str(exc))
            return []

        try:
            soup = BeautifulSoup(resp.text, "lxml")
            return self._parse_article_urls(soup)
        except Exception as exc:
            log.warning("news.index_parse_fail", error=str(exc))
            return []

    @staticmethod
    def _parse_article_urls(soup: BeautifulSoup) -> list[str]:
        """Extract article URLs from the index page.

        Tries several CSS patterns in order of specificity so that minor
        layout changes don't break the entire scraper.
        """
        urls: list[str] = []
        seen: set[str] = set()

        # Pattern 1: article cards with data-id or within <article> tags
        candidates = soup.select("article a[href], .ms-item a[href], .card a[href]")

        # Pattern 2: fallback — any link containing /f1/news/ in href
        if not candidates:
            candidates = soup.find_all("a", href=lambda h: h and "/f1/news/" in h)

        for tag in candidates:
            href = tag.get("href", "")
            if not href or "/f1/news/" not in href:
                continue
            # Make absolute
            if href.startswith("/"):
                href = f"https://www.motorsport.com{href}"
            # Skip index page itself and pagination links
            if href.rstrip("/") == INDEX_URL.rstrip("/"):
                continue
            if href in seen:
                continue
            seen.add(href)
            urls.append(href)

        return urls

    async def _fetch_article(self, url: str) -> dict | None:
        """Fetch and parse a single article page."""
        try:
            resp = await self._client.get(url, timeout=20.0)
            resp.raise_for_status()
        except Exception as exc:
            log.warning("news.article_fetch_fail", url=url, error=str(exc))
            return None

        try:
            soup = BeautifulSoup(resp.text, "lxml")
            return self._parse_article(soup, url)
        except Exception as exc:
            log.warning("news.article_parse_fail", url=url, error=str(exc))
            return None

    @staticmethod
    def _parse_article(soup: BeautifulSoup, url: str) -> dict:
        """Extract headline, date, author, body from an article page."""
        # Headline
        headline = ""
        h1 = soup.find("h1")
        if h1:
            headline = h1.get_text(strip=True)

        # Published date — try common meta tags first, then visible elements
        published_at = ""
        for selector in [
            'meta[property="article:published_time"]',
            'meta[name="date"]',
            'time[datetime]',
        ]:
            el = soup.select_one(selector)
            if el:
                published_at = el.get("content") or el.get("datetime") or ""
                if published_at:
                    break

        # Author
        author = ""
        for selector in [
            'meta[name="author"]',
            '[class*="author"] [class*="name"]',
            '[rel="author"]',
        ]:
            el = soup.select_one(selector)
            if el:
                author = el.get("content") or el.get_text(strip=True)
                if author:
                    break

        # Tags / keywords
        tags: list[str] = []
        meta_kw = soup.find("meta", {"name": "keywords"})
        if meta_kw:
            tags = [t.strip() for t in meta_kw.get("content", "").split(",") if t.strip()]

        # Article body — remove boilerplate sections
        body_parts: list[str] = []
        for selector in [
            "article .ms-article-content",
            "article .content",
            '[class*="article-body"]',
            '[class*="article__body"]',
            "article",
        ]:
            container = soup.select_one(selector)
            if container:
                # Remove nav, ads, related articles, scripts, styles
                for unwanted in container.select(
                    "nav, aside, .related, .recommended, script, style, "
                    ".advertisement, .ad, [class*='promo'], [class*='signup']"
                ):
                    unwanted.decompose()

                for p in container.find_all(["p", "h2", "h3"]):
                    text = p.get_text(separator=" ", strip=True)
                    if text:
                        body_parts.append(text)
                break

        return {
            "headline": headline,
            "url": url,
            "published_at": published_at,
            "author": author,
            "tags": tags,
            "body": "\n\n".join(body_parts),
        }

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(INDEX_URL, timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False
