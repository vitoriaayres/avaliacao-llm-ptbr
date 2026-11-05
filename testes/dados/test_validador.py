from avaliador.dados import validar_dataset


def test_dataset_valido(tmp_path, item_bruto, escrever_jsonl):
    escrever_jsonl(tmp_path / "publico" / "conhecimento" / "a.jsonl", [item_bruto()])

    relatorio = validar_dataset(tmp_path)

    assert relatorio.valido
    assert relatorio.contagem_por_categoria() == {"conhecimento": 1}


def test_id_repetido_entre_arquivos(tmp_path, item_bruto, escrever_jsonl):
    escrever_jsonl(tmp_path / "publico" / "conhecimento" / "a.jsonl", [item_bruto()])
    escrever_jsonl(tmp_path / "publico" / "conhecimento" / "b.jsonl", [item_bruto()])

    [erro] = validar_dataset(tmp_path).erros

    assert "já usado em" in erro
    assert "a.jsonl:1" in erro


def test_id_repetido_entre_publico_e_privado(tmp_path, item_bruto, escrever_jsonl):
    escrever_jsonl(tmp_path / "publico" / "conhecimento" / "a.jsonl", [item_bruto()])
    escrever_jsonl(tmp_path / "privado" / "conhecimento" / "a.jsonl", [item_bruto()])

    [erro] = validar_dataset(tmp_path).erros

    assert "já usado em" in erro


def test_categoria_na_pasta_errada(tmp_path, item_bruto, escrever_jsonl):
    escrever_jsonl(tmp_path / "publico" / "cultura" / "a.jsonl", [item_bruto()])

    [erro] = validar_dataset(tmp_path).erros

    assert "está na pasta 'cultura'" in erro


def test_erros_de_carga_entram_no_relatorio(tmp_path, escrever_jsonl):
    escrever_jsonl(tmp_path / "publico" / "conhecimento" / "a.jsonl", ["{quebrado"])

    relatorio = validar_dataset(tmp_path)

    assert not relatorio.valido
    assert "JSON inválido" in relatorio.erros[0]
