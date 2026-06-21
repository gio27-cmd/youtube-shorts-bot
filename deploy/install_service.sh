#!/usr/bin/env bash
# ============================================================
# Installiert den Bot als systemd-Dienst (Autostart + 24/7 Restart).
# Ausführen IM Projektverzeichnis:  bash deploy/install_service.sh
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="$(whoami)"
UNIT_SRC="$PROJECT_DIR/deploy/youtube-bot.service"
UNIT_DST="/etc/systemd/system/youtube-bot.service"

echo "==> Dienst-Datei erzeugen ($UNIT_DST)"
sed -e "s|__USER__|$RUN_USER|g" -e "s|__DIR__|$PROJECT_DIR|g" "$UNIT_SRC" \
    | sudo tee "$UNIT_DST" > /dev/null

echo "==> systemd neu laden + aktivieren"
sudo systemctl daemon-reload
sudo systemctl enable youtube-bot.service
sudo systemctl restart youtube-bot.service

echo ""
echo "==> Status:"
sudo systemctl --no-pager status youtube-bot.service | head -12 || true
echo ""
echo "Live-Logs ansehen:   journalctl -u youtube-bot.service -f"
echo "Bot-Logfile:         tail -f $PROJECT_DIR/logs/bot.log"
echo "Stoppen:             sudo systemctl stop youtube-bot.service"
