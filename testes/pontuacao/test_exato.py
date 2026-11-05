from datetime import date

import pytest

from avaliador.dominio import (
    ERRO_RESPOSTA_VAZIA,
    Alternativa,
    Categoria,
    Formato,
    Item,
    Resposta,
)
from avaliador.pontuacao import PontuadorExato, Situacao, pontuar_respostas

MULTIPLA = Item(
    id="conhecimento-001",
    categoria=Categoria.CONHECIMENTO,
    formato=Formato.MULTIPLA_ESCOLHA,
    enunciado="Quem aplica o ENEM?",
    fonte="teste",
    data_referencia=date(2026, 11, 4),
    alternativas=(Alternativa("A", "MEC"), Alternativa("B", "INEP")),
    resposta_correta="B",
)
CLASSIFICACAO = Item(
    id="pragmatica-001",
    categoria=Categoria.PRAGMATICA,
    formato=Formato.CLASSIFICACAO,
    enunciado="Que atendimento rápido, hein?",
    fonte="teste",
    data_referencia=date(2026, 11, 4),
    rotulos=("irônica", "literal"),
    resposta_correta="irônica",
)
ABERTA = Item(
    id="conhecimento-002",
    categoria=Categoria.CONHECIMENTO,
    formato=Formato.RESPOSTA_ABERTA,
    enunciado="Explique o que é o SUS.",
    fonte="teste",
    data_referencia=date(2026, 11, 4),
)


def _resposta(item, texto=None, erro=None, tentativa=1):
    return Resposta(item.id, "groq/modelo", texto, 10.0, tentativa=tentativa, erro=erro)


@pytest.mark.parametrize(
    ("item", "texto", "situacao", "nota"),
    [
        (MULTIPLA, "Resposta: B", Situacao.CORRETA, 1.0),
        (MULTIPLA, "Resposta: A", Situacao.INCORRETA, 0.0),
        (MULTIPLA, "Não sei responder.", Situacao.SEM_RESPOSTA, 0.0),
        (CLASSIFICACAO, "Resposta: Irônica", Situacao.CORRETA, 1.0),
        (CLASSIFICACAO, "Resposta: literal", Situacao.INCORRETA, 0.0),
    ],
)
def test_pontua_pela_opcao_extraida(item, texto, situacao, nota):
    pontuacao = PontuadorExato().pontuar(item, _resposta(item, texto))

    assert pontuacao.detalhes["situacao"] == situacao
    assert pontuacao.nota == nota
    assert pontuacao.detalhes["gabarito"] == item.resposta_correta
    assert pontuacao.pontuador == "exato"


def test_erro_de_api_fica_marcado():
    pontuacao = PontuadorExato().pontuar(MULTIPLA, _resposta(MULTIPLA, erro="timeout"))

    assert pontuacao.detalhes["situacao"] == Situacao.ERRO_API
    assert pontuacao.detalhes["extraida"] is None


def test_resposta_vazia_conta_como_falha_do_modelo():
    pontuacao = PontuadorExato().pontuar(MULTIPLA, _resposta(MULTIPLA, erro=ERRO_RESPOSTA_VAZIA))

    assert pontuacao.detalhes["situacao"] == Situacao.SEM_RESPOSTA
    assert pontuacao.nota == 0.0


def test_mantem_a_tentativa():
    pontuacao = PontuadorExato().pontuar(MULTIPLA, _resposta(MULTIPLA, "B", tentativa=3))

    assert pontuacao.tentativa == 3


def test_pontuar_respostas_separa_o_que_nao_tem_pontuador_ou_item():
    exato = PontuadorExato()
    respostas = [
        _resposta(MULTIPLA, "Resposta: B"),
        _resposta(CLASSIFICACAO, "Resposta: irônica"),
        _resposta(ABERTA, "O SUS é..."),
        Resposta("item-apagado", "groq/modelo", "B", 1.0),
    ]

    resultado = pontuar_respostas(
        [MULTIPLA, CLASSIFICACAO, ABERTA],
        respostas,
        {Formato.MULTIPLA_ESCOLHA: exato, Formato.CLASSIFICACAO: exato},
    )

    assert [p.item_id for p in resultado.pontuacoes] == ["conhecimento-001", "pragmatica-001"]
    assert resultado.sem_pontuador == 1
    assert resultado.ids_sem_item == ("item-apagado",)
