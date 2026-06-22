"""
Alle Bot-Einstellungen zentral an einem Ort.
Ändere hier nichts ohne den gesamten Plan zu lesen.
"""

import os
from dotenv import load_dotenv
load_dotenv()

# ============================================================
# API KEYS
# ============================================================
GEMINI_API_KEY        = os.getenv("GEMINI_API_KEY")

# Google-Modelle in PRIORITÄTSREIHENFOLGE: neuestes zuerst, danach bewährte
# Free-Tier-Modelle. Jedes Modell hat eine EIGENE kostenlose Tagesquota — ist
# das neueste gerade leer/nicht erreichbar, wird automatisch das nächste Google-
# Modell probiert. Erst wenn ALLE scheitern, übernimmt OpenRouter (config.llm).
# Per Env GEMINI_MODELS (kommagetrennt) überschreibbar.
# Hinweis: gemini-2.0-flash bewusst NICHT enthalten — hat im Free-Tier limit 0.
GEMINI_MODELS = [
    m.strip() for m in os.getenv(
        "GEMINI_MODELS",
        "gemini-3.5-flash,gemini-2.5-flash,gemini-2.5-flash-lite"
    ).split(",") if m.strip()
]
GEMINI_MODEL          = GEMINI_MODELS[0]   # Primär-/Default-Modell (Rückwärtskompat.)

# OpenRouter — LETZTER Fallback, erst wenn alle Google-Modelle ausfallen.
# Ohne Key bleibt es beim reinen Google-Verhalten.
OPENROUTER_API_KEY    = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL      = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")

YOUTUBE_CLIENT_ID     = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
YOUTUBE_CHANNEL_ID    = os.getenv("YOUTUBE_CHANNEL_ID")

HF_TOKEN              = os.getenv("HF_TOKEN")
# Mehrere HF-Accounts: ZeroGPU-/Inference-Quota gilt PRO Account. Durch Rotation
# über alle Tokens (ein Account pro Video) vervielfacht sich das tägliche
# Gratis-Budget. Secret HF_TOKENS = kommagetrennte Liste; Fallback auf HF_TOKEN.
HF_TOKENS             = [t.strip() for t in os.getenv("HF_TOKENS", "").split(",") if t.strip()] \
                        or ([HF_TOKEN] if HF_TOKEN else [])

REDDIT_CLIENT_ID      = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET  = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT     = "YouTubeShortsBot/1.0"

MODAL_TOKEN_ID        = os.getenv("MODAL_TOKEN_ID")
MODAL_TOKEN_SECRET    = os.getenv("MODAL_TOKEN_SECRET")

CLOUDFLARE_ACCOUNT_ID  = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_KV_NS_ID    = os.getenv("CLOUDFLARE_KV_NS_ID")
CLOUDFLARE_API_TOKEN   = os.getenv("CLOUDFLARE_API_TOKEN")

KLING_COOKIES         = os.getenv("KLING_COOKIES")

INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_USER_ID      = os.getenv("INSTAGRAM_USER_ID")

# ============================================================
# BOT TIMING
# ============================================================
VIDEOS_PER_DAY        = 2
# Stufe 3 — "mehr generieren, die besten posten":
# Es werden VIDEOS_GENERATED_PER_DAY Videos gebaut (auf die HF-Accounts verteilt),
# bewertet (vorhergesagte Verweildauer + Like-Rate) und nur die besten hochgeladen
# — max VIDEOS_UPLOADED_MAX, mind. VIDEOS_UPLOADED_MIN, alle über POTENTIAL_THRESHOLD.
VIDEOS_GENERATED_PER_DAY = 4
VIDEOS_UPLOADED_MAX      = 3
VIDEOS_UPLOADED_MIN      = 2
POTENTIAL_THRESHOLD      = 55     # 0-100; darunter wird nicht hochgeladen
UPLOAD_TIME_VIDEO_1   = "14:00"   # Werktags optimal
UPLOAD_TIME_VIDEO_2   = "20:00"   # Abends optimal
PRODUCTION_START_TIME = "02:00"   # Nachts starten (WAN 2.2 Queue leer)
RESEARCH_INTERVAL_H   = 3         # Research alle 3 Stunden (24/7 Trend-Beobachtung)
ANALYTICS_CHECK_TIME  = "10:00"   # Täglicher Analytics-Check
OPTIMIZER_DAY         = "sunday"  # Wöchentlich Sonntag
OPTIMIZER_TIME        = "23:00"

# ============================================================
# VIDEO SETTINGS
# ============================================================
VIDEO_DURATION_SEC    = 10
VIDEO_FORMAT          = "9:16"
VIDEO_RESOLUTION_W    = 720
VIDEO_RESOLUTION_H    = 1280

# ============================================================
# TIER-KATEGORIEN (nach Viral-Potential sortiert)
# ============================================================
ANIMAL_CATEGORIES = [
    "golden retriever puppy",
    "baby panda",
    "red panda",
    "capybara",
    "otter playing",
    "baby cat kitten",
    "husky dog reaction",
    "baby elephant",
    "raccoon",
    "fox in nature",
    "baby deer fawn",
    "penguin walking",
    "bunny rabbit",
    "baby bear cub",
    "dolphin jumping"
]

# ============================================================
# HOOK TEXT VORLAGEN (für A/B Testing)
# ============================================================
HOOK_TEMPLATES = {
    "shock": [
        "You won't believe this 😱",
        "Wait for it... 🤯",
        "Nobody talks about this 👀"
    ],
    "question": [
        "Can you guess what happens next? 🤔",
        "Have you ever seen this before? 😍",
        "Why does this make me cry? 🥺"
    ],
    "pov": [
        "POV: You're having the best day 🌟",
        "POV: Nature is healing 🌿",
        "POV: Pure happiness exists 💛"
    ],
    "fact": [
        "Did you know? 🧠",
        "Fun fact about this animal 🐾",
        "This will change how you see them 💡"
    ]
}

# ============================================================
# REDDIT SUBREDDITS (Research)
# ============================================================
REDDIT_SUBREDDITS = [
    "aww",
    "AnimalsBeingBros",
    "NatureIsFunny",
    "likeus",
    "rarepuppers",
    "Eyebleach",
    "babyelephantgifs",
    "otters"
]

# ============================================================
# YOUTUBE UPLOAD
# ============================================================
YOUTUBE_CATEGORY_ID    = "15"       # Tiere & Natur
YOUTUBE_PRIVACY        = "public"
YOUTUBE_MADE_FOR_KIDS  = False      # IMMER FALSE! Sonst kein Revenue!
YOUTUBE_LANGUAGE       = "de"
YOUTUBE_MAX_UPLOADS_PER_DAY = 2     # Quota schonen

# ============================================================
# VIRAL SCHWELLENWERTE
# ============================================================
VIRAL_THRESHOLD_VIEWS  = 50000
GOOD_THRESHOLD_VIEWS   = 10000
BAD_THRESHOLD_VIEWS    = 1000

# ============================================================
# FFMPEG SETTINGS
# ============================================================
FFMPEG_FONT_SIZE_HOOK  = 52
FFMPEG_FONT_SIZE_FACT  = 36
FFMPEG_FONT_COLOR      = "white"
FFMPEG_FONT_BORDER     = "black"
FFMPEG_MUSIC_VOLUME    = 0.3        # 30% Lautstärke (nur wenn Video eigenes Audio hat)
# Font-Datei für drawtext. Leer => ffmpeg nutzt fontconfig-Default.
# Auf dem VPS (Ubuntu) zuverlässig setzen, z.B. nach `apt install fonts-dejavu-core`:
#   FFMPEG_FONT_FILE=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
FFMPEG_FONT_FILE       = os.getenv("FFMPEG_FONT_FILE", "")

# ============================================================
# PFADE
# ============================================================
TEMP_DIR   = "temp"
LOGS_DIR   = "logs"

# ============================================================
# CLOUDFLARE KV KEYS
# ============================================================
KV_PREFIX_VIDEO     = "video:"
KV_KEY_RESEARCH     = "research:latest"
KV_KEY_STRATEGY     = "strategy:current"
KV_KEY_BEST         = "patterns:best"
KV_KEY_WORST        = "patterns:worst"
KV_PREFIX_ABTEST    = "abtest:"
KV_KEY_CHANNEL      = "channel:stats"
KV_KEY_WEEKLY       = "weekly:report"
