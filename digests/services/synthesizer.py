import json
import logging
from django.conf import settings
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from digests.models import Topic

logger = logging.getLogger(__name__)


class TopicSummarySchema(BaseModel):
    title: str = Field(description="Titre journalistique clair et percutant, max 120 caractères")
    summary_bullets: list[str] = Field(description="3 points clés précis et factuels")
    importance_score: int = Field(description="Score d'importance de 1 (anecdotique) à 10 (majeur)", ge=1, le=10)
    is_breaking_news: bool = Field(description="Vrai si l'événement est une alerte critique immédiate")
    category: str = Field(description="Catégorie thématique (ex: Tech, IA, Économie)")


def get_genai_client():
    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def summarize_topic(topic: Topic) -> dict:
    """
    Analyse l'ensemble des articles associés à un Topic et utilise un LLM
    pour générer un titre journalistique, 3 points clés, un score d'importance
    et un statut de breaking news.
    """
    articles = list(topic.article_set.all()[:10])
    if not articles:
        return {
            "title": topic.title,
            "summary_bullets": topic.summary_bullets,
            "importance_score": topic.importance_score,
            "is_breaking_news": topic.is_breaking_news,
        }

    # Préparation du contexte pour le LLM
    articles_context = []
    for idx, art in enumerate(articles, start=1):
        content_snippet = art.raw_content[:800] if art.raw_content else "Pas de contenu supplémentaire."
        articles_context.append(f"Article {idx} ({art.source.name if art.source else 'Source'}):\nTitre: {art.title}\nContenu: {content_snippet}")

    context_str = "\n\n".join(articles_context)
    client = get_genai_client()

    if client:
        try:
            model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
            prompt = (
                "Tu es un rédacteur en chef et analyste d'actualités expert pour un service de veille haute précision.\n"
                "Voici plusieurs articles récents qui traitent du même événement ou sujet :\n\n"
                f"{context_str}\n\n"
                "Synthétise cet ensemble d'articles et produis une analyse structurée."
            )

            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=TopicSummarySchema,
                    temperature=0.2,
                ),
            )

            data = json.loads(response.text)
            topic.title = data.get("title", topic.title)
            topic.summary_bullets = data.get("summary_bullets", [])
            topic.importance_score = data.get("importance_score", 5)
            topic.is_breaking_news = data.get("is_breaking_news", False)
            if data.get("category"):
                topic.category = data["category"]

            topic.save(update_fields=["title", "summary_bullets", "importance_score", "is_breaking_news", "category"])
            return data

        except Exception as e:
            logger.error(f"Erreur lors de l'appel Gemini pour le topic {topic.id}: {e}")

    # Fallback hors-ligne / heuristique si pas d'API key ou échec réseau
    fallback_bullets = [art.title for art in articles[:3]]
    topic.summary_bullets = fallback_bullets
    topic.save(update_fields=["summary_bullets"])
    return {
        "title": topic.title,
        "summary_bullets": fallback_bullets,
        "importance_score": topic.importance_score,
        "is_breaking_news": topic.is_breaking_news,
    }


def generate_digest_script(topics: list[Topic], format_preference: str = "both") -> str:
    """
    Génère le script complet du briefing quotidien pour un ensemble de topics.
    Si le format est audio ou les deux, produit un script parlé fluide style chronique radio.
    Si le format est texte, produit un markdown élégant.
    """
    if not topics:
        return "Aucune actualité majeure ne correspond à vos filtres aujourd'hui."

    client = get_genai_client()
    topics_data = []
    for t in topics:
        bullets = "\n  - ".join(t.summary_bullets) if t.summary_bullets else "Détails à venir."
        topics_data.append(f"• {t.title} (Importance: {t.importance_score}/10, Catégorie: {t.category})\n  - {bullets}")

    topics_summary_str = "\n\n".join(topics_data)

    if client:
        try:
            model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
            if format_preference in ["audio", "both"]:
                prompt = (
                    "Tu es le présentateur du podcast quotidien 'Synapse', un briefing d'actualité matinal intelligent, percutant et dynamique.\n"
                    "Voici les sujets d'actualité sélectionnés pour l'auditeur aujourd'hui :\n\n"
                    f"{topics_summary_str}\n\n"
                    "Rédige le script audio complet à lire à voix haute (environ 2 à 3 minutes de lecture).\n"
                    "Consignes :\n"
                    "- Commence par une accroche chaleureuse ('Bonjour et bienvenue dans votre briefing Synapse...').\n"
                    "- Fais des transitions naturelles et fluides entre chaque sujet.\n"
                    "- Pas de puces visuelles (pas de tirets, de puces ou de symboles Markdown) car ce texte sera directement lu par une voix de synthèse (TTS).\n"
                    "- Termine par un mot d'au revoir inspirant pour démarrer la journée."
                )
            else:
                prompt = (
                    "Tu es l'analyste en chef de 'Synapse', un service de veille d'élite.\n"
                    "Voici les sujets du jour :\n\n"
                    f"{topics_summary_str}\n\n"
                    "Mets en forme ce digest en Markdown clair et percutant, adapté à la lecture sur mobile (WhatsApp/Telegram).\n"
                    "Consignes :\n"
                    "- Utilise des emojis thématiques adaptés.\n"
                    "- Structure chaque sujet avec son titre en gras et ses points clés.\n"
                    "- Sois concis et direct."
                )

            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.4),
            )
            return response.text

        except Exception as e:
            logger.error(f"Erreur lors de la génération du digest script via Gemini: {e}")

    # Fallback textuel formaté
    lines = ["# 🎙️ Votre Briefing Synapse\n"]
    for t in topics:
        lines.append(f"### {t.title} `[{t.category}]`")
        if t.summary_bullets:
            for b in t.summary_bullets:
                lines.append(f"- {b}")
        lines.append("")
    return "\n".join(lines)
