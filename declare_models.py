#!/usr/bin/env python3
"""Declare each custom provider's models in Hermes' config.

Hermes only probes a custom provider's live /v1/models when it is the ACTIVE
provider, or when the picker is opened with --refresh. Every other provider
renders as "0 models". Declaring `providers.<name>.models` gives the picker a
list to show without probing, so the terminal and the dashboard agree.

`discover_models` is deliberately left unset: the declared list is the baseline
shown instantly, and --refresh still replaces it with whatever the endpoint
reports, so newly added models are not hidden.
"""
import json
import shutil
import sys
import urllib.request

sys.path.insert(0, "/usr/local/lib/hermes-agent")
import yaml  # noqa: E402  (from the Hermes venv)

CONFIG = "/root/.hermes/config.yaml"
BACKUP = "/root/.hermes/config.yaml.bak-declare-models"
ENV_FILE = "/root/.hermes/.env"


def env_key(name):
    """Read a key from Hermes' .env so no credential lives in this file."""
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return None


ENDPOINTS = {
    "llamacpp": ("http://10.10.1.92:9000/v1/models", env_key("LLAMACPP_API_KEY")),
    "antigravity": ("http://10.10.1.92:8317/v1/models", env_key("CLIPROXY_API_KEY")),
}


def fetch_models(url, key):
    req = urllib.request.Request(url)
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return sorted(m["id"] for m in data.get("data", []) if m.get("id"))


shutil.copy(CONFIG, BACKUP)
print(f"backup -> {BACKUP}")

with open(CONFIG) as f:
    cfg = yaml.safe_load(f)

providers = cfg.get("providers")
if not isinstance(providers, dict):
    sys.exit("ERROR: no 'providers' section in config")

changed = []
for name, (url, key) in ENDPOINTS.items():
    entry = providers.get(name)
    if not isinstance(entry, dict):
        print(f"skip {name}: not declared in config")
        continue
    try:
        models = fetch_models(url, key)
    except Exception as exc:  # noqa: BLE001
        print(f"skip {name}: probe failed ({exc})")
        continue
    if not models:
        print(f"skip {name}: endpoint returned no models")
        continue
    entry["models"] = models
    changed.append((name, len(models)))

if not changed:
    sys.exit("ERROR: nothing to write, config left untouched")

with open(CONFIG, "w") as f:
    yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True, default_flow_style=False)

for name, count in changed:
    print(f"declared {count} models for '{name}'")
    for m in providers[name]["models"]:
        print(f"    {m}")
