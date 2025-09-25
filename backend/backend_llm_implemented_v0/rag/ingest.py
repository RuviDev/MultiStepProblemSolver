import re, json, orjson, pathlib
from pypdf import PdfReader

ROOT = pathlib.Path(__file__).resolve().parent
VAULT = ROOT / "vault"
OUT = ROOT.parent / "rag_index"
OUT.mkdir(exist_ok=True)

ANCHOR_RE = re.compile(r"^#?\s*(BND[\-–—][A-Z0-9][^\n]+)$", re.UNICODE)  # lines like "BND–GIT-..."
NEWLINE_RE = re.compile(r"\n{2,}")

def _extract_pdf_text(path: pathlib.Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def _split_by_anchor(text: str):
    lines = text.splitlines()
    chunks = []
    current = {"anchor_id": "BND–DOC-BEGIN", "title": "BEGIN", "content": []}
    for ln in lines:
        m = ANCHOR_RE.match(ln.strip())
        if m:
            # flush
            if current["content"]:
                chunks.append(current)
            aid = m.group(1).strip()
            current = {"anchor_id": aid, "title": aid, "content": []}
        else:
            current["content"].append(ln)
    if current["content"]:
        chunks.append(current)
    # join content, normalize spacing
    for c in chunks:
        c["text"] = NEWLINE_RE.sub("\n\n", "\n".join(c.pop("content")).strip())
    return chunks

def main():
    chunks_out = []
    for p in VAULT.glob("**/*.pdf"):
        raw = _extract_pdf_text(p)
        for ch in _split_by_anchor(raw):
            chunks_out.append({
                "anchor_id": ch["anchor_id"],
                "title": ch["title"],
                "text": ch["text"],
                "source_doc": p.name
            })
    with open(OUT / "chunks.jsonl", "wb") as f:
        for obj in chunks_out:
            f.write(orjson.dumps(obj))
            f.write(b"\n")
    print(f"wrote {len(chunks_out)} chunks → {OUT/'chunks.jsonl'}")

if __name__ == "__main__":
    main()
