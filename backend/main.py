import os
import json
import asyncio
import requests
import glob

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from passlib.hash import bcrypt

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from database import SessionLocal, engine
import models
from request_types import (AuthRequest, SearchRequest, UserCreate, UserOut, IngestRequest)
from agent import agent
from ingest_data import ingest_data_main
from dotenv import load_dotenv

load_dotenv()

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


@app.post("/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
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
def login(user: UserCreate, db: Session = Depends(get_db)):
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
        set_current_user(db_user.id)
        return {"message": "Login successful", "user_id": db_user.id}



@app.get("/ingestion_status")
def get_ingestion_status():
    
    local_vectorstore_path = f"faiss_local_vectorstore/{get_current_user()}"
    ingestion_status = os.path.exists(local_vectorstore_path)
    
    return {"ingestion_status": ingestion_status}


@app.post("/auth")
async def authenticate(request: AuthRequest):
    
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
    
    # print("Async Task created ..")
    # asyncio.create_task(ingest_data())
    # print("Returning...")

    return { "status": "ok"}


@app.get("/ingest_data")
async def ingest_data():
    
    auth = json.load(open("auth_data.json"))
    client = json.load(open("web_client_creds.json"))

    creds = Credentials(
        token=auth["access_token"],
        refresh_token=auth["refresh_token"],
        token_uri=client["web"]["token_uri"],
        client_id=client["web"]["client_id"],
        client_secret=client["web"]["client_secret"]
    )
    
    drive_service = build('drive', 'v3', credentials=creds)
    
    asyncio.create_task(ingest_data_main(drive_service))
    
    return {"message": "Data Ingestion task started ..."}

    # db_user = db.query(models.User).filter(models.User.username == request.username).first()
    
    # if not db_user:
    #     return {"message": "user not found"}
    
    # if get_current_user() != str(db_user.id):
    #     return {"message": "user not logged in"}
    
    # asyncio.create_task(ingest_data_helper())
    
    
    
    

@app.post("/search")
def search(request: SearchRequest):
    
    print("in search endpoint")
    
    user_query = request.query

    prompt = (
        # f"You are an intelligent assistant. The user has access to these files: {filenames}.\n"
        # "If the query mentions a file from this list, extract its name. Otherwise, assume no file was mentioned.\n"
        # "Then call the 'context_retriever' tool with filename (if any) and a cleaned-up query.\n"
        # "The 'context_retriever' tool returns context with relevant citation in the format : (source file, page number, chunk)"
        # "Please use these provided citations in your final answer and cite every line you output in the same format enclosed in <cite></cite> tags."
        # "For example: <cite>(citation info)</cite>\n"
        # f"User query: {user_query}"
        f"You are an intelligent assistant that filters the user query and calls the tool 'retrieve_relevant_context'\n"
        "If the query mentions any source document (can be a file name or a folder name that may provide the context to answer the question)\n"
        "extract the source and whether or not it is a folder. Otherwise, assume no source was mentioned.\n"
        "Then call the 'retrieve_relevant_context' tool with source (if any) and a cleaned-up query.\n"
        "The 'retrieve_relevant_context' tool returns context with relevant citation in the format : (source_file, page_number, chunk_id)\n"
        "Please use these provided citations in your final answer and cite every line you output in the same format enclosed in <cite></cite> tags.\n"
        "For example: <cite>(file1, page 10, chuck 10)</cite>\n"
        f"User query: {user_query}"
    )

    response = agent.invoke(prompt)

    print(response)

    return {"response": response['output']}

