import json
import os
from typing import Dict, List
import time

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, File, UploadFile, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import requests
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.server.websocket_manager import WebSocketManager
from backend.server.server_utils import (
    get_config_dict, sanitize_filename,
    update_environment_variables, handle_file_upload, handle_file_deletion,
    execute_multi_agents, handle_websocket_communication
)

from backend.server.websocket_manager import run_agent
from backend.utils import write_md_to_word, write_md_to_pdf
from gpt_researcher.utils.logging_config import setup_research_logging
from gpt_researcher.utils.enum import Tone
from backend.chat.chat import ChatAgentWithMemory

import logging

# Get logger instance
logger = logging.getLogger(__name__)

# Don't override parent logger settings
logger.propagate = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()  # Only log to console
    ]
)

# Models


class ResearchRequest(BaseModel):
    task: str
    report_type: str
    report_source: str
    tone: str
    headers: dict | None = None
    repo_name: str
    branch_name: str
    knowledge_base: str | None = None
    deep_research_config: dict | None = None
    generate_in_background: bool = True


class ConfigRequest(BaseModel):
    ANTHROPIC_API_KEY: str
    TAVILY_API_KEY: str
    LANGCHAIN_TRACING_V2: str
    LANGCHAIN_API_KEY: str
    OPENAI_API_KEY: str
    DOC_PATH: str
    RETRIEVER: str
    GOOGLE_API_KEY: str = ''
    GOOGLE_CX_KEY: str = ''
    BING_API_KEY: str = ''
    SEARCHAPI_API_KEY: str = ''
    SERPAPI_API_KEY: str = ''
    SERPER_API_KEY: str = ''
    SEARX_URL: str = ''
    XAI_API_KEY: str
    DEEPSEEK_API_KEY: str


# App initialization
app = FastAPI()

# Static files and templates
app.mount("/site", StaticFiles(directory="./frontend"), name="site")
app.mount("/static", StaticFiles(directory="./frontend/static"), name="static")
templates = Jinja2Templates(directory="./frontend")

# WebSocket manager
manager = WebSocketManager()

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
DOC_PATH = os.getenv("DOC_PATH", "./my-docs")

# Startup event


@app.on_event("startup")
def startup_event():
    os.makedirs("outputs", exist_ok=True)
    app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

    # Initialize vector store directory
    vector_store_path = os.environ.get("VECTOR_STORE_PATH", "vector_store")
    os.makedirs(vector_store_path, exist_ok=True)
    

# Routes


@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "report": None})


@app.get("/report/{research_id}")
async def read_report(request: Request, research_id: str):
    docx_path = os.path.join('outputs', f"{research_id}.docx")
    if not os.path.exists(docx_path):
        return {"message": "Report not found."}
    return FileResponse(docx_path)


async def write_report(research_request: ResearchRequest, research_id: str = None):
    # Configure deep research parameters
    # The DeepResearchSkill gets its configuration from the researcher's config object (cfg).
    # The config object is populated from environment variables.
    # Therefore, we set the environment variables here before the researcher is initialized.
    if research_request.deep_research_config:
        os.environ["DEEP_RESEARCH_DEPTH"] = str(research_request.deep_research_config.get("max_iterations", 2))
        os.environ["DEEP_RESEARCH_BREADTH"] = str(research_request.deep_research_config.get("max_search_results_per_query", 4))

    vector_store_path = None
    if research_request.knowledge_base:
        vector_store_base_path = os.environ.get("VECTOR_STORE_PATH", "vector_store")
        kb_path = os.path.join(vector_store_base_path, research_request.knowledge_base)
        vector_store_path = kb_path

        # Set the document path for the researcher to the 'docs' subfolder of the knowledge base
        doc_path = os.path.join(kb_path, "docs")
        os.environ["DOC_PATH"] = doc_path

    report_information = await run_agent(
        task=research_request.task,
        report_type=research_request.report_type,
        report_source=research_request.report_source,
        source_urls=[],
        document_urls=[],
        tone=Tone[research_request.tone],
        websocket=None,
        stream_output=None,
        headers=research_request.headers,
        query_domains=[],
        config_path="",
        vector_store_path=vector_store_path,
        return_researcher=True
    )

    docx_path = await write_md_to_word(report_information[0], research_id)
    pdf_path = await write_md_to_pdf(report_information[0], research_id)
    if research_request.report_type != "multi_agents":
        report, researcher = report_information
        response = {
            "research_id": research_id,
            "research_information": {
                "source_urls": researcher.get_source_urls(),
                "research_costs": researcher.get_costs(),
                "visited_urls": list(researcher.visited_urls),
                "research_images": researcher.get_research_images(),
                # "research_sources": researcher.get_research_sources(),  # Raw content of sources may be very large
            },
            "report": report,
            "docx_path": docx_path,
            "pdf_path": pdf_path
        }
    else:
        response = { "research_id": research_id, "report": "", "docx_path": docx_path, "pdf_path": pdf_path }

    return response

@app.post("/report/")
async def generate_report(research_request: ResearchRequest, background_tasks: BackgroundTasks):
    research_id = sanitize_filename(f"task_{int(time.time())}_{research_request.task}")

    if research_request.generate_in_background:
        background_tasks.add_task(write_report, research_request=research_request, research_id=research_id)
        return {"message": "Your report is being generated in the background. Please check back later.",
                "research_id": research_id}
    else:
        response = await write_report(research_request, research_id)
        return response


@app.get("/files/")
async def list_files():
    if not os.path.exists(DOC_PATH):
        os.makedirs(DOC_PATH, exist_ok=True)
    files = os.listdir(DOC_PATH)
    print(f"Files in {DOC_PATH}: {files}")
    return {"files": files}


@app.post("/api/multi_agents")
async def run_multi_agents():
    return await execute_multi_agents(manager)


@app.post("/upload/")
async def upload_file(file: UploadFile = File(...), knowledge_base: str = Form(...)):
    if not knowledge_base:
        return JSONResponse(status_code=400, content={"message": "Knowledge base name is required."})

    vector_store_base_path = os.environ.get("VECTOR_STORE_PATH", "vector_store")
    kb_path = os.path.join(vector_store_base_path, knowledge_base)
    doc_path = os.path.join(kb_path, "docs")
    os.makedirs(doc_path, exist_ok=True)

    return await handle_file_upload(file, doc_path)


@app.delete("/files/{filename}")
async def delete_file(filename: str):
    return await handle_file_deletion(filename, DOC_PATH)


@app.get("/models")
async def get_models():
    try:
        base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:1234/v1")
        response = requests.get(f"{base_url}/models")
        response.raise_for_status()
        models = response.json()
        return {"models": models.get("data", [])}
    except requests.exceptions.RequestException as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/knowledge-bases")
async def get_knowledge_bases():
    vector_store_path = os.environ.get("VECTOR_STORE_PATH", "vector_store")
    if not os.path.isdir(vector_store_path):
        return {"knowledge_bases": []}

    directories = [d for d in os.listdir(vector_store_path) if os.path.isdir(os.path.join(vector_store_path, d))]
    return {"knowledge_bases": directories}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await handle_websocket_communication(websocket, manager)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
