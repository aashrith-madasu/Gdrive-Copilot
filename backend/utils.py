import io
import os
import json
import asyncio
from tqdm import tqdm
from collections import defaultdict

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials

from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, CSVLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS



embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-mpnet-base-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': False}
)

mime_type_path = {
    "application/pdf": "pdfs",
}


async def download_files(mime_type: str):
    
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
            q=f"mimeType='{mime_type}'",
            fields="nextPageToken, files(id, name, mimeType, parents)",
            pageSize=100,  # or smaller if needed
            pageToken=page_token
        ).execute()

        all_files.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        # break
        if not page_token:
            break
        
    save_path = os.path.join("saved_files", mime_type_path[mime_type])
    os.makedirs(save_path, exist_ok=True)
    
    # Download file
    for file in tqdm(all_files):
        request = drive_service.files().get_media(fileId=file["id"])
        filepath = os.path.join(save_path, file['name'])
        downloader = MediaIoBaseDownload(io.FileIO(filepath, 'wb'), request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            # print(f"Download {int(status.progress() * 100)}%.")

    print(f"Files downloaded : {len(all_files)}")
    
    return save_path
    

async def ingest_for_mime_type(mime_type: str):
    """download a file
    read and chunk it
    embed the chunks
    pust to vector db

    Returns:
        dict: {status}
    """
    
    save_path = await download_files(mime_type=mime_type)
    
    if mime_type == "application/pdf":
        _loader_cls = PyPDFLoader
    elif mime_type == "":
        _loader_cls = CSVLoader
        
    loader = DirectoryLoader(
        save_path,
        glob=f"{save_path}/*",              
        loader_cls=_loader_cls,
        silent_errors=True
    )
    documents = loader.load()
    
    grouped_docs = defaultdict(list)
    for doc in documents:
        grouped_docs[doc.metadata["source"]].append(doc)

    final_chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=200)

    for source, docs in tqdm(grouped_docs.items()):
        chunks = splitter.split_documents(docs)
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i        # Add index per file
            chunk.metadata["chunk_id"] = f"{source}_chunk_{i}"  # Optional unique ID
        final_chunks.extend(chunks)

    print(f"Loaded {len(grouped_docs)} files, split into {len(final_chunks)} chunks.")  
    
    if os.path.exists("faiss_index"):
        vectorstore = FAISS.load_local("faiss_index")
        vectorstore.add_documents(documents=final_chunks)
    else:
        vectorstore = FAISS.from_documents(final_chunks, embeddings)
        
    vectorstore.save_local("faiss_index")
    


async def ingest_data():
    
    for mime_type in mime_type_path.keys():
        
        await ingest_for_mime_type(mime_type)
        
        
        
        
    