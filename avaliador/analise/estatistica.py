"""Intervalos de confiança por bootstrap: quanto do placar é sinal e quanto é sorte."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np


def intervalo_bootstrap(
    grupos: Mapping[str, Sequence[float]],
    *,
    reamostragens: int = 2000,
    nivel: float = 0.95,
    semente: int = 0,
) -> tuple[float, float, float]:
    """Média macro (cada grupo pesa igual) e IC por percentil.

    Reamostra os itens dentro de cada grupo (categoria), então uma categoria com muitos
    itens não domina a nota geral nem o intervalo.
    """
    arrays = [np.asarray(notas, dtype=float) for notas in grupos.values() if len(notas)]
    if not arrays:
        raise ValueError("sem notas para resumir")
    gerador = np.random.default_rng(semente)
    medias = np.zeros(reamostragens)
    for notas in arrays:
        sorteio = gerador.integers(0, len(notas), size=(reamostragens, len(notas)))
        medias += notas[sorteio].mean(axis=1)
    medias /= len(arrays)
    alfa = (1 - nivel) / 2
    inferior, superior = np.quantile(medias, [alfa, 1 - alfa])
    estimativa = float(np.mean([notas.mean() for notas in arrays]))
    return estimativa, float(inferior), float(superior)


def diferenca_pareada(
    a: Sequence[float], b: Sequence[float], **opcoes: float
) -> tuple[float, float, float]:
    """Diferença média a - b nos mesmos itens, com IC; se o IC não cruza 0, a diferença é real."""
    if len(a) != len(b) or not len(a):
        raise ValueError("as duas listas precisam ter o mesmo tamanho (os mesmos itens)")
    diferencas = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    return intervalo_bootstrap({"diferencas": diferencas}, **opcoes)
