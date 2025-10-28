from app.services.textnorm import normalize

EMPLOYMENT_HINTS = [
    "i am a ", "i'm a ", "i work as", "my job", "my role", "position", "employment",
    "engineer", "developer", "analyst", "designer", "teacher", "nurse", "manager", "accountant"
]

SKILLS_HINTS = [
    "skills", "learn", "upskill", "improve", "develop", "teach me", "pick skills",
    "help me choose skills", "skill plan", "curriculum", "roadmap"
]

def employment_intent(text: str) -> bool:
    t = f" {normalize(text)} "
    return any(h in t for h in EMPLOYMENT_HINTS)

def skills_intent(text: str) -> bool:
    t = f" {normalize(text)} "
    return any(h in t for h in SKILLS_HINTS)
