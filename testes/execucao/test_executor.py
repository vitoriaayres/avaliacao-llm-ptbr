from datetime import date
from types import MappingProxyType

import pytest

from avaliador.configuracao import ConfigModelo, ConfigProvedor, Configuracao
from avaliador.dominio import Categoria, Formato, Item, Resposta, Visibilidade
from avaliador.execucao import Executor, carregar_templates, ler_respostas
from avaliador.infraestrutura import CacheRespostas, CotaDiariaEsgotada

LOCAL = ConfigModelo("ollama/local", "Local")
NUVEM = ConfigModelo("gemini/flash", "Flash")


class ClienteFalso:
    """Responde 'Resposta: A' e anota as chamadas; pode falhar ou esgotar a cota."""

    def __init__(self, *, erro_em=(), cota_por_provedor=None):
        self.chamadas = []
        self._erro_em = set(erro_em)
        self._cota = dict(cota_por_provedor or {})

    def responder(self, modelo, item_id, mensagens, tentativa=1):
        if modelo.provedor in self._cota:
            if self._cota[modelo.provedor] == 0:
                raise CotaDiariaEsgotada(modelo.provedor, 1)
            self._cota[modelo.provedor] -= 1
        self.chamadas.append((modelo.id, item_id, tentativa))
        if item_id in self._erro_em:
            return Resposta(item_id, modelo.id, None, 5.0, tentativa=tentativa, erro="timeout")
        return Resposta(item_id, modelo.id, "Resposta: A", 5.0, tentativa=tentativa)


def _item(numero, visibilidade=Visibilidade.PUBLICO):
    return Item(
        id=f"item-{numero}",
        categoria=Categoria.CONHECIMENTO,
        formato=Formato.RESPOSTA_ABERTA,
        enunciado=f"Pergunta {numero}?",
        fonte="teste",
        data_referencia=date(2026, 11, 4),
        visibilidade=visibilidade,
    )


ITENS = [_item(1), _item(2), _item(3)]


@pytest.fixture
def configuracao(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-falsa")
    provedores = {
        "ollama": ConfigProvedor("ollama", treina_com_dados=False),
        "gemini": ConfigProvedor("gemini", variavel_chave="GEMINI_API_KEY"),
    }
    return Configuracao(MappingProxyType(provedores), (LOCAL, NUVEM), ())


@pytest.fixture
def cache(tmp_path):
    with CacheRespostas(tmp_path / "cache.sqlite") as cache:
        yield cache


@pytest.fixture
def rodar(configuracao, cache, tmp_path):
    def rodar(cliente, itens=ITENS, modelos=(LOCAL,), repeticoes=1):
        executor = Executor(
            configuracao, cliente, cache, carregar_templates(), repeticoes=repeticoes
        )
        destino = tmp_path / "execucao" / "respostas.jsonl"
        resumo = executor.executar(itens, modelos, destino)
        return resumo, ler_respostas(destino)

    return rodar


def test_responde_e_grava_todas(rodar):
    resumo, respostas = rodar(ClienteFalso())

    assert resumo.respondidas == 3
    assert [r.item_id for r in respostas] == ["item-1", "item-2", "item-3"]
    assert all(r.texto == "Resposta: A" for r in respostas)


def test_segunda_execucao_vem_do_cache(rodar):
    rodar(ClienteFalso())
    cliente = ClienteFalso()

    resumo, respostas = rodar(cliente)

    assert cliente.chamadas == []
    assert resumo.do_cache == 3
    assert all(r.veio_do_cache for r in respostas)


def test_erros_sao_gravados_mas_refeitos_na_proxima_execucao(rodar):
    resumo, respostas = rodar(ClienteFalso(erro_em={"item-2"}))
    assert resumo.com_erro == 1
    assert respostas[1].erro == "timeout"

    cliente = ClienteFalso()
    rodar(cliente)

    assert cliente.chamadas == [("ollama/local", "item-2", 1)]


def test_item_privado_nao_vai_para_provedor_que_treina_com_os_dados(rodar):
    itens = [_item(1), _item(2, Visibilidade.PRIVADO)]
    cliente = ClienteFalso()

    resumo, _ = rodar(cliente, itens=itens, modelos=(LOCAL, NUVEM))

    assert ("gemini/flash", "item-2", 1) not in cliente.chamadas
    assert ("ollama/local", "item-2", 1) in cliente.chamadas
    assert resumo.bloqueadas_por_privacidade == 1


def test_modelo_sem_chave_e_pulado(rodar, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    cliente = ClienteFalso()

    resumo, _ = rodar(cliente, modelos=(NUVEM, LOCAL))

    assert resumo.modelos_sem_chave == ["gemini/flash"]
    assert {modelo for modelo, _, _ in cliente.chamadas} == {"ollama/local"}


def test_cota_esgotada_pula_so_o_provedor_e_mantem_o_cache(rodar):
    rodar(ClienteFalso(), itens=ITENS[:1], modelos=(NUVEM,))  # item-1 já no cache
    cliente = ClienteFalso(cota_por_provedor={"gemini": 1})

    resumo, respostas = rodar(cliente, modelos=(NUVEM, LOCAL))

    assert resumo.provedores_sem_cota == {"gemini"}
    assert resumo.puladas_sem_cota == 1  # item-2 gastou a cota, item-3 ficou para amanhã
    assert [(r.modelo_id, r.item_id) for r in respostas if r.modelo_id == "gemini/flash"] == [
        ("gemini/flash", "item-1"),
        ("gemini/flash", "item-2"),
    ]
    assert sum(r.modelo_id == "ollama/local" for r in respostas) == 3


def test_repeticoes_geram_tentativas_distintas(rodar):
    cliente = ClienteFalso()

    rodar(cliente, itens=ITENS[:1], repeticoes=3)

    assert [tentativa for _, _, tentativa in cliente.chamadas] == [1, 2, 3]


def test_repeticoes_invalidas(configuracao, cache):
    with pytest.raises(ValueError, match="repeticoes"):
        Executor(configuracao, ClienteFalso(), cache, {}, repeticoes=0)
