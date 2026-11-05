"""Leitura dos arquivos JSONL do dataset e conversão para Item."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from avaliador.dominio import Alternativa, Categoria, Formato, Item, ItemInvalido, Visibilidade

CAMINHO_ESQUEMA_PADRAO = (
    Path(__file__).resolve().parents[2] / "dados" / "esquemas" / "item.schema.json"
)


@dataclass(frozen=True, slots=True)
class ItemCarregado:
    """Item junto com o lugar de onde veio, para mensagens de erro úteis."""

    item: Item
    arquivo: Path
    linha: int

    @property
    def origem(self) -> str:
        return f"{self.arquivo}:{self.linha}"


@dataclass(frozen=True, slots=True)
class ErroDeCarga:
    arquivo: Path
    linha: int
    mensagem: str

    def __str__(self) -> str:
        return f"{self.arquivo}:{self.linha}: {self.mensagem}"


@dataclass(frozen=True, slots=True)
class ResultadoCarga:
    itens: tuple[ItemCarregado, ...]
    erros: tuple[ErroDeCarga, ...]

    @property
    def valido(self) -> bool:
        return not self.erros


def carregar_dataset(raiz: Path, esquema: Path = CAMINHO_ESQUEMA_PADRAO) -> ResultadoCarga:
    """Carrega `raiz/publico/**` e `raiz/privado/**`; a pasta define a visibilidade."""
    itens: list[ItemCarregado] = []
    erros: list[ErroDeCarga] = []
    for visibilidade in Visibilidade:
        pasta = raiz / visibilidade.value
        if not pasta.is_dir():
            continue
        for arquivo in sorted(pasta.rglob("*.jsonl")):
            resultado = carregar_arquivo(arquivo, visibilidade, esquema)
            itens.extend(resultado.itens)
            erros.extend(resultado.erros)
    return ResultadoCarga(tuple(itens), tuple(erros))


def carregar_arquivo(
    arquivo: Path,
    visibilidade: Visibilidade,
    esquema: Path = CAMINHO_ESQUEMA_PADRAO,
) -> ResultadoCarga:
    validador = _validador_de_esquema(esquema)
    itens: list[ItemCarregado] = []
    erros: list[ErroDeCarga] = []

    for numero, linha in _linhas_preenchidas(arquivo):
        try:
            bruto = json.loads(linha)
        except json.JSONDecodeError as erro:
            erros.append(ErroDeCarga(arquivo, numero, f"JSON inválido: {erro.msg}"))
            continue

        problemas = sorted(validador.iter_errors(bruto), key=lambda problema: problema.json_path)
        if problemas:
            erros.extend(ErroDeCarga(arquivo, numero, _descrever(p)) for p in problemas)
            continue

        try:
            itens.append(ItemCarregado(_para_item(bruto, visibilidade), arquivo, numero))
        except ItemInvalido as erro:
            erros.append(ErroDeCarga(arquivo, numero, str(erro)))

    return ResultadoCarga(tuple(itens), tuple(erros))


@cache
def _validador_de_esquema(caminho: Path) -> Draft202012Validator:
    esquema = json.loads(caminho.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(esquema)
    return Draft202012Validator(esquema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _linhas_preenchidas(arquivo: Path) -> Iterator[tuple[int, str]]:
    # utf-8-sig aceita arquivos salvos com BOM, comum em editores no Windows.
    texto = arquivo.read_text(encoding="utf-8-sig")
    for numero, linha in enumerate(texto.splitlines(), start=1):
        if linha.strip():
            yield numero, linha


def _descrever(problema: ValidationError) -> str:
    return f"{problema.json_path}: {problema.message}"


def _para_item(bruto: dict[str, Any], visibilidade: Visibilidade) -> Item:
    return Item(
        id=bruto["id"],
        categoria=Categoria(bruto["categoria"]),
        formato=Formato(bruto["formato"]),
        enunciado=bruto["enunciado"],
        fonte=bruto["fonte"],
        data_referencia=date.fromisoformat(bruto["data_referencia"]),
        visibilidade=visibilidade,
        texto_base=bruto.get("texto_base"),
        alternativas=tuple(
            Alternativa(alternativa["letra"], alternativa["texto"])
            for alternativa in bruto.get("alternativas", [])
        ),
        rotulos=tuple(bruto.get("rotulos", [])),
        resposta_correta=bruto.get("resposta_correta"),
        resposta_referencia=bruto.get("resposta_referencia"),
        metadados=bruto.get("metadados", {}),
    )
