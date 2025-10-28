from pydantic import BaseModel, Field
from typing import List, Optional

class Skill(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)

class EmploymentCategory(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    skills: List[Skill] = Field(default_factory=list)

class SegmentVaultVersion(BaseModel):
    vault_version: str
    is_active: bool = False
    employment_categories: List[EmploymentCategory]
    metadata: dict = Field(default_factory=dict)
