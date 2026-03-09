# astro-mcp

**Astrological MCP Server** — high-precision astrology tools for LLM agents.

Implements 14 tools backed by Swiss Ephemeris (`pyswisseph`) and integrates with any [Model Context Protocol](https://modelcontextprotocol.io) client (Claude Desktop, etc.).

## Tools

| # | Name | Description |
|---|---|---|
| 1 | `calculate_natal_chart` | Full natal chart: planets, angles, houses, aspects |
| 2 | `calculate_transits` | Transit aspects to natal chart |
| 3 | `calculate_secondary_progressions` | Day-for-a-year progressions + Solar Arc |
| 4 | `calculate_solar_return` | Annual solar return chart |
| 5 | `calculate_rectification_hints` | Score candidate birth times against life events |
| 6 | `calculate_lunar_return` | Monthly lunar return chart(s) |
| 7 | `calculate_synastry` | Cross-chart aspects + house overlays |
| 8 | `calculate_composite_chart` | Midpoint or Davison composite chart |
| 9 | `calculate_profections` | Annual profection — year lord and activated houses |
| 10 | `get_planetary_hours` | 24 planetary hours for any day/location |
| 11 | `calculate_arabic_parts` | 7 Arabic Parts (Fortune, Spirit, Marriage, etc.) |
| 12 | `get_ephemeris` | Planet position table over a date range |
| 13 | `find_aspect_exact_dates` | Find exact dates of a specific aspect |
| 14 | `calculate_antiscia` | Antiscia and contra-antiscia points |

## Installation

```bash
# 1. Clone
git clone https://github.com/your-org/astro-mcp
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

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `EPHE_PATH` | `./ephe` | Path to Swiss Ephemeris `.se1` data files |
| `GEOCODING_PROVIDER` | `nominatim` | `nominatim` or `opencage` |
| `OPENCAGE_API_KEY` | — | Required if `GEOCODING_PROVIDER=opencage` |
| `GEOCODING_USER_AGENT` | `astro-mcp/1.0` | Nominatim user-agent |
| `GEOCODE_CACHE_SIZE` | `512` | LRU cache size for geocoding results |
| `DEFAULT_HOUSE_SYSTEM` | `P` | `P`=Placidus, `W`=Whole Sign, `K`=Koch |
| `DEFAULT_ORB_FACTOR` | `1.0` | Global orb multiplier (0.5–1.5) |
| `LOG_LEVEL` | `WARNING` | Python logging level |

## Architecture

```
src/astro_mcp/
├── server.py              # MCP server — tool registration and dispatch
├── config.py              # Settings from environment variables
├── core/
│   ├── models.py          # Data models and astrological constants
│   ├── ephemeris_provider.py  # Swiss Ephemeris wrapper (pyswisseph)
│   ├── geocoding.py       # City → lat/lon/tz (geopy + timezonefinder)
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

## Testing

```bash
pytest tests/ -v --cov=src/astro_mcp --cov-report=term-missing
```

Reference charts (`tests/reference_data/`) are verified against Astro.com and Solar Fire.

## License

MIT
