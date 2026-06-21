# 🤖 YouTube Shorts Bot

Vollautomatischer Bot für realistische Tier-YouTube-Shorts.
24/7, selbstlernend, €0/Monat.

## Setup (einmalig)

### 1. Accounts erstellen
- [Google AI Studio](https://aistudio.google.com) → API Key
- [Google Cloud Console](https://console.cloud.google.com) → YouTube APIs
- [HuggingFace](https://huggingface.co/settings/tokens) → Token
- [Reddit Apps](https://reddit.com/prefs/apps) → Script App
- [Modal](https://modal.com) → Account
- [Cloudflare](https://cloudflare.com) → KV Namespace
- [Oracle Cloud](https://cloud.oracle.com) → Free ARM VPS

### 2. Installation
**WICHTIG: Python 3.10+ erforderlich** (gradio_client 2.x für die Video/Musik-Spaces).
Auf dem VPS zusätzlich ffmpeg **mit freetype** + eine Schriftart für die Text-Overlays:
```bash
# Ubuntu / Oracle ARM VPS:
sudo apt update && sudo apt install -y python3.11 python3.11-venv ffmpeg fonts-dejavu-core
```
```bash
git clone <repo>
cd youtube-shorts-bot
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config/.env.template .env
# .env mit echten Werten ausfüllen, u.a.:
#   FFMPEG_FONT_FILE=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
```

### 3. YouTube OAuth Token
```bash
python oauth2_setup.py
# Browser öffnet sich → einloggen → Token kopieren in .env
```

### 4. Kling Cookies kopieren
1. klingai.com im Browser öffnen und einloggen
2. F12 → Network Tab
3. Einen API-Request anklicken
4. Header "Cookie" kopieren
5. In .env als KLING_COOKIES einfügen

### 5. Bot starten
```bash
python main.py
```

### 6. Tests ausführen
```bash
python -m unittest tests.test_all_agents
```

## Architektur
Siehe YOUTUBE_SHORTS_BOT_PLAN.md für vollständige Dokumentation.

## Kosten: ~€0/Monat
FLUX (Bild) läuft über HF Inference Providers (begrenzte freie Monats-Credits),
Video/Musik über HF ZeroGPU (tägliche Limits, reicht für 2 Videos/Tag).

## Abweichungen vom Ur-Plan (real getestet 2026-06)
- **Python 3.10+ statt 3.9** — alte `gradio_client`/`huggingface-hub`-Pins waren veraltet.
- **Video:** WAN-2.2-Spaces des Plans sind tot/pausiert → stattdessen
  `Lightricks/ltx-video-distilled` (`/image_to_video`, ZeroGPU, ~8s).
- **Musik:** `ACE-Step/ACE-Step` (`/__call__`, instrumental).
- **Bild:** FLUX.1-schnell via aktueller HF Inference-API (alter Endpoint abgeschaltet).
- **Reddit:** weggelassen (Captcha) — Researcher nutzt YouTube + Google Trends.
- **Instagram-Cross-Poster** (`cross_poster.py`) ergänzt — braucht öffentliche video_url.
- Post-Produktion: behandelt tonlose KI-Videos, kleinere Dateien, entfernt Emojis aus Overlays.

## Wichtig
- YOUTUBE_MADE_FOR_KIDS muss immer False sein!
- Läuft am besten auf Oracle Cloud Free Tier (ARM VPS)
- ZeroGPU-Spaces können pausieren — `VIDEO_SPACES` in video_generator.py ist erweiterbar
