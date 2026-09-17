import math
from backend.services.embeddings import embed

def cosine_similarity(v1, v2):
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    return dot / (mag1 * mag2)

def verify():
    # Test 1: Length
    vec1 = embed("hello world")
    assert len(vec1) == 384, f"Expected 384 dimensions, got {len(vec1)}"
    
    # Test 2: Similarity
    vec_a = embed("I love hiking in the mountains.")
    vec_b = embed("Walking up steep trails is my favorite hobby.")
    vec_c = embed("The stock market crashed today.")
    
    sim_ab = cosine_similarity(vec_a, vec_b)
    sim_ac = cosine_similarity(vec_a, vec_c)
    
    print(f"Similarity (Hiking vs Walking): {sim_ab:.4f}")
    print(f"Similarity (Hiking vs Stock): {sim_ac:.4f}")
    
    assert sim_ab > sim_ac, "Semantically similar sentences should have higher similarity."
    print("Phase 3 verification successful.")

if __name__ == "__main__":
    verify()
