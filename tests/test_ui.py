import re
import shutil
import subprocess
from pathlib import Path

import pytest

UI_DIR = Path(__file__).parent.parent / "app" / "ui" / "static"


def test_ui_shell_is_served_with_a_strict_content_security_policy(anon_client):
    r = anon_client.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "<title>Obskit</title>" in r.text
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp and "default-src 'none'" in csp
    moved = anon_client.get("/ui", follow_redirects=False)
    assert (moved.status_code, moved.headers["location"]) == (308, "/")


def test_ui_has_no_inline_script_or_style_and_assets_are_served(anon_client):
    html = anon_client.get("/").text
    assert not re.search(r"<script(?![^>]*\bsrc=)", html) and "<style" not in html and " style=" not in html
    for asset, kind in (("app.js", "javascript"), ("format.js", "javascript"), ("app.css", "css")):
        r = anon_client.get(f"/ui/static/{asset}")
        assert r.status_code == 200 and kind in r.headers["content-type"]


def test_ui_browses_without_a_key_but_cannot_write(anon_client):
    for path in ("/workflow-runs", "/monitoring/overview", "/incidents", "/services", "/workers"):
        assert anon_client.get(path).status_code == 200
    assert anon_client.post("/events/replay", json={"workflow_run_ids": []}).status_code == 401


def test_ui_script_never_parses_data_as_html():
    source = (UI_DIR / "app.js").read_text()
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert forbidden not in source


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_ui_helper_functions_pass_node_tests():
    result = subprocess.run(
        ["node", "--test", str(Path(__file__).parent / "ui" / "format.test.mjs")],
        capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr


def test_ui_script_never_sets_inline_style_strings():
    """The CSP blocks `style="..."` attributes, so bars would silently collapse; only CSSOM objects work."""
    source = (UI_DIR / "app.js").read_text()
    assert not re.search(r"style:\s*[`\"']", source)
    assert 'setAttribute("style"' not in source
