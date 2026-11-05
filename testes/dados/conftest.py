import json
from pathlib import Path

import pytest


@pytest.fixture
def item_bruto():
    """Fábrica de um item válido em formato JSON; sobrescreva só o que o teste quer quebrar."""

    def fabricar(**sobrescritas):
        registro = {
            "id": "conhecimento-teste-001",
            "categoria": "conhecimento",
            "formato": "multipla_escolha",
            "enunciado": "Qual é a capital do Brasil?",
            "fonte": "autoria própria",
            "data_referencia": "2025-11-09",
            "alternativas": [
                {"letra": "A", "texto": "São Paulo"},
                {"letra": "B", "texto": "Brasília"},
            ],
            "resposta_correta": "B",
        }
        registro.update(sobrescritas)
        return registro

    return fabricar


@pytest.fixture
def escrever_jsonl():
    """Grava registros em JSONL; strings entram como linhas cruas (para testar JSON quebrado)."""

    def escrever(caminho: Path, registros, encoding="utf-8"):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        linhas = [
            registro if isinstance(registro, str) else json.dumps(registro, ensure_ascii=False)
            for registro in registros
        ]
        caminho.write_text("\n".join(linhas) + "\n", encoding=encoding)
        return caminho

    return escrever
