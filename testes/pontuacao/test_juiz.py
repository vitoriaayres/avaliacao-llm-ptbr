from datetime import date

import pytest

from avaliador.configuracao import ConfigModelo, ConfigProvedor
from avaliador.dominio import (
    ERRO_RESPOSTA_VAZIA,
    Categoria,
    Formato,
    Item,
    Resposta,
    Visibilidade,
)
from avaliador.infraestrutura import CacheRespostas
from avaliador.pontuacao import PontuadorJuiz, Situacao, carregar_templates_do_juiz
from avaliador.pontuacao.juiz import (
    AvaliacaoInvalida,
    ler_avaliacao_de_redacao,
    ler_avaliacao_de_resposta_aberta,
)

JUIZ = ConfigModelo("groq/juiz", "Juiz")
REDACAO = Item(
    id="escrita-001",
    categoria=Categoria.ESCRITA,
    formato=Formato.REDACAO,
    enunciado="Desafios da mobilidade urbana",
    fonte="teste",
    data_referencia=date(2026, 11, 4),
)
ABERTA = Item(
    id="conhecimento-001",
    categoria=Categoria.CONHECIMENTO,
    formato=Formato.RESPOSTA_ABERTA,
    enunciado="O que é o SUS?",
    fonte="teste",
    data_referencia=date(2026, 11, 4),
    resposta_referencia="Sistema Único de Saúde, público e universal.",
)
NOTAS_REDACAO = '{"c1": 160, "c2": 120, "c3": 120, "c4": 160, "c5": 80, "justificativa": "ok"}'


class ClienteFalso:
    def __init__(self, texto=NOTAS_REDACAO, erro=None):
        self.texto, self.erro, self.mensagens = texto, erro, []

    def responder(self, modelo, item_id, mensagens, tentativa=1):
        self.mensagens.append(mensagens[0]["content"])
        if self.erro:
            return Resposta(item_id, modelo.id, None, 1.0, tentativa=tentativa, erro=self.erro)
        return Resposta(item_id, modelo.id, self.texto, 1.0, tentativa=tentativa)


def _juiz(cliente, treina=False, cache=None):
    provedor = ConfigProvedor("groq", treina_com_dados=treina)
    return PontuadorJuiz(cliente, JUIZ, provedor, carregar_templates_do_juiz(), cache)


def _resposta(item, texto="Texto do modelo avaliado.", erro=None):
    return Resposta(item.id, "groq/modelo", None if erro else texto, 5.0, erro=erro)


def test_redacao_soma_as_cinco_competencias():
    pontuacao = _juiz(ClienteFalso()).pontuar(REDACAO, _resposta(REDACAO))

    assert pontuacao.nota == pytest.approx(0.64)
    assert pontuacao.detalhes["total"] == 640
    assert pontuacao.detalhes["situacao"] == Situacao.AVALIADA
    assert pontuacao.detalhes["juiz"] == "groq/juiz"


def test_prompt_do_juiz_traz_tema_e_redacao():
    cliente = ClienteFalso()

    _juiz(cliente).pontuar(REDACAO, _resposta(REDACAO, "Minha redação {com chaves}."))

    assert "Desafios da mobilidade urbana" in cliente.mensagens[0]
    assert "Minha redação {com chaves}." in cliente.mensagens[0]


def test_resposta_aberta_usa_a_referencia():
    cliente = ClienteFalso('Avaliação:\n```json\n{"nota": 7, "justificativa": "quase"}\n```')

    pontuacao = _juiz(cliente).pontuar(ABERTA, _resposta(ABERTA))

    assert pontuacao.nota == pytest.approx(0.7)
    assert "Sistema Único de Saúde" in cliente.mensagens[0]


def test_resposta_com_erro_de_api_nao_vai_ao_juiz():
    cliente = ClienteFalso()

    pontuacao = _juiz(cliente).pontuar(REDACAO, _resposta(REDACAO, erro="timeout"))

    assert pontuacao.detalhes["situacao"] == Situacao.ERRO_API
    assert cliente.mensagens == []


@pytest.mark.parametrize(
    ("texto", "erro"),
    [
        ("Nota boa, uns 800.", None),
        ('{"c1": 150, "c2": 120, "c3": 120, "c4": 160, "c5": 80}', None),
        ("", "timeout"),
    ],
)
def test_falhas_do_juiz_viram_erro_juiz(texto, erro):
    pontuacao = _juiz(ClienteFalso(texto or "x", erro)).pontuar(REDACAO, _resposta(REDACAO))

    assert pontuacao.detalhes["situacao"] == Situacao.ERRO_JUIZ
    assert pontuacao.detalhes["motivo"]


def test_item_privado_nao_vai_para_juiz_que_treina_com_os_dados():
    privado = Item(**{**_campos(REDACAO), "visibilidade": Visibilidade.PRIVADO})
    cliente = ClienteFalso()

    pontuacao = _juiz(cliente, treina=True).pontuar(privado, _resposta(privado))

    assert pontuacao.detalhes["situacao"] == Situacao.ERRO_JUIZ
    assert cliente.mensagens == []


def test_avaliacao_vai_para_o_cache(tmp_path):
    with CacheRespostas(tmp_path / "cache.sqlite") as cache:
        primeiro, segundo = ClienteFalso(), ClienteFalso()
        _juiz(primeiro, cache=cache).pontuar(REDACAO, _resposta(REDACAO))
        pontuacao = _juiz(segundo, cache=cache).pontuar(REDACAO, _resposta(REDACAO))

    assert segundo.mensagens == []
    assert pontuacao.detalhes["total"] == 640


def test_leitores_rejeitam_formato_errado():
    with pytest.raises(AvaliacaoInvalida, match="c5"):
        ler_avaliacao_de_redacao('{"c1": 0, "c2": 0, "c3": 0, "c4": 0}')
    with pytest.raises(AvaliacaoInvalida, match="0 a 10"):
        ler_avaliacao_de_resposta_aberta('{"nota": 11}')
    with pytest.raises(AvaliacaoInvalida, match="0 a 10"):
        ler_avaliacao_de_resposta_aberta('{"nota": true}')


def _campos(item):
    return {nome: getattr(item, nome) for nome in item.__slots__}


def test_resposta_vazia_nao_vai_para_o_juiz():
    cliente = ClienteFalso()

    pontuacao = _juiz(cliente).pontuar(REDACAO, _resposta(REDACAO, erro=ERRO_RESPOSTA_VAZIA))

    assert pontuacao.detalhes["situacao"] == Situacao.SEM_RESPOSTA
    assert pontuacao.nota == 0.0
    assert cliente.mensagens == []
