import logging

import pytest

from avaliador.infraestrutura import configurar_registro


@pytest.fixture(autouse=True)
def restaurar_registro():
    yield
    configurar_registro()  # fecha arquivos de log abertos pelos testes


def _manipuladores_do_projeto() -> list[logging.Handler]:
    return [m for m in logging.getLogger("avaliador").handlers if m.get_name() == "avaliador"]


def test_configurar_duas_vezes_nao_duplica_a_saida():
    configurar_registro()
    configurar_registro()

    assert len(_manipuladores_do_projeto()) == 1


def test_grava_em_arquivo(tmp_path):
    arquivo = tmp_path / "logs" / "execucao.log"
    configurar_registro(arquivo=arquivo)

    logging.getLogger("avaliador.teste").info("execução iniciada")
    for manipulador in _manipuladores_do_projeto():
        manipulador.flush()

    assert "execução iniciada" in arquivo.read_text(encoding="utf-8")
