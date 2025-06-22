import os
from dotenv import load_dotenv

from typing import Optional
from langchain_core.tools import tool
from langchain.agents import initialize_agent, AgentType
from langchain_google_genai import GoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader

from utils import embeddings

load_dotenv()


vectorstore = FAISS.load_local(
    folder_path="../faiss_index", 
    embeddings=embeddings, 
    allow_dangerous_deserialization=True
)


# Step 1: Define the downstream tool
@tool
def context_retriever(filename: Optional[str], query: str) -> str:
    """Processes a query, optionally with a filename."""
    
    search_kwargs = {"k": 3}
    
    print("selected docuemnt : ", filename)
    
    if filename != None:
        search_kwargs["filter"] = {"source": f"files/{filename}"}
    
    retriever =  vectorstore.as_retriever(search_kwargs=search_kwargs)
    docs = retriever.get_relevant_documents(query)
    
    context = "Retrieved context : \n"

    for i, doc in enumerate(docs):
        
        source = doc.to_json()["kwargs"]["metadata"]["source"]
        page_label = doc.to_json()["kwargs"]["metadata"]["page_label"]
        chunk_index = doc.to_json()["kwargs"]["metadata"]["chunk_index"]
        page_content = doc.to_json()["kwargs"]["page_content"]
        
        context += f"Context {i} (source file: {source}, page number {page_label}, chunk: {chunk_index}) : \n\n {page_content} \n\n"
        
    
    print("len of docs: ", len(docs))
    
    # TODO: modify this as well
    # if len(docs) == 0 and filename != None:
    #     # fetch the entire file as context
    #     loader = PyPDFLoader(f"../files/{filename}")
    #     docs = loader.load()
    #     docs = [doc.page_content for doc in docs]
    
    return context


# Step 3: Create agent
# llm = HuggingFaceEndpoint(repo_id="HuggingFaceH4/zephyr-7b-beta")
llm = GoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=os.getenv("GOOGLE_API_KEY"))

agent = initialize_agent(
    tools=[context_retriever],
    llm=llm,
    agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,  # Use a compatible agent type
    verbose=True
)


