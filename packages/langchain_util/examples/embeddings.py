"""Embeddings: `get_embeddings_client` plus a nearest-neighbour search.

The embeddings client reads its model from its own variable --
OPENAI_EMBEDDING_MODEL, AZURE_OPENAI_EMBEDDING_DEPLOYMENT, or
OLLAMA_EMBEDDING_MODEL -- and never from the chat model's, because a chat model
cannot embed.

Rank the built-in runbook snippets against a query:

    bazel run //packages/langchain_util/examples:embeddings -- \\
        --provider openai "the release broke checkout, how do I undo it?"

`--dry-run` embeds with a bag-of-words stand-in, so snippets rank by shared
words rather than by meaning. That is enough to check the wiring:

    bazel run //packages/langchain_util/examples:embeddings -- \\
        --dry-run "roll back a failed deploy"
"""

import argparse
import hashlib
import math
import re
from collections.abc import Sequence

from langchain_core.embeddings import Embeddings

from packages.common.logging_util import get_logger
from packages.langchain_util.api_client import Provider, get_embeddings_client

LOGGER = get_logger(name=__name__)

RUNBOOK = (
    "Roll back a failed deploy by redeploying the previous release tag.",
    "Rotate the database password in the secrets manager, then restart workers.",
    "When the queue backs up, scale the consumer deployment before touching Kafka.",
    "Certificates renew automatically; page on-call if one is within 7 days of expiry.",
    "A 502 from the load balancer usually means every upstream pod failed readiness.",
)


class BagOfWordsEmbeddings(Embeddings):
    """A dry-run stand-in that hashes each word into one of `size` buckets.

    Any `Embeddings` implementation fits where the real client would. That is
    also how you would wrap a model LangChain has no integration for.
    """

    def __init__(self, size: int = 256) -> None:
        self.size = size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.size
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            # hashlib rather than hash(): str hashes are salted per process, so
            # the same word would land in a different bucket on every run.
            digest = hashlib.blake2b(word.encode(), digest_size=4).digest()
            vector[int.from_bytes(digest) % self.size] += 1.0

        return vector


def build_embeddings(*, provider: Provider, dry_run: bool) -> Embeddings:
    if dry_run:
        return BagOfWordsEmbeddings()

    return get_embeddings_client(provider=provider)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity, computed in full.

    OpenAI returns unit-length vectors, where a plain dot product would do, but
    not every provider normalises. Dividing by the norms keeps the ranking
    correct whichever one is configured.
    """
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norm == 0.0:
        return 0.0

    return sum(x * y for x, y in zip(a, b, strict=True)) / norm


def search(
    *,
    query: str,
    documents: Sequence[str],
    embeddings: Embeddings,
    top_k: int,
) -> list[tuple[float, str]]:
    """Return the `top_k` documents closest to `query`, best first.

    Documents and the query go through different methods on purpose. Some
    models, e5 and nomic-embed among them, are trained with a different prefix
    on each side, and an integration that knows this adds it inside
    `embed_documents`/`embed_query`. The three providers here do not:
    `OllamaEmbeddings.embed_query` is `embed_documents([text])[0]`. So with such
    a model on Ollama, add the prefixes yourself, or search quality drops without
    any error to tell you.
    """
    document_vectors = embeddings.embed_documents(list(documents))
    query_vector = embeddings.embed_query(query)
    LOGGER.info(
        "Embedded %d document(s) and the query into %d dimensions",
        len(document_vectors),
        len(query_vector),
    )

    scored = [
        (cosine(query_vector, vector), document)
        for vector, document in zip(document_vectors, documents, strict=True)
    ]
    return sorted(scored, reverse=True)[:top_k]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="What to search the runbook for")
    parser.add_argument(
        "--provider",
        choices=("openai", "azure", "ollama"),
        default="openai",
        help="Which embeddings client to build (default: openai)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="How many snippets to print (default: 3)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Embed with a local bag-of-words stand-in instead of the provider",
    )
    args = parser.parse_args()

    try:
        hits = search(
            query=args.query,
            documents=RUNBOOK,
            embeddings=build_embeddings(provider=args.provider, dry_run=args.dry_run),
            top_k=args.top_k,
        )
    except Exception:
        # CLI boundary: report and exit non-zero. Unlike invoke_llm, the
        # embeddings client has no retry or logging wrapper in langchain_util,
        # so this is the only place the traceback gets logged.
        LOGGER.exception("Could not search for %r", args.query)
        return 1

    for score, document in hits:
        print(f"{score:.3f}  {document}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
