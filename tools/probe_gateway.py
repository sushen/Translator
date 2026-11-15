"""List available gateway models without logging credentials."""
import json
import os
import urllib.request
import urllib.error
import ssl
import truststore
from pathlib import Path
from dotenv import load_dotenv

root = Path(__file__).resolve().parents[1]
load_dotenv(root / ".env", override=True)
key = os.getenv("OPENAI_API_KEY", "")
base = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
if not key or any(mark in key for mark in ("*", "REPLACE", "&#", "\\")):
    print("The key field is still masked or empty; no authenticated request made.")
    raise SystemExit(2)
if not base.startswith("https://"):
    print("An HTTPS gateway base URL is required.")
    raise SystemExit(2)
request = urllib.request.Request(base + "/models", headers={"Authorization": "Bearer " + key})
try:
    with urllib.request.urlopen(request, timeout=30, context=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)) as response:
        data = json.load(response)
    models = [item["id"] for item in data.get("data", []) if isinstance(item, dict) and "id" in item]
    out = root / "tmp/gateway_models.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(models, indent=2), encoding="utf-8")
    print(json.dumps({"model_count": len(models), "models": models[:50]}))
except urllib.error.HTTPError as exc:
    print(f"Gateway authentication/model listing returned HTTP {exc.code}. Credentials were not logged.")
    raise SystemExit(1)
except Exception as exc:
    print(f"Gateway model listing could not complete ({type(exc).__name__}). Credentials were not logged.")
    reason = getattr(exc, "reason", None)
    print(f"Connection diagnostic: {type(reason).__name__}; errno={getattr(reason, 'errno', None)}; certificate={getattr(reason, 'verify_message', None)}")
    raise SystemExit(1)
