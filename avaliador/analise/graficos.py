"""Gráficos do placar (Altair). Requer o extra `painel`: pip install -e ".[painel]"."""

from __future__ import annotations

from collections.abc import Sequence

import altair as alt
import pandas as pd


def grafico_placar(placar: pd.DataFrame) -> alt.LayerChart:
    """Barras com a nota geral e uma linha com o intervalo de confiança de 95%."""
    dados = placar.reset_index()[["modelo", "geral", "ic_inferior", "ic_superior"]].copy()
    dados[["geral", "ic_inferior", "ic_superior"]] *= 100
    base = alt.Chart(dados).encode(y=alt.Y("modelo:N", sort="-x", title=None))
    barras = base.mark_bar().encode(
        x=alt.X(
            "geral:Q",
            title="% de acerto (média das categorias)",
            scale=alt.Scale(domain=[0, 100]),
        ),
        tooltip=[
            alt.Tooltip("modelo:N"),
            alt.Tooltip("geral:Q", format=".1f", title="nota"),
            alt.Tooltip("ic_inferior:Q", format=".1f", title="IC 95% de"),
            alt.Tooltip("ic_superior:Q", format=".1f", title="IC 95% até"),
        ],
    )
    intervalo = base.mark_rule(strokeWidth=2).encode(x="ic_inferior:Q", x2="ic_superior:Q")
    return barras + intervalo


def grafico_categorias(placar: pd.DataFrame, categorias: Sequence[str]) -> alt.Chart:
    """Mapa de calor modelo x categoria."""
    presentes = [categoria for categoria in categorias if categoria in placar.columns]
    dados = placar[presentes].mul(100).reset_index().melt(
        id_vars="modelo", var_name="categoria", value_name="acerto"
    )
    return (
        alt.Chart(dados)
        .mark_rect()
        .encode(
            x=alt.X("categoria:N", title=None),
            y=alt.Y("modelo:N", title=None),
            color=alt.Color("acerto:Q", scale=alt.Scale(domain=[0, 100]), title="% de acerto"),
            tooltip=["modelo:N", "categoria:N", alt.Tooltip("acerto:Q", format=".1f")],
        )
    )
