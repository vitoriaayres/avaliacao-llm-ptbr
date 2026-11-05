from datetime import date

import pandas as pd
import pytest

from avaliador.dominio import Alternativa, Categoria, Formato, Item
from avaliador.pontuacao import (
    com_variantes,
    id_base,
    reconstruir_variantes,
    rotacionar_alternativas,
)
from avaliador.pontuacao.vies import (
    consistencia_entre_variantes,
    preferencia_propria,
    vies_de_posicao,
)

ITEM = Item(
    id="conhecimento-001",
    categoria=Categoria.CONHECIMENTO,
    formato=Formato.MULTIPLA_ESCOLHA,
    enunciado="Quem aplica o ENEM?",
    fonte="teste",
    data_referencia=date(2026, 11, 4),
    alternativas=tuple(
        Alternativa(letra, texto)
        for letra, texto in zip("ABCDE", ["MEC", "INEP", "CAPES", "CNPq", "FNDE"], strict=True)
    ),
    resposta_correta="B",
)


def test_rotacao_move_o_gabarito_junto_com_o_texto():
    variante = rotacionar_alternativas(ITEM, 1)

    assert variante.id == "conhecimento-001~rot1"
    assert [a.texto for a in variante.alternativas] == ["FNDE", "MEC", "INEP", "CAPES", "CNPq"]
    assert variante.resposta_correta == "C"
    assert variante.alternativas[2].texto == "INEP"
    assert variante.metadados["variante_de"] == ITEM.id


def test_quatro_rotacoes_cobrem_todas_as_letras():
    letras = {rotacionar_alternativas(ITEM, k).resposta_correta for k in range(1, 5)}

    assert letras == {"A", "C", "D", "E"}


def test_rotacao_nula_e_formato_errado_sao_recusados():
    with pytest.raises(ValueError, match="no lugar"):
        rotacionar_alternativas(ITEM, 5)
    aberta = Item(
        id="x", categoria=Categoria.CONHECIMENTO, formato=Formato.RESPOSTA_ABERTA,
        enunciado="?", fonte="t", data_referencia=date(2026, 1, 1),
    )
    with pytest.raises(ValueError, match="múltipla escolha"):
        rotacionar_alternativas(aberta, 1)


def test_com_variantes_e_reconstrucao():
    expandidos = com_variantes([ITEM], 2)

    assert [i.id for i in expandidos] == [
        "conhecimento-001",
        "conhecimento-001~rot1",
        "conhecimento-001~rot2",
    ]
    reconstruidos = reconstruir_variantes([ITEM], ["conhecimento-001~rot2", "outro~rot1"])
    assert [i.id for i in reconstruidos] == ["conhecimento-001", "conhecimento-001~rot2"]
    assert id_base("conhecimento-001~rot2") == "conhecimento-001"


def _tabela(linhas):
    colunas = [
        "modelo", "item_id", "item_base", "formato", "nota", "situacao", "extraida", "gabarito"
    ]
    return pd.DataFrame(linhas, columns=colunas)


def test_consistencia_entre_variantes():
    tabela = _tabela(
        [
            ("m1", "q1", "q1", "multipla_escolha", 1.0, "correta", "B", "B"),
            ("m1", "q1~rot1", "q1", "multipla_escolha", 1.0, "correta", "C", "C"),
            ("m2", "q1", "q1", "multipla_escolha", 1.0, "correta", "B", "B"),
            ("m2", "q1~rot1", "q1", "multipla_escolha", 0.0, "incorreta", "B", "C"),
        ]
    )

    assert consistencia_entre_variantes(tabela).to_dict() == {"m1": 1.0, "m2": 0.0}


def test_vies_de_posicao():
    tabela = _tabela(
        [
            ("m1", "q1", "q1", "multipla_escolha", 0.0, "incorreta", "A", "B"),
            ("m1", "q2", "q2", "multipla_escolha", 1.0, "correta", "A", "A"),
        ]
    )

    resultado = vies_de_posicao(tabela)

    assert resultado.loc["m1", "A"] == 100.0
    assert resultado.loc["(gabarito)", "B"] == 50.0


def test_preferencia_propria():
    tabela = _tabela(
        [
            ("juiz", "r1", "r1", "redacao", 0.9, "avaliada", None, None),
            ("outro", "r1", "r1", "redacao", 0.6, "avaliada", None, None),
        ]
    )

    resultado = preferencia_propria(tabela, "juiz")

    assert resultado.loc["juiz", "e_o_proprio_juiz"]
    assert not resultado.loc["outro", "e_o_proprio_juiz"]
