from sentence_transformers import SentenceTransformer

_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-mpnet-base-v2")
    return _model


def generate_embedding(text: str) -> list[float]:
    model = get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()