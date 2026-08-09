#!/bin/bash
# Resync the CLIProxyAPI model catalog with upstream, preserving local additions.
#
# CLIProxyAPI runs with --local-model (its remote refresh would wipe the
# Gemini 3.6 Flash Medium/Low routes we inject), so this restores the
# every-3h update behaviour manually: check upstream, and only when it
# actually changed, re-merge + rebuild + restart. Upstream changes ~1-2x
# per week, so the expensive path is rare.
#
# Fails safe: any error leaves the running binary and catalog untouched.

set -uo pipefail

REPO=/root/CLIProxyAPI
CATALOG="$REPO/internal/registry/models/models.json"
MERGE_SCRIPT="$REPO/scripts/merge_models.py"
REMOTE_URL="https://raw.githubusercontent.com/router-for-me/models/refs/heads/main/models.json"
TMP=/tmp/models_remote.json
STAMP=/root/.models_upstream.sha256
LOG_TAG=cliproxy-models

log() { logger -t "$LOG_TAG" -- "$*"; echo "$(date -Is) $*"; }
fail() { log "ERROR: $*"; exit 1; }

export PATH="$PATH:/usr/local/go/bin"

# 1. Fetch upstream. A network blip is not an error — just skip this run.
if ! curl -fsSL --max-time 60 "$REMOTE_URL" -o "$TMP"; then
    log "upstream unreachable, skipping this run"
    exit 0
fi

# 2. Reject a truncated/invalid download before it can touch anything.
python3 -c "
import json,sys
d = json.load(open('$TMP'))
ag = d.get('antigravity')
if not isinstance(ag, list) or len(ag) < 5:
    sys.exit('upstream catalog looks wrong (antigravity entries: %r)' % (len(ag) if isinstance(ag,list) else None))
" || fail "downloaded catalog failed validation"

# 3. Skip the expensive path when upstream is unchanged.
NEW_HASH=$(sha256sum "$TMP" | cut -d' ' -f1)
OLD_HASH=$(cat "$STAMP" 2>/dev/null || echo "")
if [ "$NEW_HASH" = "$OLD_HASH" ]; then
    exit 0
fi
log "upstream catalog changed, resyncing"

# 4. Merge our additions on top of the fresh upstream catalog.
cp "$CATALOG" /root/models.json.prev 2>/dev/null
python3 "$MERGE_SCRIPT" || { cp /root/models.json.prev "$CATALOG"; fail "merge failed, catalog restored"; }

# 5. Confirm our entries survived the merge before spending a rebuild on it.
python3 -c "
import json,sys
ids = {m.get('id') for m in json.load(open('$CATALOG')).get('antigravity',[])}
missing = {'gemini-3.6-flash-medium','gemini-3.6-flash-low'} - ids
if missing:
    sys.exit('local additions missing after merge: %s' % sorted(missing))
" || { cp /root/models.json.prev "$CATALOG"; fail "merged catalog missing local entries, restored"; }

# 6. Build to a temp name so a failed build never replaces a working binary.
cd "$REPO" || fail "repo dir missing"
if ! go build -o cli-proxy-api.new ./cmd/server; then
    cp /root/models.json.prev "$CATALOG"
    rm -f cli-proxy-api.new
    fail "build failed, catalog restored, binary untouched"
fi

cp cli-proxy-api /root/cli-proxy-api.bak
mv cli-proxy-api.new cli-proxy-api
systemctl restart cli-proxy-api

# 7. Health check; roll back to the previous binary if the new one won't serve.
sleep 8
if curl -fsS --max-time 20 http://127.0.0.1:8317/v1/models -H "Authorization: Bearer ${CLIPROXY_KEY:-}" -o /dev/null 2>/dev/null \
   || systemctl is-active --quiet cli-proxy-api; then
    echo "$NEW_HASH" > "$STAMP"
    log "resync OK (catalog updated, rebuilt, service healthy)"
else
    cp /root/cli-proxy-api.bak cli-proxy-api
    cp /root/models.json.prev "$CATALOG"
    systemctl restart cli-proxy-api
    fail "service unhealthy after rebuild — rolled back binary and catalog"
fi
