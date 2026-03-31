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


# Custom routes
from starlette.requests import Request
from starlette.responses import JSONResponse, HTMLResponse


@mcp.custom_route("/", methods=["GET"])
async def landing(request: Request) -> HTMLResponse:
    cache = fetcher.cache_stats()
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SteadyFetch — Reliable Web Fetching for AI Agents</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 3rem 1.5rem; }}
  .container {{ max-width: 720px; width: 100%; }}
  h1 {{ font-size: 2.5rem; font-weight: 700; color: #fff; margin-bottom: 0.5rem; }}
  h1 span {{ color: #22c55e; }}
  .tagline {{ font-size: 1.15rem; color: #888; margin-bottom: 2.5rem; line-height: 1.6; }}
  .status {{ display: inline-flex; align-items: center; gap: 0.5rem; background: #111; border: 1px solid #222; border-radius: 999px; padding: 0.4rem 1rem; font-size: 0.85rem; margin-bottom: 2rem; }}
  .dot {{ width: 8px; height: 8px; background: #22c55e; border-radius: 50%; animation: pulse 2s infinite; }}
  @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}
  .section {{ background: #111; border: 1px solid #1a1a1a; border-radius: 12px; padding: 1.5rem; margin-bottom: 1.25rem; }}
  .section h2 {{ font-size: 1rem; color: #22c55e; margin-bottom: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }}
  .tools {{ display: grid; gap: 0.5rem; }}
  .tool {{ display: flex; justify-content: space-between; align-items: baseline; padding: 0.5rem 0; border-bottom: 1px solid #1a1a1a; }}
  .tool:last-child {{ border-bottom: none; }}
  .tool-name {{ font-family: 'SF Mono', 'Fira Code', monospace; color: #22c55e; font-size: 0.9rem; }}
  .tool-desc {{ color: #666; font-size: 0.85rem; text-align: right; }}
  pre {{ background: #0d0d0d; border: 1px solid #1a1a1a; border-radius: 8px; padding: 1rem; overflow-x: auto; font-size: 0.85rem; color: #ccc; line-height: 1.5; }}
  .stats {{ display: flex; gap: 2rem; }}
  .stat {{ text-align: center; }}
  .stat-val {{ font-size: 1.5rem; font-weight: 700; color: #fff; }}
  .stat-label {{ font-size: 0.75rem; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }}
  .features {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }}
  .feature {{ font-size: 0.9rem; color: #aaa; padding-left: 1.25rem; position: relative; }}
  .feature::before {{ content: ''; position: absolute; left: 0; top: 0.5em; width: 6px; height: 6px; background: #22c55e; border-radius: 50%; }}
  a {{ color: #22c55e; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .footer {{ margin-top: 2rem; color: #444; font-size: 0.8rem; text-align: center; }}
</style>
</head>
<body>
<div class="container">
  <div class="status"><span class="dot"></span> Operational</div>
  <h1>Steady<span>Fetch</span></h1>
  <p class="tagline">Reliable web fetching for AI agents. Retry, circuit breaker, caching, and anti-bot bypass — so your agents stop breaking on Cloudflare.</p>

  <div class="section">
    <h2>Connect</h2>
    <pre>{{
  "mcpServers": {{
    "steadyfetch": {{
      "url": "https://steadyfetch-production.up.railway.app/mcp"
    }}
  }}
}}</pre>
  </div>

  <div class="section">
    <h2>Tools</h2>
    <div class="tools">
      <div class="tool"><span class="tool-name">fetch_url</span><span class="tool-desc">Full reliability fetch — markdown + HTML</span></div>
      <div class="tool"><span class="tool-name">fetch_markdown</span><span class="tool-desc">Clean text optimized for LLMs</span></div>
      <div class="tool"><span class="tool-name">check_domain</span><span class="tool-desc">Circuit breaker status for any domain</span></div>
      <div class="tool"><span class="tool-name">cache_stats</span><span class="tool-desc">Cache utilization metrics</span></div>
      <div class="tool"><span class="tool-name">clear_cache</span><span class="tool-desc">Flush cache for fresh data</span></div>
    </div>
  </div>

  <div class="section">
    <h2>How It Works</h2>
    <div class="features">
      <div class="feature">Stealth browser with anti-bot bypass</div>
      <div class="feature">Retry with exponential backoff + jitter</div>
      <div class="feature">Per-domain circuit breaker</div>
      <div class="feature">HTTP fallback when browser fails</div>
      <div class="feature">Disk cache with 1hr TTL</div>
      <div class="feature">Clean markdown output for LLMs</div>
    </div>
  </div>

  <div class="section">
    <h2>Live Stats</h2>
    <div class="stats">
      <div class="stat"><div class="stat-val">{cache['item_count']}</div><div class="stat-label">Cached Pages</div></div>
      <div class="stat"><div class="stat-val">{cache['size_bytes'] // 1024}KB</div><div class="stat-label">Cache Size</div></div>
      <div class="stat"><div class="stat-val">v0.1.0</div><div class="stat-label">Version</div></div>
    </div>
  </div>

  <p class="footer">
    <a href="/health">Health Check</a> &middot;
    <a href="https://github.com/carsonlabs/steadyfetch">GitHub</a> &middot;
    Built by <a href="https://freedomengineers.tech">Freedom Engineers</a>
  </p>
</div>
</body>
</html>""")


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
