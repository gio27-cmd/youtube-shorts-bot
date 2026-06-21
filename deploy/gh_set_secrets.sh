#!/usr/bin/env bash
# ============================================================
# Lädt alle relevanten Werte aus .env als GitHub-Actions-Secrets hoch.
# Voraussetzung:  gh auth login  (einmalig, interaktiv)
#
#   bash deploy/gh_set_secrets.sh [.env] [owner/repo]
# ============================================================
set -euo pipefail

ENV_FILE="${1:-.env}"
REPO="${2:-}"

[ -f "$ENV_FILE" ] || { echo "❌ $ENV_FILE nicht gefunden"; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "❌ gh CLI fehlt (brew install gh)"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "❌ Bitte zuerst: gh auth login"; exit 1; }

echo "==> Secrets aus $ENV_FILE hochladen..."
while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|\#*) continue ;; esac
    key="${line%%=*}"
    val="${line#*=}"
    [ -z "$val" ] && continue
    case "$key" in
        GEMINI_API_KEY|YOUTUBE_CLIENT_ID|YOUTUBE_CLIENT_SECRET|YOUTUBE_REFRESH_TOKEN|\
        YOUTUBE_CHANNEL_ID|HF_TOKEN|CLOUDFLARE_ACCOUNT_ID|CLOUDFLARE_KV_NS_ID|\
        CLOUDFLARE_API_TOKEN|KLING_COOKIES|INSTAGRAM_ACCESS_TOKEN|INSTAGRAM_USER_ID|\
        MODAL_TOKEN_ID|MODAL_TOKEN_SECRET)
            if [ -n "$REPO" ]; then
                gh secret set "$key" --repo "$REPO" --body "$val"
            else
                gh secret set "$key" --body "$val"
            fi
            echo "  ✓ $key"
            ;;
    esac
done < "$ENV_FILE"

echo "==> Fertig. Prüfen mit:  gh secret list ${REPO:+--repo $REPO}"
