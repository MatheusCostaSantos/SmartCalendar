from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ExtratorDeCronograma(ABC):
    """Contrato: qualquer coisa que saiba transformar um PDF de cronograma em texto."""

    @abstractmethod
    def extrair(self, caminho_pdf: str) -> str:
        """Recebe o caminho de um PDF e devolve o conteúdo já organizado em texto."""


@dataclass
class CredenciaisGoogle:
    """Tudo que é preciso para agir na agenda do Google de UM usuário específico."""

    email: str
    access_token: str
    refresh_token: str
    client_id: str
    client_secret: str
    token_uri: str = "https://oauth2.googleapis.com/token"
    scopes: list[str] = field(default_factory=list)
    expiry: str | None = None  # ISO 8601; None se ainda não soubermos


class AssistenteDeAgendamento(ABC):
    """Contrato: qualquer coisa que saiba interpretar um cronograma e criar eventos."""

    @abstractmethod
    async def processar(
        self,
        conteudo: str,
        credenciais: CredenciaisGoogle,
        contexto_adicional: str | None = None,
    ) -> str:
        """Recebe o conteúdo extraído, as credenciais do usuário dono da agenda,
        e um contexto extra opcional (informações que o usuário sabe mas que não
        estão escritas no PDF), e devolve um resumo do que foi feito."""


class RepositorioDeCredenciais(ABC):
    """Contrato: qualquer coisa que saiba guardar e recuperar credenciais por
    api_key ou por email — hoje é um JSON, amanhã pode ser um banco de verdade."""

    @abstractmethod
    def salvar(self, credenciais: CredenciaisGoogle) -> str:
        """Guarda as credenciais (substituindo um login anterior do mesmo email,
        se existir) e devolve a api_key associada a esse usuário."""

    @abstractmethod
    def buscar_por_api_key(self, api_key: str) -> CredenciaisGoogle | None:
        """Devolve as credenciais associadas a essa api_key, ou None se não existir."""


class AutenticadorGoogle(ABC):
    """Contrato: qualquer coisa que saiba conversar com o OAuth do Google."""

    @abstractmethod
    def gerar_url_login(self) -> str:
        """Devolve a URL para onde o navegador do usuário deve ser redirecionado
        para autorizar o acesso à agenda."""

    @abstractmethod
    def trocar_code_por_credenciais(self, code: str, state: str) -> CredenciaisGoogle:
        """Recebe o 'code' e o 'state' devolvidos pelo Google no callback e
        troca por credenciais utilizáveis (access_token, refresh_token, email
        do dono). O 'state' identifica qual login pendente é esse."""