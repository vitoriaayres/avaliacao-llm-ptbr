"""Sinal de contaminação: o modelo vai melhor em itens anteriores ao fim do seu treino?"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pandas as pd

from avaliador.pontuacao import SITUACOES_FORA_DA_MEDIA


def acerto_antes_e_depois_do_corte(
    tabela: pd.DataFrame, datas_de_corte: Mapping[str, date]
) -> pd.DataFrame:
    """Acerto em itens publicados antes e depois da data de corte de cada modelo.

    Acerto bem maior "antes" sugere que o modelo viu as questões no treino. Não é prova:
    as provas de anos diferentes também mudam de dificuldade.
    """
    validas = tabela[~tabela["situacao"].isin(SITUACOES_FORA_DA_MEDIA)]
    linhas = []
    for modelo, corte in datas_de_corte.items():
        dados = validas[validas["modelo"] == modelo]
        if dados.empty:
            continue
        antes = dados.loc[dados["data_referencia"] < corte, "nota"]
        depois = dados.loc[dados["data_referencia"] >= corte, "nota"]
        linhas.append(
            {
                "modelo": modelo,
                "data_corte": corte,
                "acerto_antes": antes.mean() if len(antes) else None,
                "n_antes": len(antes),
                "acerto_depois": depois.mean() if len(depois) else None,
                "n_depois": len(depois),
            }
        )
    return pd.DataFrame(linhas)
