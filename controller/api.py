import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from agents import Agent
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from data.assistente_openai_agents import INSTRUCTIONS, AssistenteAgentesOpenAI
from data.extrator_pdfplumber import ExtratorPdfplumber
from service.criar_eventos_service import CriarEventosDoPdfService

load_dotenv()

GCALENDAR_MCP_PATH = Path(
    os.environ.get("GCALENDAR_MCP_PATH", "../gcalendar-mcp/src/index.js")
).resolve()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not GCALENDAR_MCP_PATH.exists():
        raise FileNotFoundError(f"Não encontrei o servidor MCP em {GCALENDAR_MCP_PATH}")

    async with MCPServerStdio(
        name="Google Calendar MCP",
        params={"command": "node", "args": [str(GCALENDAR_MCP_PATH)]},
        cache_tools_list=True,
        client_session_timeout_seconds=60,
    ) as calendar_server:
        agente = Agent(
            name="Criador de Eventos",
            instructions=INSTRUCTIONS,
            model="gpt-4.1-mini",
            mcp_servers=[calendar_server],
        )
        app.state.servico = CriarEventosDoPdfService(
            extrator=ExtratorPdfplumber(),
            assistente=AssistenteAgentesOpenAI(agente),
        )
        yield


app = FastAPI(lifespan=lifespan)


class ScheduleResponse(BaseModel):
    filename: str
    resumo: str


@app.post("/pdf/schedule", response_model=ScheduleResponse)
async def parse_pdf_and_schedule(
    file: UploadFile = File(...),
    contexto_adicional: str | None = Form(None),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="O arquivo deve ser um PDF")

    content = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        resumo = await app.state.servico.executar(tmp_path, contexto_adicional)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erro ao processar PDF: {e}")
    finally:
        os.remove(tmp_path)

    return ScheduleResponse(filename=file.filename, resumo=resumo)