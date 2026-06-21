# 🚀 Deployment auf Oracle Cloud (Always Free ARM)

Ziel: Bot läuft 24/7 als systemd-Dienst auf einem kostenlosen Ubuntu-ARM-Server.

---

## Schritt 1 — Oracle-Account + ARM-Instanz (machst DU)

> Das kann ich dir nicht abnehmen (Kreditkarten-Verifizierung, persönliche Daten, AGB).
> 0 € Belastung, die Karte dient nur der Verifizierung.

1. **https://cloud.oracle.com** → Account erstellen (Region nahe dir wählen, z.B. Frankfurt).
2. Console → **Compute → Instances → Create Instance**.
3. **Image & Shape:**
   - Image: **Canonical Ubuntu 22.04** (oder 24.04)
   - Shape: **Ampere (ARM) → VM.Standard.A1.Flex** → **2 OCPU / 12 GB RAM**
     (alles innerhalb „Always Free")
4. **SSH-Key:** „Generate a key pair for me" → **beide Dateien herunterladen**
   (den privaten Key brauchst du gleich, z.B. `~/Downloads/ssh-key.key`).
5. **Create.** Wenn „Out of capacity" kommt: andere Availability Domain wählen oder
   später erneut versuchen (ARM ist oft knapp — einfach dranbleiben).
6. Wenn die Instanz läuft: **Public IP** notieren.

Tipp `chmod` für den Key (einmalig, lokal):
```bash
chmod 600 ~/Downloads/ssh-key.key
```

---

## Schritt 2 — Projekt + .env auf den Server kopieren (lokal auf dem Mac)

Ersetze `DEIN_KEY` und `DEINE_IP`:
```bash
rsync -av \
  --exclude='.venv' --exclude='__pycache__' \
  --exclude='temp/*' --exclude='logs/*' \
  -e "ssh -i ~/Downloads/ssh-key.key" \
  /Users/a27/Claude/youtube-shorts-bot/ \
  ubuntu@DEINE_IP:~/youtube-shorts-bot/
```
> Das lädt auch deine `.env` mit allen Keys hoch (über SSH verschlüsselt). Die lokale
> Mac-`.venv` wird bewusst ausgelassen — sie wird auf dem ARM-Server neu gebaut.

---

## Schritt 3 — Auf den Server einloggen & einrichten

```bash
ssh -i ~/Downloads/ssh-key.key ubuntu@DEINE_IP

# auf dem Server:
cd ~/youtube-shorts-bot
bash deploy/setup_vps.sh        # Python 3.11, ffmpeg, Fonts, venv, requirements
```

---

## Schritt 4 — Als 24/7-Dienst starten

```bash
bash deploy/install_service.sh
```
Der Bot startet automatisch (auch nach Reboot) und wird bei Absturz neu gestartet.

---

## Schritt 5 — Läuft er?

```bash
journalctl -u youtube-bot.service -f      # Live-Logs (systemd)
tail -f ~/youtube-shorts-bot/logs/bot.log # Bot-eigenes Logfile
```
Beim Start läuft sofort der Researcher; die Produktion startet planmäßig um 02:00 UTC.

---

## Hinweise
- **Keine Ports öffnen nötig** — der Bot macht nur ausgehende Anfragen.
- **Updates einspielen:** lokal Code ändern → Schritt 2 (rsync) erneut →
  `sudo systemctl restart youtube-bot.service`.
- **Erster echter Upload:** Der Bot postet öffentlich auf den Kanal „Dogslikecats".
  Für einen kontrollierten ersten Lauf vorher manuell testen:
  `./.venv/bin/python main.py` und beobachten (Strg+C zum Stoppen), bevor du den
  Dienst dauerhaft aktivierst.
