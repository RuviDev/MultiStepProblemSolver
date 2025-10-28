from pydantic import BaseModel

class AliasIndexItem(BaseModel):
    vault_version: str
    type: str                 # "ec" | "skill"
    alias: str
    alias_norm: str
    target_id: str            # ec_id or skill_id
    employment_category_id: str | None = None  # required when type="skill"
