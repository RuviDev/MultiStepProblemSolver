import pathlib, json, orjson
import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

ROOT = pathlib.Path(__file__).resolve().parent
IDX = ROOT.parent / "rag_index"
OUT = ROOT / "insight_to_anchors.json"
CHUNKS_PATH = IDX / "chunks.jsonl"

# STEP 1 — Define insight fields and descriptions (can live in config later)
# You can expand this list easily
INSIGHT_DESCRIPTIONS = {
    "modality.visual": "prefers visual learning like diagrams and videos",
    "modality.hands_on": "prefers hands-on learning through projects or building things",
    "goal_type.deliverable_shipped": "wants to ship a deliverable or demo as a goal",
    "deadline_profile.near_term_1_4w": "needs to complete the task in around 1 to 4 weeks",
    "interactivity_level.project_first": "likes to start with projects and build-first approach",
    "chunk_size.small": "prefers small manageable chunks of work",
    "ramp_rate.balanced": "wants a balanced ramp up of difficulty or intensity",
    "tradeoff_priority.time": "wants to prioritize time and complete quickly",
    "availability_windows.evening": "works best or is available during evenings",
    "session_length.standard_25_45": "comfortable with 25 to 45 minute sessions"
}

# STEP 2 — Load RAG chunks
def load_chunks():
    chunks = []
    with open(CHUNKS_PATH, "rb") as f:
        for line in f:
            obj = orjson.loads(line)
            chunks.append({
                "anchor_id": obj["anchor_id"],
                "text": obj["text"],
                "title": obj.get("title", ""),
                "source_doc": obj.get("source_doc", ""),
            })
    return chunks

# STEP 3 — Generate similarity map
def generate_mapping():
    print("[INFO] Loading chunks and insights...")
    chunks = load_chunks()
    insight_keys = list(INSIGHT_DESCRIPTIONS.keys())
    insight_texts = list(INSIGHT_DESCRIPTIONS.values())

    print(f"[INFO] {len(insight_keys)} insights × {len(chunks)} chunks")

    model = SentenceTransformer("intfloat/e5-small-v2")
    print("[INFO] Embedding insights...")
    insight_embs = model.encode(insight_texts, normalize_embeddings=True)

    print("[INFO] Embedding chunks...")
    chunk_embs = model.encode([c["text"] for c in chunks], normalize_embeddings=True)

    # similarity: cosine (dot product because vectors are normalized)
    print("[INFO] Computing similarity matrix...")
    scores = np.matmul(insight_embs, chunk_embs.T)  # shape: (num_insights, num_chunks)

    # STEP 4 — For each insight, select top-k most similar anchors
    top_k = 5
    min_score = 0.4  # optional threshold

    mapping = {}
    for i, insight_key in enumerate(insight_keys):
        row = scores[i]
        top_idxs = row.argsort()[::-1][:top_k]
        anchors = []
        for idx in top_idxs:
            score = row[idx]
            if score < min_score:
                continue
            anchors.append(chunks[idx]["anchor_id"])
        mapping[insight_key] = anchors

    print(f"[INFO] Saving to {OUT}")
    with open(OUT, "w") as f:
        json.dump(mapping, f, indent=2)

    print("[DONE] Mapped", len(mapping), "insights → anchors")

if __name__ == "__main__":
    generate_mapping()
