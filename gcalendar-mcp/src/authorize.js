import readline from "readline";
import fs from "fs";
import { createOAuthClient, SCOPES, TOKEN_PATH } from "./auth.js";

async function main() {
  const client = createOAuthClient();

  const authUrl = client.generateAuthUrl({
    access_type: "offline", // necessário para receber refresh_token
    prompt: "consent",
    scope: SCOPES,
  });

  console.log("\n1. Abre este URL no browser e autoriza a app:\n");
  console.log(authUrl);
  console.log("\n2. Copia o código que o Google te dá e cola aqui.\n");

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const code = await new Promise((resolve) => rl.question("Código: ", resolve));
  rl.close();

  const { tokens } = await client.getToken(code.trim());
  fs.writeFileSync(TOKEN_PATH, JSON.stringify(tokens, null, 2));
  console.log(`\nToken guardado em ${TOKEN_PATH}. Já podes correr o servidor MCP.`);
}

main().catch((err) => {
  console.error("Falha na autorização:", err.message);
  process.exit(1);
});
