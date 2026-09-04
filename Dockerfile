# Remote MCP server image: streamable-HTTP transport for claude.ai connectors.
# Build:  docker build -t astro-mcp .
#         (on Apple Silicon add: --platform linux/amd64 — pyswisseph publishes
#          cp311 wheels for x86_64 only, other platforms compile from sdist)
# Run:    docker run --rm -p 8080:8080 astro-mcp   ->  http://localhost:8080/mcp
#
# Python 3.11 on purpose: pyswisseph 2.10.3.2 ships manylinux wheels only for
# cp311, so the install needs no C toolchain and the image stays small.
FROM python:3.11-slim

# curl is needed for the HEALTHCHECK; bash for scripts/download_ephe.sh.
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the package; README.md is referenced by pyproject.toml metadata.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Swiss Ephemeris data (~2 MB, 1800-2400). Downloaded at build time; the
# files are gitignored in the repo, so COPY cannot be used.
COPY scripts ./scripts
RUN bash scripts/download_ephe.sh

ENV ASTRO_MCP_TRANSPORT=http \
    HOST=0.0.0.0 \
    PORT=8080 \
    EPHE_PATH=/app/ephe \
    GEOCODE_CACHE_PATH=/tmp/geocode.json \
    PYTHONUNBUFFERED=1

# Run as an unprivileged user; /tmp is writable for the geocode cache.
RUN useradd --create-home --uid 1000 astro
USER astro

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1

CMD ["astro-mcp"]
