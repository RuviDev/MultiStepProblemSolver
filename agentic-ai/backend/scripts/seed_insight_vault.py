# scripts/seed_insight_vault.py
import asyncio, datetime as dt
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.settings import settings
from app.db.init_db import ensure_collections, INSIGHT_VAULT

# SAMPLE_BATCH = {
#     "batchId": "learning_architecture_process_feedback",
#     "name": "Learning Architecture, Process & Feedbac",
#     "language": "en",
#     "isActive": True,
#     "vaultVersion": settings.INSIGHT_VAULT_VERSION,
#     "insights": [
#         {
#             "insightId": "learning_architecture_components",
#             "question": "Which components do you currently have?",
#             "isMultiSelect": True,
#             "isActive": True,
#             "answers": {
#                 "A": {"text": "Curriculum/sequence", "aliases": ["curriculum"]},
#                 "B": {"text": "Weekly plan", "aliases": ["plan", "schedule"]},
#                 "C": {"text": "Milestones/rubrics", "aliases": ["milestones", "goals"]},
#                 "D": {"text": "Feedback channel", "aliases": ["feedback"]},
#                 "E": {"text": "Reflection log", "aliases": ["log", "journal"]},
#                 "F": {"text": "None of these", "aliases": ["none"]}
#             }
#         },
#         {
#             "insightId": "process_bottlenecks",
#             "question": "Which bottlenecks slow you down most?",
#             "isMultiSelect": True,
#             "isActive": True,
#             "answers": {
#                 "A": {"text": "Unclear SOPs", "aliases": ["sops", "unclear process"]},
#                 "B": {"text": "Context switching", "aliases": ["multitasking", "switching"]},
#                 "C": {"text": "Tool fragmentation", "aliases": ["tools", "fragmentation"]},
#                 "D": {"text": "Rework/redo", "aliases": ["rework", "mistakes"]},
#                 "E": {"text": "Waiting on others", "aliases": ["waiting", "dependencies"]},
#                 "F": {"text": "Lack of templates", "aliases": ["templates"]},
#                 "G": {"text": "Other", "aliases": ["other reason"]}
#             }
#         },
#         {
#             "insightId": "feedback_availability",
#             "question": "How available is timely, honest feedback on your work?",
#             "isMultiSelect": False,
#             "isActive": True,
#             "answers": {
#                 "A": {"text": "Not available", "aliases": ["none", "not available"]},
#                 "B": {"text": "rarely", "aliases": ["rarely"]},
#                 "C": {"text": "sometimes", "aliases": ["sometimes"]},
#                 "D": {"text": "often", "aliases": ["often"]},
#                 "E": {"text": "Plentiful and timely", "aliases": ["plentiful", "always"]}
#             }
#         },
#     ],
#     "createdAt": dt.datetime.utcnow().isoformat(),
#     "updatedAt": dt.datetime.utcnow().isoformat(),
# }

SAMPLE_BATCH = {
    "batchId": "cognitive_preferences_problem_solving",
    "name": "Cognitive Preferences & Problem-Solving",
    "language": "en",
    "isActive": True,
    "vaultVersion": settings.INSIGHT_VAULT_VERSION,
    "insights": [
        {
            "insightId": "primary_learning_modes",
            "question": "Primary learning modes that stick for you",
            "isMultiSelect": True,
            "isActive": True,
            "answers": {
                "A": {"text": "Reading", "aliases": ["books", "articles"]},
                "B": {"text": "Videos", "aliases": ["lectures", "tutorials"]},
                "C": {"text": "Audio/podcasts", "aliases": ["audio", "podcasts"]},
                "D": {"text": "Hands-on practice", "aliases": ["doing", "projects"]},
                "E": {"text": "Teaching/explaining", "aliases": ["explaining", "teaching"]},
                "F": {"text": "Visual diagrams", "aliases": ["diagrams", "visuals"]},
                "G": {"text": "Worked examples", "aliases": ["examples"]}
            }
        },
        {
            "insightId": "concept_introduction_preference",
            "question": "How you want new concepts introduced",
            "isMultiSelect": False,
            "isActive": True,
            "answers": {
                "A": {"text": "Big picture -> details", "aliases": ["top-down", "macro-first"]},
                "B": {"text": "Concrete example -> principle", "aliases": ["example-first"]},
                "C": {"text": "Step-by-step from basics", "aliases": ["basics-first", "bottom-up"]},
                "D": {"text": "Compare/contrast with what I already know", "aliases": ["analogy", "compare"]}
            }
        },
        {
            "insightId": "problem_solving_posture",
            "question": "Problem-solving posture",
            "isMultiSelect": False,
            "isActive": True,
            "answers": {
                "A": {"text": "Divergent (generate many ideas)", "aliases": ["brainstorming", "ideation"]},
                "B": {"text": "Convergent (narrow to one best)", "aliases": ["analytical", "precision"]},
                "C": {"text": "Balanced", "aliases": ["both", "flexible"]}
            }
        },
        {
            "insightId": "unstick_preference",
            "question": "When you get stuck, what usually helps first?",
            "isMultiSelect": False,
            "isActive": True,
            "answers": {
                "A": {"text": "Search docs/examples", "aliases": ["search", "google"]},
                "B": {"text": "Restate/simplify the problem", "aliases": ["restate", "simplify"]},
                "C": {"text": "Sketch a diagram", "aliases": ["draw", "visualize"]},
                "D": {"text": "Compare to a prior pattern", "aliases": ["pattern-matching", "compare"]},
                "E": {"text": "Ask for a targeted hint", "aliases": ["hint", "ask"]}
            }
        },
        {
            "insightId": "practice_limiters",
            "question": "What most limits your consistent practice?",
            "isMultiSelect": True,
            "isActive": True,
            "answers": {
                "A": {"text": "Low energy/fatigue", "aliases": ["tired", "fatigue"]},
                "B": {"text": "Stress/overload", "aliases": ["stress", "overwhelmed"]},
                "C": {"text": "Environment/noise", "aliases": ["distractions", "noise"]},
                "D": {"text": "Competing obligations", "aliases": ["no time", "busy"]},
                "E": {"text": "Health concerns", "aliases": ["health", "sickness"]},
                "F": {"text": "Irregular schedule", "aliases": ["schedule", "unpredictable"]},
                "G": {"text": "Other", "aliases": ["other reason"]}
            }
        }
    ],
    "createdAt": dt.datetime.utcnow().isoformat(),
    "updatedAt": dt.datetime.utcnow().isoformat(),
}


async def main():
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    await ensure_collections(db)

    # idempotent upsert by batchId + version
    existing = await db[INSIGHT_VAULT].find_one({
        "batchId": SAMPLE_BATCH["batchId"],
        "vaultVersion": SAMPLE_BATCH["vaultVersion"],
    })
    if not existing:
        await db[INSIGHT_VAULT].insert_one(SAMPLE_BATCH)
        print(f"Seeded Insight Vault batch '{SAMPLE_BATCH['batchId']}' for version {SAMPLE_BATCH['vaultVersion']}")
    else:
        print("Insight Vault seed already present; nothing to do.")

if __name__ == "__main__":
    asyncio.run(main())
