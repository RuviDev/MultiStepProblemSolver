# intent_llm.py
import json
from typing import Tuple
from app.core.openai_client import client, DEFAULT_MODEL, REQUEST_TIMEOUT

# SYSTEM_PROMPT = (
#     "You are a precise boolean classifier for a single chat message.\n"
#     "Return ONLY a JSON object that conforms to the provided JSON Schema.\n"
#     "\n"
#     "Definitions:\n"
#     "- employment_intent: true if the message does ANY of the following:\n"
#     "  (a) states or implies the user's job/role/title/category, OR\n"
#     "  (b) discusses or asks about a job category, profession, or professional field/industry\n"
#     "      even in general (e.g., 'tell me about data science', 'what does a product manager do',\n"
#     "      'careers in cybersecurity', 'is data science a good field?').\n"
#     "  Set to false only when the message is unrelated to jobs/roles/professional fields.\n"
#     "\n"
#     "  DETERMINISTIC RULES (take priority):\n"
#     "  - If the text contains the exact phrase 'data science' (case-insensitive), set employment_intent=true\n"
#     "    even if the word 'field' is not present.\n"
#     "  - If the text explicitly names a role/title like 'data scientist', set employment_intent=true.\n"
#     "\n"
#     "- skills_intent: true ONLY if the message asks to choose, prioritize, or improve skills, or\n"
#     "  requests a learning plan/roadmap/course.\n"
#     "  Examples: 'which skills should I learn', 'help me pick 4 skills',\n"
#     "  'how do I improve my SQL skill', 'make me a learning roadmap'.\n"
#     "  Set to false for general explanations/overviews of a field (e.g., 'explain data science',\n"
#     "  'what is data science') unless the user is explicitly asking about skills.\n"
#     "\n"
#     "- ec_hit: set to 'ec_ds' ONLY if the message explicitly mentions a Data Scientist role/title.\n"
#     "  Treat these as explicit mentions (examples, not exhaustive):\n"
#     "  'data scientist', 'senior data scientist', 'lead data scientist',\n"
#     "  'ml/data scientist', 'machine learning scientist' (as a role),\n"
#     "  'i am a data scientist', 'i work as a data scientist'.\n"
#     "  Do NOT set ec_hit when the text only references data science as a field/activity\n"
#     "  (e.g., 'i like data science', 'i study data science', 'tell me about data science').\n"
#     "\n"
#     "Notes:\n"
#     "- employment_intent can be true while ec_hit is null.\n"
#     "- skills_intent is independent of employment_intent.\n"
#     "- Never guess based on profile or prior chats—use the current message only.\n"
#     "- When unsure about an explicit Data Scientist role mention, leave ec_hit null.\n"
# )

SYSTEM_PROMPT = (
    "You are a precise boolean classifier for a single chat message.\n"
    "Return ONLY a JSON object that conforms to the provided JSON Schema.\n"
    "\n"
    "Definitions:\n"
    "- employment_intent: true if the message does ANY of the following:\n"
    "  (a) states or implies the user's job/role/title/category, OR\n"
    "  (b) discusses or asks about a job category, profession, or professional field/industry\n"
    "      even in general (e.g., 'tell me about data science', 'what does a product manager do',\n"
    "      'careers in cybersecurity', 'is data science a good field?').\n"
    "  Set to false only when the message is unrelated to jobs/roles/professional fields.\n"
    "\n"
    "  DETERMINISTIC RULES (employment):\n"
    "  - If the text contains the exact phrase 'data science' (case-insensitive), set employment_intent=true\n"
    "    even if the word 'field' is not present.\n"
    "  - If the text explicitly names a role/title like 'data scientist', set employment_intent=true.\n"
    "\n"
    "- skills_intent: true if the message asks to choose, prioritize, or improve skills, or requests a learning\n"
    "  plan/roadmap/course.\n"
    "  Additionally, set skills_intent=true if the text MENTIONS any concrete skills/technologies commonly associated\n"
    "  with the employment category (case-insensitive), even without an explicit 'learn/improve' request.\n"
    "  (Examples for Data-Science skill lexicon — not exhaustive):\n"
    "  ['python','r (language)','sql','pandas','numpy','scikit-learn','sklearn','tensorflow','pytorch',\n"
    "   'machine learning','ml','deep learning','dl','nlp','natural language processing','computer vision','cv',\n"
    "   'time series','feature engineering','statistics','probability','matplotlib','seaborn','tableau','power bi']\n"
    "  If any of these appear as words/phrases in the message, set skills_intent=true.\n"
    "  (Note: the general phrase 'data science' alone does NOT imply a specific skill; use the lexicon above.)\n"
    "\n"
    "- ec_hit: set to 'ec_ds' ONLY if the message explicitly mentions a Data Scientist role/title.\n"
    "  Treat these as explicit mentions (examples, not exhaustive):\n"
    "  'data scientist', 'senior data scientist', 'lead data scientist', 'ml/data scientist',\n"
    "  'machine learning scientist' (as a role), 'i am a data scientist', 'i work as a data scientist'.\n"
    "  Do NOT set ec_hit when the text only references data science as a field/activity\n"
    "  (e.g., 'i like data science', 'i study data science', 'tell me about data science').\n"
    "\n"
    "Notes:\n"
    "- employment_intent can be true while ec_hit is null.\n"
    "- skills_intent is independent of employment_intent (mentioning skills is enough to set it true).\n"
    "- Never guess based on profile or prior chats—use the current message only.\n"
    "- When unsure about an explicit Data Scientist role mention, leave ec_hit null.\n"
)


INTENT_SCHEMA = {
    "name": "UIAIntent",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "employment_intent": {"type": "boolean"},
            "skills_intent": {"type": "boolean"},
            "ec_hit": {"type": ["string", "null"], "enum": ["ec_ds", None]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        },
        "required": ["employment_intent", "skills_intent", "ec_hit", "confidence"]
    },
    "strict": True
}

def _coerce_bool(v) -> bool:
    return True if v is True else False

async def detect_intents_llm(message: str) -> Tuple[bool, bool]:
    comp = await client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        response_format={"type": "json_schema", "json_schema": INTENT_SCHEMA},
        temperature=0,
        timeout=REQUEST_TIMEOUT,
    )
    data = json.loads(comp.choices[0].message.content)
    return _coerce_bool(data["employment_intent"]), _coerce_bool(data["skills_intent"]), data["ec_hit"]
