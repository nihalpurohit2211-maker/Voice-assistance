from fastembed import TextEmbedding
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

_model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2")

def embed(text: str) -> list[float]:
    """
    Generate an embedding for a given text using fastembed.
    Returns a 384-dimensional vector.
    """
    # fastembed returns a generator of numpy arrays
    embeddings = list(_model.embed([text]))
    return embeddings[0].tolist()
