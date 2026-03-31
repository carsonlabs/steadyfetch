# SteadyFetch

**Reliable web fetching for AI agents.** Stop losing hours to Cloudflare blocks, timeouts, and flaky scrapes.

SteadyFetch is an MCP server that gives your AI agents reliable web access with automatic retry, circuit breaker protection, caching, and anti-bot bypass — out of the box.

## The Problem

Every AI agent that touches the web hits the same wall:
- Cloudflare blocks your requests
- Sites return CAPTCHAs
- Pages timeout or load partially
- Rate limits kill your batch jobs
- You waste hours debugging flaky scrapes

## The Solution

One MCP tool call. SteadyFetch handles the rest.

```
Agent calls fetch_url("https://example.com")
  → Checks cache (instant if hit)
  → Checks circuit breaker (fail-fast if domain is down)
  → Stealth browser fetch with anti-bot bypass
  → On failure: retry with exponential backoff
  → Fallback: plain HTTP fetch
  → Cache the result
  → Return clean markdown + raw HTML
```

## Tools

| Tool | Description |
|------|-------------|
| `fetch_url` | Full reliability fetch — returns markdown + HTML |
| `fetch_markdown` | Returns only clean markdown, optimized for LLMs |
| `check_domain` | Circuit breaker status for a domain |
| `cache_stats` | Cache utilization metrics |
| `clear_cache` | Flush the cache for fresh data |

## Quick Start

### As MCP Server (remote)

Connect to the hosted server:

```json
{
  "mcpServers": {
    "steadyfetch": {
      "url": "https://your-steadyfetch-instance.up.railway.app/mcp"
    }
  }
}
```

### Self-hosted

```bash
pip install steadyfetch
steadyfetch
```

Or with Docker:

```bash
docker build -t steadyfetch .
docker run -p 8200:8200 steadyfetch
```

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8200 | Server port |
| `STEADYFETCH_MAX_RETRIES` | 3 | Retry attempts per URL |
| `STEADYFETCH_CIRCUIT_THRESHOLD` | 5 | Failures before circuit opens |
| `STEADYFETCH_CIRCUIT_COOLDOWN` | 120 | Seconds before retrying a broken domain |
| `STEADYFETCH_CACHE_TTL` | 3600 | Cache lifetime in seconds |
| `STEADYFETCH_TIMEOUT` | 30000 | Page load timeout in ms |

## How It Works

**Retry with backoff** — Exponential backoff + jitter prevents retry storms. 3 browser attempts before falling back to HTTP.

**Circuit breaker** — Per-domain failure tracking. After 5 consecutive failures, the domain is circuit-broken for 2 minutes. Prevents wasting time on sites that are blocking you.

**Caching** — Disk-backed cache with configurable TTL. Repeat fetches are instant. 500MB default limit.

**Anti-bot bypass** — Stealth browser with magic mode, navigator patching, and human-like behavior simulation via Crawl4AI.

**Graceful degradation** — If the browser can't get through, falls back to plain HTTP. If HTTP fails, returns a clear error with domain health status. Never hangs, never silently fails.

## License

MIT
