from pydantic import BaseModel
from typing_extensions import Optional

class AuthRequest(BaseModel):
    code: str
    
class SearchRequest(BaseModel):
    document_name: Optional[str] = None
    query: str
    