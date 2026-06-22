"""
Post Production — FFmpeg kombiniert Video + Musik + Text.

In EINEM Durchlauf:
1. Musik mischen (30% Lautstärke)
2. Hook-Text erste 2 Sekunden (groß, oben, fett)
3. Tier-Fakt Sekunde 4-8 (mittig, gelb)
4. Fade in/out (0.3 Sek)
"""

import os
import re
import ffmpeg
from loguru import logger
from config.settings import (
    TEMP_DIR, VIDEO_DURATION_SEC,
    FFMPEG_FONT_SIZE_HOOK, FFMPEG_FONT_SIZE_FACT,
    FFMPEG_FONT_COLOR, FFMPEG_FONT_BORDER, FFMPEG_MUSIC_VOLUME,
    FFMPEG_FONT_FILE
)

# Emoji-/Symbol-Bereiche — ffmpeg drawtext kann keine Farb-Emojis rendern,
# sonst erscheinen leere Kästchen im Video. Daher aus den Overlays entfernen
# (in Titel/Beschreibung auf YouTube bleiben Emojis natürlich erhalten).
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F\U0000200D]+",
    flags=re.UNICODE
)


class PostProduction:

    def produce(
        self,
        video_path:  str,
        music_path:  str,
        content:     dict,
        video_id:    str,
        variant:     str = "a"
    ) -> str:
        """
        Produziert das finale Video.
        variant: "a" oder "b" für A/B Test (unterschiedliche Hook-Texte)
        """
        output_path = os.path.join(TEMP_DIR, f"{video_id}_final_{variant}.mp4")
        os.makedirs(TEMP_DIR, exist_ok=True)

        hook_text   = content.get(f"hook_text_{variant}", "You won't believe this 😱")
        animal_fact = content.get("animal_fact", "")

        # Emojis raus (drawtext kann sie nicht) + Sonderzeichen für FFmpeg escapen
        hook_escaped  = self._escape_ffmpeg_text(self._strip_emoji(hook_text))
        fact_escaped  = self._escape_ffmpeg_text(self._strip_emoji(animal_fact))

        # Optionale Font-Datei (auf dem VPS gesetzt) für alle drawtext-Aufrufe
        font_kw = {"fontfile": FFMPEG_FONT_FILE} if FFMPEG_FONT_FILE else {}

        # Echte Videodauer für den Fade-out (zeitbasiert, kein Frame-Ausdruck).
        dur = self._duration(video_path)
        fade_d = 0.33
        fade_out_start = max(dur - fade_d, 0.0)

        try:
            # Video Input
            video_in = ffmpeg.input(video_path)
            audio_in = ffmpeg.input(music_path)

            # Audio: KI-Videos (LTX & Co.) haben i.d.R. KEINE Tonspur.
            # Hat das Video Audio -> mischen (Original 1 : Musik FFMPEG_MUSIC_VOLUME).
            # Hat es keins -> Musik ist die alleinige Tonspur (volle Lautstärke).
            if self._has_audio(video_path):
                mixed_audio = ffmpeg.filter(
                    [video_in.audio, audio_in.audio],
                    "amix",
                    inputs=2,
                    weights=f"1 {FFMPEG_MUSIC_VOLUME}"
                )
            else:
                mixed_audio = audio_in.audio

            # Video Filter Chain
            video_filtered = (
                video_in.video
                # Fade in (erste ~0.33 Sek)
                .filter("fade", type="in", start_time=0, duration=fade_d)
                # Fade out (letzte ~0.33 Sek) — zeitbasiert, da der fade-Filter
                # bei start_frame KEINE Ausdrücke akzeptiert (war der Crash-Grund).
                .filter("fade", type="out", start_time=fade_out_start, duration=fade_d)
                # Hook-Text: erste 2 Sekunden, oben zentriert
                .drawtext(
                    text=hook_escaped,
                    fontsize=FFMPEG_FONT_SIZE_HOOK,
                    fontcolor=FFMPEG_FONT_COLOR,
                    borderw=3,
                    bordercolor=FFMPEG_FONT_BORDER,
                    x="(w-text_w)/2",
                    y="80",
                    enable="between(t,0,2)",
                    **font_kw
                )
                # Tier-Fakt: Sekunde 4-8, mittig
                .drawtext(
                    text=fact_escaped,
                    fontsize=FFMPEG_FONT_SIZE_FACT,
                    fontcolor="yellow",
                    borderw=2,
                    bordercolor=FFMPEG_FONT_BORDER,
                    x="(w-text_w)/2",
                    y="(h-text_h)/2",
                    enable="between(t,4,8)",
                    **font_kw
                )
            )

            # Output
            ffmpeg.output(
                video_filtered,
                mixed_audio,
                output_path,
                vcodec="libx264",
                acodec="aac",
                audio_bitrate="128k",
                video_bitrate="2000k",
                r=24,
                shortest=None
            ).overwrite_output().run(quiet=True)

            if self.verify_output(output_path):
                logger.info(f"✅ Post-Produktion: {output_path}")
                return output_path
            else:
                raise RuntimeError("Output-Verifikation fehlgeschlagen")

        except ffmpeg.Error as e:
            # Die eigentliche Ursache steht in ffmpegs stderr, nicht in str(e).
            stderr = e.stderr.decode("utf-8", "replace") if getattr(e, "stderr", None) else ""
            logger.error(f"Post-Produktion ffmpeg-Fehler: {stderr[-1500:] or e}")
            raise
        except Exception as e:
            logger.error(f"Post-Produktion Fehler: {e}")
            raise

    def _duration(self, video_path: str) -> float:
        """Liest die Videodauer in Sekunden; Fallback auf die Soll-Länge."""
        try:
            probe = ffmpeg.probe(video_path)
            return float(probe["format"]["duration"])
        except Exception:
            return float(VIDEO_DURATION_SEC)

    def _has_audio(self, video_path: str) -> bool:
        """Prüft ob die Videodatei eine Audiospur enthält."""
        try:
            probe = ffmpeg.probe(video_path)
            return any(s.get("codec_type") == "audio" for s in probe.get("streams", []))
        except Exception:
            return False

    def _strip_emoji(self, text: str) -> str:
        """Entfernt Emojis/Symbole, die drawtext nicht rendern kann."""
        return _EMOJI_RE.sub("", text).strip()

    def _escape_ffmpeg_text(self, text: str) -> str:
        """Escaped Sonderzeichen für FFmpeg drawtext."""
        return (
            text
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
        )

    def verify_output(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        size = os.path.getsize(path)
        # 100KB - 256MB: kurze 8s-Shorts sind oft <1MB, daher untere Grenze gesenkt
        if not (100_000 <= size <= 256_000_000):
            return False
        try:
            probe = ffmpeg.probe(path)
            duration = float(probe["format"]["duration"])
            return 3.0 <= duration <= 65.0
        except Exception:
            return False

    def cleanup_temp(self, video_id: str) -> None:
        """Löscht temporäre Dateien nach erfolgreichem Upload."""
        patterns = [
            f"{video_id}_image.jpg",
            f"{video_id}_raw.mp4",
            f"{video_id}_music.mp3",
            f"{video_id}_final_a.mp4",
            f"{video_id}_final_b.mp4"
        ]
        for filename in patterns:
            path = os.path.join(TEMP_DIR, filename)
            if os.path.exists(path):
                os.remove(path)
                logger.debug(f"Gelöscht: {filename}")
