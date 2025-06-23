import os
import json
from dotenv import load_dotenv

from typing import Optional
from langchain_core.tools import tool
from langchain.agents import initialize_agent, AgentType
from langchain_google_genai import GoogleGenerativeAI
from langchain_community.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

from ingest_data import embeddings


load_dotenv()




        
@tool
def retrieve_relevant_context(file_or_folder_name: Optional[str], is_folder: Optional[bool], cleaned_query: str) -> str:
    """A useful tool that fetchs relevant docs for the user query
    Args:
        file_or_folder_name (str): the file or folder mentioned in the user query
        is_folder (bool): whether or not the 'file_or_folder_name' is a folder
        cleaned_query: the main cleaned up query without the mention of the file or folder (if any)
    """
    
    ## retrivers
    docs = []
    filepaths = json.load(open("filepaths.json"))
    for f in filepaths.values():
        docs.append(
            Document(
                page_content=f["path_to_root"], 
                metadata={"id": f["id"], "name": f["name"]}
            )
        )
    path_retriever = BM25Retriever.from_documents(docs)

    vectorstore = FAISS.load_local(
        folder_path="index_document_content",
        embeddings=embeddings,
        allow_dangerous_deserialization=True
    )

    all_content_docs = vectorstore.docstore._dict.values()
    all_content_docs = list(all_content_docs) 
    
    ######
    
    search_kwargs = {"k": 2}
    
    if file_or_folder_name:

        relevant_files = path_retriever.get_relevant_documents(file_or_folder_name)
        
        print(relevant_files[0].page_content)
        
        file_id = relevant_files[0].metadata["id"]

        search_kwargs["filter"] = {"id": file_id}
        
        faiss_retriever = vectorstore.as_retriever(search_kwargs=search_kwargs)
        
        bm25_retriever_content = BM25Retriever.from_documents(
            documents=[doc for doc in all_content_docs if doc.metadata["id"] == file_id],
            k=2
        )
    
    else:
        faiss_retriever = vectorstore.as_retriever(search_kwargs=search_kwargs)
        
        bm25_retriever_content = BM25Retriever.from_documents(
            documents=all_content_docs,
            k=2
        )
        
     
    print("search kwargs: ", search_kwargs)   
    
    hybrid_retriever = EnsembleRetriever(
        retrievers=[faiss_retriever, bm25_retriever_content],
        weights=[0.6, 0.4], 
    )
    
    ret_docs = hybrid_retriever.get_relevant_documents(cleaned_query)
    
    print(len(ret_docs))
    
    context = "Context : \n\n"
    
    for i, doc in enumerate(ret_docs):
        filepath = doc.metadata["path"]
        page_label = doc.metadata.get("page_label", 0)
        chunk_index = doc.metadata["chunk_index"]
        page_content = doc.page_content
        
        context += f"Context {i} (source file: {filepath}, page number {page_label}, chunk: {chunk_index}) : \n\n {page_content} \n\n"
        
    return context



llm = GoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=os.getenv("GOOGLE_API_KEY"))

agent = initialize_agent(
    tools=[retrieve_relevant_context],
    llm=llm,
    agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION, 
    verbose=True
)


