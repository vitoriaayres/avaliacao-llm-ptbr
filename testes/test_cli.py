import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from avaliador import cli
from avaliador.dominio import Resposta
from avaliador.infraestrutura import configurar_registro

DADOS_DO_PROJETO = Path(__file__).resolve().parents[1] / "dados"
MODELO_LOCAL = "ollama/deepseek-coder:6.7b"


@pytest.fixture(autouse=True)
def isolar(tmp_path, monkeypatch):
    """Roda cada teste numa pasta vazia, sem .env e com um cliente que não acessa a rede."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda *_: None)

    class ClienteFalso:
        def __init__(self, *_):
            pass

        def responder(self, modelo, item_id, mensagens, tentativa=1):
            return Resposta(item_id, modelo.id, "Resposta: B", 1.0, tentativa=tentativa)

    monkeypatch.setattr(cli, "ClienteLLM", ClienteFalso)
    yield
    configurar_registro()


@pytest.fixture
def dados_exemplo(tmp_path):
    """Só os itens de exemplo versionados: o teste não depende do que foi gerado localmente."""
    destino = tmp_path / "dados_exemplo"
    for arquivo in DADOS_DO_PROJETO.glob("*/*/exemplos.jsonl"):
        copia = destino / arquivo.relative_to(DADOS_DO_PROJETO)
        copia.parent.mkdir(parents=True, exist_ok=True)
        copia.write_bytes(arquivo.read_bytes())
    return destino


def _rodar(*argumentos):
    return CliRunner().invoke(cli.app, list(argumentos))


def test_validar_dataset_do_projeto(dados_exemplo):
    resultado = _rodar("validar", "--dados", str(dados_exemplo))

    assert resultado.exit_code == 0, resultado.output
    assert "conhecimento" in resultado.output


def test_validar_dataset_invalido(tmp_path):
    pasta = tmp_path / "dados" / "publico" / "conhecimento"
    pasta.mkdir(parents=True)
    (pasta / "ruim.jsonl").write_text('{"id": "x"}\n', encoding="utf-8")

    assert _rodar("validar", "--dados", str(tmp_path / "dados")).exit_code == 1


def test_modelos_lista_o_que_esta_configurado():
    resultado = _rodar("modelos")

    assert resultado.exit_code == 0, resultado.output
    assert MODELO_LOCAL in resultado.output


def test_executar_grava_respostas(tmp_path, dados_exemplo):
    resultado = _rodar(
        "executar", "-m", MODELO_LOCAL, "-c", "conhecimento",
        "--nome", "teste", "--dados", str(dados_exemplo),
    )

    assert resultado.exit_code == 0, resultado.output
    linhas = (tmp_path / "resultados" / "teste" / "respostas.jsonl").read_text(encoding="utf-8")
    respostas = [json.loads(linha) for linha in linhas.splitlines()]
    assert {r["item_id"] for r in respostas} == {"conhecimento-exemplo-001"}
    assert "1 respostas" in resultado.output


def test_pontuar_depois_de_executar(tmp_path, dados_exemplo):
    _rodar("executar", "-m", MODELO_LOCAL, "--nome", "teste", "--dados", str(dados_exemplo))

    resultado = _rodar("pontuar", "teste", "--sem-juiz", "--dados", str(dados_exemplo))

    assert resultado.exit_code == 0, resultado.output
    linhas = (tmp_path / "resultados" / "teste" / "pontuacoes.jsonl").read_text(encoding="utf-8")
    situacoes = {
        json.loads(linha)["item_id"]: json.loads(linha)["detalhes"]["situacao"]
        for linha in linhas.splitlines()
    }
    # o cliente falso sempre responde "Resposta: B"
    assert situacoes == {
        "conhecimento-exemplo-001": "correta",
        "pragmatica-exemplo-001": "sem_resposta",
    }
    assert "1 respostas abertas/redações aguardam o juiz" in resultado.output


def test_pontuar_filtra_por_prefixo_do_item(tmp_path, dados_exemplo):
    _rodar("executar", "-m", MODELO_LOCAL, "--nome", "teste", "--dados", str(dados_exemplo))

    resultado = _rodar(
        "pontuar", "teste", "--sem-juiz", "--prefixo-item", "conhecimento-",
        "--dados", str(dados_exemplo),
    )

    assert resultado.exit_code == 0, resultado.output
    linhas = (tmp_path / "resultados" / "teste" / "pontuacoes.jsonl").read_text(encoding="utf-8")
    ids = {json.loads(linha)["item_id"] for linha in linhas.splitlines()}
    assert ids == {"conhecimento-exemplo-001"}


def test_pontuar_prefixo_sem_respostas(dados_exemplo):
    _rodar("executar", "-m", MODELO_LOCAL, "--nome", "teste", "--dados", str(dados_exemplo))

    resultado = _rodar(
        "pontuar", "teste", "--prefixo-item", "nao-existe", "--dados", str(dados_exemplo)
    )

    assert resultado.exit_code == 1


def test_executar_com_variantes_e_exportar(tmp_path, dados_exemplo):
    argumentos = ("--nome", "teste", "--dados", str(dados_exemplo))
    _rodar("executar", "-m", MODELO_LOCAL, "--variantes", "2", *argumentos)
    pontuado = _rodar("pontuar", "teste", "--sem-juiz", "--dados", str(dados_exemplo))
    exportado = _rodar("exportar", "teste", "--dados", str(dados_exemplo))

    assert pontuado.exit_code == 0, pontuado.output
    assert "consistência entre variantes" in pontuado.output
    assert exportado.exit_code == 0, exportado.output
    publicado = json.loads(
        (tmp_path / "resultados" / "publicados" / "leaderboard.json").read_text(encoding="utf-8")
    )
    assert publicado["modelos"][0]["modelo"] == MODELO_LOCAL


def test_novo_item_interativo(tmp_path):
    dados = tmp_path / "dados"
    # categoria, formato, enunciado, texto base, rótulos, correto, fonte e data padrão
    entradas = "cultura\nclassificacao\nO que significa 'arretado'?\n\nelogio, ofensa\nelogio\n\n\n"

    resultado = CliRunner().invoke(cli.app, ["novo-item", "--dados", str(dados)], input=entradas)

    assert resultado.exit_code == 0, resultado.output
    salvo = dados / "publico" / "cultura" / "itens_proprios.jsonl"
    item = json.loads(salvo.read_text(encoding="utf-8"))
    assert item["id"] == "cultura-001"
    assert item["rotulos"] == ["elogio", "ofensa"]
    assert _rodar("validar", "--dados", str(dados)).exit_code == 0


def test_validar_juiz(tmp_path):
    arquivo = tmp_path / "notas.csv"
    arquivo.write_text("humano,juiz\n600,640\n800,800\n400,360\n", encoding="utf-8")

    resultado = _rodar("validar-juiz", str(arquivo))

    assert resultado.exit_code == 0, resultado.output
    assert "kappa_quadratico" in resultado.output


def test_pontuar_execucao_inexistente(dados_exemplo):
    assert _rodar("pontuar", "nao-existe", "--dados", str(dados_exemplo)).exit_code == 1


def test_executar_modelo_desconhecido(dados_exemplo):
    resultado = _rodar("executar", "-m", "groq/nao-existe", "--dados", str(dados_exemplo))

    assert resultado.exit_code == 1
