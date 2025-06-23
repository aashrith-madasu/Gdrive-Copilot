import io
import os
import json
import asyncio
import shutil
from tqdm import tqdm
from collections import defaultdict
from typing import Dict, List

from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.discovery import build
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
    "application/vnd.google-apps.document": "docs"
}


def get_current_user():
    if not os.path.exists("current_user.json"): 
        return None
    d = json.load(open("current_user.json"))
    return d["current_user"]

def set_current_user(user_id):
    json.dump({"current_user": str(user_id)}, open("current_user.json", "w+"))

def get_local_vectorstore():
    userid = get_current_user()
    if not userid:
        return None
    
    local_vectorstore_path = f"faiss_local_vectorstore/{userid}"
    if not os.path.exists(local_vectorstore_path):
        return None
    
    vectorstore = FAISS.load_local(
        folder_path=local_vectorstore_path, 
        embeddings=embeddings, 
        allow_dangerous_deserialization=True
    )
    return vectorstore
    

def save_local_vectorstore(vectorstore: FAISS):
    userid = get_current_user()
    if not userid:
        return None
    
    local_vectorstore_path = f"faiss_local_vectorstore/{userid}"
    vectorstore.save_local(local_vectorstore_path)





async def read_gdrive_file_metadata(drive_service):
    
    all_files = {}
    page_token = None

    while True:
        response = drive_service.files().list(
            # q=f"'root' in parents",
            # q=f"'{mime_type}' in mimeType ",
            fields="nextPageToken, files(id, name, mimeType, parents)",
            pageSize=100,  # or smaller if needed
            pageToken=page_token
        ).execute()

        for file in response.get('files', []):
            all_files[file['id']] = file
            
        page_token = response.get('nextPageToken')
        # break
        if not page_token:
            break
    
    print(f"Found {len(all_files)} files")
    
    return all_files
    


def compute_paths(all_files: Dict[str, Dict]):
    
    for file_id in all_files.keys():
        
        path_to_root = []
        cur_id = file_id
        
        while cur_id in all_files.keys():
            
            path_to_root.append(all_files[cur_id]["name"])
            
            if "parents" in all_files[cur_id].keys():
                cur_id = all_files[cur_id]["parents"][0]
            else:
                path_to_root.append("shared")
                break
        else:
            path_to_root.append("root")
        
        all_files[file_id]['path_to_root'] = path_to_root
        
    return all_files
    

def save_filepaths(all_files):
    
    filepaths = {}
    
    for file in all_files.values():
        
        if file["mimeType"] == "application/vnd.google-apps.folder":
            continue
        
        path_to_root_str = " > ".join(list(reversed(file["path_to_root"])))
        
        filepaths[file["id"]] = {
            "id": file["id"],
            "name": file["name"],
            "path_to_root": path_to_root_str
        }
    
    json.dump(filepaths, open("filepaths.json", "w+"))
    
    
async def download_files(all_files, save_path, drive_service):
    
    os.makedirs(save_path, exist_ok=True)

    for file in tqdm(all_files.values()):
        
        if file["mimeType"] == "application/vnd.google-apps.spreadsheet":
            request = drive_service.files().export_media(
                fileId=file["id"], 
                mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            extension = ".xlsx"
            
        elif file["mimeType"] == "application/pdf":
            request = drive_service.files().get_media(fileId=file["id"])
            extension = ".pdf"
        
        elif file["mimeType"] == "application/vnd.google-apps.document":
            request = drive_service.files().export_media(
                fileId=file["id"], 
                mimeType='application/pdf'
            )
            extension = ".pdf"
        
        elif file["mimeType"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            request = drive_service.files().get_media(fileId=file["id"])
            extension = ".xlsx"
        else:
            continue
            
        filepath = os.path.join(save_path, file['id'] + extension)
        downloader = MediaIoBaseDownload(io.FileIO(filepath, 'wb'), request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            
    all_mime_types = set(file["mimeType"] for file in all_files.values())
    all_mime_types.discard("application/vnd.google-apps.folder")
    all_mime_types.discard('application/vnd.google-apps.document')

    return all_mime_types
    


def load_files_and_chunk(files_dir: str, all_mime_types: List, all_files):
    
    final_chunks = []
    
    for mime_type in all_mime_types:

        if mime_type == "application/pdf":
            my_loader_cls = PyPDFLoader
            pattern = "*.pdf"
        elif mime_type == "application/vnd.google-apps.spreadsheet" or mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            my_loader_cls = UnstructuredExcelLoader
            pattern = "*.xlsx"
            
        print(f"Loading {pattern} using {my_loader_cls.__name__}")

        loader = DirectoryLoader(
            files_dir,
            glob=pattern,              
            loader_cls=my_loader_cls,
            silent_errors=True
        )
        documents = loader.load()

        grouped_docs = defaultdict(list)
        for doc in documents:
            grouped_docs[doc.metadata["source"]].append(doc)

        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=200)

        for source, docs in tqdm(grouped_docs.items()):
            chunks = splitter.split_documents(docs)
            for i, chunk in enumerate(chunks):
                file_id = os.path.basename(source).split(".")[0]
                chunk.metadata["id"] = file_id
                chunk.metadata["chunk_index"] = i        
                chunk.metadata["path"] = " > ".join(list(reversed(all_files[file_id]["path_to_root"])))
                
            final_chunks.extend(chunks)

        print(f"Loaded {len(grouped_docs)} files, of type {mime_type}")  
        
    return final_chunks
    

async def ingest_data_main(drive_service):
    
    print("Reading gdrive file metadata ...")
    
    all_files = await read_gdrive_file_metadata(drive_service)
    
    print("Computing paths to root ...")
    
    all_files = compute_paths(all_files)
    
    print("saving file paths ...")
    
    save_filepaths(all_files)
    
    save_path = "local_files"
    
    print("Downloading files ...")
    
    all_mime_types = await download_files(all_files=all_files, save_path=save_path, drive_service=drive_service)
    
    print("Loading and Chunking files ...")
    
    final_chunks = load_files_and_chunk(files_dir=save_path, all_mime_types=all_mime_types, all_files=all_files)
    
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-mpnet-base-v2",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': False}
    )
    
    print("Building FAISS index ...")
    
    vectorstore = FAISS.from_documents(final_chunks, embeddings)
    
    print("Saving the index ...")
    
    vectorstore.save_local("index_document_content")
    
    return
    
    

if __name__ == "__main__":
    
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
    
    asyncio.run(ingest_data_main(drive_service))