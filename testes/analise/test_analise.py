from datetime import date

import numpy as np
import pandas as pd
import pytest

from avaliador.analise import (
    acerto_antes_e_depois_do_corte,
    diferenca_pareada,
    intervalo_bootstrap,
    kappa_quadratico,
    placar,
    relatorio_de_concordancia,
)


class TestEstatistica:
    def test_ic_contem_a_media_e_estreita_com_mais_itens(self):
        pequeno = intervalo_bootstrap({"c": [1, 0] * 10})
        grande = intervalo_bootstrap({"c": [1, 0] * 500})

        assert pequeno[0] == grande[0] == 0.5
        assert pequeno[1] < 0.5 < pequeno[2]
        assert (grande[2] - grande[1]) < (pequeno[2] - pequeno[1])

    def test_media_macro_da_peso_igual_as_categorias(self):
        media, _, _ = intervalo_bootstrap({"grande": [1.0] * 100, "pequena": [0.0] * 2})

        assert media == 0.5

    def test_reprodutivel_com_a_mesma_semente(self):
        assert intervalo_bootstrap({"c": [1, 0, 1]}) == intervalo_bootstrap({"c": [1, 0, 1]})

    def test_diferenca_pareada(self):
        estimativa, inferior, _ = diferenca_pareada([1.0] * 50, [0.0] * 25 + [1.0] * 25)

        assert estimativa == 0.5
        assert inferior > 0

    def test_erros(self):
        with pytest.raises(ValueError):
            intervalo_bootstrap({})
        with pytest.raises(ValueError):
            diferenca_pareada([1, 0], [1])


def _tabela():
    linhas = []
    for numero in range(40):
        for modelo, acerta in (("forte", True), ("fraco", numero % 2 == 0)):
            linhas.append(
                {
                    "modelo": modelo,
                    "item_id": f"q{numero}",
                    "item_base": f"q{numero}",
                    "categoria": "conhecimento" if numero < 20 else "pragmatica",
                    "data_referencia": date(2023 if numero < 10 else 2025, 1, 1),
                    "nota": 1.0 if acerta else 0.0,
                    "situacao": "correta" if acerta else "incorreta",
                }
            )
    linhas.append({**linhas[0], "item_id": "q0~rot1", "situacao": "erro_api", "nota": 0.0})
    return pd.DataFrame(linhas)


class TestPlacar:
    def test_ordem_ic_e_empate(self):
        resultado = placar(_tabela(), reamostragens=500)

        assert list(resultado.index) == ["forte", "fraco"]
        assert resultado.loc["forte", "geral"] == 1.0
        assert resultado.loc["fraco", "geral"] == 0.5
        assert resultado.loc["fraco", "ic_inferior"] < 0.5 < resultado.loc["fraco", "ic_superior"]
        assert not resultado.loc["fraco", "empata_com_lider"]
        assert resultado.loc["forte", "n_itens"] == 40

    def test_erro_de_api_nao_conta_na_media_mas_aparece(self):
        resultado = placar(_tabela(), reamostragens=100)

        assert resultado.loc["forte", "geral"] == 1.0
        assert resultado.loc["forte", "erro_api"] == 1

    def test_tabela_vazia(self):
        assert placar(_tabela().iloc[0:0]).empty


def test_contaminacao_compara_antes_e_depois_do_corte():
    resultado = acerto_antes_e_depois_do_corte(_tabela(), {"fraco": date(2024, 6, 1)})

    linha = resultado.iloc[0]
    assert (linha["n_antes"], linha["n_depois"]) == (10, 30)
    assert linha["acerto_antes"] == 0.5


class TestConcordancia:
    def test_kappa_perfeito_e_ao_acaso(self):
        assert kappa_quadratico([0, 40, 80, 120], [0, 40, 80, 120]) == pytest.approx(1.0)
        aleatorio = np.random.default_rng(0)
        a, b = aleatorio.integers(0, 6, 2000) * 40, aleatorio.integers(0, 6, 2000) * 40
        assert abs(kappa_quadratico(a, b)) < 0.1

    def test_erro_pequeno_pesa_menos_que_erro_grande(self):
        perto = kappa_quadratico([200, 600, 1000], [240, 640, 960])
        longe = kappa_quadratico([200, 600, 1000], [1000, 600, 200])

        assert perto > 0.9 > longe

    def test_relatorio(self):
        relatorio = relatorio_de_concordancia([600, 800, 400], [640, 800, 360])

        assert relatorio["n"] == 3
        assert relatorio["erro_medio_absoluto"] == pytest.approx(80 / 3)
        assert relatorio["spearman"] == pytest.approx(1.0)
