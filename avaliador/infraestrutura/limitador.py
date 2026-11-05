"""Controle de taxa por provedor: requisições por minuto e por dia."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

JANELA_SEGUNDOS = 60.0


class CotaDiariaEsgotada(Exception):
    """A cota do dia acabou: esperar alguns segundos não resolve."""

    def __init__(self, provedor: str, limite: int) -> None:
        super().__init__(f"{provedor}: cota diária de {limite} requisições esgotada")
        self.provedor = provedor
        self.limite = limite


@dataclass(frozen=True, slots=True)
class LimitesProvedor:
    requisicoes_por_minuto: int | None = None
    requisicoes_por_dia: int | None = None

    def __post_init__(self) -> None:
        for nome in ("requisicoes_por_minuto", "requisicoes_por_dia"):
            valor = getattr(self, nome)
            if valor is not None and valor < 1:
                raise ValueError(f"{nome} deve ser positivo, recebido {valor}")


def _hoje_utc() -> date:
    return datetime.now(UTC).date()


class LimitadorDeTaxa:
    """Faz cada chamada esperar o necessário para não estourar os limites do provedor.

    Por minuto: janela deslizante, conta as requisições dos últimos 60 segundos.
    Por dia: não espera; lança CotaDiariaEsgotada e o executor decide pular o provedor.
    """

    def __init__(
        self,
        provedor: str,
        limites: LimitesProvedor,
        *,
        ja_usadas_hoje: int = 0,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
        hoje: Callable[[], date] = _hoje_utc,
    ) -> None:
        self.provedor = provedor
        self._limites = limites
        self._relogio = relogio
        self._dormir = dormir
        self._hoje = hoje
        self._dia = hoje()
        self._usadas_hoje = ja_usadas_hoje
        self._recentes: deque[float] = deque()
        self._trava = threading.Lock()

    @property
    def restantes_hoje(self) -> int | None:
        if self._limites.requisicoes_por_dia is None:
            return None
        with self._trava:
            self._renovar_se_mudou_o_dia()
            return max(self._limites.requisicoes_por_dia - self._usadas_hoje, 0)

    def aguardar_vez(self) -> None:
        with self._trava:
            self._renovar_se_mudou_o_dia()
            self._exigir_cota_diaria()
            espera = self._espera_necessaria()
            if espera > 0:
                self._dormir(espera)
            self._recentes.append(self._relogio())
            self._usadas_hoje += 1

    def _renovar_se_mudou_o_dia(self) -> None:
        hoje = self._hoje()
        if hoje != self._dia:
            self._dia = hoje
            self._usadas_hoje = 0

    def _exigir_cota_diaria(self) -> None:
        limite = self._limites.requisicoes_por_dia
        if limite is not None and self._usadas_hoje >= limite:
            raise CotaDiariaEsgotada(self.provedor, limite)

    def _espera_necessaria(self) -> float:
        limite = self._limites.requisicoes_por_minuto
        if limite is None:
            return 0.0
        agora = self._relogio()
        while self._recentes and self._recentes[0] <= agora - JANELA_SEGUNDOS:
            self._recentes.popleft()
        if len(self._recentes) < limite:
            return 0.0
        return self._recentes[0] + JANELA_SEGUNDOS - agora
