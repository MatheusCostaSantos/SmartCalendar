from abc import ABC, abstractmethod


class ExtratorDeCronograma(ABC):
    """Contrato: qualquer coisa que saiba transformar um PDF de cronograma em texto."""

    @abstractmethod
    def extrair(self, caminho_pdf: str) -> str:
        """Recebe o caminho de um PDF e devolve o conteúdo já organizado em texto."""


class AssistenteDeAgendamento(ABC):
    """Contrato: qualquer coisa que saiba interpretar um cronograma e criar eventos."""

    @abstractmethod
    async def processar(self, conteudo: str, contexto_adicional: str | None = None) -> str:
        """Recebe o conteúdo extraído e um contexto extra opcional (informações
        que o usuário sabe mas que não estão escritas no PDF), e devolve um
        resumo do que foi feito."""