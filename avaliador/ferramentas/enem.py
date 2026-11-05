"""Extração das questões objetivas do ENEM a partir dos PDFs oficiais do INEP.

Provas e gabaritos: https://www.gov.br/inep/pt-br/areas-de-atuacao/avaliacao-e-exames-educacionais/enem/provas-e-gabaritos
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from avaliador.dominio import Categoria

_QUESTAO = re.compile(r"^QUESTÃO\s+(\d{1,3})\s*$", re.MULTILINE)
# \s+ porque o PDF usa espaços especiais (como U+2003) entre essas palavras.
_INICIO_DA_REDACAO = re.compile(r"(PROPOSTA\s+DE|INSTRU\w+\s+PARA\s+A|RASCUNHO\s+DA)\s+REDA")
_RUIDO = re.compile(
    r"ENEM20\d\d"  # marca d'água repetida
    r"|^\*[0-9A-Z]+\*$"  # código de barras da página
    r"|CADERNO \d"  # cabeçalho e rodapé
    r"|^\d+\s*Dia$|^\d\W*Capa$"
    r"|^Questões de \d+ a \d+$"
    r"|^(LINGUAGENS|CIÊNCIAS|MATEMÁTICA)\b.*TECNOLOGIAS$"
)
# Rodapé da gráfica, que o pypdf cola no fim da última linha da página:
# "... de nação. 20 P1_1_Dia_CHT_REG_1_Azul.indd 20 28/08/2024 15:32:18"
_RODAPE_DA_GRAFICA = re.compile(r"(\s+\d+)?\s*\S*\.ind[bd]\b[^\n]*")
_GABARITO = re.compile(r"^(\d{1,3})\s+([A-E])(?:\s+[A-E])?\s*$", re.MULTILINE)
# Questões que dependem de imagem não fazem sentido para um modelo só de texto.
_MARCAS_DE_IMAGEM = re.compile(
    r"\b(imagem|imagens|figuras?|fotografias?|fotos?|charges?|tirinhas?|quadrinhos?|cartuns?|"
    r"gr[aá]ficos?|mapas?|infogr[aá]ficos?|cartaz|cartazes|ilustra[cç](?:[aã]o|[oõ]es)|"
    r"tabelas?|esquemas?|an[uú]ncios?|placas?)\b",
    re.IGNORECASE,
)
_LETRAS = "ABCDE"
_LINGUA_ESTRANGEIRA = range(1, 6)  # inglês ou espanhol: fora de um benchmark de português


@dataclass(frozen=True, slots=True)
class QuestaoEnem:
    numero: int
    enunciado: str
    alternativas: tuple[tuple[str, str], ...]

    @property
    def possivel_imagem(self) -> bool:
        return len(self.enunciado) < 80 or bool(_MARCAS_DE_IMAGEM.search(self.enunciado))


def extrair_texto_pdf(caminho: Path) -> str:
    from pypdf import PdfReader  # extra opcional: pip install -e ".[ferramentas]"

    logging.getLogger("pypdf").setLevel(logging.ERROR)  # avisos de fonte não afetam o texto
    return "\n".join(pagina.extract_text() or "" for pagina in PdfReader(caminho).pages)


def separar_questoes(texto: str) -> list[QuestaoEnem]:
    """Questões com 5 alternativas de texto; as que não se encaixam são descartadas."""
    # O número da página às vezes fica na linha anterior ao rodapé: o corte atravessa a quebra.
    sem_rodape = _RODAPE_DA_GRAFICA.sub("\n", texto)
    limpo = "\n".join(
        linha for linha in sem_rodape.splitlines() if not _RUIDO.search(linha.strip())
    )
    marcadores = list(_QUESTAO.finditer(limpo))
    questoes, vistas = [], set()
    for atual, proximo in zip(marcadores, [*marcadores[1:], None], strict=True):
        numero = int(atual[1])
        if numero in vistas:  # 01 a 05 aparecem duas vezes (inglês e espanhol)
            continue
        vistas.add(numero)
        bloco = limpo[atual.end() : proximo.start() if proximo else len(limpo)]
        # A proposta de redação fica entre duas questões (em 2024, entre a 45 e a 46).
        redacao = _INICIO_DA_REDACAO.search(bloco)
        bloco = bloco[: redacao.start()] if redacao else bloco
        questao = _ler_bloco(numero, bloco)
        if questao is not None:
            questoes.append(questao)
    return questoes


def _ler_bloco(numero: int, bloco: str) -> QuestaoEnem | None:
    linhas = [linha.strip() for linha in bloco.splitlines()]
    # Procura de trás para frente: E, depois o D antes dele, e assim por diante.
    posicoes: dict[str, int] = {}
    limite = len(linhas)
    for letra in reversed(_LETRAS):
        posicao = next(
            (i for i in range(limite - 1, -1, -1) if re.match(rf"{letra}(\s|$)", linhas[i])), None
        )
        if posicao is None:
            return None
        posicoes[letra] = limite = posicao
    enunciado = _juntar(linhas[: posicoes["A"]])
    alternativas = []
    for indice, letra in enumerate(_LETRAS):
        fim = posicoes[_LETRAS[indice + 1]] if indice < 4 else len(linhas)
        alternativas.append((letra, _juntar(linhas[posicoes[letra] : fim])[1:].strip()))
    if not enunciado or not all(texto for _, texto in alternativas):
        return None
    return QuestaoEnem(numero, enunciado, tuple(alternativas))


def _juntar(linhas: Iterable[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(linhas)).strip()


def ler_gabarito(texto: str) -> dict[int, str]:
    """Número da questão -> letra. Nas questões 1 a 5 vale a coluna de inglês."""
    gabarito: dict[int, str] = {}
    for encontrado in _GABARITO.finditer(texto):
        gabarito.setdefault(int(encontrado[1]), encontrado[2])
    return gabarito


def _area(numero: int) -> str:
    if numero <= 45:
        return "linguagens"
    if numero <= 90:
        return "ciencias_humanas"
    return "ciencias_natureza" if numero <= 135 else "matematica"


def questoes_para_itens(
    questoes: Iterable[QuestaoEnem],
    gabarito: Mapping[int, str],
    *,
    ano: int,
    data_prova: date,
    incluir_imagens: bool = False,
) -> list[dict[str, Any]]:
    """Itens no formato do dataset (dicionários prontos para JSONL)."""
    itens = []
    for questao in questoes:
        if questao.numero in _LINGUA_ESTRANGEIRA or questao.numero not in gabarito:
            continue  # sem gabarito = questão anulada
        if questao.possivel_imagem and not incluir_imagens:
            continue
        area = _area(questao.numero)
        categoria = Categoria.INTERPRETACAO if area == "linguagens" else Categoria.CONHECIMENTO
        itens.append(
            {
                "id": f"enem-{ano}-q{questao.numero:03d}",
                "categoria": categoria.value,
                "formato": "multipla_escolha",
                "enunciado": questao.enunciado,
                "alternativas": [
                    {"letra": letra, "texto": texto} for letra, texto in questao.alternativas
                ],
                "resposta_correta": gabarito[questao.numero],
                "fonte": f"INEP - ENEM {ano}, questão {questao.numero}",
                "data_referencia": data_prova.isoformat(),
                "metadados": {
                    "area": area,
                    "ano": ano,
                    "numero": questao.numero,
                    "possivel_imagem": questao.possivel_imagem,
                },
            }
        )
    return itens
