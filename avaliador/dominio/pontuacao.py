"""Nota atribuída a uma resposta por um pontuador."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class Pontuacao:
    """Nota normalizada entre 0 e 1; a escala original fica em `detalhes`.

    Exemplo: redação nota 840/1000 -> nota=0.84, detalhes={"total": 840, "c1": 160, ...}
    """

    item_id: str
    modelo_id: str
    pontuador: str
    nota: float
    tentativa: int = 1
    detalhes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.nota <= 1.0:
            raise ValueError(f"nota deve estar entre 0 e 1, recebido {self.nota}")
        object.__setattr__(self, "detalhes", MappingProxyType(dict(self.detalhes)))
