#!/usr/bin/env bash
# Install the Devin CLI and (optionally) materialize credentials.toml.
#
# Env:
#   DEVIN_API_KEY            — windsurf_api_key value (from `devin auth login`)
#   DEVIN_CREDENTIALS_TOML   — full credentials.toml contents (alternative)
#   DEVIN_API_SERVER_URL     — default https://server.codeium.com
#   DEVIN_API_URL            — default https://api.devin.ai
#   DEVIN_WEBAPP_HOST        — default https://app.devin.ai
#
# The engine's ensure_credentials() also performs the credentials step at
# runtime; this script exists so CI and local runs share one installer.
set -euo pipefail

if ! command -v devin >/dev/null 2>&1; then
  echo "installing devin cli…"
  curl -fsSL https://cli.devin.ai/install.sh | bash
fi
export PATH="$HOME/.local/bin:$PATH"
devin --version

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
