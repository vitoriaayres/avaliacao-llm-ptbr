"""Leaderboard publicável: só números agregados, nenhum texto de item ou resposta."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from avaliador.dominio import Categoria

PASTA_PUBLICADOS = Path("resultados") / "publicados"
NOME_ARQUIVO_LEADERBOARD = "leaderboard.json"
_COLUNAS_FIXAS = ("geral", "ic_inferior", "ic_superior", "n_itens", "empata_com_lider")


def montar_leaderboard(
    placar: pd.DataFrame,
    *,
    execucao: str,
    itens_por_categoria: Mapping[str, int],
    nomes: Mapping[str, str],
) -> dict[str, Any]:
    categorias = [c.value for c in Categoria if c.value in placar.columns]
    modelos = []
    for posicao, (modelo, linha) in enumerate(placar.iterrows(), start=1):
        modelos.append(
            {
                "posicao": posicao,
                "modelo": modelo,
                "nome": nomes.get(modelo, modelo),
                "geral": _numero(linha["geral"]),
                "ic_inferior": _numero(linha["ic_inferior"]),
                "ic_superior": _numero(linha["ic_superior"]),
                "n_itens": int(linha["n_itens"]),
                "empata_com_lider": bool(linha["empata_com_lider"]),
                "categorias": {c: _numero(linha[c]) for c in categorias},
            }
        )
    return {
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "execucao": execucao,
        "itens_por_categoria": dict(itens_por_categoria),
        "modelos": modelos,
    }


def _numero(valor: Any) -> float | None:
    return None if valor is None or math.isnan(valor) else round(float(valor), 4)


def salvar_leaderboard(leaderboard: Mapping[str, Any], pasta: Path = PASTA_PUBLICADOS) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / NOME_ARQUIVO_LEADERBOARD
    destino.write_text(json.dumps(leaderboard, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


def ler_leaderboard(caminho: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    """O JSON e o placar de volta como DataFrame (mesmas colunas do analise.placar)."""
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    linhas = [
        {"modelo": m["nome"], **{c: m[c] for c in _COLUNAS_FIXAS}, **m["categorias"]}
        for m in dados["modelos"]
    ]
    return dados, pd.DataFrame(linhas).set_index("modelo")
