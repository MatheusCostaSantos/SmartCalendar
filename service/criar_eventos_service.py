from domain.interfaces import (
    AssistenteDeAgendamento,
    CredenciaisGoogle,
    ExtratorDeCronograma,
)


class CriarEventosDoPdfService:
    """Orquestra a extração do PDF e a criação dos eventos, sem saber
    qual biblioteca faz a extração nem qual IA cria os eventos de fato."""

    def __init__(self, extrator: ExtratorDeCronograma, assistente: AssistenteDeAgendamento):
        self._extrator = extrator
        self._assistente = assistente

    async def executar(
        self,
        caminho_pdf: str,
        credenciais: CredenciaisGoogle,
        contexto_adicional: str | None = None,
    ) -> str:
        conteudo = self._extrator.extrair(caminho_pdf)
        return await self._assistente.processar(conteudo, credenciais, contexto_adicional)
