#!/usr/bin/env bash
# Install the Devin CLI and materialize credentials.toml.
#
# Env:
#   DEVIN_API_KEY            — windsurf_api_key value (from `devin auth login`)
#   DEVIN_CREDENTIALS_TOML   — full credentials.toml contents (alternative)
#   DEVIN_API_SERVER_URL     — default https://server.codeium.com
#   DEVIN_API_URL            — default https://api.devin.ai
#   DEVIN_WEBAPP_HOST        — default https://app.devin.ai
#
# NOTE: the upstream installer ends with `devin setup`, an interactive
# first-run flow that fails on a headless runner. The binary is already
# installed by then, so we feed it a closed stdin and ignore the failure.
# Credentials are written BEFORE any further devin invocation — an
# unauthenticated `devin` call would otherwise trigger the same login flow.
set -euo pipefail

if ! command -v devin >/dev/null 2>&1; then
  echo "installing devin cli…"
  curl -fsSL https://cli.devin.ai/install.sh | bash </dev/null || true
fi
export PATH="$HOME/.local/bin:$PATH"
command -v devin   # must exist — real failure if the install itself broke

if [ -n "${DEVIN_CREDENTIALS_TOML:-}" ]; then
  mkdir -p "$HOME/.local/share/devin"
  printf '%s' "$DEVIN_CREDENTIALS_TOML" > "$HOME/.local/share/devin/credentials.toml"
  chmod 600 "$HOME/.local/share/devin/credentials.toml"
  echo "credentials.toml written from DEVIN_CREDENTIALS_TOML"
elif [ -n "${DEVIN_API_KEY:-}" ]; then
  mkdir -p "$HOME/.local/share/devin"
  cat > "$HOME/.local/share/devin/credentials.toml" <<EOF
windsurf_api_key = "${DEVIN_API_KEY}"
api_server_url = "${DEVIN_API_SERVER_URL:-https://server.codeium.com}"
devin_webapp_host = "${DEVIN_WEBAPP_HOST:-https://app.devin.ai}"
devin_api_url = "${DEVIN_API_URL:-https://api.devin.ai}"
EOF
  chmod 600 "$HOME/.local/share/devin/credentials.toml"
  echo "credentials.toml written from DEVIN_API_KEY"
else
  echo "no DEVIN_API_KEY / DEVIN_CREDENTIALS_TOML — expecting existing credentials.toml"
fi

# auth check (server round-trip); informational — the pipeline's check-setup
# is the authoritative gate
devin auth status 2>&1 | head -8 || true
