import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { google } from "googleapis";
import { z } from "zod";
import { getAuthorizedClient } from "./auth.js";

const auth = getAuthorizedClient();
const calendar = google.calendar({ version: "v3", auth });

const MAX_TENTATIVAS = 5;
const ESPERA_BASE_MS = 1000;

function esperar(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function ehErroDeLimite(err) {
  const status = err?.code ?? err?.response?.status;
  const motivo = err?.errors?.[0]?.reason ?? err?.response?.data?.error?.errors?.[0]?.reason;
  return status === 429 || (status === 403 && (motivo === "rateLimitExceeded" || motivo === "userRateLimitExceeded"));
}

async function comRetentativa(funcao) {
  let tentativa = 0;
  while (true) {
    try {
      return await funcao();
    } catch (err) {
      if (!ehErroDeLimite(err) || tentativa >= MAX_TENTATIVAS) {
        throw err;
      }
      const espera = ESPERA_BASE_MS * 2 ** tentativa;
      console.error(`Limite de requisições atingido. Tentando de novo em ${espera}ms (tentativa ${tentativa + 1}/${MAX_TENTATIVAS})`);
      await esperar(espera);
      tentativa++;
    }
  }
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
    const res = await comRetentativa(() => calendar.calendarList.list());
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
    const res = await comRetentativa(() =>
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
    const res = await comRetentativa(() =>
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

    const res = await comRetentativa(() =>
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
    await comRetentativa(() => calendar.events.delete({ calendarId, eventId }));
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
    const res = await comRetentativa(() =>
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
