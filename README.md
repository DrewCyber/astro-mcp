# astro-mcp

**Astrological MCP Server** — high-precision astrology tools for LLM agents.

Implements 14 tools backed by Swiss Ephemeris (`pyswisseph`) and integrates with any [Model Context Protocol](https://modelcontextprotocol.io) client (Claude Desktop, etc.).

Runs locally over stdio **or** remotely over streamable HTTP — including as a claude.ai custom connector on the free plan:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/DrewCyber/astro-mcp)

**New to claude.ai connectors?** A step-by-step guide in Russian — connecting the
free shared instance or deploying your own with one button, project setup and
example prompts — lives at **[drewcyber.github.io/astro-mcp](https://drewcyber.github.io/astro-mcp/)**.

## Tools

| # | Name | Description |
|---|---|---|
| 1 | `calculate_natal_chart` | Full natal chart: planets, angles, houses, aspects |
| 2 | `calculate_transits` | Transit aspects to natal chart, Moon phase, lunations and void-of-course |
| 3 | `calculate_secondary_progressions` | Day-for-a-year progressions + Solar Arc |
| 4 | `calculate_solar_return` | Annual solar return chart |
| 5 | `calculate_rectification_hints` | Score candidate birth times against life events |
| 6 | `calculate_lunar_return` | Monthly lunar return chart(s) |
| 7 | `calculate_synastry` | Cross-chart aspects + house overlays |
| 8 | `calculate_composite_chart` | Midpoint or Davison composite chart |
| 9 | `calculate_profections` | Annual profection — year lord and activated houses |
| 10 | `get_planetary_hours` | 24 planetary hours for any day/location |
| 11 | `calculate_arabic_parts` | 12 Arabic Parts / Lots (Fortune, Spirit, Marriage, etc.) |
| 12 | `get_ephemeris` | Planet position table over a date range |
| 13 | `find_aspect_exact_dates` | Find exact dates of a specific aspect |
| 14 | `calculate_antiscia` | Antiscia and contra-antiscia points, with optional transit contacts |

## Installation

```bash
# 1. Clone
git clone https://github.com/DrewCyber/astro-mcp
cd astro-mcp

# 2. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install package + dev dependencies
pip install -e ".[dev]"

# 4. Download Swiss Ephemeris data files
bash scripts/download_ephe.sh

# 5. Set environment variable
export EPHE_PATH="$(pwd)/ephe"

# 6. Run tests
pytest tests/
```

## Claude Desktop configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "astro": {
      "command": "/path/to/astro-mcp/.venv/bin/python",
      "args": ["-m", "astro_mcp"],
      "env": {
        "EPHE_PATH": "/path/to/astro-mcp/ephe",
        "GEOCODING_PROVIDER": "nominatim",
        "GEOCODING_USER_AGENT": "astro-mcp/1.0",
        "LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

## Remote hosting (claude.ai and other web clients)

Free claude.ai accounts can connect one custom connector — a remote MCP server
at a public HTTPS URL. Set `ASTRO_MCP_TRANSPORT=http` and the server exposes
the same tools over stateless streamable HTTP at `/mcp` (plus `/health` for
uptime pings):

```bash
export ASTRO_MCP_TRANSPORT=http
python -m astro_mcp    # serves http://127.0.0.1:8080/mcp
```

The fastest path is the **Deploy to Render** button above (free, no credit
card). A prebuilt image is also published to GHCR on every release —
`docker run -d -p 8080:8080 ghcr.io/drewcyber/astro-mcp:latest` serves
`http://localhost:8080/mcp` with zero build steps. For a public shared
instance, quick `cloudflared` tunnels, Google Cloud Run, Koyeb and
troubleshooting, see **[DEPLOY.md](DEPLOY.md)**.

### HTTP admission and header validation

Local HTTP (`HOST=127.0.0.1`, or `localhost` / `::1`) uses the MCP SDK's
Host/Origin guard automatically. Use an explicit port, e.g.
`http://localhost:8080/mcp`: the SDK's automatic loopback patterns require a
port. Foreign Host headers receive HTTP 421; disallowed Origins receive 403.
Requests without an Origin header are allowed when their Host is allowed.

Containers retain `HOST=0.0.0.0` and public, unauthenticated access by default;
without explicit allowlists, the SDK does not apply the loopback header guard.
For a deployed service, enable explicit validation with JSON lists:

```bash
export HOST=0.0.0.0
export HTTP_ALLOWED_HOSTS='["myapp.onrender.com", "myapp.onrender.com:*"]'
export HTTP_ALLOWED_ORIGINS='["https://your-browser-client.example"]'
export HTTP_MAX_CONCURRENT_REQUESTS=16
```

Use the actual Host and browser Origin values reaching the service. Hosts have
no scheme; Origins include the scheme and omit paths. The SDK supports a `:*`
port suffix; include the bare hostname separately for standard-port traffic.
Setting either list enables validation and replaces automatic defaults: an
unset/empty hosts list denies all MCP requests, while an unset/empty origins
list denies requests carrying Origin (requests without Origin still work).
These are header checks, not CORS configuration or authentication.

For local cloudflared tunnels, the foreign public Host is no longer implicitly
accepted on a loopback binding. Set explicit allowlists for the tunnel hostname
and expected Origins, then restart the server; update them when the tunnel URL
changes. Alternatively `HOST=0.0.0.0` without allowlists retains public behavior,
but also binds all network interfaces, so use appropriate network restrictions.

At most `HTTP_MAX_CONCURRENT_REQUESTS` MCP HTTP exchanges (default **16**) are
active per app/worker. Overflow gets **503** with **Retry-After: 2** immediately,
without a waiting queue; clients should back off. Slots remain held through the
whole response and are released on completion, errors or cancellation.
`/health` bypasses admission and header validation. This limit does not bound
proxy/socket queues, total request rate, or CPU execution time; synchronous
calculations can still delay the event loop and health responses.

No authentication or per-client quotas are introduced. Header allowlists do
not identify clients and are not an abuse-prevention boundary. Private access
and fair-use quotas remain optional deployment work (e.g. an authenticated
proxy with deliberately configured trusted-proxy/client identity handling).
Multiple workers or replicas each have their own admission limit.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ASTRO_MCP_TRANSPORT` | `stdio` | `stdio` for local clients, `http` for remote streamable-HTTP (`/mcp`) |
| `HOST` | `127.0.0.1` | Bind address for the HTTP transport (containers want `0.0.0.0`) |
| `PORT` | `8080` | Port for the HTTP transport |
| `HTTP_ALLOWED_HOSTS` | unset | Optional JSON list of allowed Host headers; enables SDK validation |
| `HTTP_ALLOWED_ORIGINS` | unset | Optional JSON list of allowed Origin headers; enables SDK validation |
| `HTTP_MAX_CONCURRENT_REQUESTS` | `16` | Positive per-worker active MCP request limit; overflow returns 503 without queueing |
| `EPHE_PATH` | `./ephe` | Path to Swiss Ephemeris `.se1` data files |
| `GEOCODING_PROVIDER` | `nominatim` | `nominatim` or `opencage` |
| `OPENCAGE_API_KEY` | — | Required if `GEOCODING_PROVIDER=opencage` |
| `GEOCODING_USER_AGENT` | `astro-mcp/1.0` | Nominatim user-agent |
| `GEOCODE_CACHE_SIZE` | `512` | LRU cache size for geocoding results |
| `GEOCODE_CACHE_PATH` | `~/.cache/astro-mcp/geocode.json` | Persistent geocode cache so lookups survive a restart. Stores only city → lat/lon/tz. Set empty to disable |
| `DEFAULT_HOUSE_SYSTEM` | `P` | `P`=Placidus, `W`=Whole Sign, `K`=Koch |
| `DEFAULT_ORB_FACTOR` | `1.0` | Global orb multiplier (0.1–3.0) |
| `NODE_TYPE` | `true` | `true`=True Node, `mean`=Mean Node (applied consistently across all tools) |
| `LOG_LEVEL` | `WARNING` | Python logging level |

## Architecture

```
src/astro_mcp/
├── server.py              # MCP server — tool registration and dispatch
├── schemas.py             # Pydantic input models (source of the JSON schemas)
├── config.py              # Settings from environment variables
├── core/
│   ├── models.py          # Data models and astrological constants
│   ├── errors.py          # AstroError and the structured error codes
│   ├── ephemeris_provider.py  # Swiss Ephemeris wrapper (pyswisseph)
│   ├── geocoding.py       # City → lat/lon/tz (geopy + timezonefinder)
│   ├── moon.py            # Lunar phase, lunations and void-of-course
│   └── formatters.py      # LLM-optimized serialization
└── tools/
    ├── natal.py           # Tool 1
    ├── transits.py        # Tool 2
    ├── progressions.py    # Tool 3
    ├── returns.py         # Tools 4 + 6
    ├── rectification.py   # Tool 5
    ├── synastry.py        # Tools 7 + 8
    ├── profections.py     # Tool 9
    ├── planetary_hours.py # Tool 10
    ├── arabic_parts.py    # Tool 11
    ├── ephemeris.py       # Tools 12 + 13
    └── antiscia.py        # Tool 14
```

## Output Format

All tools return compact JSON without whitespace to minimise LLM context tokens (~75% smaller than verbose JSON). Planet codes are abbreviated (`Su`, `Mo`, `Me`, etc.), aspects use 3-letter codes (`Cnj`, `Tri`, `Squ`), and the retrograde flag (`"R":true`) is omitted when direct to save additional tokens.

Failures use the same contract, so a client never has to parse prose:

```json
{"error":true,"code":"INPUT_ERROR","message":"Invalid arguments for 'calculate_natal_chart'.","hint":"birth_location.lat: Input should be less than or equal to 90"}
```

## Planet Codes

Supported codes across tools:

- `Su` Sun
- `Mo` Moon
- `Me` Mercury
- `Ve` Venus
- `Ma` Mars
- `Ju` Jupiter
- `Sa` Saturn
- `Ur` Uranus
- `Ne` Neptune
- `Pl` Pluto
- `Ch` Chiron
- `Li` Black Moon Lilith (Mean Apogee)
- `NN` North Node (True Node by default; Mean Node when `NODE_TYPE=mean`)
- `SN` South Node
- Asteroids (where `include_asteroids` is supported): `Ce` Ceres, `Pa` Pallas, `Jun` Juno, `Ves` Vesta

Pass `include_legend: true` to `calculate_natal_chart` or `calculate_transits`
to get a one-shot decoding dictionary for all codes. Aspect entries carry a
`sig` field (0–1 significance: body weight × aspect weight × orb tightness);
`min_significance` / `top_n` trim the lists, and `degree_format` defaults to
`"dec"` (`"dms"` restores human-readable degree strings).

## API Notes

- `get_ephemeris` accepts either a single `planet` or a list of planets.
- `get_ephemeris.step` supports `1h`, `2h`, `3h`, `6h`, `12h`, `1d`, `7d`, `30d`.
- `get_ephemeris` now returns a `timezone` field and formats `dt` in `output_tz`.
- `find_aspect_exact_dates.mode` supports:
  - `transit-to-transit` for two moving bodies
  - `transit-to-natal` for transit to a natal planet/angle
  - `auto` (default) infers mode from presence of `birth_*`

## Testing

```bash
pytest tests/ -v --cov=src/astro_mcp --cov-report=term-missing
```

Golden-chart regressions live inline in the test suite (`tests/test_audit_regressions.py`) and were verified against Astro.com and Solar Fire.

## License

MIT
