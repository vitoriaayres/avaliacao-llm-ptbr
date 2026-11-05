from datetime import date

import pytest

from avaliador.dominio import Alternativa, Categoria, Formato, Item, ItemInvalido


def _multipla_escolha(**sobrescritas) -> Item:
    campos = dict(
        id="conhecimento-enem2025-001",
        categoria=Categoria.CONHECIMENTO,
        formato=Formato.MULTIPLA_ESCOLHA,
        enunciado="Qual é a capital do Brasil?",
        fonte="autoria própria",
        data_referencia=date(2025, 11, 9),
        alternativas=(
            Alternativa("A", "São Paulo"),
            Alternativa("B", "Brasília"),
            Alternativa("C", "Rio de Janeiro"),
        ),
        resposta_correta="B",
    )
    campos.update(sobrescritas)
    return Item(**campos)


def _classificacao(**sobrescritas) -> Item:
    campos = dict(
        id="pragmatica-ironia-001",
        categoria=Categoria.PRAGMATICA,
        formato=Formato.CLASSIFICACAO,
        enunciado="'Nossa, que ótimo, choveu no meu único dia de folga.' A frase é irônica?",
        fonte="autoria própria",
        data_referencia=date(2026, 1, 1),
        rotulos=("irônica", "literal"),
        resposta_correta="irônica",
    )
    campos.update(sobrescritas)
    return Item(**campos)


class TestMultiplaEscolha:
    def test_item_valido(self):
        item = _multipla_escolha()
        assert item.letras == ("A", "B", "C")

    def test_resposta_fora_das_alternativas(self):
        with pytest.raises(ItemInvalido, match="não está em"):
            _multipla_escolha(resposta_correta="E")

    def test_letras_repetidas(self):
        with pytest.raises(ItemInvalido, match="repetidos"):
            _multipla_escolha(alternativas=(Alternativa("A", "x"), Alternativa("A", "y")))

    def test_poucas_alternativas(self):
        with pytest.raises(ItemInvalido, match="ao menos 2"):
            _multipla_escolha(alternativas=(Alternativa("A", "x"),), resposta_correta="A")

    @pytest.mark.parametrize("letra", ["a", "AB", "1", ""])
    def test_letra_invalida(self, letra):
        with pytest.raises(ItemInvalido, match="letra"):
            Alternativa(letra, "texto")


class TestClassificacao:
    def test_item_valido(self):
        assert _classificacao().resposta_correta == "irônica"

    def test_resposta_fora_dos_rotulos(self):
        with pytest.raises(ItemInvalido, match="não está em"):
            _classificacao(resposta_correta="sarcástica")

    def test_nao_aceita_alternativas(self):
        with pytest.raises(ItemInvalido, match="não alternativas"):
            _classificacao(alternativas=(Alternativa("A", "x"), Alternativa("B", "y")))


class TestRedacao:
    def _redacao(self, **sobrescritas) -> Item:
        campos = dict(
            id="escrita-tema-001",
            categoria=Categoria.ESCRITA,
            formato=Formato.REDACAO,
            enunciado="Desafios para a valorização da herança africana no Brasil",
            fonte="INEP - ENEM 2024",
            data_referencia=date(2024, 11, 3),
        )
        campos.update(sobrescritas)
        return Item(**campos)

    def test_item_valido(self):
        assert self._redacao().formato is Formato.REDACAO

    def test_so_na_categoria_escrita(self):
        with pytest.raises(ItemInvalido, match="categoria"):
            self._redacao(categoria=Categoria.CULTURA)

    def test_nao_tem_gabarito(self):
        with pytest.raises(ItemInvalido, match="gabarito"):
            self._redacao(resposta_correta="qualquer")


class TestRegrasGerais:
    def test_id_vazio(self):
        with pytest.raises(ItemInvalido, match="id"):
            _multipla_escolha(id="  ")

    def test_enunciado_vazio(self):
        with pytest.raises(ItemInvalido, match="enunciado"):
            _multipla_escolha(enunciado="")

    def test_metadados_imutaveis(self):
        item = _multipla_escolha(metadados={"ano": 2025})
        with pytest.raises(TypeError):
            item.metadados["ano"] = 2026

    def test_metadados_desacoplados_do_dict_original(self):
        original = {"ano": 2025}
        item = _multipla_escolha(metadados=original)
        original["ano"] = 1999
        assert item.metadados["ano"] == 2025
