import { OAuth2Client } from "google-auth-library";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, "..");

// Ficheiro obtido no Google Cloud Console (OAuth Client ID -> Desktop app)
export const CREDENTIALS_PATH = path.join(ROOT, "credentials.json");
// Onde o token de acesso/refresh fica guardado depois do primeiro login
export const TOKEN_PATH = path.join(ROOT, "token.json");

// Scopes: leitura + escrita de eventos. Se só precisares de ler, troca
// "calendar.events" por "calendar.events.readonly" e "calendar" por "calendar.readonly".
export const SCOPES = [
  "https://www.googleapis.com/auth/calendar.readonly",
  "https://www.googleapis.com/auth/calendar.events",
  "https://www.googleapis.com/auth/calendar.freebusy",
];

function loadCredentials() {
  if (!fs.existsSync(CREDENTIALS_PATH)) {
    throw new Error(
      `Não encontrei ${CREDENTIALS_PATH}. Cria um OAuth Client ID (tipo "Desktop app") ` +
        `no Google Cloud Console, ativa a Google Calendar API, e faz download do JSON ` +
        `para esse caminho.`
    );
  }
  const raw = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, "utf-8"));
  return raw.installed || raw.web;
}

export function createOAuthClient() {
  const { client_id, client_secret, redirect_uris } = loadCredentials();
  return new OAuth2Client(client_id, client_secret, redirect_uris[0]);
}

// Devolve um client já autenticado, pronto a usar nas chamadas à API.
// Lança erro se ainda não houver token (nesse caso corre `npm run auth` primeiro).
export function getAuthorizedClient() {
  const client = createOAuthClient();
  if (!fs.existsSync(TOKEN_PATH)) {
    throw new Error(
      "Ainda não há token guardado. Corre `npm run auth` uma vez para autenticar " +
        "a tua conta Google (abre o browser, pede consentimento, guarda o token)."
    );
  }
  const token = JSON.parse(fs.readFileSync(TOKEN_PATH, "utf-8"));
  client.setCredentials(token);

  // Garante refresh automático e persiste o novo token quando o Google o renovar
  client.on("tokens", (tokens) => {
    const merged = { ...token, ...tokens };
    fs.writeFileSync(TOKEN_PATH, JSON.stringify(merged, null, 2));
  });

  return client;
}
