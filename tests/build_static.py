#!/usr/bin/env python3
"""
build_static.py — Pre-render all 6 Flask apps to static HTML for GitHub Pages.
Run from anywhere:  python tests/build_static.py
Output:             docs/  (at repo root, ready for GitHub Pages)
"""
import os, sys, time, subprocess
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
TESTS_DIR = Path(__file__).parent.resolve()
ROOT_DIR  = TESTS_DIR.parent
DOCS_DIR  = ROOT_DIR / "docs"

# ── App manifest (id must match TOOLS id in switcher/app.py) ───────────────
APPS = [
    {"id": "bmad_v4",      "dir": TESTS_DIR / "bmadv4_imp",    "port": 8080},
    {"id": "traycer",      "dir": TESTS_DIR / "traycer_imp",    "port": 8081},
    {"id": "amp",          "dir": TESTS_DIR / "amp_imp",        "port": 8082},
    {"id": "superpowers",  "dir": TESTS_DIR / "superpower_imp", "port": 8083},
    {"id": "ralph",        "dir": TESTS_DIR / "ralph_imp",      "port": 8084},
    {"id": "bmad_v6",      "dir": TESTS_DIR / "bmadv6",         "port": 8085},
]

# ── Helpers ────────────────────────────────────────────────────────────────
def wait_for_port(port, timeout=20):
    import urllib.request, urllib.error
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False

def fetch_html(port):
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as r:
        return r.read().decode("utf-8")

def render_switcher(port_to_id):
    """Import switcher TOOLS + HTML, inject staticUrl, render, patch URLs."""
    sys.path.insert(0, str(TESTS_DIR / "switcher"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("switcher_app", TESTS_DIR / "switcher" / "app.py")
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    tools = mod.TOOLS
    html_tmpl = mod.HTML

    # Inject staticUrl into every tool dict so JS can use it
    for t in tools:
        t["staticUrl"] = f"{t['id']}/index.html"

    # Render Jinja2 template (Flask needed for tojson filter)
    from flask import Flask
    tmp_app = Flask(__name__)
    with tmp_app.app_context():
        from flask import render_template_string
        rendered = render_template_string(html_tmpl, tools=tools)

    # Replace localhost iframe srcs with relative paths
    for port, tool_id in port_to_id.items():
        rendered = rendered.replace(
            f"http://127.0.0.1:{port}",
            f"{tool_id}/index.html"
        )

    # Patch JS selectTool — use staticUrl instead of building localhost URL
    rendered = rendered.replace(
        "const url = 'http://127.0.0.1:' + tool.port;",
        "const url = tool.staticUrl || ('http://127.0.0.1:' + tool.port);"
    )

    # Update the initial previewUrl text
    rendered = rendered.replace(
        ">http://127.0.0.1:8080<",
        ">bmad_v4/index.html<"
    )

    return rendered

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    # Kill anything on our ports first
    for app in APPS:
        os.system(f"lsof -ti :{app['port']} | xargs kill -9 2>/dev/null")

    DOCS_DIR.mkdir(exist_ok=True)

    # Start all servers
    procs = []
    for app in APPS:
        print(f"  Starting {app['id']} on :{app['port']} …")
        proc = subprocess.Popen(
            [sys.executable, "app.py"],
            cwd=str(app["dir"]),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append((app, proc))

    # Wait for each to be ready, then capture HTML
    port_to_id = {}
    for app, proc in procs:
        ok = wait_for_port(app["port"])
        if not ok:
            print(f"  ⚠  {app['id']} timed out — writing placeholder")
            out = DOCS_DIR / app["id"]
            out.mkdir(exist_ok=True)
            (out / "index.html").write_text(
                f"<html><body><h1>{app['id']} — did not start in time</h1></body></html>",
                encoding="utf-8"
            )
            port_to_id[app["port"]] = app["id"]
            continue

        try:
            html = fetch_html(app["port"])
        except Exception as e:
            # ralph returns 500 — urllib raises, so fall back to requests-style read
            import urllib.request, urllib.error
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{app['port']}/")
                with urllib.error.HTTPError as _:
                    pass
            except Exception:
                pass
            html = f"<html><body><h1>{app['id']} — {e}</h1></body></html>"

        out = DOCS_DIR / app["id"]
        out.mkdir(exist_ok=True)
        (out / "index.html").write_text(html, encoding="utf-8")
        print(f"  ✓  {app['id']}/index.html  ({len(html):,} bytes)")
        port_to_id[app["port"]] = app["id"]

    # Stop all servers
    for _, proc in procs:
        proc.terminate()
    for _, proc in procs:
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
    print("  All servers stopped.")

    # Render switcher → docs/index.html
    print("  Rendering switcher …")
    switcher_html = render_switcher(port_to_id)
    (DOCS_DIR / "index.html").write_text(switcher_html, encoding="utf-8")
    print(f"  ✓  docs/index.html  ({len(switcher_html):,} bytes)")

    print(f"\n✅ Static build complete → {DOCS_DIR}")
    print("Next steps:")
    print("  1. git add docs/ && git commit -m 'Static build for GitHub Pages'")
    print("  2. git push")
    print("  3. GitHub repo → Settings → Pages → Source: Deploy from branch → main → /docs")

if __name__ == "__main__":
    print("🏀 Building static site for GitHub Pages …\n")
    main()
