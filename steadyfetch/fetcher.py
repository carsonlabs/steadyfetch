"""Core reliability engine — wraps Crawl4AI with retry, fallback, circuit breaker, and caching."""

import asyncio
import logging
import os
import time
import random
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
)

from .circuit_breaker import CircuitBreaker
from .cache import FetchCache

logger = logging.getLogger("steadyfetch")


@dataclass
class FetchResult:
    url: str
    success: bool
    markdown: str | None = None
    html: str | None = None
    status_code: int | None = None
    error: str | None = None
    cached: bool = False
    attempts: int = 0
    elapsed_ms: int = 0
    domain_status: str = "closed"

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "success": self.success,
            "markdown": self.markdown,
            "html": self.html,
            "status_code": self.status_code,
            "error": self.error,
            "cached": self.cached,
            "attempts": self.attempts,
            "elapsed_ms": self.elapsed_ms,
            "domain_status": self.domain_status,
        }


class SteadyFetcher:
    """Reliable web fetcher with multiple fallback strategies.

    Strategy chain:
    1. Check cache → return if hit
    2. Check circuit breaker → fail fast if domain is down
    3. Try stealth browser fetch (Crawl4AI with anti-bot)
    4. On failure: retry with exponential backoff + jitter
    5. Fallback: plain HTTP fetch via httpx (works for non-JS sites)
    6. Cache successful results
    7. Update circuit breaker state
    """

    def __init__(
        self,
        max_retries: int = 3,
        circuit_threshold: int = 5,
        circuit_cooldown: float = 120.0,
        cache_ttl: int = 3600,
        timeout: int = 30000,
    ):
        self.max_retries = max_retries
        self.timeout = timeout
        self.circuit = CircuitBreaker(
            threshold=circuit_threshold,
            cooldown=circuit_cooldown,
        )
        self.cache = FetchCache(ttl=cache_ttl)

        # Browser config — stealth by default
        self.browser_cfg = BrowserConfig(
            headless=True,
            browser_type="chromium",
            viewport_width=1280,
            viewport_height=720,
            java_script_enabled=True,
        )

    @staticmethod
    def _domain(url: str) -> str:
        return urlparse(url).netloc

    async def fetch(
        self,
        url: str,
        use_cache: bool = True,
        js_render: bool = True,
        wait_for: str | None = None,
        extract_schema: str | None = None,
    ) -> FetchResult:
        """Fetch a URL with full reliability chain."""
        start = time.time()
        domain = self._domain(url)

        # 1. Cache check
        if use_cache:
            cached = self.cache.get(url, extract_schema)
            if cached:
                return FetchResult(
                    url=url,
                    success=True,
                    markdown=cached.get("markdown"),
                    html=cached.get("html"),
                    status_code=cached.get("status_code"),
                    cached=True,
                    elapsed_ms=int((time.time() - start) * 1000),
                    domain_status=self.circuit.get_status(domain)["state"],
                )

        # 2. Circuit breaker check
        if not self.circuit.can_request(domain):
            status = self.circuit.get_status(domain)
            return FetchResult(
                url=url,
                success=False,
                error=f"Circuit breaker OPEN for {domain}. "
                      f"Too many failures ({status['failure_count']}). "
                      f"Retry in {status['cooldown_remaining']:.0f}s.",
                domain_status="open",
                elapsed_ms=int((time.time() - start) * 1000),
            )

        # 3. Try browser fetch with retries
        last_error = None
        attempts = 0

        if js_render:
            for attempt in range(self.max_retries):
                attempts += 1
                try:
                    result = await self._browser_fetch(url, wait_for)
                    if result.success:
                        self.circuit.record_success(domain)
                        if use_cache:
                            self.cache.set(url, {
                                "markdown": result.markdown,
                                "html": result.html,
                                "status_code": result.status_code,
                            }, extract_schema)
                        result.attempts = attempts
                        result.elapsed_ms = int((time.time() - start) * 1000)
                        result.domain_status = self.circuit.get_status(domain)["state"]
                        return result
                    last_error = result.error
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"Browser fetch attempt {attempt + 1} failed for {url}: {e}")

                # Exponential backoff with jitter
                if attempt < self.max_retries - 1:
                    delay = min(2 ** attempt + random.uniform(0, 1), 10)
                    await asyncio.sleep(delay)

        # 4. Fallback: plain HTTP
        attempts += 1
        try:
            result = await self._http_fetch(url)
            if result.success:
                self.circuit.record_success(domain)
                if use_cache:
                    self.cache.set(url, {
                        "markdown": result.markdown,
                        "html": result.html,
                        "status_code": result.status_code,
                    }, extract_schema)
                result.attempts = attempts
                result.elapsed_ms = int((time.time() - start) * 1000)
                result.domain_status = self.circuit.get_status(domain)["state"]
                return result
            last_error = result.error
        except Exception as e:
            last_error = str(e)

        # 5. All strategies failed
        self.circuit.record_failure(domain)
        return FetchResult(
            url=url,
            success=False,
            error=f"All fetch strategies failed after {attempts} attempts. Last error: {last_error}",
            attempts=attempts,
            elapsed_ms=int((time.time() - start) * 1000),
            domain_status=self.circuit.get_status(domain)["state"],
        )

    async def _browser_fetch(self, url: str, wait_for: str | None = None) -> FetchResult:
        """Fetch using Crawl4AI with stealth and JS rendering."""
        run_cfg = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=self.timeout,
            wait_until="domcontentloaded",
            magic=True,
            simulate_user=True,
            override_navigator=True,
            remove_overlay_elements=True,
            verbose=False,
        )
        if wait_for:
            run_cfg.wait_for = f"css:{wait_for}"

        async with AsyncWebCrawler(config=self.browser_cfg) as crawler:
            result = await crawler.arun(url=url, config=run_cfg)

        if result.success:
            return FetchResult(
                url=url,
                success=True,
                markdown=result.markdown or "",
                html=result.html or "",
                status_code=result.status_code,
            )
        return FetchResult(
            url=url,
            success=False,
            error=f"Browser fetch failed: status {result.status_code}",
            status_code=result.status_code,
        )

    async def _http_fetch(self, url: str) -> FetchResult:
        """Lightweight HTTP fallback — no JS rendering but fast and reliable."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout / 1000,
            headers=headers,
            verify=False,  # fallback doesn't need strict SSL
        ) as client:
            resp = await client.get(url)

        if resp.status_code == 200:
            # Convert HTML to basic markdown-ish text
            html = resp.text
            return FetchResult(
                url=url,
                success=True,
                markdown=self._html_to_text(html),
                html=html,
                status_code=resp.status_code,
            )
        return FetchResult(
            url=url,
            success=False,
            error=f"HTTP fallback returned status {resp.status_code}",
            status_code=resp.status_code,
        )

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Crude HTML → text. Crawl4AI handles the real markdown conversion."""
        import re
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def check_domain(self, domain: str) -> dict:
        """Get circuit breaker status for a domain."""
        return self.circuit.get_status(domain)

    def cache_stats(self) -> dict:
        """Get cache statistics."""
        return self.cache.stats()

    def clear_cache(self) -> dict:
        """Clear the fetch cache."""
        self.cache.clear()
        return {"cleared": True}
