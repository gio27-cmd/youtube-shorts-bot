#!/usr/bin/env bash
# ============================================================
# YouTube Shorts Bot — VPS Setup (Ubuntu / Oracle ARM Always Free)
# Idempotent: kann gefahrlos mehrfach ausgeführt werden.
#
# Ausführen IM Projektverzeichnis auf dem VPS:
#   cd ~/youtube-shorts-bot && bash deploy/setup_vps.sh
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
echo "==> Projekt: $PROJECT_DIR"

# 1) System-Pakete (Python 3.11, ffmpeg MIT freetype, Schriftart für drawtext)
echo "==> System-Pakete installieren..."
sudo apt-get update -y
sudo apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    ffmpeg fonts-dejavu-core \
    git curl build-essential

# 2) ffmpeg drawtext-Check (muss vorhanden sein, sonst keine Text-Overlays)
if ! ffmpeg -hide_banner -filters 2>/dev/null | grep -q drawtext; then
    echo "!! WARNUNG: ffmpeg ohne 'drawtext' (freetype fehlt). Overlays funktionieren nicht."
else
    echo "==> ffmpeg drawtext OK"
fi

# 3) Python venv + Abhängigkeiten
echo "==> venv + requirements..."
python3.11 -m venv .venv
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements.txt

# 4) Font-Pfad in .env eintragen (falls noch nicht gesetzt)
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
if [ -f .env ]; then
    if ! grep -q '^FFMPEG_FONT_FILE=.\+' .env; then
        # vorhandene leere Zeile ersetzen oder anhängen
        if grep -q '^FFMPEG_FONT_FILE=' .env; then
            sed -i "s|^FFMPEG_FONT_FILE=.*|FFMPEG_FONT_FILE=$FONT|" .env
        else
            echo "FFMPEG_FONT_FILE=$FONT" >> .env
        fi
        echo "==> FFMPEG_FONT_FILE in .env gesetzt"
    fi
else
    echo "!! .env fehlt — bitte vom lokalen Rechner hochladen (siehe deploy/README_DEPLOY.md)"
fi

# 5) Schneller Import-Check
echo "==> Import-Check..."
./.venv/bin/python -c "from agents.video_generator import VideoGenerator; from agents.post_production import PostProduction; print('OK: Module laden')"

echo ""
echo "============================================================"
echo " Setup fertig. Bot als 24/7-Dienst starten:"
echo "   bash deploy/install_service.sh"
echo " Oder manuell testen:"
echo "   ./.venv/bin/python main.py"
echo "============================================================"
