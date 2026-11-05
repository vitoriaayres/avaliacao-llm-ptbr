"""Adiciona um item ao dataset só depois de validá-lo como o carregador validaria."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from avaliador.dados import carregar_arquivo, validar_dataset
from avaliador.dominio import Visibilidade

NOME_ARQUIVO_PROPRIO = "itens_proprios.jsonl"


class ItemRecusado(ValueError):
    """O item viola o esquema, as regras do formato ou repete um id."""


def proximo_id(categoria: str, ids_existentes: set[str]) -> str:
    prefixo = categoria.replace("_", "-")
    numero = 1
    while f"{prefixo}-{numero:03d}" in ids_existentes:
        numero += 1
    return f"{prefixo}-{numero:03d}"


def adicionar_item(bruto: Mapping[str, Any], dados: Path, visibilidade: Visibilidade) -> Path:
    """Valida e acrescenta o item em `dados/<visibilidade>/<categoria>/itens_proprios.jsonl`."""
    linha = json.dumps(dict(bruto), ensure_ascii=False)
    with tempfile.TemporaryDirectory() as pasta:
        provisorio = Path(pasta) / "item.jsonl"
        provisorio.write_text(linha + "\n", encoding="utf-8")
        carga = carregar_arquivo(provisorio, visibilidade)
    if carga.erros:
        raise ItemRecusado("; ".join(erro.mensagem for erro in carga.erros))
    if bruto["id"] in {item.id for item in validar_dataset(dados).itens}:
        raise ItemRecusado(f"id '{bruto['id']}' já existe no dataset")

    destino = dados / visibilidade.value / bruto["categoria"] / NOME_ARQUIVO_PROPRIO
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("a", encoding="utf-8") as arquivo:
        arquivo.write(linha + "\n")
    return destino
