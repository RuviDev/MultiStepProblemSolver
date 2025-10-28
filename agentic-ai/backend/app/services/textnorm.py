import unicodedata
import re

_ws = re.compile(r"\s+")

def normalize(text: str) -> str:
    if text is None:
        return ""
    t = text.strip().lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^\w\s-]", " ", t)  # keep word chars, whitespace, hyphen
    t = _ws.sub(" ", t)
    return t.strip()
