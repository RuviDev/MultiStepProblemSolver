import json, orjson, numpy as np, pathlib
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
import faiss

ROOT = pathlib.Path(__file__).resolve().parent
IDX = ROOT.parent / "rag_index"

def _load_chunks():
    chunks = []
    with open(IDX / "chunks.jsonl", "rb") as f:
        for line in f:
            chunks.append(orjson.loads(line))
    return chunks

def main():
    chunks = _load_chunks()
    texts = [c["text"] for c in chunks]
    # ----- BM25 -----
    tokenized = [t.lower().split() for t in texts]
    bm25 = BM25Okapi(tokenized)
    np.save(IDX / "bm25_tokenized.npy", np.array(tokenized, dtype=object))
    with open(IDX / "manifest.json", "w") as f:
        json.dump({"count": len(chunks)}, f)

    # ----- Dense embeddings -----
    model = SentenceTransformer("intfloat/e5-small-v2")
    embs = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    np.save(IDX / "dense.npy", embs)

    # ----- FAISS -----
    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim)  # cosine if normalized
    index.add(embs.astype("float32"))
    faiss.write_index(index, str(IDX / "faiss.index"))

    # ID map
    with open(IDX / "id_map.json", "w") as f:
        json.dump({i: {"anchor_id": c["anchor_id"], "source_doc": c["source_doc"], "title": c["title"]} for i, c in enumerate(chunks)}, f)
    print(f"indexed {len(chunks)} chunks")

if __name__ == "__main__":
    main()
