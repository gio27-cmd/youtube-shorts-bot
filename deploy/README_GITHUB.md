# 🤖 Deployment über GitHub Actions (kein Server nötig)

Der Bot läuft komplett kostenlos über GitHub Actions. Statt eines Dauerprozesses
ruft jeder Cron-Trigger genau eine Aufgabe auf (`run_task.py`). Der Zustand liegt
in Cloudflare KV — die Runner sind also zustandslos.

**Workflow:** [`.github/workflows/bot.yml`](../.github/workflows/bot.yml)

| Task | Zeitplan (UTC) |
|------|----------------|
| research    | alle 6 h |
| produce     | täglich 02:30 (plant + baut + lädt 2 Videos hoch) |
| analytics   | täglich 10:00 |
| ab_evaluate | täglich 12:00 |
| comments    | 09:00 / 15:00 / 21:00 |
| optimize    | sonntags 23:00 |

---

## Voraussetzungen
- Ein GitHub-Account.
- `gh` CLI: `brew install gh` → dann `gh auth login` (einmalig, im Browser bestätigen).
- Die fertig ausgefüllte `.env` (haben wir — liegt im Projekt, wird NICHT mit hochgeladen).

---

## Schritt 1 — Repo anlegen & Code hochladen
Im Projektordner (`/Users/a27/Claude/youtube-shorts-bot`):
```bash
git init
git add .
git commit -m "YouTube Shorts Bot"
gh repo create youtube-shorts-bot --private --source=. --remote=origin --push
```
> **`--private`** empfohlen. GitHub Actions sind bei privaten Repos bis **2000 Min/Monat**
> gratis (reicht für diesen Bot). Brauchst du mehr, mach das Repo **public** (unbegrenzte
> Minuten). `.env`, `.venv`, `temp/`, `logs/` sind per `.gitignore` ausgeschlossen —
> es landen **keine Secrets** im Repo.

## Schritt 2 — Secrets hochladen (aus .env)
```bash
bash deploy/gh_set_secrets.sh
```
Lädt Gemini-, YouTube-, HuggingFace- und Cloudflare-Secrets als verschlüsselte
GitHub-Actions-Secrets hoch. Prüfen: `gh secret list`.

## Schritt 3 — Ersten Lauf manuell testen
⚠️ `produce` macht **echte öffentliche Uploads** auf den Kanal „Dogslikecats".
Zum gefahrlosen Antesten zuerst einen harmlosen Task starten:
```bash
gh workflow run "YouTube Shorts Bot" -f task=research
gh run watch
```
Wenn `research` grün ist, einen echten Produktionslauf auslösen:
```bash
gh workflow run "YouTube Shorts Bot" -f task=produce
gh run watch
```

## Schritt 4 — Läuft automatisch
Sind die Secrets gesetzt, laufen die Crons von selbst. Logs pro Lauf im
GitHub-Tab **Actions**.

---

## Wichtige Hinweise
- **Scheduled Workflows brauchen den Default-Branch** und werden nach **60 Tagen
  ohne Repo-Aktivität automatisch deaktiviert** (GitHub-Regel). Einfach gelegentlich
  committen oder den Workflow manuell starten hält sie aktiv.
- **Cron ist „best effort"** — Läufe können sich bei Last um einige Minuten verzögern.
- **Token-Erneuerung:** Ändert sich ein Key, nur das eine Secret neu setzen:
  `gh secret set HF_TOKEN --body "neuer_wert"`.
- **Instagram-Cross-Post** ist nicht im produce-Task verdrahtet (braucht eine öffentliche
  Video-URL). Bei Bedarf separat ergänzen.
