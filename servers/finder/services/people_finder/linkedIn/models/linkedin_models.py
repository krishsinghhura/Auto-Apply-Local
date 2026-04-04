from pydantic import BaseModel
from typing import Optional

class Staff(BaseModel):
    id: str
    urn: Optional[str] = None
    name: Optional[str] = None
    headline: Optional[str] = None
    profile_link: Optional[str] = None
    search_term: Optional[str] = None

    def to_dict(self):
        return self.model_dump()
