"""
Einmaliges Script zum Generieren des YouTube OAuth Refresh Tokens.
Führe dies NUR EINMAL aus bevor du den Bot startest.

Ausführung: python oauth2_setup.py
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

def main():
    client_config = {
        "installed": {
            "client_id": os.getenv("YOUTUBE_CLIENT_ID"),
            "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET"),
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=0)

    print("\n" + "="*60)
    print("✅ ERFOLG! Kopiere diesen Refresh Token in deine .env:")
    print("="*60)
    print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
