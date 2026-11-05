"""Variantes de itens para medir robustez: a mesma questão com as alternativas giradas."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace

from avaliador.dominio import Alternativa, Formato, Item

SEPARADOR = "~rot"


def rotacionar_alternativas(item: Item, deslocamento: int) -> Item:
    """Gira os textos das alternativas; o gabarito acompanha o texto correto.

    Com 5 alternativas, os deslocamentos 1 a 4 põem a resposta certa em todas as outras letras.
    """
    if item.formato is not Formato.MULTIPLA_ESCOLHA:
        raise ValueError(f"{item.id}: só itens de múltipla escolha têm alternativas para girar")
    total = len(item.alternativas)
    if deslocamento % total == 0:
        raise ValueError(f"deslocamento {deslocamento} deixa as {total} alternativas no lugar")
    letras = item.letras
    textos = [alternativa.texto for alternativa in item.alternativas]
    correta = letras.index(item.resposta_correta)
    return replace(
        item,
        id=f"{item.id}{SEPARADOR}{deslocamento}",
        alternativas=tuple(
            Alternativa(letras[posicao], textos[(posicao - deslocamento) % total])
            for posicao in range(total)
        ),
        resposta_correta=letras[(correta + deslocamento) % total],
        metadados={**item.metadados, "variante_de": item.id},
    )


def com_variantes(itens: Iterable[Item], quantidade: int) -> list[Item]:
    """Cada item seguido de até `quantidade` variantes (só múltipla escolha)."""
    resultado = []
    for item in itens:
        resultado.append(item)
        if item.formato is Formato.MULTIPLA_ESCOLHA:
            maximo = min(quantidade, len(item.alternativas) - 1)
            resultado.extend(rotacionar_alternativas(item, k) for k in range(1, maximo + 1))
    return resultado


def id_base(item_id: str) -> str:
    return item_id.split(SEPARADOR, 1)[0]


def reconstruir_variantes(itens: Sequence[Item], ids_usados: Iterable[str]) -> list[Item]:
    """Itens do dataset mais as variantes citadas nas respostas, para poder pontuá-las."""
    por_id = {item.id: item for item in itens}
    extras = []
    for item_id in sorted(set(ids_usados)):
        base, separador, deslocamento = item_id.partition(SEPARADOR)
        if separador and base in por_id and deslocamento.isdigit():
            extras.append(rotacionar_alternativas(por_id[base], int(deslocamento)))
    return [*itens, *extras]
