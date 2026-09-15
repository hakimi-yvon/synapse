import asyncio
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
import edge_tts
from django.conf import settings
from digests.models import Digest

logger = logging.getLogger(__name__)

# Voix françaises neuronales Microsoft de haute fidélité
VOICE_HENRI = "fr-FR-HenriNeural"   # Voix masculine posée, chaleureuse (animateur principal)
VOICE_DENISE = "fr-FR-DeniseNeural" # Voix féminine vive, claire (co-animatrice)
DEFAULT_VOICE = VOICE_HENRI

SPEAKER_VOICES = {
    "HENRI": VOICE_HENRI,
    "DENISE": VOICE_DENISE,
}


def clean_script_for_tts(text: str) -> str:
    """
    Nettoie le texte pour la synthèse vocale :
    enlève les balises Markdown, astérisques, dièses, crochets et URLs.
    """
    if not text:
        return ""
    # Supprimer les URLs
    text = re.sub(r"https?://\S+", "", text)
    # Supprimer le balisage markdown et crochets résiduels
    text = re.sub(r"[#*_`~\[\]()]", " ", text)
    # Supprimer les sauts de ligne multiples
    text = re.sub(r"\n+", ". ", text)
    # Supprimer les espaces multiples
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_dialogue_turns(script_text: str) -> list[tuple[str, str]]:
    """
    Découpe un script contenant des balises de dialogue [HENRI]: ... et [DENISE]: ...
    en une liste ordonnée de (speaker, texte).
    Si aucune balise n'est détectée, retourne un segment unique sous DEFAULT_VOICE.
    """
    pattern = re.compile(r"\[(HENRI|DENISE)\]\s*:\s*(.*?)(?=\[(?:HENRI|DENISE)\]\s*:|\Z)", re.DOTALL | re.IGNORECASE)
    matches = list(pattern.finditer(script_text))
    if not matches:
        return [("HENRI", script_text.strip())]

    turns = []
    for m in matches:
        speaker = m.group(1).upper()
        content = m.group(2).strip()
        if content:
            turns.append((speaker, content))

    return turns if turns else [("HENRI", script_text.strip())]


async def _synthesize_async(text: str, output_path: str, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def synthesize_text_to_file(text: str, output_path: str, voice: str = DEFAULT_VOICE) -> str:
    """
    Vocalise un texte simple vers un fichier de destination en MP3.
    """
    cleaned = clean_script_for_tts(text)
    if not cleaned:
        raise ValueError("Le texte à vocaliser est vide après nettoyage.")

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    asyncio.run(_synthesize_async(cleaned, str(out_file), voice))
    return str(out_file)


def _generate_silence_file(path: str, duration_sec: float = 0.25) -> None:
    """
    Génère un court fichier de silence MP3 pour respirer entre deux répliques radio.
    """
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "anullsrc=r=24000:cl=mono",
        "-t", str(duration_sec),
        "-c:a", "libmp3lame", "-b:a", "128k",
        path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def generate_audio_for_digest(digest: Digest, voice: str = DEFAULT_VOICE) -> str:
    """
    Génère un podcast audio complet de qualité studio.
    Si le script contient des répliques [HENRI] et [DENISE], alterne les voix
    en mode Duo Radio et fusionne les pistes avec micro-silences.
    Sauvegarde l'URL relative dans digest.audio_url.
    """
    if not digest.script_text:
        raise ValueError(f"Le digest {digest.id} n'a pas de script_text à vocaliser.")

    turns = parse_dialogue_turns(digest.script_text)
    if not turns:
        raise ValueError("Aucun texte exploitable pour la synthèse vocale.")

    # Dossier de destination media/audio/digests
    audio_dir = Path(settings.MEDIA_ROOT) / "audio" / "digests"
    audio_dir.mkdir(parents=True, exist_ok=True)

    filename = f"briefing_{digest.user.username}_{digest.date}.mp3"
    final_filepath = audio_dir / filename

    # Cas 1 : Voix unique (sans alternance duo)
    if len(turns) == 1 and turns[0][0] not in SPEAKER_VOICES:
        cleaned_text = clean_script_for_tts(turns[0][1])
        asyncio.run(_synthesize_async(cleaned_text, str(final_filepath), voice))
    else:
        # Cas 2 : Duo Radio multi-voix
        with tempfile.TemporaryDirectory() as tmpdir:
            silence_path = os.path.join(tmpdir, "silence.mp3")
            try:
                _generate_silence_file(silence_path, duration_sec=0.25)
                has_silence = True
            except Exception as e:
                logger.warning(f"Impossible de générer le silence ffmpeg: {e}")
                has_silence = False

            concat_entries = []
            for idx, (speaker, turn_text) in enumerate(turns):
                cleaned_turn = clean_script_for_tts(turn_text)
                if not cleaned_turn:
                    continue

                speaker_voice = SPEAKER_VOICES.get(speaker, voice)
                turn_filename = f"turn_{idx}.mp3"
                turn_path = os.path.join(tmpdir, turn_filename)

                asyncio.run(_synthesize_async(cleaned_turn, turn_path, speaker_voice))

                if concat_entries and has_silence:
                    concat_entries.append(silence_path)
                concat_entries.append(turn_path)

            if not concat_entries:
                raise ValueError("Aucun segment audio n'a pu être synthétisé pour le digest.")

            # Création du fichier liste pour FFmpeg concat demuxer
            concat_txt = os.path.join(tmpdir, "concat_list.txt")
            with open(concat_txt, "w", encoding="utf-8") as f:
                for entry in concat_entries:
                    f.write(f"file '{entry}'\n")

            # Concaténation et réencodage haute fidélité
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_txt,
                "-c:a", "libmp3lame", "-b:a", "128k",
                str(final_filepath)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                logger.error(f"Erreur ffmpeg concat: {res.stderr}")
                raise RuntimeError(f"FFmpeg concat a échoué: {res.stderr}")

    audio_url = f"{settings.MEDIA_URL}audio/digests/{filename}"
    digest.audio_url = audio_url
    digest.save(update_fields=["audio_url"])

    return audio_url
