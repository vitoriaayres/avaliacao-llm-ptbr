"""Painel do benchmark. Rode a partir da raiz do projeto: streamlit run painel/app.py"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from avaliador.analise.graficos import grafico_categorias, grafico_placar
from avaliador.dominio import Categoria
from avaliador.ferramentas.leaderboard import NOME_ARQUIVO_LEADERBOARD, ler_leaderboard

RAIZ = Path(__file__).resolve().parents[1]
PADRAO = RAIZ / "resultados" / "publicados" / NOME_ARQUIVO_LEADERBOARD
CAMINHO = Path(os.environ.get("LEADERBOARD", PADRAO))

st.set_page_config(page_title="LLMs em português brasileiro", layout="wide")
st.title("Avaliação de LLMs em português brasileiro")

if not CAMINHO.exists():
    st.info("Nenhum leaderboard publicado ainda. Rode `avaliador exportar <execucao>`.")
    st.stop()

dados, placar = ler_leaderboard(CAMINHO)
total_itens = sum(dados["itens_por_categoria"].values())
st.caption(
    f"Execução `{dados['execucao']}` · {total_itens} itens · {len(placar)} modelos · "
    f"gerado em {dados['gerado_em']}"
)

lider = placar.iloc[0]
colunas = st.columns(3)
colunas[0].metric("Líder", placar.index[0])
colunas[1].metric("Nota do líder", f"{lider['geral'] * 100:.1f}%")
colunas[2].metric(
    "Empatados com o líder", int(placar["empata_com_lider"].sum()),
    help="Modelos cuja diferença para o 1º lugar cabe no intervalo de confiança.",
)

st.subheader("Placar geral")
st.caption(
    "Média das categorias, cada uma com o mesmo peso. A linha é o intervalo de confiança de 95%."
)
st.altair_chart(grafico_placar(placar), use_container_width=True)

st.subheader("Por categoria")
st.altair_chart(grafico_categorias(placar, [c.value for c in Categoria]), use_container_width=True)

st.subheader("Tabela")
tabela = placar.copy()
porcentagens = [c for c in tabela.columns if c not in ("n_itens", "empata_com_lider")]
tabela[porcentagens] = (tabela[porcentagens] * 100).round(1)
st.dataframe(tabela, use_container_width=True)

st.markdown(
    "Itens por categoria: "
    + ", ".join(f"{categoria}: {n}" for categoria, n in dados["itens_por_categoria"].items())
    + ". Metodologia completa no `METODOLOGIA.md` do repositório."
)
