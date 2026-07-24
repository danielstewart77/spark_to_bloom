"""First-party static assets must be served cache-busted.

A stale `terminal-routing.js` cached against a freshly-rendered
terminal.html is what once blanked the session rail: the template called
`TerminalRouting.contrastText`, the browser's cached copy predated that
export, and the resulting TypeError aborted `renderCards` mid-loop so the
page showed "No active sessions" with live sessions on the server. That
page has since moved to its own site (terminal.sparktobloom.com); the
versioning mechanism it motivated stays and is covered generically here.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main as main_mod

TEMPLATE_DIR = main_mod.BASE_DIR / "templates"
STATIC_DIR = main_mod.BASE_DIR / "static"

# url_for('static', path='<name>') with whatever follows the closing brace,
# so we can tell a stamped reference from a bare one.
STATIC_REF = re.compile(
    r"""url_for\(\s*['"]static['"]\s*,\s*path=['"](?P<path>[^'"]+)['"]\s*\)\s*\}\}(?P<suffix>[^"']*)"""
)


def test_asset_versions_covers_every_first_party_static_file():
    versions = main_mod._asset_versions()
    on_disk = {p.name for p in STATIC_DIR.iterdir() if p.is_file()}
    assert on_disk, "no first-party static files found — wrong BASE_DIR?"
    assert set(versions) == on_disk
    assert all(isinstance(v, int) and v > 0 for v in versions.values())


def test_asset_versions_tracks_file_mtime(tmp_path, monkeypatch):
    before = main_mod._asset_versions()["scripts.js"]
    target = STATIC_DIR / "scripts.js"
    stat = target.stat()
    try:
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        assert main_mod._asset_versions()["scripts.js"] != before
    finally:
        os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))


@pytest.mark.parametrize(
    "template", sorted(p.name for p in TEMPLATE_DIR.glob("*.html"))
)
def test_mutable_static_references_are_version_stamped(template):
    """Every reference to a changeable first-party asset carries ?v=.

    vendor/ is pinned third-party and images are effectively immutable, so
    only top-level static files are required to be stamped.
    """
    source = (TEMPLATE_DIR / template).read_text(encoding="utf-8")
    unstamped = [
        m.group("path")
        for m in STATIC_REF.finditer(source)
        if (STATIC_DIR / m.group("path")).is_file()
        and "/" not in m.group("path")
        and not m.group("suffix").startswith("?v=")
    ]
    assert not unstamped, f"{template} loads {unstamped} without a ?v= stamp"
