from contextlib import asynccontextmanager
from pathlib import Path
import os
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from docling.document_converter import DocumentConverter
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

load_dotenv()

converter = DocumentConverter()

GCALENDAR_MCP_PATH = Path(
    os.environ.get("GCALENDAR_MCP_PATH", "../gcalendar-mcp/src/index.js")
).resolve()

INSTRUCTIONS = """
Você é um assistente que cria eventos no Google Calendar a partir do
conteúdo de um cronograma extraído de um PDF (em Markdown).

Sua tarefa:
1. Identificar cada evento relevante (aula, prova, feriado, entrega de
   lista, teste, revisão etc.) presente no texto.
2. Para cada evento, chamar create_event com:
   - summary: título curto e descritivo
   - description: detalhes relevantes (conteúdo da aula, observações)
   - start / end: datas em ISO 8601. Se não houver horário explícito,
     use 00:00:00 até 23:59:59 do mesmo dia (evento de dia inteiro).
   - timeZone: America/Sao_Paulo
3. Ignore cabeçalhos repetidos ou lixo de formatação da tabela.
4. Se dois eventos ocorrerem na mesma data, crie eventos separados.
5. NÃO peça confirmação — crie todos os eventos diretamente.
6. Ao final, responda com um resumo: quantos eventos foram criados e uma
   lista com título + data de cada um.
"""


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
        app.state.agent = Agent(
            name="Criador de Eventos",
            instructions=INSTRUCTIONS,
            model="gpt-4.1-mini",
            mcp_servers=[calendar_server],
        )
        yield
        # ao encerrar a aplicação, o "async with" fecha o subprocesso do MCP sozinho


app = FastAPI(lifespan=lifespan)


class ScheduleResponse(BaseModel):
    filename: str
    resumo: str


@app.post("/pdf/schedule", response_model=ScheduleResponse)
async def parse_pdf_and_schedule(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="O arquivo deve ser um PDF")

    content = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = converter.convert(tmp_path)
        markdown = result.document.export_to_markdown()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erro ao processar PDF: {e}")
    finally:
        os.remove(tmp_path)

    prompt = (
        "Aqui está o conteúdo extraído do documento (em Markdown):\n\n"
        f"{markdown}\n\n"
        "Crie todos os eventos correspondentes no Google Calendar."
    )

    result = await Runner.run(app.state.agent, prompt, max_turns=60)

    return ScheduleResponse(filename=file.filename, resumo=result.final_output)