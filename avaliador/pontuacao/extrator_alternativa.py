"""Extrai a opção escolhida (letra ou rótulo) do texto livre de um modelo."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

_TRECHO_RESPOSTA = re.compile(
    r"\bresposta(?:\s+(?:final|correta))?\s*(?::|é\s)\s*(?P<trecho>[^\n]+)", re.IGNORECASE
)
_MARCACAO = re.compile(r"[*_`#>]")
# shortcut: "a resposta é a B" (artigo sem a palavra "letra") é lido como A; raro na prática.
_PREFIXO = re.compile(r"^(?:[ao]\s+)?(?:letra|alternativa|opcao)\s+")
_LETRA = re.compile(r"^\(?([a-z])\)?(?!\w)")
_LETRA_SOZINHA = re.compile(r"^\(?([a-z])\)?$")


def extrair_opcao(texto: str, opcoes: Sequence[str]) -> str | None:
    """Usa o último "Resposta: X"; sem ele, só aceita a última linha se ela for só a opção.

    Devolve None quando não dá para saber: nunca chuta uma opção.
    """
    limpo = _MARCACAO.sub("", texto)
    trechos = [encontrado["trecho"] for encontrado in _TRECHO_RESPOSTA.finditer(limpo)]
    if trechos:
        return _casar(trechos[-1], opcoes, estrito=False)
    linhas = [linha for linha in limpo.splitlines() if linha.strip()]
    return _casar(linhas[-1], opcoes, estrito=True) if linhas else None


def _casar(trecho: str, opcoes: Sequence[str], *, estrito: bool) -> str | None:
    trecho = _PREFIXO.sub("", _normalizar(trecho))
    if all(len(opcao) == 1 and opcao.isupper() for opcao in opcoes):
        encontrado = (_LETRA_SOZINHA if estrito else _LETRA).match(trecho)
        letra = encontrado.group(1).upper() if encontrado else None
        return letra if letra in opcoes else None
    return _casar_rotulo(trecho, opcoes, estrito=estrito)


def _casar_rotulo(trecho: str, rotulos: Sequence[str], *, estrito: bool) -> str | None:
    por_forma_normal = {_normalizar(rotulo): rotulo for rotulo in rotulos}
    if trecho in por_forma_normal:
        return por_forma_normal[trecho]
    if estrito:
        return None
    citados = [
        forma
        for forma in por_forma_normal
        if re.search(rf"(?<!\w){re.escape(forma)}(?!\w)", trecho)
    ]
    if not citados:
        return None
    # "não irônica" cita "irônica" também: vale o rótulo mais longo que contém os outros.
    maior = max(citados, key=len)
    if all(forma in maior for forma in citados):
        return por_forma_normal[maior]
    return None


def _normalizar(texto: str) -> str:
    sem_acento = "".join(
        letra
        for letra in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(letra)
    )
    return sem_acento.casefold().strip().strip(".,;:!?\"'“”").strip()
