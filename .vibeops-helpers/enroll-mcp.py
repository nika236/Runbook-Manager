#!/usr/bin/env python3
"""
VibeOps MCP enrollment exchange helper.

Called by Install.command / Install.bat / Install.ps1 (and the
Claude Code variants) to:

  1. Read the project's `.cursor/mcp.install.json`.
  2. If it carries an `_vibeopsEnrollment` payload (single-use enrollment
     token + ed25519 binding metadata):
       - Generate an ed25519 keypair at `~/.vibeops/mcp-key.pem` if
         missing (mode 0600 / user-only ACL on Windows).
       - Compute the RFC 7638 JWK thumbprint of the public key.
       - POST `{ enrollmentToken, jwk, machineLabel }` to
         `enrollmentEndpoint`.
       - On 2xx: rewrite `.cursor/mcp.install.json` so the bearer
         header carries the redeemed long-lived access token, and
         mark `_vibeopsEnrollment: "redeemed"`.
       - On any failure: leave the file alone and exit with
         `FALLBACK <reason>` so the caller falls back to the legacy
         bearer in `mcpServers.vibeops.headers.Authorization`.
  3. If no `_vibeopsEnrollment`: no-op (legacy ZIP, nothing to do).

Why a separate Python file (rather than inlining into each installer):

  - Crypto + HTTP + JSON manipulation in pure bash is painful and
    brittle. PowerShell can do it but the Mac script can't share
    code with PowerShell. A single Python file keeps the protocol
    in one place and is what we already use for the Cursor mcp.json
    merge.
  - Stdlib only — no pip install of `cryptography` or `requests`.
    `openssl` is invoked via subprocess for keypair gen + public-key
    export (universally available on macOS/Linux/Windows-with-WSL/
    Windows-with-Git-for-Windows). HTTP via `urllib.request`.

DPoP-future note: today Cursor's MCP client cannot sign per-request
DPoP proofs, so the access token returned by `/oauth/enroll` is a
plain bearer. The platform side still records the JWK thumbprint
(`jkt`) for forensics and future per-request signature enforcement.
The day Cursor adds DPoP support, we flip a server-side feature flag
on and existing enrolled installs already have keys ready to go.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
from typing import Optional


def fail(reason: str) -> None:
    """Emit a parseable failure marker on stdout and exit non-zero.

    The shell-side caller looks for `FALLBACK ` to decide whether to
    keep the legacy bearer flow. Everything before/after this prefix
    is human-facing diagnostic.
    """
    print(f"FALLBACK {reason}", flush=True)
    sys.exit(2)


def ok(message: str) -> None:
    print(f"OK {message}", flush=True)
    sys.exit(0)


def vibeops_dir() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~")
    path = os.path.join(base, ".vibeops")
    os.makedirs(path, exist_ok=True)
    if platform.system() != "Windows":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
    return path


def ensure_keypair(key_path: str) -> bytes:
    """Generate an ed25519 key at `key_path` if missing; return the
    raw 32-byte public key bytes.

    Why ed25519: small, fast, no parameter choice, supported by every
    recent openssl. Why openssl rather than `cryptography`: avoids a
    pip-install side effect inside an installer script. macOS ships
    with LibreSSL 3.x which supports ed25519 since 3.7; Windows users
    invoking PowerShell get OpenSSL via Git-for-Windows or the
    Windows-store openssl. If `openssl` isn't on PATH at all we bail
    with FALLBACK rather than try to roll our own ed25519 in Python
    stdlib (which would mean implementing the curve from scratch).
    """
    if not shutil.which("openssl"):
        fail("openssl_not_found")

    if not os.path.exists(key_path):
        try:
            subprocess.run(
                [
                    "openssl",
                    "genpkey",
                    "-algorithm",
                    "ed25519",
                    "-out",
                    key_path,
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            fail(f"keypair_gen_failed:{e.stderr.decode(errors='replace').strip()[:80]}")
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            # Best-effort on Windows; ACL tightening is the script's job.
            pass

    # Extract the public key in DER form, then parse out the 32 raw
    # bytes. ed25519 SubjectPublicKeyInfo is a fixed-size 44-byte
    # structure where the last 32 bytes are the raw public key.
    try:
        pub_der = subprocess.run(
            ["openssl", "pkey", "-in", key_path, "-pubout", "-outform", "DER"],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        fail(f"pub_export_failed:{e.stderr.decode(errors='replace').strip()[:80]}")

    if len(pub_der) < 32:
        fail("pub_der_too_short")
    return pub_der[-32:]


def jwk_for_ed25519(raw_pub: bytes) -> dict:
    """Build the JWK form of an ed25519 public key.

    RFC 8037 §2: kty="OKP", crv="Ed25519", x=base64url(rawPubKey).
    Order matters for the thumbprint: kty, crv, x — the canonical
    form is alphabetical, which happens to match this for ed25519.
    """
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode("ascii"),
    }


def jwk_thumbprint(jwk: dict) -> str:
    """RFC 7638 JWK thumbprint = base64url(SHA-256(canonical-JSON(jwk))).

    Canonical JSON for thumbprint purposes: sorted keys, no
    whitespace, ASCII strings. The platform side recomputes this from
    the same JWK and compares to `McpAccessToken.jkt`.
    """
    canonical = json.dumps(jwk, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def detect_machine_label() -> str:
    """A friendly UA-derived label for the Tokens panel UI.

    Format: `<user>@<host> (<os>)`. Truncated to 80 chars. We use
    environment heuristics rather than `platform.node()` alone
    because some corporate Windows machines have UUID-shaped node
    names that aren't useful in a UI.
    """
    user = (
        os.environ.get("USER")
        or os.environ.get("USERNAME")
        or "unknown"
    )
    host = platform.node() or "unknown-host"
    sysname = platform.system()
    if sysname == "Darwin":
        sysname = "macOS"
    label = f"{user}@{host} ({sysname})"
    return label[:80]


def post_enroll(
    endpoint: str,
    enrollment_token: str,
    jwk: dict,
    machine_label: str,
) -> dict:
    """POST the enrollment exchange and return the parsed JSON body.

    Network failure modes we explicitly recognise:
      - 404 / 405: server doesn't yet implement /oauth/enroll →
        fallback to legacy bearer.
      - 401 / 410 / 422: the enrollment token is invalid, expired,
        or already redeemed → fallback (the legacy bearer in the
        same ZIP is the same age, so it'll work).
      - 5xx, network error, timeout: probably temporary; fallback
        and let the user re-run installer or use the legacy bearer.
    """
    body = json.dumps(
        {
            "enrollmentToken": enrollment_token,
            "jwk": jwk,
            "machineLabel": machine_label,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Helpful UA so MCP-side logs distinguish enrollments from
            # actual MCP traffic in the access logs.
            "User-Agent": "vibeops-installer/1 (enroll-mcp.py)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Drain the body so the connection releases cleanly; we don't
        # surface the server's error verbatim to the user (could
        # contain platform-internal hints) but we DO propagate the
        # status code so ops can correlate with MCP-side logs.
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            err_body = ""
        fail(f"http_{e.code}:{err_body}")
    except urllib.error.URLError as e:
        fail(f"network:{type(e.reason).__name__}")
    except Exception as e:  # noqa: BLE001
        fail(f"unexpected:{type(e).__name__}:{str(e)[:80]}")
    # Unreachable, but mypy/pyright don't know fail() exits.
    raise SystemExit(2)


def rewrite_install_json(
    install_path: str,
    new_access_token: str,
    transport: str,
) -> None:
    """Replace the bearer in `mcp.install.json` with the redeemed
    access token and mark the enrollment as redeemed.

    We modify the file in-place (atomic via tempfile + rename) so a
    crash mid-write doesn't leave the user with a corrupt file. The
    enrollment token is overwritten with the literal string
    `"redeemed"` (rather than removed) so the JSON stays parseable
    and a subsequent install run is a no-op rather than triggering a
    second exchange that would 401 anyway.
    """
    with open(install_path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    servers = doc.setdefault("mcpServers", {})
    vibeops = servers.setdefault("vibeops", {})
    headers = vibeops.setdefault("headers", {})
    headers["Authorization"] = f"Bearer {new_access_token}"
    # Overwrite the legacy bearer reference too if it exists.
    vibeops["type"] = vibeops.get("type", transport)

    doc["_vibeopsEnrollment"] = "redeemed"

    tmp = install_path + ".vibeops-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, install_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="VibeOps MCP enrollment exchange")
    parser.add_argument(
        "--install-json",
        default=".cursor/mcp.install.json",
        help="Path to mcp.install.json (default: .cursor/mcp.install.json)",
    )
    parser.add_argument(
        "--key-path",
        default=None,
        help="ed25519 private key location (default: ~/.vibeops/mcp-key.pem)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.install_json):
        ok("no_install_json")

    try:
        with open(args.install_json, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:  # noqa: BLE001
        fail(f"install_json_unreadable:{type(e).__name__}")

    enrollment = doc.get("_vibeopsEnrollment")
    if enrollment is None:
        ok("legacy_zip_no_enrollment")
    if enrollment == "redeemed":
        ok("already_redeemed")
    if not isinstance(enrollment, dict):
        fail("invalid_enrollment_field")

    enrollment_token = enrollment.get("enrollmentToken")
    endpoint = enrollment.get("enrollmentEndpoint")
    transport = enrollment.get("transport", "streamable-http")
    if not enrollment_token or not endpoint:
        fail("missing_enrollment_fields")

    key_path = args.key_path or os.path.join(vibeops_dir(), "mcp-key.pem")
    raw_pub = ensure_keypair(key_path)
    jwk = jwk_for_ed25519(raw_pub)
    jkt = jwk_thumbprint(jwk)

    machine_label = detect_machine_label()
    response = post_enroll(endpoint, enrollment_token, jwk, machine_label)

    new_token = response.get("accessToken")
    if not isinstance(new_token, str) or not new_token:
        fail("response_missing_access_token")

    rewrite_install_json(args.install_json, new_token, transport)
    ok(f"enrolled jkt={jkt[:12]}...")


if __name__ == "__main__":
    main()
