"""Regression tests for ``scripts/download_ephe.sh``.

The script's contract: a file is installed only when its bytes match the
pinned SHA-256, a failed or mismatched download leaves the previously
installed copy untouched, and no partial/temporary file survives the run.

Exercising that against the real ~2 MB upstream files would put network
downloads in the unit suite, so the behavioural tests run a copy of the real
script whose ``FILES``/``HASHES`` arrays are substituted for tiny fixture
content, served by a fake ``curl``/``wget`` on ``PATH`` (no network). Static
tests pin the *real* script's structure and the fact that CI validates the
cache after every restore instead of trusting a cache hit.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "download_ephe.sh"
CI_WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

FILE_NAMES = ["seas_18.se1", "sepl_18.se1", "semo_18.se1", "sefstars.txt"]

FAKE_CURL = r"""#!/usr/bin/env sh
# Minimal curl stand-in: `curl -o OUT URL` copies FAKE_SERVE_DIR/<name>.
# A sibling `<name>.fail` makes the transfer fail after writing nothing; a
# `<name>.truncate` writes partial bytes and fails (interrupted transfer).
# Every invocation is logged to FAKE_CALLS when that variable is set.
out=""
prev=""
for arg in "$@"; do
    if [ "$prev" = "-o" ]; then out="$arg"; fi
    prev="$arg"
done
name="$(basename "$out" | sed 's/^\.//; s/\.[A-Za-z0-9]\{6\}$//')"
[ -n "${FAKE_CALLS:-}" ] && printf '%s\n' "$name" >> "$FAKE_CALLS"
dir="${FAKE_SERVE_DIR:?FAKE_SERVE_DIR required}"
if [ -f "$dir/$name.fail" ]; then
    echo "fake curl: connection failed for $name" >&2
    exit 7
fi
if [ -f "$dir/$name.truncate" ]; then
    printf 'partial' > "$out"
    exit 18
fi
if [ ! -f "$dir/$name" ]; then
    echo "fake curl: no fixture for $name" >&2
    exit 22
fi
cp "$dir/$name" "$out"
"""

FAKE_WGET = r"""#!/usr/bin/env sh
# Minimal wget stand-in: `wget -q --tries=N -O OUT URL` behaves like the curl
# stand-in above.
out=""
prev=""
for arg in "$@"; do
    if [ "$prev" = "-O" ]; then out="$arg"; fi
    prev="$arg"
done
name="$(basename "$out" | sed 's/^\.//; s/\.[A-Za-z0-9]\{6\}$//')"
[ -n "${FAKE_CALLS:-}" ] && printf '%s\n' "$name" >> "$FAKE_CALLS"
dir="${FAKE_SERVE_DIR:?FAKE_SERVE_DIR required}"
if [ -f "$dir/$name.fail" ]; then
    echo "fake wget: connection failed for $name" >&2
    exit 4
fi
if [ ! -f "$dir/$name" ]; then
    echo "fake wget: no fixture for $name" >&2
    exit 8
fi
cp "$dir/$name" "$out"
"""


def _content(name: str, variant: str = "good") -> bytes:
    return f"{name} {variant}\n".encode()


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _harness_script(tmp_path: Path) -> Path:
    """The real script with FILES/HASHES substituted for the tiny fixtures."""
    hashes = [hashlib.sha256(_content(n)).hexdigest() for n in FILE_NAMES]
    text = SCRIPT.read_text(encoding="utf-8")
    text = re.sub(r"FILES=\([^)]*\)", f"FILES=({' '.join(FILE_NAMES)})", text)
    text = re.sub(r"HASHES=\([^)]*\)", f"HASHES=({' '.join(hashes)})", text)
    path = tmp_path / "download_ephe.sh"
    path.write_text(text, encoding="utf-8")
    return path


def _fake_downloader(bin_dir: Path, which: str) -> None:
    """Install a fake curl and/or wget; the wget path also needs every other
    external command the script uses, so when curl is absent we symlink them
    into the same private bin directory."""
    _write_executable(bin_dir / which, FAKE_CURL if which == "curl" else FAKE_WGET)
    for tool in ("sh", "cp", "mkdir", "basename", "sed", "dirname", "mktemp",
                 "cut", "sha256sum", "shasum", "mv", "chmod", "rm"):
        found = shutil.which(tool)
        if found is not None:
            (bin_dir / tool).symlink_to(found)


def _run(script: Path, ephe_dir: Path, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["EPHE_PATH"] = str(ephe_dir)
    env["FAKE_SERVE_DIR"] = str(ephe_dir.parent / "serve")
    env["FAKE_CALLS"] = str(ephe_dir.parent / "calls.log")
    env["PATH"] = str(bin_dir)
    bash = shutil.which("bash")
    assert bash is not None
    return subprocess.run(
        [bash, str(script)], capture_output=True, text=True, env=env, timeout=120,
        check=False,
    )


def _install_fixtures(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A completed first download: ephe/ holds all four verified files, serve/
    holds the matching upstream fixtures."""
    serve = tmp_path / "serve"
    serve.mkdir()
    for name in FILE_NAMES:
        (serve / name).write_bytes(_content(name))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_downloader(bin_dir, "curl")
    ephe = tmp_path / "ephe"
    result = _run(_harness_script(tmp_path), ephe, bin_dir)
    assert result.returncode == 0, result.stderr
    assert _calls(tmp_path) == FILE_NAMES
    (tmp_path / "calls.log").write_text("", encoding="utf-8")
    return ephe, serve, bin_dir


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text(encoding="utf-8").split() if log.exists() else []


def test_download_installs_all_files(tmp_path: Path) -> None:
    ephe, _, _ = _install_fixtures(tmp_path)
    for name in FILE_NAMES:
        assert (ephe / name).read_bytes() == _content(name)
    # No temporary download files left behind.
    assert sorted(p.name for p in ephe.iterdir()) == sorted(FILE_NAMES)


def test_verified_files_are_not_refetched(tmp_path: Path) -> None:
    ephe, serve, bin_dir = _install_fixtures(tmp_path)
    # The first run downloaded everything; make any further fetch fail.
    for name in FILE_NAMES:
        (serve / f"{name}.fail").touch()
    result = _run(_harness_script(tmp_path), ephe, bin_dir)
    assert result.returncode == 0, result.stderr
    assert result.stdout.count("[verified]") == 4
    assert _calls(tmp_path) == []


def test_corrupt_installed_file_is_repaired(tmp_path: Path) -> None:
    ephe, serve, bin_dir = _install_fixtures(tmp_path)
    before = {n: (ephe / n).read_bytes() for n in FILE_NAMES}
    (ephe / "sepl_18.se1").write_bytes(b"corrupted bytes")
    result = _run(_harness_script(tmp_path), ephe, bin_dir)
    assert result.returncode == 0, result.stderr
    assert (ephe / "sepl_18.se1").read_bytes() == _content("sepl_18.se1")
    for name in FILE_NAMES:
        if name != "sepl_18.se1":
            assert (ephe / name).read_bytes() == before[name]
    assert _calls(tmp_path) == ["sepl_18.se1"]
    assert sorted(p.name for p in ephe.iterdir()) == sorted(FILE_NAMES)


def test_checksum_mismatch_keeps_installed_file(tmp_path: Path) -> None:
    ephe, serve, bin_dir = _install_fixtures(tmp_path)
    (ephe / "sefstars.txt").write_bytes(b"corrupted")
    (serve / "sefstars.txt").write_bytes(_content("sefstars.txt", "TAMPERED"))
    result = _run(_harness_script(tmp_path), ephe, bin_dir)
    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    # The previously installed copy is untouched and no temp file remains.
    assert (ephe / "sefstars.txt").read_bytes() == b"corrupted"
    assert sorted(p.name for p in ephe.iterdir()) == sorted(FILE_NAMES)


def test_failed_download_preserves_existing_files(tmp_path: Path) -> None:
    ephe, serve, bin_dir = _install_fixtures(tmp_path)
    (ephe / "semo_18.se1").write_bytes(b"previous copy")
    (serve / "semo_18.se1.fail").touch()
    result = _run(_harness_script(tmp_path), ephe, bin_dir)
    assert result.returncode != 0
    assert "connection failed" in result.stderr
    assert (ephe / "semo_18.se1").read_bytes() == b"previous copy"
    assert (ephe / "sefstars.txt").read_bytes() == _content("sefstars.txt")
    assert sorted(p.name for p in ephe.iterdir()) == sorted(FILE_NAMES)
    assert not any(p.name.startswith(".") for p in ephe.iterdir())


def test_interrupted_download_leaves_no_temp_file(tmp_path: Path) -> None:
    serve = tmp_path / "serve"
    serve.mkdir()
    (serve / "seas_18.se1.truncate").touch()
    for name in FILE_NAMES[1:]:
        (serve / name).write_bytes(_content(name))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_downloader(bin_dir, "curl")
    result = _run(_harness_script(tmp_path), tmp_path / "ephe", bin_dir)
    assert result.returncode != 0
    ephe = tmp_path / "ephe"
    assert list(ephe.iterdir()) == []


def test_wget_fallback(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_downloader(bin_dir, "wget")
    serve = tmp_path / "serve"
    serve.mkdir()
    for name in FILE_NAMES:
        (serve / name).write_bytes(_content(name))
    result = _run(_harness_script(tmp_path), tmp_path / "ephe", bin_dir)
    assert result.returncode == 0, result.stderr
    for name in FILE_NAMES:
        assert (tmp_path / "ephe" / name).read_bytes() == _content(name)


def test_real_script_pins_one_hash_per_file() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    files_block = re.search(r"^FILES=\((.*?)\)$", text, re.MULTILINE)
    hashes_block = re.search(r"^HASHES=\((.*?)\)$", text, re.MULTILINE | re.DOTALL)
    assert files_block is not None and hashes_block is not None
    files = files_block.group(1).split()
    hashes = hashes_block.group(1).split()
    assert files == FILE_NAMES
    assert len(hashes) == len(files)
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes)
    revision = re.search(r'^REVISION="([0-9a-f]{40})"$', text, re.MULTILINE)
    assert revision is not None, "upstream revision must be a pinned commit sha"
    assert "raw.githubusercontent.com/aloistr/swisseph/${REVISION}/ephe" in text
    assert "set -euo pipefail" in text
    # Downloads go to a temp file and are atomically renamed into place.
    assert "mktemp" in text and "mv -f" in text


def test_ci_validates_cache_after_restore() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "uses: actions/cache@v4" in ci
    assert "path: ephe" in ci
    assert "hashFiles('scripts/download_ephe.sh')" in ci
    # The download step must run on every job, cache hit or not: the script
    # re-verifies existing files against the pinned checksums.
    block = ci[ci.index("Download ephemeris data"):]
    step = block.split("      - name:", 1)[0]
    assert "bash scripts/download_ephe.sh" in step
    assert "if:" not in step
