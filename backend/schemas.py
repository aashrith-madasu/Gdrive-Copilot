from pydantic import BaseModel
from typing_extensions import Optional

class AuthRequest(BaseModel):
    code: str
    
class SearchRequest(BaseModel):
    document_name: Optional[str] = None
    query: str
    
    
class UserCreate(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    id: int
    username: str

    class Config:
        orm_mode = True
    