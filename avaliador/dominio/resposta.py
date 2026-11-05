"""Resposta de um modelo a um item."""

from __future__ import annotations

from dataclasses import dataclass

# O provedor atendeu, mas o modelo não entregou texto (ex.: raciocinou até o limite de tokens).
ERRO_RESPOSTA_VAZIA = "resposta sem texto"


@dataclass(frozen=True, slots=True)
class UsoTokens:
    entrada: int = 0
    saida: int = 0

    def __post_init__(self) -> None:
        if self.entrada < 0 or self.saida < 0:
            raise ValueError("contagem de tokens não pode ser negativa")


@dataclass(frozen=True, slots=True)
class Resposta:
    """Resultado de uma chamada: ou tem texto, ou tem erro, nunca os dois."""

    item_id: str
    modelo_id: str
    texto: str | None
    latencia_ms: float
    uso: UsoTokens = UsoTokens()
    tentativa: int = 1
    erro: str | None = None
    veio_do_cache: bool = False

    def __post_init__(self) -> None:
        if (self.texto is None) == (self.erro is None):
            raise ValueError(f"{self.item_id}/{self.modelo_id}: informe texto OU erro")
        if self.latencia_ms < 0:
            raise ValueError("latência não pode ser negativa")
        if self.tentativa < 1:
            raise ValueError("tentativa começa em 1")

    @property
    def sucesso(self) -> bool:
        return self.erro is None

    @property
    def vazia(self) -> bool:
        return self.erro == ERRO_RESPOSTA_VAZIA
