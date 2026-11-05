from datetime import UTC, datetime, timedelta

import pytest

from avaliador.dominio import Resposta, UsoTokens
from avaliador.infraestrutura import CacheRespostas, gerar_chave

MENSAGENS = [{"role": "user", "content": "Qual é a capital do Brasil?"}]


def _resposta(**sobrescritas) -> Resposta:
    campos = dict(
        item_id="conhecimento-teste-001",
        modelo_id="groq/gpt-oss-120b",
        texto="B",
        latencia_ms=320.0,
        uso=UsoTokens(entrada=40, saida=2),
    )
    campos.update(sobrescritas)
    return Resposta(**campos)


@pytest.fixture
def cache(tmp_path):
    with CacheRespostas(tmp_path / "cache.sqlite") as cache:
        yield cache


class TestCacheRespostas:
    def test_guarda_e_recupera(self, cache):
        original = _resposta()
        cache.guardar("chave-1", original)

        recuperada = cache.obter("chave-1")

        assert recuperada.texto == original.texto
        assert recuperada.uso == original.uso
        assert recuperada.veio_do_cache

    def test_chave_inexistente(self, cache):
        assert cache.obter("nao-existe") is None

    def test_persiste_entre_execucoes(self, tmp_path):
        caminho = tmp_path / "cache.sqlite"
        with CacheRespostas(caminho) as primeira_execucao:
            primeira_execucao.guardar("chave-1", _resposta())

        with CacheRespostas(caminho) as segunda_execucao:
            assert segunda_execucao.obter("chave-1") is not None

    def test_recusa_resposta_com_erro(self, cache):
        with pytest.raises(ValueError, match="só respostas com sucesso"):
            cache.guardar("chave-1", _resposta(texto=None, erro="timeout"))

    def test_conta_respostas(self, cache):
        cache.guardar("chave-1", _resposta())
        cache.guardar("chave-2", _resposta(tentativa=2))
        cache.guardar("chave-1", _resposta())

        assert len(cache) == 2

    def test_requisicoes_do_dia_por_provedor(self, cache):
        cache.guardar("chave-1", _resposta(modelo_id="groq/gpt-oss-120b"))
        cache.guardar("chave-2", _resposta(modelo_id="groq/llama-3.3-70b"))
        cache.guardar("chave-3", _resposta(modelo_id="gemini/gemini-flash"))
        hoje = datetime.now(UTC).date()

        assert cache.requisicoes_do_dia("groq/", hoje) == 2
        assert cache.requisicoes_do_dia("groq/", hoje - timedelta(days=1)) == 0


class TestGerarChave:
    def test_ordem_dos_parametros_nao_importa(self):
        a = gerar_chave("m", "i", 1, MENSAGENS, {"temperature": 0, "max_tokens": 10})
        b = gerar_chave("m", "i", 1, MENSAGENS, {"max_tokens": 10, "temperature": 0})

        assert a == b

    @pytest.mark.parametrize(
        "mudanca",
        [
            {"modelo_id": "outro-modelo"},
            {"item_id": "outro-item"},
            {"tentativa": 2},
            {"mensagens": [{"role": "user", "content": "Outra pergunta"}]},
            {"parametros": {"temperature": 0.7}},
        ],
    )
    def test_qualquer_mudanca_gera_outra_chave(self, mudanca):
        base = dict(
            modelo_id="m",
            item_id="i",
            tentativa=1,
            mensagens=MENSAGENS,
            parametros={"temperature": 0},
        )

        assert gerar_chave(**base) != gerar_chave(**{**base, **mudanca})
