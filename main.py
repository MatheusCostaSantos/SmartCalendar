
from contextlib import asynccontextmanager
from pathlib import Path
import os
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import pdfplumber
from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from datetime import date
import re

DIAS_SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]

MESES_PT = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}




load_dotenv()

GCALENDAR_MCP_PATH = Path(
    os.environ.get("GCALENDAR_MCP_PATH", "../gcalendar-mcp/src/index.js")
).resolve()

INSTRUCTIONS = """
Você é um assistente que cria eventos no Google Calendar a partir do
conteúdo de um cronograma extraído de um PDF.

O texto que você vai receber pode conter tabelas (formatadas como linhas
de colunas separadas por " | ") e também texto solto (parágrafos, avisos,
bibliografia etc). Nem tudo é evento de calendário.

Quando o texto vier no formato "AAAA-MM-DD (dia da semana): descrição",
a data já está calculada corretamente — use-a exatamente como está,
NÃO recalcule nem infira outra data para esse evento.

Sua tarefa:
1. Identificar cada evento relevante (aula, prova, feriado, entrega de
   lista, avaliação, revisão, "não haverá aula" etc.) presente no texto.
2. Algumas tabelas têm uma coluna de Mês que só aparece na primeira linha
   de cada bloco (as linhas seguintes pertencem ao mesmo mês, mesmo sem
   repetir o nome). Se um bloco de dias no início do documento não tiver
   NENHUM mês indicado (nem na própria linha, nem em nenhuma anterior),
   infira o mês com base no contexto do semestre (ex: se o cronograma é
   "2026/1" e o primeiro mês explícito é "Abril", os dias sem mês que
   vêm antes dele provavelmente são de Março).
3. Para cada evento, chamar a ferramenta create_event com:
   - summary: título curto e descritivo
   - description: detalhes relevantes (ex: número da aula, observações)
   - start / end: datas em ISO 8601. Se não houver horário explícito,
     use 00:00:00 até 23:59:59 do mesmo dia (evento de dia inteiro).
   - timeZone: America/Sao_Paulo
4. Ignore texto que não seja um evento datado (bibliografia, regras de
   avaliação, pesos de nota, cabeçalhos institucionais).
5. Se a data ficar genuinamente ambígua mesmo após tentar inferir o mês,
   NÃO invente — pule esse evento e relate a ambiguidade no resumo final.
6. NÃO peça confirmação ao usuário — crie todos os eventos diretamente.
7. Ao final, responda com um resumo: quantos eventos foram criados, uma
   lista com título + data de cada um, e qualquer ambiguidade que você
   teve que resolver ou pulou.
"""
def parece_grade_semanal(cabecalho: list) -> bool:
    """Detecta se a tabela é uma grade semanal (Mês | Dom | Seg | ... | Sáb)."""
    colunas = [str(c).strip() for c in cabecalho[1:]]
    return colunas == DIAS_SEMANA


def extrair_mes_e_ano_juntos(texto: str):
    m = re.search(r"([A-Za-zç]{3,})\.?\s+(\d{4})", texto or "")
    if not m:
        return None
    mes = MESES_PT.get(m.group(1)[:3].lower())
    return (mes, int(m.group(2))) if mes else None


def extrair_so_mes(texto: str):
    m = re.fullmatch(r"\s*([A-Za-zç]{3,})\.?\s*", texto or "")
    return MESES_PT.get(m.group(1)[:3].lower()) if m else None


def extrair_so_ano(texto: str):
    m = re.fullmatch(r"\s*(\d{4})\s*", texto or "")
    return int(m.group(1)) if m else None


def calcular_eventos_grade_semanal(tabela: list[list]) -> list[dict]:
    celulas_com_posicao = []
    deslocamento = 0
    ultimo_dia_numero = None

    for idx_linha, linha in enumerate(tabela[1:]):
        for idx_coluna, celula in enumerate(linha[1:]):
            if celula:
                m = re.match(r"\s*(\d{1,2})\b", str(celula))
                if m:
                    dia_numero = int(m.group(1))
                    if ultimo_dia_numero is not None and dia_numero < ultimo_dia_numero - 20:
                        deslocamento += 1
                    ultimo_dia_numero = dia_numero
            celulas_com_posicao.append((idx_linha, idx_coluna, celula, deslocamento))

    deslocamento_por_linha = {}
    for idx_linha, idx_coluna, celula, desl in celulas_com_posicao:
        deslocamento_por_linha.setdefault(idx_linha, desl)

    mes_ancora = ano_ancora = deslocamento_ancora = None
    nome_mes_pendente = deslocamento_pendente = None

    for idx_linha, linha in enumerate(tabela[1:]):
        desl = deslocamento_por_linha.get(idx_linha, 0)
        celula_mes = linha[0]
        junto = extrair_mes_e_ano_juntos(celula_mes)
        if junto:
            mes_ancora, ano_ancora, deslocamento_ancora = junto[0], junto[1], desl
            break
        so_mes = extrair_so_mes(celula_mes)
        if so_mes:
            nome_mes_pendente, deslocamento_pendente = so_mes, desl
            continue
        so_ano = extrair_so_ano(celula_mes)
        if so_ano and nome_mes_pendente is not None:
            mes_ancora, ano_ancora, deslocamento_ancora = nome_mes_pendente, so_ano, deslocamento_pendente
            break

    if mes_ancora is None:
        return []

    eventos = []
    for idx_linha, idx_coluna, celula, desl in celulas_com_posicao:
        if not celula:
            continue
        m = re.match(r"\s*(\d{1,2})\b", str(celula))
        if not m:
            continue
        evento_texto = str(celula)[m.end():].strip()
        if not evento_texto:
            continue
        dia_numero = int(m.group(1))
        diferenca = desl - deslocamento_ancora
        mes_total = (mes_ancora - 1) + diferenca
        mes_linha = mes_total % 12 + 1
        ano_linha = ano_ancora + mes_total // 12
        eventos.append({
            "data": date(ano_linha, mes_linha, dia_numero).isoformat(),
            "dia_semana": DIAS_SEMANA[idx_coluna],
            "descricao": evento_texto.replace("\n", " "),
        })
    return eventos

def preencher_mes_para_baixo(tabela: list[list]) -> list[list]:
    """
    Preenche a primeira coluna (mês) repetindo o último valor visto,
    já que tabelas de cronograma costumam mesclar essa célula
    verticalmente no PDF original.
    """
    ultimo_mes = None
    resultado = []
    for linha in tabela[1:]:  # pula o cabeçalho
        primeira_coluna = linha[0]
        if primeira_coluna:
            ultimo_mes = primeira_coluna
        resultado.append([ultimo_mes] + list(linha[1:]))
    return resultado


def tabela_para_texto(cabecalho: list, linhas: list[list]) -> str:
    partes = [" | ".join(str(c) if c is not None else "" for c in cabecalho)]
    for linha in linhas:
        partes.append(" | ".join(str(c) if c is not None else "" for c in linha))
    return "\n".join(partes)


def extrair_conteudo_pdf(pdf_path: str) -> str:
    blocos = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            partes_pagina = [f"--- Página {i + 1} ---"]

            tabelas = page.extract_tables()
            for tabela in tabelas:
                if not tabela or len(tabela) < 2:
                    continue

                if parece_grade_semanal(tabela[0]):
                    eventos = calcular_eventos_grade_semanal(tabela)
                    linhas_texto = [
                        f"{ev['data']} ({ev['dia_semana']}): {ev['descricao']}"
                        for ev in eventos
                    ]
                    partes_pagina.append("\n".join(linhas_texto))
                else:
                    cabecalho = tabela[0]
                    linhas_preenchidas = preencher_mes_para_baixo(tabela)
                    partes_pagina.append(tabela_para_texto(cabecalho, linhas_preenchidas))

            texto_solto = page.extract_text(layout=True) or ""
            if texto_solto.strip():
                partes_pagina.append("Texto adicional da página:\n" + texto_solto)

            blocos.append("\n\n".join(partes_pagina))

    return "\n\n".join(blocos)


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
        conteudo = extrair_conteudo_pdf(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Erro ao processar PDF: {e}")
    finally:
        os.remove(tmp_path)

    prompt = (
        "Aqui está o conteúdo extraído do documento:\n\n"
        f"{conteudo}\n\n"
        "Crie todos os eventos correspondentes no Google Calendar."
    )

    result = await Runner.run(app.state.agent, prompt, max_turns=60)

    return ScheduleResponse(filename=file.filename, resumo=result.final_output)