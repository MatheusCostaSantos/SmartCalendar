from pathlib import Path

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

from domain.interfaces import AutenticadorGoogle, CredenciaisGoogle

# openid + userinfo.email: só pra sabermos QUEM logou (o "email" que vira
# chave no nosso repositório). O resto é o mesmo acesso que o gcalendar-mcp
# já pedia.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy",
]


class AutenticadorGoogleOAuthlib(AutenticadorGoogle):
    """Implementação concreta usando a lib oficial google-auth-oauthlib."""

    def __init__(self, caminho_credenciais_client: str | Path, redirect_uri: str):
        self._caminho_credenciais = str(caminho_credenciais_client)
        self._redirect_uri = redirect_uri
        # Guarda o Flow (com seu code_verifier) entre o /login e o /callback,
        # indexado pelo 'state' que o Google devolve intacto no redirecionamento.
        # Isso é memória do processo — reiniciar a API invalida logins pendentes.
        self._flows_pendentes: dict[str, Flow] = {}

    def _criar_flow(self) -> Flow:
        return Flow.from_client_secrets_file(
            self._caminho_credenciais,
            scopes=SCOPES,
            redirect_uri=self._redirect_uri,
            autogenerate_code_verifier=True,  # liga o PKCE, exigido pelo Google
        )

    def gerar_url_login(self) -> str:
        flow = self._criar_flow()
        url, state = flow.authorization_url(
            access_type="offline",  # sem isso o Google não manda refresh_token
            prompt="consent",  # força reconsentimento, garantindo refresh_token mesmo num re-login
            include_granted_scopes="true",
        )
        self._flows_pendentes[state] = flow
        return url

    def trocar_code_por_credenciais(self, code: str, state: str) -> CredenciaisGoogle:
        flow = self._flows_pendentes.pop(state, None)
        if flow is None:
            raise ValueError(
                "Login expirado ou inválido (state desconhecido) — tente fazer login novamente."
            )

        flow.fetch_token(code=code)
        creds = flow.credentials

        info = id_token.verify_oauth2_token(
            creds.id_token, google_requests.Request(), creds.client_id
        )

        return CredenciaisGoogle(
            email=info["email"],
            access_token=creds.token,
            refresh_token=creds.refresh_token,
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            token_uri=creds.token_uri,
            scopes=list(creds.scopes or SCOPES),
            expiry=creds.expiry.isoformat() if creds.expiry else None,
        )
