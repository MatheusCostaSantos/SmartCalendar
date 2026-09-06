import re
from datetime import date

import pdfplumber

from domain.interfaces import ExtratorDeCronograma

DIAS_SEMANA = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
MESES_PT = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def parece_grade_semanal(cabecalho: list) -> bool:
    return [str(c).strip() for c in cabecalho[1:]] == DIAS_SEMANA


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


def calcular_eventos_grade_semanal(tabela: list) -> list[dict]:
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


def preencher_mes_para_baixo(tabela: list) -> list:
    ultimo_mes = None
    resultado = []
    for linha in tabela[1:]:
        primeira_coluna = linha[0]
        if primeira_coluna:
            ultimo_mes = primeira_coluna
        resultado.append([ultimo_mes] + list(linha[1:]))
    return resultado


def tabela_para_texto(cabecalho: list, linhas: list) -> str:
    partes = [" | ".join(str(c) if c is not None else "" for c in cabecalho)]
    for linha in linhas:
        partes.append(" | ".join(str(c) if c is not None else "" for c in linha))
    return "\n".join(partes)


class ExtratorPdfplumber(ExtratorDeCronograma):
    """Implementação concreta que usa pdfplumber para extrair o conteúdo do PDF."""

    def extrair(self, caminho_pdf: str) -> str:
        blocos = []
        with pdfplumber.open(caminho_pdf) as pdf:
            for i, page in enumerate(pdf.pages):
                partes_pagina = [f"--- Página {i + 1} ---"]

                for tabela in page.extract_tables():
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
