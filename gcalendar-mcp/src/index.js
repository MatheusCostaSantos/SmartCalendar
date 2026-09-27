import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { google } from "googleapis";
import { z } from "zod";
import { getAuthorizedClient } from "./auth.js";

const auth = getAuthorizedClient();
const calendar = google.calendar({ version: "v3", auth });

// 3000ms entre chamadas (mantido por escolha do usuário, mesmo sendo mais
// conservador que a cota real da Calendar API). O trade-off: quanto mais
// eventos no cronograma, mais tempo a fila toda leva — por isso o
// client_session_timeout_seconds do lado Python (e o readTimeout do app
// Android) precisam ter folga suficiente pra cobrir N eventos * 3s.
const ESPACAMENTO_MS = 3000;

function esperar(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

let filaPromise = Promise.resolve();

function enfileirar(funcao) {
  const execucao = filaPromise.then(() => funcao());
  filaPromise = execucao.catch(() => {}).then(() => esperar(ESPACAMENTO_MS));
  return execucao;
}

const server = new McpServer({
  name: "gcalendar-mcp",
  version: "1.0.0",
});

function asText(obj) {
  return { content: [{ type: "text", text: JSON.stringify(obj, null, 2) }] };
}

// --- Ferramenta: listar agendas disponíveis ---
server.tool(
  "list_calendars",
  "Lista as agendas (calendars) a que a conta autenticada tem acesso",
  {},
  async () => {
    const res = await enfileirar(() => calendar.calendarList.list());
    return asText(res.data.items ?? []);
  }
);

// --- Ferramenta: listar eventos ---
server.tool(
  "list_events",
  "Lista eventos de uma agenda num intervalo de datas",
  {
    calendarId: z
      .string()
      .default("primary")
      .describe("ID da agenda (usa 'primary' para a agenda principal do utilizador)"),
    timeMin: z
      .string()
      .describe("Data/hora inicial em ISO 8601, ex: 2026-09-02T00:00:00Z"),
    timeMax: z
      .string()
      .describe("Data/hora final em ISO 8601, ex: 2026-09-09T00:00:00Z"),
    maxResults: z.number().int().min(1).max(250).default(50),
  },
  async ({ calendarId, timeMin, timeMax, maxResults }) => {
    const res = await enfileirar(() =>
      calendar.events.list({
        calendarId,
        timeMin,
        timeMax,
        maxResults,
        singleEvents: true,
        orderBy: "startTime",
      })
    );
    return asText(res.data.items ?? []);
  }
);

// --- Ferramenta: criar evento ---
server.tool(
  "create_event",
  "Cria um novo evento numa agenda",
  {
    calendarId: z.string().default("primary"),
    summary: z.string().describe("Título do evento"),
    description: z.string().optional(),
    location: z.string().optional(),
    start: z.string().describe("Data/hora de início em ISO 8601"),
    end: z.string().describe("Data/hora de fim em ISO 8601"),
    timeZone: z.string().default("Europe/Lisbon"),
    attendees: z
      .array(z.string())
      .optional()
      .describe("Lista de emails a convidar"),
  },
  async ({ calendarId, summary, description, location, start, end, timeZone, attendees }) => {
    const res = await enfileirar(() =>
      calendar.events.insert({
        calendarId,
        requestBody: {
          summary,
          description,
          location,
          start: { dateTime: start, timeZone },
          end: { dateTime: end, timeZone },
          attendees: attendees?.map((email) => ({ email })),
        },
      })
    );
    return asText(res.data);
  }
);

// --- Ferramenta: atualizar evento ---
server.tool(
  "update_event",
  "Atualiza campos de um evento existente",
  {
    calendarId: z.string().default("primary"),
    eventId: z.string().describe("ID do evento (obtido via list_events)"),
    summary: z.string().optional(),
    description: z.string().optional(),
    location: z.string().optional(),
    start: z.string().optional().describe("Nova data/hora de início em ISO 8601"),
    end: z.string().optional().describe("Nova data/hora de fim em ISO 8601"),
    timeZone: z.string().default("Europe/Lisbon"),
  },
  async ({ calendarId, eventId, summary, description, location, start, end, timeZone }) => {
    const patch = {};
    if (summary !== undefined) patch.summary = summary;
    if (description !== undefined) patch.description = description;
    if (location !== undefined) patch.location = location;
    if (start !== undefined) patch.start = { dateTime: start, timeZone };
    if (end !== undefined) patch.end = { dateTime: end, timeZone };

    const res = await enfileirar(() =>
      calendar.events.patch({ calendarId, eventId, requestBody: patch })
    );
    return asText(res.data);
  }
);

// --- Ferramenta: apagar evento ---
server.tool(
  "delete_event",
  "Apaga um evento de uma agenda",
  {
    calendarId: z.string().default("primary"),
    eventId: z.string(),
  },
  async ({ calendarId, eventId }) => {
    await enfileirar(() => calendar.events.delete({ calendarId, eventId }));
    return asText({ deleted: true, eventId });
  }
);

// --- Ferramenta: verificar disponibilidade (free/busy) ---
server.tool(
  "check_freebusy",
  "Verifica os períodos ocupados de uma ou mais agendas num intervalo",
  {
    calendarIds: z.array(z.string()).default(["primary"]),
    timeMin: z.string().describe("Data/hora inicial em ISO 8601"),
    timeMax: z.string().describe("Data/hora final em ISO 8601"),
  },
  async ({ calendarIds, timeMin, timeMax }) => {
    const res = await enfileirar(() =>
      calendar.freebusy.query({
        requestBody: {
          timeMin,
          timeMax,
          items: calendarIds.map((id) => ({ id })),
        },
      })
    );
    return asText(res.data.calendars ?? {});
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("gcalendar-mcp a correr via stdio.");
}

main().catch((err) => {
  console.error("Erro fatal:", err);
  process.exit(1);
});
