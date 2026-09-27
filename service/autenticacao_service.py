from domain.interfaces import AutenticadorGoogle, RepositorioDeCredenciais


class AutenticacaoGoogleService:
    """Orquestra o fluxo de login: gera a URL de consentimento, e depois
    processa o callback trocando o 'code' por credenciais e guardando-as."""

    def __init__(self, autenticador: AutenticadorGoogle, repositorio: RepositorioDeCredenciais):
        self._autenticador = autenticador
        self._repositorio = repositorio

    def gerar_url_login(self) -> str:
        return self._autenticador.gerar_url_login()

    def processar_callback(self, code: str, state: str) -> str:
        """Devolve a api_key que o usuário deve usar nas próximas chamadas."""
        credenciais = self._autenticador.trocar_code_por_credenciais(code, state)
        return self._repositorio.salvar(credenciais)
