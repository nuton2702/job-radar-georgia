"""Verify the deployed snapshot and assets over public HTTPS."""
import json
import os
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

base = os.environ["PAGE_URL"].rstrip("/") + "/"
if urlparse(base).scheme != "https" or urlparse(base).hostname != "nuton2702.github.io":
    raise SystemExit("Unexpected deployment URL")
expected = json.loads(Path("dist/data/bundle.json").read_text())
for attempt in range(12):
    try:
        for name in ("index.html", "app.js", "style.css", "data/bundle.json"):
            req = urllib.request.Request(base + name, headers={"Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=20) as response:
                body = response.read()
            if name.endswith(".json"):
                assert json.loads(body) == expected, "Published database differs from deployed snapshot"
            else:
                assert body == Path("dist", name).read_bytes(), "Published asset differs: " + name
        print("Public site assets and database match the deployed snapshot.")
        break
    except Exception as error:
        print("Verification attempt", attempt + 1, str(error))
        if attempt == 11:
            raise
        time.sleep(10)
