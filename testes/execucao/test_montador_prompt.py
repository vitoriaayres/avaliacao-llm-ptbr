from datetime import date

import pytest

from avaliador.dominio import Alternativa, Categoria, Formato, Item
from avaliador.execucao import carregar_templates, montar_mensagens


@pytest.fixture(scope="module")
def templates():
    return carregar_templates()


def _item(**campos) -> Item:
    padrao = dict(
        id="teste-001",
        categoria=Categoria.CONHECIMENTO,
        enunciado="Qual instituição aplica o ENEM?",
        fonte="autoria própria",
        data_referencia=date(2026, 11, 4),
    )
    return Item(**{**padrao, **campos})


def _conteudo(item, templates) -> str:
    (mensagem,) = montar_mensagens(item, templates)
    assert mensagem["role"] == "user"
    return mensagem["content"]


def test_multipla_escolha_lista_as_alternativas(templates):
    item = _item(
        formato=Formato.MULTIPLA_ESCOLHA,
        alternativas=(Alternativa("A", "MEC"), Alternativa("B", "INEP")),
        resposta_correta="B",
    )

    conteudo = _conteudo(item, templates)

    assert "Qual instituição aplica o ENEM?" in conteudo
    assert "A) MEC\nB) INEP" in conteudo
    assert "Resposta: <letra>" in conteudo


def test_classificacao_lista_os_rotulos(templates):
    item = _item(
        categoria=Categoria.PRAGMATICA,
        formato=Formato.CLASSIFICACAO,
        rotulos=("irônica", "literal"),
        resposta_correta="irônica",
    )

    assert "Opções: irônica, literal" in _conteudo(item, templates)


def test_texto_base_vem_antes_do_enunciado(templates):
    item = _item(formato=Formato.RESPOSTA_ABERTA, texto_base="  Texto de apoio.  ")

    assert _conteudo(item, templates).startswith("Texto de apoio.\n\nQual instituição")


def test_sem_texto_base_nao_sobra_linha_vazia(templates):
    conteudo = _conteudo(_item(formato=Formato.RESPOSTA_ABERTA), templates)

    assert conteudo.startswith("Qual instituição")


def test_chaves_no_enunciado_nao_quebram_o_template(templates):
    item = _item(formato=Formato.RESPOSTA_ABERTA, enunciado="Quanto vale {x} em f(x) = {2x}?")

    assert "{x}" in _conteudo(item, templates)


def test_redacao(templates):
    item = _item(
        categoria=Categoria.ESCRITA,
        formato=Formato.REDACAO,
        enunciado="Desafios da mobilidade urbana",
    )

    assert _conteudo(item, templates).startswith("Tema: Desafios da mobilidade urbana")


def test_template_ausente(tmp_path):
    with pytest.raises(FileNotFoundError, match="multipla_escolha"):
        carregar_templates(tmp_path)
