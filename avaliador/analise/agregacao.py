"""Tabela de pontuações e placar com intervalo de confiança."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from avaliador.analise.estatistica import diferenca_pareada, intervalo_bootstrap
from avaliador.dominio import Item, Pontuacao
from avaliador.pontuacao import SITUACOES_FORA_DA_MEDIA, Situacao, id_base

COLUNAS = [
    "modelo",
    "item_id",
    "item_base",
    "categoria",
    "formato",
    "data_referencia",
    "tentativa",
    "pontuador",
    "nota",
    "situacao",
    "extraida",
    "gabarito",
]
CONTAGENS = [Situacao.SEM_RESPOSTA, Situacao.ERRO_API, Situacao.ERRO_JUIZ]


def tabela_de_pontuacoes(pontuacoes: Iterable[Pontuacao], itens: Iterable[Item]) -> pd.DataFrame:
    """Uma linha por pontuação, já com categoria, formato e data do item."""
    por_id = {item.id: item for item in itens}
    linhas = []
    for pontuacao in pontuacoes:
        item = por_id[pontuacao.item_id]
        linhas.append(
            {
                "modelo": pontuacao.modelo_id,
                "item_id": pontuacao.item_id,
                "item_base": id_base(pontuacao.item_id),
                "categoria": item.categoria.value,
                "formato": item.formato.value,
                "data_referencia": item.data_referencia,
                "tentativa": pontuacao.tentativa,
                "pontuador": pontuacao.pontuador,
                "nota": pontuacao.nota,
                "situacao": pontuacao.detalhes.get("situacao"),
                "extraida": pontuacao.detalhes.get("extraida"),
                "gabarito": pontuacao.detalhes.get("gabarito"),
            }
        )
    return pd.DataFrame(linhas, columns=COLUNAS)


def notas_por_item(tabela: pd.DataFrame) -> pd.DataFrame:
    """Média por modelo e questão: repetições e variantes viram uma nota só por questão."""
    validas = tabela[~tabela["situacao"].isin(SITUACOES_FORA_DA_MEDIA)]
    return validas.groupby(["modelo", "categoria", "item_base"], as_index=False)["nota"].mean()


def placar(tabela: pd.DataFrame, *, reamostragens: int = 2000, semente: int = 0) -> pd.DataFrame:
    """Uma linha por modelo, do melhor para o pior.

    `geral` é a média das categorias (cada categoria pesa igual), com IC de 95%.
    `empata_com_lider` diz se a diferença para o 1º lugar cabe no acaso.
    """
    por_item = notas_por_item(tabela)
    if por_item.empty:
        return pd.DataFrame()
    linhas = []
    for modelo, dados in por_item.groupby("modelo"):
        grupos = {cat: notas["nota"].to_numpy() for cat, notas in dados.groupby("categoria")}
        geral, inferior, superior = intervalo_bootstrap(
            grupos, reamostragens=reamostragens, semente=semente
        )
        linhas.append(
            {
                "modelo": modelo,
                "geral": geral,
                "ic_inferior": inferior,
                "ic_superior": superior,
                "n_itens": len(dados),
                **{categoria: notas.mean() for categoria, notas in grupos.items()},
            }
        )
    resultado = pd.DataFrame(linhas).set_index("modelo").sort_values("geral", ascending=False)
    resultado["empata_com_lider"] = _empata_com_lider(por_item, resultado.index, reamostragens)
    contagens = tabela.groupby("modelo")["situacao"].value_counts().unstack(fill_value=0)
    for situacao in CONTAGENS:
        resultado[situacao.value] = contagens.get(situacao.value, 0)
    return resultado


def _empata_com_lider(
    por_item: pd.DataFrame, ordem: pd.Index, reamostragens: int
) -> list[bool]:
    largo = por_item.pivot_table(index=["categoria", "item_base"], columns="modelo", values="nota")
    lider = ordem[0]
    empates = []
    for modelo in ordem:
        pares = largo[[lider, modelo]].dropna()
        if modelo == lider or pares.empty:
            empates.append(True)
            continue
        _, inferior, _ = diferenca_pareada(
            pares[lider].to_numpy(), pares[modelo].to_numpy(), reamostragens=reamostragens
        )
        empates.append(bool(inferior <= 0))
    return empates
