# gcalendar-mcp

Servidor MCP (Model Context Protocol) que liga a um cliente MCP (Claude Desktop, Claude Code, etc.) à tua conta Google Calendar.

## Ferramentas disponíveis

- `list_calendars` — lista as agendas acessíveis
- `list_events` — lista eventos de uma agenda num intervalo de datas
- `create_event` — cria um evento novo
- `update_event` — atualiza campos de um evento existente
- `delete_event` — apaga um evento
- `check_freebusy` — verifica períodos ocupados de uma ou várias agendas

## 1. Criar credenciais no Google Cloud

1. Vai a https://console.cloud.google.com/ e cria (ou seleciona) um projeto.
2. Em **APIs e serviços > Biblioteca**, ativa a **Google Calendar API**.
3. Em **APIs e serviços > Ecrã de consentimento OAuth**, configura o consentimento
   (tipo "Externo" chega se fores só tu a usar; adiciona-te como utilizador de teste).
4. Em **APIs e serviços > Credenciais > Criar credenciais > ID de cliente OAuth**,
   escolhe o tipo **"App para computador" (Desktop app)**.
5. Faz download do JSON gerado e guarda-o como `credentials.json` na raiz deste
   projeto (`gcalendar-mcp/credentials.json`).

## 2. Instalar dependências

```bash
npm install
```

## 3. Autenticar (uma vez)

```bash
npm run auth
```

Isto abre um URL no terminal — copia para o browser, autoriza o acesso, copia o
código de volta e cola no terminal. Isto cria o ficheiro `token.json` com o
`refresh_token`, para não teres de repetir o login.

## 4. Correr o servidor

```bash
npm start
```

O servidor comunica por **stdio** — é assim que a maioria dos clientes MCP
(Claude Desktop, Claude Code, etc.) espera receber o servidor.

## 5. Ligar a um cliente MCP

Exemplo de configuração para o Claude Desktop
(`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gcalendar": {
      "command": "node",
      "args": ["/caminho/completo/para/gcalendar-mcp/src/index.js"]
    }
  }
}
```

Depois de reiniciar o cliente, as ferramentas do Google Calendar ficam
disponíveis para o modelo invocar.

## Notas de segurança

- `credentials.json` e `token.json` nunca devem ser partilhados nem enviados
  para um repositório público — dão acesso à tua conta Google.
- Ajusta os `SCOPES` em `src/auth.js` ao mínimo necessário. Por omissão inclui
  leitura, gestão de eventos e consulta de disponibilidade.
- Se mudares os `SCOPES`, apaga o `token.json` e corre `npm run auth`
  novamente — tokens antigos não incluem os novos scopes.
