import json

import pandas as pd
import pytest

from avaliador.dominio import Visibilidade
from avaliador.ferramentas.leaderboard import (
    ler_leaderboard,
    montar_leaderboard,
    salvar_leaderboard,
)
from avaliador.ferramentas.novo_item import ItemRecusado, adicionar_item, proximo_id

PLACAR = pd.DataFrame(
    {
        "geral": [0.9, 0.6],
        "ic_inferior": [0.85, 0.5],
        "ic_superior": [0.95, 0.7],
        "n_itens": [40, 40],
        "empata_com_lider": [True, False],
        "conhecimento": [0.9, float("nan")],
        "erro_api": [0, 2],
    },
    index=pd.Index(["groq/a", "groq/b"], name="modelo"),
)


def test_leaderboard_ida_e_volta(tmp_path):
    conteudo = montar_leaderboard(
        PLACAR, execucao="teste", itens_por_categoria={"conhecimento": 40}, nomes={"groq/a": "A"}
    )
    caminho = salvar_leaderboard(conteudo, tmp_path)

    dados, placar = ler_leaderboard(caminho)

    assert dados["modelos"][0] == {
        "posicao": 1,
        "modelo": "groq/a",
        "nome": "A",
        "geral": 0.9,
        "ic_inferior": 0.85,
        "ic_superior": 0.95,
        "n_itens": 40,
        "empata_com_lider": True,
        "categorias": {"conhecimento": 0.9},
    }
    assert dados["modelos"][1]["categorias"] == {"conhecimento": None}  # NaN vira null no JSON
    assert list(placar.index) == ["A", "groq/b"]
    json.loads(caminho.read_text(encoding="utf-8"))  # JSON válido, sem NaN


ITEM = {
    "categoria": "pragmatica",
    "formato": "classificacao",
    "enunciado": "Que calor, hein? (num dia de 10 graus)",
    "rotulos": ["irônica", "literal"],
    "resposta_correta": "irônica",
    "fonte": "autoria própria",
    "data_referencia": "2026-11-04",
}


def test_adiciona_item_valido(tmp_path):
    destino = adicionar_item({"id": "pragmatica-001", **ITEM}, tmp_path, Visibilidade.PRIVADO)

    assert destino == tmp_path / "privado" / "pragmatica" / "itens_proprios.jsonl"
    assert json.loads(destino.read_text(encoding="utf-8"))["id"] == "pragmatica-001"


def test_recusa_item_invalido_e_id_repetido(tmp_path):
    with pytest.raises(ItemRecusado, match="resposta_correta"):
        adicionar_item(
            {"id": "pragmatica-001", **ITEM, "resposta_correta": "sarcástica"},
            tmp_path,
            Visibilidade.PUBLICO,
        )
    adicionar_item({"id": "pragmatica-001", **ITEM}, tmp_path, Visibilidade.PUBLICO)
    with pytest.raises(ItemRecusado, match="já existe"):
        adicionar_item({"id": "pragmatica-001", **ITEM}, tmp_path, Visibilidade.PUBLICO)


def test_proximo_id():
    assert proximo_id("brasil_pratico", set()) == "brasil-pratico-001"
    assert proximo_id("cultura", {"cultura-001", "cultura-002"}) == "cultura-003"
