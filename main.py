
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


def extrair_mes_ano(texto_mes: str) -> tuple[int, int] | None:
    """Extrai (mês, ano) de algo como 'Ago 2026'."""
    match = re.search(r"([A-Za-zç]{3,})\.?\s+(\d{4})", texto_mes or "")
    if not match:
        return None
    nome_mes, ano = match.groups()
    mes = MESES_PT.get(nome_mes[:3].lower())
    return (mes, int(ano)) if mes else None


def calcular_eventos_grade_semanal(tabela: list[list]) -> list[dict]:
    """
    Converte uma tabela no formato Mês | Dom | Seg | Ter | Qua | Qui | Sex | Sáb
    em uma lista de eventos com data exata já calculada (sem depender do
    modelo de linguagem para nenhuma conta).
    """
    eventos = []
    mes_atual, ano_atual = None, None
    # referência do último dia visto, para detectar virada de mês
    # (ex: dia 31 seguido de dia 1 significa que viramos o mês)
    ultimo_dia_numero = None

    for linha in tabela[1:]:  # pula cabeçalho
        celula_mes = linha[0]
        extraido = extrair_mes_ano(celula_mes)
        if extraido:
            mes_atual, ano_atual = extraido

        if mes_atual is None:
            continue  # ainda não conseguimos identificar o mês, pula a linha

        for i, celula in enumerate(linha[1:]):
            if not celula:
                continue

            match_dia = re.match(r"\s*(\d{1,2})\b", str(celula))
            if not match_dia:
                continue

            dia_numero = int(match_dia.group(1))
            evento_texto = str(celula)[match_dia.end():].strip()

            # detecta virada de mês: se o número do dia "voltou" para um
            # valor bem menor que o anterior dentro da mesma linha, o mês virou
            if ultimo_dia_numero is not None and dia_numero < ultimo_dia_numero - 20:
                mes_atual += 1
                if mes_atual > 12:
                    mes_atual = 1
                    ano_atual += 1
            ultimo_dia_numero = dia_numero

            if evento_texto:  # só cria evento se a célula tiver texto além do número
                data_evento = date(ano_atual, mes_atual, dia_numero)
                eventos.append({
                    "data": data_evento.isoformat(),
                    "dia_semana": DIAS_SEMANA[i],
                    "descricao": evento_texto,
                })

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