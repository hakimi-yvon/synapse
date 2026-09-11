import asyncio
import logging
import re
from pathlib import Path
import edge_tts
from django.conf import settings
from digests.models import Digest

logger = logging.getLogger(__name__)

# Voix par défaut : Voix française masculine naturelle et radio
DEFAULT_VOICE = "fr-FR-HenriNeural"


def clean_script_for_tts(text: str) -> str:
    """
    Nettoie le texte pour la synthèse vocale :
    enlève les balises Markdown, astérisques, dièses et URLs.
    """
    if not text:
        return ""
    # Supprimer les URLs
    text = re.sub(r"https?://\S+", "", text)
    # Supprimer le balisage markdown
    text = re.sub(r"[#*_`~\[\]()]", " ", text)
    # Supprimer les sauts de ligne multiples
    text = re.sub(r"\n+", ". ", text)
    # Supprimer les espaces multiples
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _synthesize_async(text: str, output_path: str, voice: str) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def generate_audio_for_digest(digest: Digest, voice: str = DEFAULT_VOICE) -> str:
    """
    Génère un fichier audio MP3 de qualité studio à partir du script du digest
    et sauvegarde l'URL relative dans digest.audio_url.
    """
    if not digest.script_text:
        raise ValueError(f"Le digest {digest.id} n'a pas de script_text à vocaliser.")

    text_to_speak = clean_script_for_tts(digest.script_text)
    if not text_to_speak:
        raise ValueError("Le texte nettoyé pour la synthèse vocale est vide.")

    # Création du dossier media/audio/digests
    audio_dir = Path(settings.MEDIA_ROOT) / "audio" / "digests"
    audio_dir.mkdir(parents=True, exist_ok=True)

    filename = f"briefing_{digest.user.username}_{digest.date}.mp3"
    filepath = audio_dir / filename

    try:
        asyncio.run(_synthesize_async(text_to_speak, str(filepath), voice))
    except Exception as e:
        logger.error(f"Erreur lors de la génération audio TTS pour digest {digest.id}: {e}")
        raise e

    audio_url = f"{settings.MEDIA_URL}audio/digests/{filename}"
    digest.audio_url = audio_url
    digest.save(update_fields=["audio_url"])

    return audio_url
