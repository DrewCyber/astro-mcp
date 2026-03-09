#!/usr/bin/env bash
# Download Swiss Ephemeris data files required for high-precision calculations.
# Files are fetched from the official Swiss Ephemeris GitHub repository:
# https://github.com/aloistr/swisseph/tree/master/ephe

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EPHE_DIR="${SCRIPT_DIR}/../ephe"

mkdir -p "$EPHE_DIR"
cd "$EPHE_DIR"

BASE_URL="https://raw.githubusercontent.com/aloistr/swisseph/master/ephe"

FILES=(
    "seas_18.se1"   # Asteroids  1800–2400
    "sepl_18.se1"   # Planets    1800–2400
    "semo_18.se1"   # Moon       1800–2400
    "fixstars.cat"  # Fixed stars catalogue
)

# Optional extended-range files (uncomment if you need dates outside 1800–2400):
# EXTENDED=(
#     "sepl_06.se1"  # Planets  600–1800
#     "semo_06.se1"  # Moon     600–1800
#     "sepl_30.se1"  # Planets 2400–3000
# )

echo "Downloading Swiss Ephemeris files to: $EPHE_DIR"

for FILE in "${FILES[@]}"; do
    if [[ -f "$FILE" ]]; then
        echo "  [skip] $FILE already exists"
    else
        echo "  [download] $FILE"
        if command -v curl &>/dev/null; then
            curl -sSfL --retry 3 -o "$FILE" "${BASE_URL}/${FILE}"
        elif command -v wget &>/dev/null; then
            wget -q --tries=3 -O "$FILE" "${BASE_URL}/${FILE}"
        else
            echo "ERROR: neither curl nor wget found. Install one and retry." >&2
            exit 1
        fi
        echo "  [done] $FILE ($(du -sh "$FILE" | cut -f1))"
    fi
done

echo ""
echo "Done. Set EPHE_PATH=$(pwd) in your environment."
