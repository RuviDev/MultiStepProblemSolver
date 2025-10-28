from typing import List, Dict, Any

def build_ec_survey(options: List[Dict[str, str]], vault_version: str) -> dict:
    return {
        "type": "single-select",
        "title": "Choose your employment category",
        "help": "Pick the one that best describes you.",
        "options": options,
        "vault_version": vault_version
    }

def build_skills_survey(
    options: List[Dict[str, str]],
    vault_version: str,
    ec_id: str,
    max_select: int = 4
) -> dict:
    return {
        "type": "multi-select-with-limit",
        "title": "Pick up to 4 skills to focus on",
        "help": "You can choose 1–4, or let the system decide for you.",
        "max": max_select,
        "options": options,
        "let_system_decide": True,
        "employment_category_id": ec_id,
        "vault_version": vault_version
    }
