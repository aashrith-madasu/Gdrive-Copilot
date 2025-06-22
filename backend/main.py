from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import requests
import json
import asyncio
import os
import io

from request_types import (
    AuthRequest, SearchRequest
)
from agent import agent



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/hello")
def say_hello():
    return "hello"

@app.get("/ingestion_status")
def get_ingestion_status():
    
    ingestion_status = os.path.exists("../faiss_index")
    filenames = os.listdir("../files")
    
    return {"ingestion_status": ingestion_status,
            "files": filenames}


async def ingest_data():
    """download a file
    read and chunk it
    embed the chunks
    pust to vector db

    Returns:
        dict: {status}
    """
    
    auth_data = json.load(open("auth_data.json"))
    creds = Credentials(
        token=auth_data["access_token"],
        refresh_token=auth_data["refresh_token"]
    )
    
    drive_service = build('drive', 'v3', credentials=creds)
    
    print("Ingesting started ....")
    
    all_files = []
    page_token = None

    while True:
        response = drive_service.files().list(
            q="mimeType='application/pdf'",
            fields="nextPageToken, files(id, name, mimeType, parents)",
            pageSize=100,  # or smaller if needed
            pageToken=page_token
        ).execute()

        all_files.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        # break
        if not page_token:
            break
        
    await asyncio.sleep(60)
    
    # Download file
    file = all_files[10]
    request = drive_service.files().get_media(fileId=file["id"])
    os.makedirs("saved_files", exist_ok=True)
    filename = "saved_files/" + file["name"]
    fh = io.FileIO(filename, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        print(f"Download {int(status.progress() * 100)}%.")

    print(f"File downloaded as {filename}")
    
    return { "status": "ok"}
    
    

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
    
    print("Async Task created ..")
    asyncio.create_task(ingest_data())
    print("Returning...")

    return { "status": "ok"}


@app.post("/search")
def search(request: SearchRequest):
    
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

