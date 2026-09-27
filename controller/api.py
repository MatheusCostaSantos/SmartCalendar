import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from data.assistente_openai_agents import AssistenteAgentesOpenAI
from data.autenticador_google_oauthlib import AutenticadorGoogleOAuthlib
from data.extrator_pdfplumber import ExtratorPdfplumber
from data.repositorio_credenciais_json import RepositorioCredenciaisJson
from service.autenticacao_service import AutenticacaoGoogleService
from service.criar_eventos_service import CriarEventosDoPdfService

load_dotenv()

GCALENDAR_MCP_PATH = Path(
    os.environ.get("GCALENDAR_MCP_PATH", "../gcalendar-mcp/src/index.js")
).resolve()

# credentials.json do OAuth Client (client_id/secret) — o mesmo que o
# gcalendar-mcp usa, reaproveitado aqui só para o fluxo de login web.
GOOGLE_OAUTH_CLIENT_PATH = Path(
    os.environ.get("GOOGLE_OAUTH_CLIENT_PATH", "../gcalendar-mcp/credentials.json")
).resolve()
REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
CREDENCIAIS_DB_PATH = os.environ.get("CREDENCIAIS_DB_PATH", "credenciais_usuarios.json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not GCALENDAR_MCP_PATH.exists():
        raise FileNotFoundError(f"Não encontrei o servidor MCP em {GCALENDAR_MCP_PATH}")

    repositorio = RepositorioCredenciaisJson(CREDENCIAIS_DB_PATH)
    autenticador = AutenticadorGoogleOAuthlib(GOOGLE_OAUTH_CLIENT_PATH, REDIRECT_URI)

    app.state.autenticacao = AutenticacaoGoogleService(autenticador, repositorio)
    app.state.repositorio_credenciais = repositorio
    app.state.servico = CriarEventosDoPdfService(
        extrator=ExtratorPdfplumber(),
        assistente=AssistenteAgentesOpenAI(caminho_mcp=str(GCALENDAR_MCP_PATH)),
    )
    yield


app = FastAPI(lifespan=lifespan)


class ScheduleResponse(BaseModel):
    filename: str
    resumo: str


class LoginResponse(BaseModel):
    email: str
    api_key: str


@app.get("/auth/google/login")
async def login_google():
    """Redireciona o navegador do usuário pro consentimento do Google."""
    url = app.state.autenticacao.gerar_url_login()
    return RedirectResponse(url)


@app.get("/auth/google/callback", response_model=LoginResponse)
async def callback_google(code: str, state: str):
    """O Google chama esta rota depois do usuário aceitar. Devolvemos a
    api_key que ele vai usar daqui pra frente em vez de fazer login de novo."""
    try:
        api_key = app.state.autenticacao.processar_callback(code, state)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Falha na autenticação: {e}")

    credenciais = app.state.repositorio_credenciais.buscar_por_api_key(api_key)
    return LoginResponse(email=credenciais.email, api_key=api_key)


@app.post("/pdf/schedule", response_model=ScheduleResponse)
async def parse_pdf_and_schedule(
    file: UploadFile = File(...),
    api_key: str = Form(...),
    contexto_adicional: str | None = Form(None),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="O arquivo deve ser um PDF")

    credenciais = app.state.repositorio_credenciais.buscar_por_api_key(api_key)
    if credenciais is None:
        raise HTTPException(status_code=401, detail="api_key inválida — faça login em /auth/google/login")

    content = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        resumo = await app.state.servico.executar(tmp_path, credenciais, contexto_adicional)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erro ao processar PDF: {e}")
    finally:
        os.remove(tmp_path)

    return ScheduleResponse(filename=file.filename, resumo=resumo)
