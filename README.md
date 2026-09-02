# gcalendar-openai-agent

Liga um agente da **OpenAI Agents SDK** ao servidor MCP `gcalendar-mcp`
(Google Calendar), sem precisar de expor nada à internet — corre tudo
localmente.

## Como funciona

O OpenAI Agents SDK arranca o `gcalendar-mcp` como um processo local
(`node src/index.js`), fala com ele via stdio (o mesmo protocolo que o
Claude Desktop usa), e converte automaticamente as ferramentas do MCP
(`list_events`, `create_event`, etc.) em function calls que o modelo
GPT consegue invocar.

```
Tu → agent.py → OpenAI API (GPT) → MCPServerStdio → gcalendar-mcp → Google Calendar
```

## 1. Pré-requisito: gcalendar-mcp já configurado

Este agente não repete a autenticação Google — reaproveita o projeto
`gcalendar-mcp` que já configuraste (com `credentials.json` e
`token.json` gerados via `npm run auth`). Se ainda não o tens
configurado, faz isso primeiro (ver o README desse projeto).

Por omissão, este script espera encontrar o `gcalendar-mcp` na pasta
irmã `../gcalendar-mcp`. Se estiver noutro sítio, define a variável de
ambiente `GCALENDAR_MCP_PATH` com o caminho completo para o
`src/index.js`.

## 2. Instalar dependências Python

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Configurar a chave da OpenAI

Cria um ficheiro `.env` nesta pasta:

```
OPENAI_API_KEY=sk-...
```

Ou define a variável de ambiente diretamente no terminal.

## 4. Correr

```bash
python agent.py "que eventos tenho esta semana?"
python agent.py "cria uma reunião amanhã às 15h"
python agent.py "estou livre na sexta de manhã?"
```

O agente decide sozinho que ferramentas do MCP invocar consoante o
pedido.

## Notas

- O modelo por omissão é `gpt-4.1-mini`; muda a linha `model=...` em
  `agent.py` se quiseres outro.
- `cache_tools_list=True` evita perguntar ao servidor MCP pela lista de
  ferramentas em cada execução — mais rápido, mas se adicionares
  ferramentas novas ao `gcalendar-mcp` pode ser preciso reiniciar.
- Isto é um script de linha de comandos, útil para testar. Para usar
  isto num serviço contínuo (ex: bot do Slack, API própria), envolve a
  função `run()` num servidor (Flask/FastAPI) ou num worker.
