"""Medidas de viés sobre a tabela de pontuações (ver analise.agregacao.tabela_de_pontuacoes)."""

from __future__ import annotations

import pandas as pd

from avaliador.dominio import Formato
from avaliador.pontuacao.base import SITUACOES_FORA_DA_MEDIA, Situacao


def vies_de_posicao(tabela: pd.DataFrame) -> pd.DataFrame:
    """% de vezes que cada letra foi escolhida por modelo, com a distribuição do gabarito.

    Um modelo sem viés escolhe as letras na mesma proporção em que elas são corretas.
    """
    objetivas = tabela[
        (tabela["formato"] == Formato.MULTIPLA_ESCOLHA) & tabela["extraida"].notna()
    ]
    if objetivas.empty:
        return pd.DataFrame()
    escolhas = pd.crosstab(objetivas["modelo"], objetivas["extraida"], normalize="index")
    gabarito = objetivas.drop_duplicates("item_id")["gabarito"].value_counts(normalize=True)
    # Letras que são gabarito mas nunca foram escolhidas também precisam de coluna.
    letras = sorted(set(escolhas.columns) | set(gabarito.index))
    escolhas = escolhas.reindex(columns=letras, fill_value=0.0)
    escolhas.loc["(gabarito)"] = gabarito
    return (escolhas.fillna(0) * 100).round(1)


def consistencia_entre_variantes(tabela: pd.DataFrame) -> pd.Series:
    """Fração das questões em que o modelo acertou (ou errou) em todas as versões giradas."""
    girados = tabela.loc[tabela["item_id"] != tabela["item_base"], "item_base"].unique()
    recorte = tabela[
        tabela["item_base"].isin(girados) & ~tabela["situacao"].isin(SITUACOES_FORA_DA_MEDIA)
    ]
    if recorte.empty:
        return pd.Series(name="consistencia", dtype=float)
    estavel = recorte.groupby(["modelo", "item_base"])["nota"].nunique() == 1
    return estavel.groupby("modelo").mean().rename("consistencia")


def preferencia_propria(tabela: pd.DataFrame, juiz_id: str) -> pd.DataFrame:
    """Nota média dada pelo juiz a cada modelo; a linha do próprio juiz merece desconfiança."""
    avaliadas = tabela[tabela["situacao"] == Situacao.AVALIADA]
    resumo = avaliadas.groupby("modelo")["nota"].mean().to_frame("nota_media_do_juiz")
    resumo["e_o_proprio_juiz"] = resumo.index == juiz_id
    return resumo
