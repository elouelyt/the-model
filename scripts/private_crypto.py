"""Encrypt/decrypt files with the dashboard password (gzip + AES-256-CBC via openssl).

Used so private data (full site, NBA picks) can live in the public repo only as ciphertext.
"""

import gzip
import os
import subprocess
from pathlib import Path

_OPENSSL = ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-md", "sha256", "-pass", "env:DASHBOARD_PASSWORD"]


def _run(extra: list[str], data: bytes) -> bytes:
    if not os.environ.get("DASHBOARD_PASSWORD"):
        raise SystemExit("DASHBOARD_PASSWORD is not set")
    return subprocess.run(_OPENSSL + extra, input=data, capture_output=True, check=True).stdout


def encrypt_file(src: Path, dst: Path) -> None:
    dst.write_bytes(_run(["-salt"], gzip.compress(src.read_bytes())))


def decrypt_file(src: Path, dst: Path) -> None:
    dst.write_bytes(gzip.decompress(_run(["-d"], src.read_bytes())))
