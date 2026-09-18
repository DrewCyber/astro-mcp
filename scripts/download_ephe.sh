#!/usr/bin/env bash
# Official Swiss Ephemeris data, pinned to an immutable upstream revision.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EPHE_DIR="${EPHE_PATH:-${SCRIPT_DIR}/../ephe}"
REVISION="9083a12d59e98034fb2337061481ac8800c16e64"
BASE_URL="https://raw.githubusercontent.com/aloistr/swisseph/${REVISION}/ephe"
mkdir -p "$EPHE_DIR"
cd "$EPHE_DIR"

FILES=(seas_18.se1 sepl_18.se1 semo_18.se1 sefstars.txt)
HASHES=(
    a2cd8fc33807c78ca9a700c91c2e042258b12fc4796519e00781440b5ad8b2e2
    ca1393ceab3a44fbc895887cf789c68819ae6a1cbc9b22225872dbe4ccd99a66
    1ca07bd67c24374d77226180c20a4f9996cba013697894810518e7eb582ca4f7
    18b0dcafbe5b7240773daba2c038a325f5b3fc4163f61e0a7f4e92abd4f517c6
)

checksum() {
    if command -v sha256sum >/dev/null; then
        sha256sum "$1" | cut -d ' ' -f 1
    else
        shasum -a 256 "$1" | cut -d ' ' -f 1
    fi
}

temporary=""
trap 'if [[ -n "$temporary" ]]; then rm -f "$temporary"; fi' EXIT
for i in "${!FILES[@]}"; do
    file="${FILES[$i]}"
    expected="${HASHES[$i]}"
    if [[ -f "$file" ]] && [[ "$(checksum "$file")" == "$expected" ]]; then
        printf '  [verified] %s\n' "$file"
        continue
    fi
    temporary="$(mktemp "./.${file}.XXXXXX")"
    if command -v curl >/dev/null; then
        curl -sSfL --retry 3 -o "$temporary" "${BASE_URL}/${file}"
    elif command -v wget >/dev/null; then
        wget -q --tries=3 -O "$temporary" "${BASE_URL}/${file}"
    else
        printf 'ERROR: install curl or wget.\n' >&2
        exit 1
    fi
    if [[ "$(checksum "$temporary")" != "$expected" ]]; then
        printf 'ERROR: checksum mismatch for %s; installed file unchanged.\n' "$file" >&2
        exit 1
    fi
    chmod 644 "$temporary"
    mv -f "$temporary" "$file"
    temporary=""
    printf '  [installed] %s\n' "$file"
done
