import logging
from django.conf import settings
from django.core.cache import cache
from django.contrib.auth.models import User
from pgvector.django import CosineDistance
from google.genai import types
from digests.models import Article, Topic
from digests.embeddings import generate_embedding
from digests.services.synthesizer import get_genai_client

logger = logging.getLogger(__name__)


def retrieve_relevant_news(question: str, top_k: int = 5) -> tuple[list[dict], str]:
    """
    Recherche sémantiquement les articles et thématiques les plus pertinents
    dans la base pgvector pour contextualiser la réponse.
    """
    try:
        q_embedding = generate_embedding(question)
    except Exception as e:
        logger.error(f"Erreur génération embedding pour question: {e}")
        return [], ""

    # Recherche des articles les plus proches par similarité cosinus
    articles_qs = (
        Article.objects.filter(embedding__isnull=False)
        .annotate(distance=CosineDistance("embedding", q_embedding))
        .select_related("source", "topic")
        .order_by("distance")[:top_k]
    )

    items = []
    context_lines = []

    for art in articles_qs:
        source_name = art.source.name if art.source else "Source inconnue"
        pub_date = art.published_at.strftime("%d/%m/%Y") if art.published_at else "Date inconnue"
        snippet = (art.raw_content or "")[:600].replace("\n", " ").strip()
        topic_title = art.topic.title if art.topic else art.title

        items.append({
            "id": art.id,
            "title": art.title,
            "source": source_name,
            "date": pub_date,
            "url": art.url,
            "distance": float(art.distance) if hasattr(art, "distance") else 1.0,
        })

        context_lines.append(
            f"• Source: [{source_name}] ({pub_date})\n"
            f"  Titre: {art.title}\n"
            f"  Sujet global: {topic_title}\n"
            f"  Contenu: {snippet}\n"
            f"  Lien: {art.url}"
        )

    context_str = "\n\n".join(context_lines)
    return items, context_str


def answer_news_question(user: User, question: str) -> str:
    """
    Formule une réponse contextuelle détaillée à la question de l'utilisateur
    en interrogeant la mémoire vectorielle et Gemini.
    """
    articles, context_str = retrieve_relevant_news(question, top_k=5)

    # Récupérer l'historique de conversation récent
    cache_key = f"news_chat_history:{user.id}"
    history = cache.get(cache_key, [])

    history_str = ""
    if history:
        history_lines = []
        for turn in history[-3:]:
            role = "Utilisateur" if turn.get("role") == "user" else "Synapse"
            history_lines.append(f"{role}: {turn.get('text')}")
        history_str = "Historique récent du dialogue :\n" + "\n".join(history_lines) + "\n\n"

    client = get_genai_client()

    if client:
        models_to_try = [
            getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
            "gemini-2.0-flash",
        ]
        prompt = (
            "Tu es Synapse Assistant, un analyste d'actualités expert, neutre, vif et précis.\n"
            "Un lecteur te pose une question sur l'actualité ou souhaite approfondir un sujet.\n\n"
            f"{history_str}"
            "Dépêches et articles récents extraits de la base de veille Synapse :\n"
            f"{context_str if context_str else 'Aucune dépêche récente spécifique trouvée dans la base.'}\n\n"
            f"Question de l'utilisateur : « {question} »\n\n"
            "Consignes de rédaction :\n"
            "1. Réponds en français fluide avec un style journalistique percutant et élégant.\n"
            "2. Cite impérativement tes sources entre crochets dès qu'un fait provient d'une dépêche (ex: [TechCrunch], [Reuters]).\n"
            "3. Si les dépêches fournies sont incomplètes, complète avec tes connaissances générales avec transparence.\n"
            "4. Structure ta réponse (paragraphes courts, puces si pertinent) pour une lecture mobile agréable sur Telegram.\n"
            "5. Termine par une brève phrase d'ouverture ou un angle de réflexion complémentaire."
        )

        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.3,
                    ),
                )
                answer_text = response.text.strip()

                # Mettre à jour l'historique (max 4 échanges)
                history.append({"role": "user", "text": question})
                history.append({"role": "assistant", "text": answer_text})
                cache.set(cache_key, history[-8:], timeout=3600)

                return answer_text
            except Exception as e:
                logger.warning(f"Erreur modèle {model_name} pour news chat: {e}")
                continue

    # Fallback si le modèle LLM est indisponible
    if articles:
        lines = [
            f"🔍 *Résultats pertinents pour votre question :* « _{question}_ »\n",
            "Voici les articles les plus proches trouvés dans nos flux :",
        ]
        for art in articles[:3]:
            lines.append(f"\n📰 *{art['title']}*\nSource : {art['source']} ({art['date']})\n🔗 [Lire l'article]({art['url']})")
        lines.append("\n💡 Tapez `/digest` pour lancer la synthèse quotidienne.")
        return "\n".join(lines)

    return (
        f"Je n'ai pas trouvé d'informations récentes sur « _{question}_ » dans les dépêches surveillées.\n\n"
        "Vous pouvez reformuler votre question ou taper `/digest` pour recevoir votre briefing du jour !"
    )
