from types import SimpleNamespace

import httpx
import litellm
import pytest

from avaliador.configuracao import ConfigModelo, ConfigProvedor
from avaliador.dominio import Resposta, UsoTokens
from avaliador.infraestrutura import (
    CacheRespostas,
    CotaDiariaEsgotada,
    LimitadorDeTaxa,
    LimitesProvedor,
)
from avaliador.provedores import ClienteLLM, criar_limitadores, eh_transitorio

MODELO = ConfigModelo("groq/openai/gpt-oss-120b", "GPT-OSS", {"temperature": 0})
MENSAGENS = [{"role": "user", "content": "Qual é a capital do Brasil?"}]


def _bruta(texto="Resposta: B", entrada=12, saida=3):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=texto))],
        usage=SimpleNamespace(prompt_tokens=entrada, completion_tokens=saida),
    )


def _limite_de_taxa(retry_after=None):
    cabecalhos = {"retry-after": retry_after} if retry_after else {}
    resposta = httpx.Response(429, headers=cabecalhos, request=httpx.Request("POST", "http://x"))
    return litellm.RateLimitError(
        "muitas requisições", llm_provider="groq", model="m", response=resposta
    )


def _chave_errada():
    return litellm.AuthenticationError("chave inválida", llm_provider="groq", model="m")


class CompletarFalso:
    """Devolve (ou lança) as saídas na ordem e guarda os argumentos de cada chamada."""

    def __init__(self, *saidas):
        self.saidas = list(saidas)
        self.chamadas = []

    def __call__(self, **argumentos):
        self.chamadas.append(argumentos)
        saida = self.saidas.pop(0)
        if isinstance(saida, Exception):
            raise saida
        return saida


def _cliente(completar, limites=None, esperas=None):
    limites = limites or LimitesProvedor()
    provedores = {"groq": ConfigProvedor("groq", limites, variavel_chave="GROQ_API_KEY")}
    return ClienteLLM(
        provedores,
        {"groq": LimitadorDeTaxa("groq", limites, dormir=lambda _: None)},
        completar=completar,
        dormir=(esperas.append if esperas is not None else lambda _: None),
    )


def test_resposta_com_sucesso(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "chave-falsa")
    completar = CompletarFalso(_bruta())

    resposta = _cliente(completar).responder(MODELO, "item-1", MENSAGENS, tentativa=2)

    assert resposta.texto == "Resposta: B"
    assert resposta.uso == UsoTokens(12, 3)
    assert resposta.tentativa == 2
    assert resposta.latencia_ms >= 0
    chamada = completar.chamadas[0]
    assert chamada["model"] == MODELO.id
    assert chamada["api_key"] == "chave-falsa"
    assert chamada["temperature"] == 0
    assert chamada["messages"] == MENSAGENS


def test_refaz_erro_transitorio_com_espera_crescente():
    esperas = []
    completar = CompletarFalso(_limite_de_taxa(), _limite_de_taxa(), _bruta())

    resposta = _cliente(completar, esperas=esperas).responder(MODELO, "item-1", MENSAGENS)

    assert resposta.sucesso
    assert esperas == [2.0, 4.0]


@pytest.mark.parametrize(
    ("retry_after", "espera"),
    [("17", 17.0), ("1", 2.0), ("3600", 60.0), ("Wed, 21 Oct 2026 07:28:00 GMT", 2.0)],
)
def test_respeita_o_retry_after_do_provedor(retry_after, espera):
    esperas = []
    completar = CompletarFalso(_limite_de_taxa(retry_after), _bruta())

    _cliente(completar, esperas=esperas).responder(MODELO, "item-1", MENSAGENS)

    assert esperas == [espera]


def test_desiste_depois_do_maximo_de_retentativas():
    completar = CompletarFalso(*[_limite_de_taxa() for _ in range(4)])

    resposta = _cliente(completar).responder(MODELO, "item-1", MENSAGENS)

    assert not resposta.sucesso
    assert "RateLimitError" in resposta.erro
    assert len(completar.chamadas) == 4


def test_erro_permanente_nao_e_refeito():
    completar = CompletarFalso(_chave_errada())

    resposta = _cliente(completar).responder(MODELO, "item-1", MENSAGENS)

    assert "AuthenticationError" in resposta.erro
    assert len(completar.chamadas) == 1


def test_resposta_vazia_vira_erro():
    resposta = _cliente(CompletarFalso(_bruta(texto=""))).responder(MODELO, "item-1", MENSAGENS)

    assert resposta.erro == "resposta sem texto"


def test_bug_fora_do_provedor_nao_e_engolido():
    with pytest.raises(KeyError):
        _cliente(CompletarFalso(KeyError("bug"))).responder(MODELO, "item-1", MENSAGENS)


def test_cota_diaria_esgotada_sobe_para_o_executor():
    cliente = _cliente(CompletarFalso(_bruta()), LimitesProvedor(requisicoes_por_dia=1))
    cliente.responder(MODELO, "item-1", MENSAGENS)

    with pytest.raises(CotaDiariaEsgotada):
        cliente.responder(MODELO, "item-2", MENSAGENS)


def test_classificacao_dos_erros():
    assert eh_transitorio(_limite_de_taxa())
    assert not eh_transitorio(_chave_errada())


def test_modelo_com_limite_proprio_espera_alem_do_provedor():
    lento = ConfigModelo("groq/lento", "Lento", requisicoes_por_minuto=1)
    provedores = {"groq": ConfigProvedor("groq", LimitesProvedor(requisicoes_por_minuto=30))}
    limitadores = criar_limitadores(provedores, modelos=[lento, MODELO])
    esperas = []
    limitadores[lento.id] = LimitadorDeTaxa(
        lento.id, LimitesProvedor(requisicoes_por_minuto=1), relogio=lambda: 0.0,
        dormir=esperas.append,
    )
    cliente = ClienteLLM(
        provedores, limitadores, completar=CompletarFalso(_bruta(), _bruta(), _bruta())
    )

    cliente.responder(lento, "item-1", MENSAGENS)
    cliente.responder(lento, "item-2", MENSAGENS)
    cliente.responder(MODELO, "item-3", MENSAGENS)  # sem limite próprio: não espera

    assert MODELO.id not in limitadores
    assert esperas == [60.0]


def test_limitadores_descontam_o_que_o_cache_ja_registrou_hoje(tmp_path):
    provedores = {"groq": ConfigProvedor("groq", LimitesProvedor(requisicoes_por_dia=10))}
    with CacheRespostas(tmp_path / "cache.sqlite") as cache:
        cache.guardar("chave", Resposta("item-1", MODELO.id, "B", latencia_ms=1.0))

        limitadores = criar_limitadores(provedores, cache)

    assert limitadores["groq"].restantes_hoje == 9
