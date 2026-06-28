"""
Post Production — FFmpeg kombiniert Video + Musik.

In EINEM Durchlauf:
1. Musik mischen (30% Lautstärke)
2. Auf echtes HD-Shorts-Format (1080×1920) bringen
3. Fade in/out (0.3 Sek)

Hinweis: Es werden KEINE Text-Overlays (Hook/Fakt) mehr ins Video gebrannt.
Der Tier-Fakt landet stattdessen in der YouTube-Beschreibung (siehe uploader).
"""

import os
import ffmpeg
from loguru import logger
from config.settings import (
    TEMP_DIR, VIDEO_DURATION_SEC, VIDEO_RESOLUTION_W, VIDEO_RESOLUTION_H,
    FFMPEG_MUSIC_VOLUME
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
                # Auf echtes HD-Shorts-Format bringen (1080×1920). Das KI-Modell
                # liefert oft eine niedrigere Auflösung → ohne diesen Schritt stuft
                # YouTube das Video als SD ein. scale (cover) + crop = exakt
                # 1080×1920 ohne schwarze Balken; setsar=1 für saubere Pixel.
                .filter("scale", VIDEO_RESOLUTION_W, VIDEO_RESOLUTION_H,
                        force_original_aspect_ratio="increase")
                .filter("crop", VIDEO_RESOLUTION_W, VIDEO_RESOLUTION_H)
                .filter("setsar", 1)
                # Fade in (erste ~0.33 Sek)
                .filter("fade", type="in", start_time=0, duration=fade_d)
                # Fade out (letzte ~0.33 Sek) — zeitbasiert, da der fade-Filter
                # bei start_frame KEINE Ausdrücke akzeptiert (war der Crash-Grund).
                .filter("fade", type="out", start_time=fade_out_start, duration=fade_d)
                # KEINE Text-Overlays mehr — Hook/Fakt stehen in der Beschreibung.
            )

            # Output
            ffmpeg.output(
                video_filtered,
                mixed_audio,
                output_path,
                vcodec="libx264",
                acodec="aac",
                audio_bitrate="128k",
                # 2000k war zu niedrig für 1080p (Block-Artefakte). 6000k ist für
                # 1080×1920 Shorts angemessen.
                video_bitrate="6000k",
                pix_fmt="yuv420p",
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
