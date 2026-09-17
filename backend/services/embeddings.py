from sentence_transformers import SentenceTransformer
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def embed(text: str) -> list[float]:
    """
    Generate an embedding for a given text.
    Returns a 384-dimensional vector.
    """
    embedding = _model.encode(text)
    return embedding.tolist()
