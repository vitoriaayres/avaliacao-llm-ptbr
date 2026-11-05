"""Logging padronizado do projeto."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

FORMATO = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"
_NOME_MANIPULADOR = "avaliador"


def configurar_registro(
    nivel: int | str = logging.INFO, arquivo: Path | None = None
) -> logging.Logger:
    """Configura o logger raiz do projeto; chamar de novo substitui a configuração anterior."""
    registrador = logging.getLogger("avaliador")
    registrador.setLevel(nivel)
    _remover_manipuladores_anteriores(registrador)

    manipuladores: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if arquivo is not None:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        manipuladores.append(logging.FileHandler(arquivo, encoding="utf-8"))

    formatador = logging.Formatter(FORMATO, FORMATO_DATA)
    for manipulador in manipuladores:
        manipulador.set_name(_NOME_MANIPULADOR)
        manipulador.setFormatter(formatador)
        registrador.addHandler(manipulador)
    return registrador


def _remover_manipuladores_anteriores(registrador: logging.Logger) -> None:
    for manipulador in list(registrador.handlers):
        if manipulador.get_name() == _NOME_MANIPULADOR:
            registrador.removeHandler(manipulador)
            manipulador.close()
