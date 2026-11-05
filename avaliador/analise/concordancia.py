"""Concordância entre avaliadores: valida o juiz contra notas humanas (ou outro juiz)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def kappa_quadratico(a: Sequence[float], b: Sequence[float]) -> float:
    """Kappa de Cohen com pesos quadráticos: 1 = concordância total, 0 = igual ao acaso.

    Errar 600 por 640 pesa pouco; errar 200 por 1000 pesa muito.
    """
    a_array, b_array = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if len(a_array) != len(b_array) or not len(a_array):
        raise ValueError("as duas listas precisam ter o mesmo tamanho e não podem ser vazias")
    valores = np.unique(np.concatenate([a_array, b_array]))
    if len(valores) == 1:
        return 1.0
    posicao = {valor: indice for indice, valor in enumerate(valores)}
    observada = np.zeros((len(valores), len(valores)))
    for x, y in zip(a_array, b_array, strict=True):
        observada[posicao[x], posicao[y]] += 1
    observada /= observada.sum()
    esperada = np.outer(observada.sum(axis=1), observada.sum(axis=0))
    pesos = np.subtract.outer(valores, valores) ** 2
    return float(1 - (pesos * observada).sum() / (pesos * esperada).sum())


def relatorio_de_concordancia(humano: Sequence[float], juiz: Sequence[float]) -> dict[str, float]:
    humano_serie, juiz_serie = pd.Series(humano, dtype=float), pd.Series(juiz, dtype=float)
    return {
        "n": len(humano_serie),
        "kappa_quadratico": kappa_quadratico(humano_serie, juiz_serie),
        # Spearman = Pearson dos postos; assim não precisa do scipy.
        "spearman": float(humano_serie.rank().corr(juiz_serie.rank())),
        "erro_medio_absoluto": float((humano_serie - juiz_serie).abs().mean()),
        "concordancia_exata": float((humano_serie == juiz_serie).mean()),
    }
