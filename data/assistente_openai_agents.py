import json
import os
from pathlib import Path

from agents import Agent, Runner
from agents.mcp import MCPServerStdio

from domain.interfaces import AssistenteDeAgendamento, CredenciaisGoogle

INSTRUCTIONS = """
Você é um assistente que cria eventos no Google Calendar a partir do
conteúdo de um cronograma extraído de um PDF.

O texto que você vai receber pode conter tabelas (formatadas como linhas
de colunas separadas por " | ", ou como "AAAA-MM-DD (dia da semana):
descrição") e também texto solto (parágrafos, avisos, bibliografia etc).
Nem tudo é evento de calendário.

Sua tarefa:
1. Identificar cada evento relevante (aula, prova, feriado, entrega de
   lista, avaliação, revisão, "não haverá aula" etc.) presente no texto.
2. Quando o texto vier no formato "AAAA-MM-DD (dia da semana): descrição",
   a data já está calculada corretamente — use-a exatamente como está,
   NÃO recalcule nem infira outra data para esse evento.
3. Algumas tabelas têm uma coluna de Mês que só aparece na primeira linha
   de cada bloco. Se um bloco de dias no início do documento não tiver
   NENHUM mês indicado, infira o mês com base no contexto do semestre.
4. Para cada evento, chamar a ferramenta create_event com:
   - summary: título curto e descritivo
   - description: detalhes relevantes (ex: número da aula, observações)
   - start / end: datas em ISO 8601. Se não houver horário explícito,
     use 00:00:00 até 23:59:59 do mesmo dia (evento de dia inteiro).
   - timeZone: America/Sao_Paulo
5. Ignore texto que não seja um evento datado (bibliografia, regras de
   avaliação, pesos de nota, cabeçalhos institucionais).
6. Se a data ficar genuinamente ambígua mesmo após tentar inferir o mês,
   NÃO invente — pule esse evento e relate a ambiguidade no resumo final.
7. Se o usuário fornecer um "Contexto adicional", trate essas informações
   como MAIS CONFIÁVEIS que qualquer inferência sua a partir do PDF sozinho
   — use-as para resolver ambiguidades (ex: em que dia da semana cai uma
   aula que o PDF não especifica claramente).
8. NÃO peça confirmação ao usuário — crie todos os eventos diretamente.
9. Ao final, responda com um resumo: quantos eventos foram criados, uma
   lista com título + data de cada um, e qualquer ambiguidade que você
   teve que resolver ou pulou.
   
"""


class AssistenteAgentesOpenAI(AssistenteDeAgendamento):
    """Implementação concreta que usa o OpenAI Agents SDK + o MCP do Google Calendar.

    Diferente da v1: não guarda mais um único `Agent` fixo. Cada chamada a
    `processar` sobe seu próprio processo do gcalendar-mcp, autenticado com
    as credenciais DAQUELE usuário, e o derruba ao terminar."""

    def __init__(self, caminho_mcp: str | Path, modelo: str = "gpt-4.1-mini"):
        self._caminho_mcp = str(caminho_mcp)
        self._modelo = modelo

    def _montar_prompt(self, conteudo: str, contexto_adicional: str | None) -> str:
        partes_prompt = [
            "Aqui está o conteúdo extraído do documento:",
            "",
            conteudo,
        ]
        if contexto_adicional:
            partes_prompt += [
                "",
                "--- Contexto adicional fornecido pelo usuário (use com prioridade) ---",
                contexto_adicional,
            ]
        partes_prompt += ["", "Crie todos os eventos correspondentes no Google Calendar."]
        return "\n".join(partes_prompt)

    def _env_com_token_do_usuario(self, credenciais: CredenciaisGoogle) -> dict:
        # O gcalendar-mcp (Node) lê essa variável em vez do token.json fixo
        # quando ela existe — veja a mudança em gcalendar-mcp/src/auth.js.
        token = {
            "access_token": credenciais.access_token,
            "refresh_token": credenciais.refresh_token,
            "scope": " ".join(credenciais.scopes),
            "token_type": "Bearer",
        }
        return {
            **os.environ,
            "GOOGLE_TOKEN_JSON": json.dumps(token),
            "GOOGLE_CLIENT_ID": credenciais.client_id,
            "GOOGLE_CLIENT_SECRET": credenciais.client_secret,
        }

    async def processar(
        self,
        conteudo: str,
        credenciais: CredenciaisGoogle,
        contexto_adicional: str | None = None,
    ) -> str:
        prompt = self._montar_prompt(conteudo, contexto_adicional)

        async with MCPServerStdio(
            name="Google Calendar MCP",
            params={
                "command": "node",
                "args": [self._caminho_mcp],
                "env": self._env_com_token_do_usuario(credenciais),
            },
            cache_tools_list=True,
            client_session_timeout_seconds=60,
        ) as calendar_server:
            agente = Agent(
                name="Criador de Eventos",
                instructions=INSTRUCTIONS,
                model=self._modelo,
                mcp_servers=[calendar_server],
            )
            resultado = await Runner.run(agente, prompt, max_turns=60)
            return resultado.final_output