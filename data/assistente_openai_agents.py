from agents import Runner

from domain.interfaces import AssistenteDeAgendamento

INSTRUCTIONS = """
Você é um assistente que cria eventos no Google Calendar a partir do
conteúdo de um cronograma extraído de um PDF.

O texto que você vai receber pode conter tabelas (formatadas como linhas
de colunas separadas por " | ", ou como "AAAA-MM-DD (dia da semana):
descrição") e também texto solto (parágrafos, avisos, bibliografia etc).
Nem tudo é evento de calendário.

Sua tarefa:
1. Identificar cada evento relevante (aula, prova, feriado, entrega de
   lista, avaliação, revisão, "não haverá aula" etc.) presente no texto.
2. Quando o texto vier no formato "AAAA-MM-DD (dia da semana): descrição",
   a data já está calculada corretamente — use-a exatamente como está,
   NÃO recalcule nem infira outra data para esse evento.
3. Algumas tabelas têm uma coluna de Mês que só aparece na primeira linha
   de cada bloco. Se um bloco de dias no início do documento não tiver
   NENHUM mês indicado, infira o mês com base no contexto do semestre.
4. Para cada evento, chamar a ferramenta create_event com:
   - summary: título curto e descritivo
   - description: detalhes relevantes (ex: número da aula, observações)
   - start / end: datas em ISO 8601. Se não houver horário explícito,
     use 00:00:00 até 23:59:59 do mesmo dia (evento de dia inteiro).
   - timeZone: America/Sao_Paulo
5. Ignore texto que não seja um evento datado (bibliografia, regras de
   avaliação, pesos de nota, cabeçalhos institucionais).
6. Se a data ficar genuinamente ambígua mesmo após tentar inferir o mês,
   NÃO invente — pule esse evento e relate a ambiguidade no resumo final.
7. NÃO peça confirmação ao usuário — crie todos os eventos diretamente.
8. Ao final, responda com um resumo: quantos eventos foram criados, uma
   lista com título + data de cada um, e qualquer ambiguidade que você
   teve que resolver ou pulou.
"""


class AssistenteAgentesOpenAI(AssistenteDeAgendamento):
    """Implementação concreta que usa o OpenAI Agents SDK + o MCP do Google Calendar."""

    def __init__(self, agente):
        self._agente = agente

    async def processar(self, conteudo: str) -> str:
        prompt = (
            "Aqui está o conteúdo extraído do documento:\n\n"
            f"{conteudo}\n\n"
            "Crie todos os eventos correspondentes no Google Calendar."
        )
        resultado = await Runner.run(self._agente, prompt, max_turns=60)
        return resultado.final_output
