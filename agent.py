"""
Agente OpenAI que fala com o Google Calendar através do gcalendar-mcp.

Pré-requisitos:
  1. O projeto gcalendar-mcp já configurado (credentials.json + token.json
     gerados via `npm run auth`) — ver o README desse projeto.
  2. `pip install -r requirements.txt`
  3. Variável de ambiente OPENAI_API_KEY definida (ou num ficheiro .env).

Uso:
  python agent.py "que eventos tenho esta semana?"
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

load_dotenv()

# Caminho para o servidor MCP do Google Calendar que já construímos.
# Ajusta se tiveres o projeto gcalendar-mcp noutro sítio.
GCALENDAR_MCP_PATH = Path(
    os.environ.get("GCALENDAR_MCP_PATH", "../gcalendar-mcp/src/index.js")
).resolve()

INSTRUCTIONS = """
És um assistente que ajuda a gerir a agenda do utilizador através do
Google Calendar. Usa as ferramentas disponíveis (list_calendars,
list_events, create_event, update_event, delete_event, check_freebusy)
sempre que precisares de consultar ou alterar eventos.

Datas e horas: quando o utilizador não especificar o fuso horário,
assume America/Sao_Paulo. Confirma sempre os detalhes de um evento (título,
data, hora) antes de o criar, atualizar ou apagar, caso não tenham sido
dados explicitamente pelo utilizador.
"""


async def run(prompt: str) -> None:
    if not GCALENDAR_MCP_PATH.exists():
        raise FileNotFoundError(
            f"Não encontrei o servidor MCP em {GCALENDAR_MCP_PATH}. "
            "Define a variável de ambiente GCALENDAR_MCP_PATH ou ajusta "
            "o caminho no topo deste ficheiro."
        )

    async with MCPServerStdio(
        name="Google Calendar MCP",
        params={
            "command": "node",
            "args": [str(GCALENDAR_MCP_PATH)],
        },
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    ) as calendar_server:
        agent = Agent(
            name="Assistente de Agenda",
            instructions=INSTRUCTIONS,
            model="gpt-4.1",
            mcp_servers=[calendar_server],
        )

        result = await Runner.run(agent, prompt)
        print(result.final_output)


def main() -> None:
    if len(sys.argv) < 2:
        print('Uso: python agent.py "a tua pergunta ou pedido"')
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    asyncio.run(run(prompt))


if __name__ == "__main__":
    main()
