import logging
import numpy as np
from django.contrib.auth.models import User
from digests.models import Feedback, Digest, Topic, UserPreference

logger = logging.getLogger(__name__)


def process_user_feedback(user: User, score: int, digest_id: int | None = None, topic_id: int | None = None) -> tuple[bool, str]:
    """
    Enregistre le feedback utilisateur et ajuste dynamiquement son profil vectoriel d'intérêt
    (Apprentissage par renforcement vectoriel).
    """
    try:
        topic = Topic.objects.filter(id=topic_id).first() if topic_id else None
        digest = Digest.objects.filter(id=digest_id).first() if digest_id else None

        # Enregistrer le feedback en base
        Feedback.objects.create(
            user=user,
            topic=topic,
            digest=digest,
            score=score,
        )

        # Extraction du vecteur cible pour l'ajustement
        target_vector = None
        if topic and topic.centroid_embedding:
            target_vector = np.array(topic.centroid_embedding, dtype=np.float32)
        elif digest:
            topic_embeddings = list(
                digest.topics.filter(centroid_embedding__isnull=False).values_list("centroid_embedding", flat=True)
            )
            if topic_embeddings:
                avg_vec = np.mean(np.array(topic_embeddings, dtype=np.float32), axis=0)
                norm = np.linalg.norm(avg_vec)
                if norm > 0:
                    target_vector = avg_vec / norm

        # Mise à jour du profil vectoriel utilisateur
        pref, _ = UserPreference.objects.get_or_create(user=user)

        if target_vector is not None:
            # Facteurs d'apprentissage (Learning rates)
            alpha = 0.30  # Renforcement positif
            beta = 0.25   # Répulsion négative

            if pref.interest_vector is None:
                if score > 0:
                    pref.interest_vector = target_vector.tolist()
                else:
                    pref.interest_vector = (-1.0 * target_vector).tolist()
            else:
                current_vec = np.array(pref.interest_vector, dtype=np.float32)
                if score > 0:
                    updated = current_vec + alpha * target_vector
                else:
                    updated = current_vec - beta * target_vector

                norm = np.linalg.norm(updated)
                if norm > 0:
                    updated = updated / norm
                pref.interest_vector = updated.tolist()

            pref.save(update_fields=["interest_vector"])

        if score > 0:
            msg = "👍 Merci pour votre retour ! Votre profil a été enrichi : vos prochains briefings mettront davantage en avant ce genre d'actualités."
        else:
            msg = "👎 C'est bien noté ! Nous réduirons la fréquence de ce type de sujet dans vos futurs résumés."

        return True, msg

    except Exception as e:
        logger.error(f"Erreur process_user_feedback: {e}")
        return False, "Une erreur est survenue lors de l'enregistrement de votre avis."
