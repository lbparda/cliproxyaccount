#!/usr/bin/env python3
"""Merge missing Antigravity model entries into the CLIProxyAPI catalog.

Adds the Gemini 3.6 Flash Medium/Low routes that Google's GetAvailableModels
returns for this account but that the community catalog omits.
Structure mirrors router-for-me/models PR #26 (validated against the real
Antigravity client response).
"""
import json
import sys

SRC = "/tmp/models_remote.json"
DST = "/root/CLIProxyAPI/internal/registry/models/models.json"


def entry(model_id, display):
    return {
        "id": model_id,
        "object": "model",
        "owned_by": "antigravity",
        "type": "antigravity",
        "display_name": display,
        "name": model_id,
        "description": display,
        "context_length": 1048576,
        "max_completion_tokens": 65536,
        "thinking": {
            "min": 1,
            "max": 65535,
            "dynamic_allowed": True,
            "levels": ["minimal", "low", "medium", "high"],
        },
        "supportedInputModalities": ["text", "image", "audio", "video"],
        "supportedOutputModalities": ["text"],
    }


ADDITIONS = [
    ("gemini-3.6-flash-medium", "Gemini 3.6 Flash (Medium)"),
    ("gemini-3.6-flash-low", "Gemini 3.6 Flash (Low)"),
]

with open(SRC) as f:
    catalog = json.load(f)

ag = catalog.get("antigravity")
if not isinstance(ag, list):
    sys.exit("ERROR: no antigravity list in catalog")

existing = {m.get("id") for m in ag if isinstance(m, dict)}

# Clarify the High entry's display name so the three tiers read consistently.
for m in ag:
    if isinstance(m, dict) and m.get("id") == "gemini-3.6-flash-high":
        m["display_name"] = "Gemini 3.6 Flash (High)"

added = []
for model_id, display in ADDITIONS:
    if model_id in existing:
        continue
    # Insert right after the High entry so the tiers stay grouped.
    idx = next(
        (i for i, m in enumerate(ag)
         if isinstance(m, dict) and m.get("id") == "gemini-3.6-flash-high"),
        len(ag) - 1,
    )
    ag.insert(idx + 1 + len(added), entry(model_id, display))
    added.append(model_id)

with open(DST, "w") as f:
    json.dump(catalog, f, indent=2, ensure_ascii=False)
    f.write("\n")

print("ADDED:", added or "(nothing, already present)")
print("antigravity entries now:", len(ag))
for m in ag:
    if isinstance(m, dict) and "3.6" in str(m.get("id", "")):
        print("  ", m["id"], "->", m.get("display_name"))
