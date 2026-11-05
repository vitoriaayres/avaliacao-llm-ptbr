import pytest

from avaliador.configuracao import ErroDeConfiguracao, carregar_configuracao


@pytest.fixture
def pasta(tmp_path):
    def escrever(provedores="", modelos="", juizes=""):
        (tmp_path / "provedores.yaml").write_text(provedores, encoding="utf-8")
        (tmp_path / "modelos.yaml").write_text(modelos, encoding="utf-8")
        (tmp_path / "juizes.yaml").write_text(juizes, encoding="utf-8")
        return tmp_path

    return escrever


PROVEDORES = """
provedores:
  ollama:
    treina_com_dados: false
  groq:
    variavel_chave: GROQ_API_KEY
    requisicoes_por_minuto: 30
    requisicoes_por_dia: 1000
"""

MODELOS = """
parametros_padrao:
  temperature: 0
  max_tokens: 100
modelos:
  - id: groq/openai/gpt-oss-120b
    nome: GPT-OSS 120B
    parametros:
      max_tokens: 500
  - id: ollama/llama3
"""


def test_carrega_a_configuracao_do_projeto():
    configuracao = carregar_configuracao()

    assert configuracao.modelos
    assert all(configuracao.provedor_de(modelo) for modelo in configuracao.modelos)


def test_le_provedores_e_modelos(pasta):
    configuracao = carregar_configuracao(pasta(PROVEDORES, MODELOS))
    groq = configuracao.provedores["groq"]
    modelo = configuracao.modelo("groq/openai/gpt-oss-120b")

    assert groq.limites.requisicoes_por_dia == 1000
    assert groq.treina_com_dados  # padrão conservador quando o YAML não diz
    assert not configuracao.provedores["ollama"].treina_com_dados
    assert modelo.provedor == "groq"
    assert dict(modelo.parametros) == {"temperature": 0, "max_tokens": 500}
    assert configuracao.modelo("ollama/llama3").nome == "ollama/llama3"


def test_chave_vem_do_ambiente(pasta, monkeypatch):
    configuracao = carregar_configuracao(pasta(PROVEDORES, MODELOS))
    groq = configuracao.provedores["groq"]

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert not groq.disponivel
    monkeypatch.setenv("GROQ_API_KEY", "chave-falsa")
    assert groq.chave == "chave-falsa"
    assert configuracao.provedores["ollama"].disponivel


@pytest.mark.parametrize(
    ("modelos", "mensagem"),
    [
        ("modelos:\n  - id: mistral/large\n", "provedor 'mistral'"),
        ("modelos:\n  - id: ollama/a\n  - id: ollama/a\n", "repetidos"),
        ("modelos:\n  - nome: sem id\n", "sem 'id'"),
        ("modelos: [", "YAML inválido"),
    ],
)
def test_configuracao_invalida(pasta, modelos, mensagem):
    with pytest.raises(ErroDeConfiguracao, match=mensagem):
        carregar_configuracao(pasta(PROVEDORES, modelos))


def test_limite_invalido(pasta):
    provedores = "provedores:\n  groq:\n    requisicoes_por_minuto: 0\n"

    with pytest.raises(ErroDeConfiguracao, match="groq"):
        carregar_configuracao(pasta(provedores))


def test_modelo_desconhecido(pasta):
    configuracao = carregar_configuracao(pasta(PROVEDORES, MODELOS))

    with pytest.raises(ErroDeConfiguracao, match="não está"):
        configuracao.modelo("groq/nao-existe")
