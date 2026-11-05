"""Tipos que descrevem um item (questão ou tema) do benchmark."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class ItemInvalido(ValueError):
    """Item que viola alguma regra do seu formato."""


class Categoria(StrEnum):
    CONHECIMENTO = "conhecimento"
    BRASIL_PRATICO = "brasil_pratico"
    CULTURA = "cultura"
    PRAGMATICA = "pragmatica"
    INTERPRETACAO = "interpretacao"
    ESCRITA = "escrita"
    VIES_REGIONAL = "vies_regional"


class Formato(StrEnum):
    MULTIPLA_ESCOLHA = "multipla_escolha"
    CLASSIFICACAO = "classificacao"
    RESPOSTA_ABERTA = "resposta_aberta"
    REDACAO = "redacao"


class Visibilidade(StrEnum):
    PUBLICO = "publico"
    PRIVADO = "privado"


@dataclass(frozen=True, slots=True)
class Alternativa:
    letra: str
    texto: str

    def __post_init__(self) -> None:
        if len(self.letra) != 1 or not self.letra.isalpha() or not self.letra.isupper():
            raise ItemInvalido(f"letra de alternativa inválida: '{self.letra}' (use A, B, C...)")
        if not self.texto.strip():
            raise ItemInvalido(f"alternativa {self.letra} sem texto")


@dataclass(frozen=True, slots=True)
class Item:
    id: str
    categoria: Categoria
    formato: Formato
    enunciado: str
    fonte: str
    data_referencia: date
    visibilidade: Visibilidade = Visibilidade.PUBLICO
    texto_base: str | None = None
    alternativas: tuple[Alternativa, ...] = ()
    rotulos: tuple[str, ...] = ()
    resposta_correta: str | None = None
    resposta_referencia: str | None = None
    metadados: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ItemInvalido("id não pode ser vazio")
        if not self.enunciado.strip():
            raise ItemInvalido(f"{self.id}: enunciado vazio")
        # Impede alteração dos metadados depois de criado o item.
        object.__setattr__(self, "metadados", MappingProxyType(dict(self.metadados)))
        _VALIDADORES_POR_FORMATO[self.formato](self)

    @property
    def letras(self) -> tuple[str, ...]:
        return tuple(alternativa.letra for alternativa in self.alternativas)


def _exigir_valores_unicos(item: Item, valores: tuple[str, ...], nome: str) -> None:
    if len(set(valores)) != len(valores):
        raise ItemInvalido(f"{item.id}: {nome} repetidos em {valores}")


def _validar_multipla_escolha(item: Item) -> None:
    if len(item.alternativas) < 2:
        raise ItemInvalido(f"{item.id}: múltipla escolha precisa de ao menos 2 alternativas")
    if item.rotulos:
        raise ItemInvalido(f"{item.id}: múltipla escolha usa alternativas, não rotulos")
    _exigir_valores_unicos(item, item.letras, "letras")
    if item.resposta_correta not in item.letras:
        raise ItemInvalido(
            f"{item.id}: resposta_correta '{item.resposta_correta}' não está em {item.letras}"
        )


def _validar_classificacao(item: Item) -> None:
    if len(item.rotulos) < 2:
        raise ItemInvalido(f"{item.id}: classificação precisa de ao menos 2 rótulos")
    if item.alternativas:
        raise ItemInvalido(f"{item.id}: classificação usa rotulos, não alternativas")
    _exigir_valores_unicos(item, item.rotulos, "rótulos")
    if item.resposta_correta not in item.rotulos:
        raise ItemInvalido(
            f"{item.id}: resposta_correta '{item.resposta_correta}' não está em {item.rotulos}"
        )


def _validar_resposta_aberta(item: Item) -> None:
    if item.alternativas or item.rotulos:
        raise ItemInvalido(f"{item.id}: resposta aberta não tem alternativas nem rótulos")


def _validar_redacao(item: Item) -> None:
    if item.categoria != Categoria.ESCRITA:
        raise ItemInvalido(f"{item.id}: redação só existe na categoria '{Categoria.ESCRITA}'")
    if item.alternativas or item.rotulos or item.resposta_correta:
        raise ItemInvalido(f"{item.id}: redação não tem alternativas, rótulos nem gabarito")


_VALIDADORES_POR_FORMATO: dict[Formato, Callable[[Item], None]] = {
    Formato.MULTIPLA_ESCOLHA: _validar_multipla_escolha,
    Formato.CLASSIFICACAO: _validar_classificacao,
    Formato.RESPOSTA_ABERTA: _validar_resposta_aberta,
    Formato.REDACAO: _validar_redacao,
}
