# astro-mcp

**Astrological MCP Server** — high-precision astrology tools for LLM agents.

Implements 14 tools backed by Swiss Ephemeris (`pyswisseph`) and integrates with any [Model Context Protocol](https://modelcontextprotocol.io) client (Claude Desktop, etc.).

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
| `GEOCODE_CACHE_PATH` | `~/.cache/astro-mcp/geocode.json` | Persistent geocode cache so lookups survive a restart. Stores only city → lat/lon/tz. Set empty to disable |
| `DEFAULT_HOUSE_SYSTEM` | `P` | `P`=Placidus, `W`=Whole Sign, `K`=Koch |
| `DEFAULT_ORB_FACTOR` | `1.0` | Global orb multiplier (0.5–1.5) |
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
- `NN` North Node (True Node)
- `SN` South Node

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

Reference charts (`tests/reference_data/`) are verified against Astro.com and Solar Fire.

## License

MIT
