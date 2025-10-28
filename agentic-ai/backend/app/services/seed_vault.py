from typing import Iterable
from app.models.vault import SegmentVaultVersion, EmploymentCategory, Skill
from app.services.textnorm import normalize
from app.models.alias import AliasIndexItem

def build_alias_index(vault: SegmentVaultVersion) -> Iterable[dict]:
    vv = vault.vault_version
    for ec in vault.employment_categories:
        # ---- EC aliases (dedupe by normalized form)
        seen_norms_ec = set()
        for a in [ec.name] + ec.aliases:
            an = normalize(a)
            if an in seen_norms_ec:
                continue
            seen_norms_ec.add(an)
            yield AliasIndexItem(
                vault_version=vv, type="ec", alias=a, alias_norm=an,
                target_id=ec.id, employment_category_id=None
            ).model_dump()

        # ---- Skill aliases (dedupe by normalized form)
        for sk in ec.skills:
            seen_norms_sk = set()
            for a in [sk.name] + sk.aliases:
                an = normalize(a)
                if an in seen_norms_sk:
                    continue
                seen_norms_sk.add(an)
                yield AliasIndexItem(
                    vault_version=vv, type="skill", alias=a, alias_norm=an,
                    target_id=sk.id, employment_category_id=ec.id
                ).model_dump()

def example_vault(vault_version: str) -> SegmentVaultVersion:
    return SegmentVaultVersion(
        vault_version=vault_version,
        is_active=True,
        employment_categories=[
            EmploymentCategory(
                id="ec_ds",
                name="Data Scientist",
                description="Build data products and insights using statistics, ML, and software.",
                aliases=["data scientist", "ds", "ml scientist"],
                skills=[
                    Skill(
                        id="sk_prog_wrangling",
                        name="Programming & data wrangling",
                        aliases=["python", "pandas", "numpy", "data wrangling"]
                    ),
                    Skill(
                        id="sk_stats_math",
                        name="Statistics & math",
                        aliases=["statistics", "probability", "linear algebra"]
                    ),
                    Skill(
                        id="sk_ml_fundamentals",
                        name="Machine learning fundamentals",
                        aliases=["machine learning", "ml basics", "supervised", "unsupervised"]
                    ),
                    Skill(
                        id="sk_dl_genai",
                        name="Deep learning & GenAI",
                        aliases=["deep learning", "neural networks", "genai", "llms"]
                    ),
                    Skill(
                        id="sk_data_eng_basics",
                        name="Data engineering basics",
                        aliases=["data engineering", "etl", "pipelines", "sql"]
                    ),
                    Skill(
                        id="sk_mlops",
                        name="MLOps / productionization",
                        aliases=["mlops", "deployment", "model serving", "monitoring"]
                    ),
                    Skill(
                        id="sk_cloud_platforms",
                        name="Cloud & platforms",
                        aliases=["cloud", "aws", "gcp", "azure"]
                    ),
                    Skill(
                        id="sk_analytics_experimentation",
                        name="Analytics & experimentation",
                        aliases=["ab testing", "experimentation", "causal inference"]
                    ),
                    Skill(
                        id="sk_viz_storytelling",
                        name="Visualization & storytelling",
                        aliases=["data viz", "visualization", "dashboards", "storytelling"]
                    ),
                    Skill(
                        id="sk_responsible_ai",
                        name="Responsible AI, privacy & security",
                        aliases=["responsible ai", "ai ethics", "privacy", "security"]
                    ),
                    Skill(
                        id="sk_domain_business",
                        name="Domain knowledge & business sense",
                        aliases=["domain knowledge", "business sense", "product thinking"]
                    ),
                    Skill(
                        id="sk_collab_soft_skills",
                        name="Collaboration & soft skills",
                        aliases=["communication", "collaboration", "soft skills", "teamwork"]
                    ),
                ]
            )
        ],
        metadata={"notes": "seed"}
    )