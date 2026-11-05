from datetime import date, timedelta

import pytest

from avaliador.infraestrutura import CotaDiariaEsgotada, LimitadorDeTaxa, LimitesProvedor


class RelogioFalso:
    """Relógio controlado pelo teste: dormir avança o tempo em vez de esperar de verdade."""

    def __init__(self) -> None:
        self.agora = 0.0
        self.dia = date(2026, 11, 4)
        self.esperas: list[float] = []

    def relogio(self) -> float:
        return self.agora

    def dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.agora += segundos

    def hoje(self) -> date:
        return self.dia


@pytest.fixture
def relogio():
    return RelogioFalso()


def _limitador(relogio: RelogioFalso, ja_usadas_hoje: int = 0, **limites) -> LimitadorDeTaxa:
    return LimitadorDeTaxa(
        "groq",
        LimitesProvedor(**limites),
        ja_usadas_hoje=ja_usadas_hoje,
        relogio=relogio.relogio,
        dormir=relogio.dormir,
        hoje=relogio.hoje,
    )


def test_sem_limites_nunca_espera(relogio):
    limitador = _limitador(relogio)

    for _ in range(100):
        limitador.aguardar_vez()

    assert relogio.esperas == []


def test_espera_ao_estourar_o_limite_por_minuto(relogio):
    limitador = _limitador(relogio, requisicoes_por_minuto=2)

    for _ in range(3):
        limitador.aguardar_vez()

    assert relogio.esperas == [60.0]


def test_janela_deslizante_espera_so_o_necessario(relogio):
    limitador = _limitador(relogio, requisicoes_por_minuto=2)

    limitador.aguardar_vez()
    relogio.agora = 30.0
    limitador.aguardar_vez()
    limitador.aguardar_vez()

    assert relogio.esperas == [30.0]


def test_cota_diaria_esgotada(relogio):
    limitador = _limitador(relogio, requisicoes_por_dia=2)
    limitador.aguardar_vez()
    limitador.aguardar_vez()

    with pytest.raises(CotaDiariaEsgotada, match="groq"):
        limitador.aguardar_vez()


def test_considera_o_que_ja_foi_usado_hoje(relogio):
    limitador = _limitador(relogio, ja_usadas_hoje=5, requisicoes_por_dia=5)

    with pytest.raises(CotaDiariaEsgotada):
        limitador.aguardar_vez()


def test_cota_renova_no_dia_seguinte(relogio):
    limitador = _limitador(relogio, requisicoes_por_dia=1)
    limitador.aguardar_vez()

    relogio.dia += timedelta(days=1)
    limitador.aguardar_vez()

    assert limitador.restantes_hoje == 0


def test_restantes_hoje(relogio):
    assert _limitador(relogio).restantes_hoje is None

    limitador = _limitador(relogio, requisicoes_por_dia=10)
    limitador.aguardar_vez()

    assert limitador.restantes_hoje == 9


@pytest.mark.parametrize("limites", [{"requisicoes_por_minuto": 0}, {"requisicoes_por_dia": -1}])
def test_limites_invalidos(limites):
    with pytest.raises(ValueError, match="positivo"):
        LimitesProvedor(**limites)
