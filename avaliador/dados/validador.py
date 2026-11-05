"""Regras que dependem do dataset inteiro, e não de um item isolado."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from avaliador.dados.carregador import CAMINHO_ESQUEMA_PADRAO, ItemCarregado, carregar_dataset
from avaliador.dominio import Item


@dataclass(frozen=True, slots=True)
class RelatorioValidacao:
    itens: tuple[Item, ...]
    erros: tuple[str, ...]

    @property
    def valido(self) -> bool:
        return not self.erros

    def contagem_por_categoria(self) -> dict[str, int]:
        return dict(Counter(item.categoria.value for item in self.itens))


def validar_dataset(raiz: Path, esquema: Path = CAMINHO_ESQUEMA_PADRAO) -> RelatorioValidacao:
    carga = carregar_dataset(raiz, esquema)
    erros = [str(erro) for erro in carga.erros]
    erros.extend(_ids_repetidos(carga.itens))
    erros.extend(_categorias_fora_da_pasta(carga.itens))
    return RelatorioValidacao(
        itens=tuple(carregado.item for carregado in carga.itens),
        erros=tuple(erros),
    )


def _ids_repetidos(carregados: Iterable[ItemCarregado]) -> list[str]:
    primeira_ocorrencia: dict[str, ItemCarregado] = {}
    erros: list[str] = []
    for carregado in carregados:
        anterior = primeira_ocorrencia.setdefault(carregado.item.id, carregado)
        if anterior is not carregado:
            erros.append(
                f"{carregado.origem}: id '{carregado.item.id}' já usado em {anterior.origem}"
            )
    return erros


def _categorias_fora_da_pasta(carregados: Iterable[ItemCarregado]) -> list[str]:
    return [
        f"{carregado.origem}: categoria '{carregado.item.categoria}' "
        f"está na pasta '{carregado.arquivo.parent.name}'"
        for carregado in carregados
        if carregado.arquivo.parent.name != carregado.item.categoria
    ]
