from avaliador.dados import carregar_arquivo, carregar_dataset
from avaliador.dominio import Formato, Visibilidade


def test_carrega_item_valido(tmp_path, item_bruto, escrever_jsonl):
    arquivo = escrever_jsonl(tmp_path / "itens.jsonl", [item_bruto()])

    resultado = carregar_arquivo(arquivo, Visibilidade.PUBLICO)

    assert resultado.valido
    [carregado] = resultado.itens
    assert carregado.item.formato is Formato.MULTIPLA_ESCOLHA
    assert carregado.item.visibilidade is Visibilidade.PUBLICO
    assert carregado.linha == 1


def test_ignora_linhas_em_branco(tmp_path, item_bruto, escrever_jsonl):
    arquivo = escrever_jsonl(tmp_path / "itens.jsonl", ["", item_bruto(), "   "])

    resultado = carregar_arquivo(arquivo, Visibilidade.PUBLICO)

    assert resultado.valido
    assert [carregado.linha for carregado in resultado.itens] == [2]


def test_json_invalido_informa_a_linha(tmp_path, item_bruto, escrever_jsonl):
    arquivo = escrever_jsonl(tmp_path / "itens.jsonl", [item_bruto(), "{quebrado"])

    [erro] = carregar_arquivo(arquivo, Visibilidade.PUBLICO).erros

    assert erro.linha == 2
    assert "JSON inválido" in erro.mensagem


def test_campo_desconhecido_e_recusado(tmp_path, item_bruto, escrever_jsonl):
    arquivo = escrever_jsonl(tmp_path / "itens.jsonl", [item_bruto(enunciadoo="erro de digitação")])

    [erro] = carregar_arquivo(arquivo, Visibilidade.PUBLICO).erros

    assert "enunciadoo" in erro.mensagem


def test_data_fora_do_formato_iso(tmp_path, item_bruto, escrever_jsonl):
    arquivo = escrever_jsonl(tmp_path / "itens.jsonl", [item_bruto(data_referencia="09/11/2025")])

    [erro] = carregar_arquivo(arquivo, Visibilidade.PUBLICO).erros

    assert "$.data_referencia" in erro.mensagem


def test_id_fora_do_padrao(tmp_path, item_bruto, escrever_jsonl):
    arquivo = escrever_jsonl(tmp_path / "itens.jsonl", [item_bruto(id="Conhecimento 001")])

    [erro] = carregar_arquivo(arquivo, Visibilidade.PUBLICO).erros

    assert "$.id" in erro.mensagem


def test_regra_de_dominio_vira_erro_de_carga(tmp_path, item_bruto, escrever_jsonl):
    arquivo = escrever_jsonl(tmp_path / "itens.jsonl", [item_bruto(resposta_correta="E")])

    [erro] = carregar_arquivo(arquivo, Visibilidade.PUBLICO).erros

    assert "não está em" in erro.mensagem


def test_erro_em_uma_linha_nao_bloqueia_as_outras(tmp_path, item_bruto, escrever_jsonl):
    registros = [item_bruto(), "{quebrado", item_bruto(id="conhecimento-teste-002")]
    arquivo = escrever_jsonl(tmp_path / "itens.jsonl", registros)

    resultado = carregar_arquivo(arquivo, Visibilidade.PUBLICO)

    assert len(resultado.itens) == 2
    assert len(resultado.erros) == 1


def test_aceita_arquivo_com_bom(tmp_path, item_bruto, escrever_jsonl):
    arquivo = escrever_jsonl(tmp_path / "itens.jsonl", [item_bruto()], encoding="utf-8-sig")

    assert carregar_arquivo(arquivo, Visibilidade.PUBLICO).valido


def test_pasta_define_a_visibilidade(tmp_path, item_bruto, escrever_jsonl):
    escrever_jsonl(tmp_path / "publico" / "conhecimento" / "a.jsonl", [item_bruto()])
    escrever_jsonl(
        tmp_path / "privado" / "conhecimento" / "b.jsonl",
        [item_bruto(id="conhecimento-teste-002")],
    )

    resultado = carregar_dataset(tmp_path)

    visibilidades = {c.item.id: c.item.visibilidade for c in resultado.itens}
    assert visibilidades == {
        "conhecimento-teste-001": Visibilidade.PUBLICO,
        "conhecimento-teste-002": Visibilidade.PRIVADO,
    }


def test_dataset_sem_pasta_privada(tmp_path, item_bruto, escrever_jsonl):
    escrever_jsonl(tmp_path / "publico" / "conhecimento" / "a.jsonl", [item_bruto()])

    resultado = carregar_dataset(tmp_path)

    assert resultado.valido
    assert len(resultado.itens) == 1
