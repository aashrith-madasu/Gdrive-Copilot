import os
import json
import asyncio
import requests

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from passlib.hash import bcrypt

from database import SessionLocal, engine
import models
import schemas
from agent import agent
from utils import ingest_data



models.Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency: get db session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Utility: hash password
def hash_password(password: str):
    return bcrypt.hash(password)

# Utility: verify password
def verify_password(plain, hashed):
    return bcrypt.verify(plain, hashed)


@app.post("/register", response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_pw = hash_password(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/login")
def login(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.username == user.username).first()
    
    if not db_user:
        # register
        print("Registering new user... ")
        if len(user.username) < 5 or len(user.password) < 5:
            raise HTTPException(status_code=401, detail="Username or password too small")
        
        hashed_pw = hash_password(user.password)
        new_user = models.User(username=user.username, hashed_password=hashed_pw)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"message": "Register successful", "user_id": new_user.id}
        
    elif not verify_password(user.password, db_user.hashed_password):
        print("Password incorrect")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    else:
        print("User logged in ... ")
        return {"message": "Login successful", "user_id": db_user.id}



@app.get("/ingestion_status")
def get_ingestion_status():
    
    ingestion_status = os.path.exists("../faiss_index")
    filenames = os.listdir("../files")
    
    return {"ingestion_status": ingestion_status,
            "files": filenames}


@app.post("/auth")
async def authenticate(request: schemas.AuthRequest):
    
    response = requests.post(
        url="https://oauth2.googleapis.com/token",
        data={
            "code": request.code,
            "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
            "redirect_uri": "https://minidhhloohbamlddjghdbmnjaejkmjb.chromiumapp.org",
            "grant_type": "authorization_code"
        }
    )
    auth_data = response.json()
    
    json.dump(auth_data, open("auth_data.json", "w+"))
    
    print("Async Task created ..")
    asyncio.create_task(ingest_data())
    print("Returning...")

    return { "status": "ok"}


@app.post("/search")
def search(request: schemas.SearchRequest):
    
    print("in search endpoint")
    
    filenames = os.listdir("../files")
    user_query = request.query

    prompt = (
        f"You are an intelligent assistant. The user has access to these files: {filenames}.\n"
        "If the query mentions a file from this list, extract its name. Otherwise, assume no file was mentioned.\n"
        "Then call the 'context_retriever' tool with filename (if any) and a cleaned-up query.\n"
        "The 'context_retriever' tool returns context with relevant citation in the format : (source file, page number, chunk)"
        "Please use these provided citations in your final answer and cite every line you output in the same format enclosed in <cite></cite> tags."
        "For example: <cite>(citation info)</cite>\n"
        f"User query: {user_query}"
    )

    response = agent.invoke(prompt)

    print(response)

    return {"response": response['output']}

