import json
import secrets
from dataclasses import asdict
from pathlib import Path

from domain.interfaces import CredenciaisGoogle, RepositorioDeCredenciais


class RepositorioCredenciaisJson(RepositorioDeCredenciais):
    """Implementação concreta que usa um arquivo JSON como banco de dados.

    Formato do arquivo: { "api_key": {..dados da CredenciaisGoogle..}, ... }
    Simples de propósito — para trocar por SQLite/Postgres depois, só se cria
    outra classe que implemente RepositorioDeCredenciais; nada fora daqui muda.
    """

    def __init__(self, caminho_arquivo: str | Path):
        self._caminho = Path(caminho_arquivo)
        if not self._caminho.exists():
            self._caminho.write_text("{}", encoding="utf-8")

    def _ler_tudo(self) -> dict:
        return json.loads(self._caminho.read_text(encoding="utf-8"))

    def _escrever_tudo(self, dados: dict) -> None:
        self._caminho.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")

    def salvar(self, credenciais: CredenciaisGoogle) -> str:
        dados = self._ler_tudo()

        # Se esse email já tinha uma api_key, reaproveita — evita acumular
        # chaves órfãs toda vez que o mesmo usuário refaz o login.
        api_key_existente = next(
            (chave for chave, valor in dados.items() if valor.get("email") == credenciais.email),
            None,
        )
        api_key = api_key_existente or secrets.token_urlsafe(32)

        dados[api_key] = asdict(credenciais)
        self._escrever_tudo(dados)
        return api_key

    def buscar_por_api_key(self, api_key: str) -> CredenciaisGoogle | None:
        dados = self._ler_tudo()
        valor = dados.get(api_key)
        return CredenciaisGoogle(**valor) if valor else None
