"""SteadyFetch MCP Server — Reliable web fetching for AI agents.

Tools:
  fetch_url       — Fetch any URL with full reliability (retry, circuit breaker, cache, anti-bot)
  fetch_markdown  — Fetch a URL and return clean markdown optimized for LLMs
  check_domain    — Check if a domain is healthy or circuit-broken
  cache_stats     — Get cache hit/miss statistics
  clear_cache     — Clear the fetch cache
"""

import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP, Context

from .fetcher import SteadyFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("steadyfetch")

# Server config from env
MAX_RETRIES = int(os.environ.get("STEADYFETCH_MAX_RETRIES", "3"))
CIRCUIT_THRESHOLD = int(os.environ.get("STEADYFETCH_CIRCUIT_THRESHOLD", "5"))
CIRCUIT_COOLDOWN = float(os.environ.get("STEADYFETCH_CIRCUIT_COOLDOWN", "120"))
CACHE_TTL = int(os.environ.get("STEADYFETCH_CACHE_TTL", "3600"))
TIMEOUT = int(os.environ.get("STEADYFETCH_TIMEOUT", "30000"))

# Initialize
fetcher = SteadyFetcher(
    max_retries=MAX_RETRIES,
    circuit_threshold=CIRCUIT_THRESHOLD,
    circuit_cooldown=CIRCUIT_COOLDOWN,
    cache_ttl=CACHE_TTL,
    timeout=TIMEOUT,
)

mcp = FastMCP(
    "steadyfetch",
    instructions=(
        "SteadyFetch provides reliable web fetching for AI agents. "
        "Use fetch_url to get any webpage with automatic retry, anti-bot bypass, "
        "circuit breaker protection, and caching. Use fetch_markdown for LLM-optimized "
        "clean text. Use check_domain to see if a site is currently reachable."
    ),
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "8200")),
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def fetch_url(
    url: str,
    use_cache: bool = True,
    js_render: bool = True,
    wait_for: str | None = None,
    ctx: Context = None,
) -> str:
    """Fetch a URL with full reliability — retry, circuit breaker, cache, and anti-bot bypass.

    Returns both raw HTML and clean markdown. Automatically retries on failure
    with exponential backoff, falls back to plain HTTP if browser fetch fails,
    and circuit-breaks domains that are consistently down.

    Args:
        url: The URL to fetch
        use_cache: Whether to use cached results (default: true, TTL 1 hour)
        js_render: Whether to render JavaScript (default: true, disable for speed)
        wait_for: CSS selector to wait for before capturing (e.g., '.results-loaded')
    """
    if ctx:
        ctx.info(f"Fetching {url} (cache={use_cache}, js={js_render})")

    result = await fetcher.fetch(
        url=url,
        use_cache=use_cache,
        js_render=js_render,
        wait_for=wait_for,
    )

    if ctx and result.cached:
        ctx.info("Returned from cache")

    return json.dumps(result.to_dict(), indent=2)


@mcp.tool()
async def fetch_markdown(
    url: str,
    use_cache: bool = True,
    wait_for: str | None = None,
    ctx: Context = None,
) -> str:
    """Fetch a URL and return clean markdown text optimized for LLM consumption.

    Same reliability as fetch_url but returns only the markdown content,
    stripping HTML, scripts, and noise. Best for when you need the page
    content for analysis, summarization, or data extraction.

    Args:
        url: The URL to fetch
        use_cache: Whether to use cached results (default: true)
        wait_for: CSS selector to wait for before capturing
    """
    if ctx:
        ctx.info(f"Fetching markdown for {url}")

    result = await fetcher.fetch(
        url=url,
        use_cache=use_cache,
        js_render=True,
        wait_for=wait_for,
    )

    if not result.success:
        return json.dumps({
            "success": False,
            "error": result.error,
            "domain_status": result.domain_status,
        })

    return result.markdown or ""


@mcp.tool()
async def check_domain(domain: str) -> str:
    """Check the health status of a domain.

    Returns the circuit breaker state: 'closed' (healthy), 'open' (failing),
    or 'half_open' (testing recovery). Use this before batch operations to
    avoid wasting time on domains that are down.

    Args:
        domain: The domain to check (e.g., 'example.com')
    """
    status = fetcher.check_domain(domain)
    return json.dumps(status, indent=2)


@mcp.tool()
async def cache_stats() -> str:
    """Get cache statistics — size and item count.

    Useful for monitoring cache utilization and deciding when to clear.
    """
    stats = fetcher.cache_stats()
    return json.dumps(stats, indent=2)


@mcp.tool()
async def clear_cache() -> str:
    """Clear the entire fetch cache.

    Use when you need fresh data and don't want to rely on cached results.
    """
    result = fetcher.clear_cache()
    return json.dumps(result)


# Health check endpoint
from starlette.requests import Request
from starlette.responses import JSONResponse


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({
        "status": "healthy",
        "service": "steadyfetch",
        "version": "0.1.0",
        "cache": fetcher.cache_stats(),
    })


def main():
    transport = os.environ.get("STEADYFETCH_TRANSPORT", "streamable-http")
    logger.info(f"Starting SteadyFetch MCP server (transport={transport})")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
