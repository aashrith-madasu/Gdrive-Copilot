import io
import os
import json
import asyncio
from tqdm import tqdm
from collections import defaultdict

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials

from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader, UnstructuredExcelLoader
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
    "application/vnd.google-apps.spreadsheet": "sheets",
}


async def download_files(mime_type: str):
    
    auth = json.load(open("auth_data.json"))
    client = json.load(open("../client_creds/web_client_creds.json"))
    
    creds = Credentials(
        token=auth["access_token"],
        refresh_token=auth["refresh_token"],
        token_uri=client["web"]["token_uri"],
        client_id=client["web"]["client_id"],
        client_secret=client["web"]["client_secret"]
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
        
        if mime_type == "application/vnd.google-apps.spreadsheet":
            request = drive_service.files().export_media(
                fileId=file["id"], 
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            extension = ".xlsx"
            
        elif mime_type == "application/pdf":
            request = drive_service.files().get_media(fileId=file["id"])
            extension = ".pdf"
            
        filepath = os.path.join(save_path, file['name'] + extension)
        downloader = MediaIoBaseDownload(io.FileIO(filepath, 'wb'), request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

    print(f"Files downloaded : {len(all_files)}")
    
    return save_path
    

async def ingest_for_mime_type(mime_type: str):
    
    save_path = await download_files(mime_type=mime_type)
    
    print(save_path)
    
    if mime_type == "application/pdf":
        my_loader_cls = PyPDFLoader
    elif mime_type == "application/vnd.google-apps.spreadsheet":
        my_loader_cls = UnstructuredExcelLoader
        
    print(my_loader_cls.__name__)
    
    loader = DirectoryLoader(
        save_path,
        glob="*",              
        loader_cls=my_loader_cls,
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
        vectorstore = FAISS.load_local("faiss_index", embeddings, allow_dangerous_deserialization=True)
        vectorstore.add_documents(documents=final_chunks)
    else:
        vectorstore = FAISS.from_documents(final_chunks, embeddings)
        
    vectorstore.save_local("faiss_index")
    


async def ingest_data():
    
    for mime_type in mime_type_path.keys():
        
        await ingest_for_mime_type(mime_type)
        
        
        
        
if __name__ == "__main__":
    
    # asyncio.run(ingest_for_mime_type(mime_type="application/vnd.google-apps.spreadsheet"))
    asyncio.run(ingest_data())