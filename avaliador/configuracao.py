"""Leitura dos YAMLs de configuracao/: provedores, modelos e juízes."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from avaliador.infraestrutura import LimitesProvedor

PASTA_PADRAO = Path(__file__).resolve().parents[1] / "configuracao"


class ErroDeConfiguracao(ValueError):
    """YAML de configuração ausente, malformado ou inconsistente."""


@dataclass(frozen=True, slots=True)
class ConfigProvedor:
    nome: str
    limites: LimitesProvedor = field(default_factory=LimitesProvedor)
    variavel_chave: str | None = None
    treina_com_dados: bool = True

    @property
    def chave(self) -> str | None:
        if self.variavel_chave is None:
            return None
        return os.environ.get(self.variavel_chave) or None

    @property
    def disponivel(self) -> bool:
        return self.variavel_chave is None or self.chave is not None


@dataclass(frozen=True, slots=True)
class ConfigModelo:
    id: str
    nome: str
    parametros: Mapping[str, Any] = field(default_factory=dict)
    data_corte: date | None = None  # fim dos dados de treino, para medir contaminação
    # Alguns modelos têm limite próprio, menor que o do provedor (ex.: tokens por minuto).
    requisicoes_por_minuto: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "parametros", MappingProxyType(dict(self.parametros)))

    @property
    def provedor(self) -> str:
        return self.id.split("/", 1)[0]


@dataclass(frozen=True, slots=True)
class Configuracao:
    provedores: Mapping[str, ConfigProvedor]
    modelos: tuple[ConfigModelo, ...]
    juizes: tuple[ConfigModelo, ...]

    def provedor_de(self, modelo: ConfigModelo) -> ConfigProvedor:
        return self.provedores[modelo.provedor]

    def modelo(self, modelo_id: str) -> ConfigModelo:
        for modelo in (*self.modelos, *self.juizes):
            if modelo.id == modelo_id:
                return modelo
        raise ErroDeConfiguracao(f"modelo '{modelo_id}' não está em modelos.yaml nem juizes.yaml")


def carregar_configuracao(pasta: Path = PASTA_PADRAO) -> Configuracao:
    provedores = _ler_provedores(_ler_yaml(pasta / "provedores.yaml").get("provedores") or {})
    dados_modelos = _ler_yaml(pasta / "modelos.yaml")
    padrao = dados_modelos.get("parametros_padrao") or {}
    modelos = _ler_modelos(dados_modelos.get("modelos") or [], padrao, "modelos.yaml")
    juizes = _ler_modelos(
        _ler_yaml(pasta / "juizes.yaml").get("juizes") or [], padrao, "juizes.yaml"
    )
    _exigir_consistencia(provedores, modelos, "modelos.yaml")
    _exigir_consistencia(provedores, juizes, "juizes.yaml")
    return Configuracao(MappingProxyType(provedores), modelos, juizes)


def _ler_yaml(caminho: Path) -> dict[str, Any]:
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError as erro:
        raise ErroDeConfiguracao(f"arquivo não encontrado: {caminho}") from erro
    except yaml.YAMLError as erro:
        raise ErroDeConfiguracao(f"{caminho.name}: YAML inválido: {erro}") from erro
    if dados is None:
        return {}
    if not isinstance(dados, dict):
        raise ErroDeConfiguracao(f"{caminho.name}: esperado um mapa no topo do arquivo")
    return dados


def _ler_provedores(dados: Mapping[str, Any]) -> dict[str, ConfigProvedor]:
    provedores = {}
    for nome, campos in dados.items():
        campos = campos or {}
        try:
            limites = LimitesProvedor(
                requisicoes_por_minuto=campos.get("requisicoes_por_minuto"),
                requisicoes_por_dia=campos.get("requisicoes_por_dia"),
            )
        except ValueError as erro:
            raise ErroDeConfiguracao(f"provedor '{nome}': {erro}") from erro
        provedores[nome] = ConfigProvedor(
            nome=nome,
            limites=limites,
            variavel_chave=campos.get("variavel_chave"),
            treina_com_dados=campos.get("treina_com_dados", True),
        )
    return provedores


def _ler_modelos(
    dados: list[Mapping[str, Any]], padrao: Mapping[str, Any], origem: str
) -> tuple[ConfigModelo, ...]:
    modelos = []
    for posicao, campos in enumerate(dados, start=1):
        if "id" not in campos:
            raise ErroDeConfiguracao(f"{origem}: modelo na posição {posicao} sem 'id'")
        modelos.append(
            ConfigModelo(
                id=campos["id"],
                nome=campos.get("nome", campos["id"]),
                parametros={**padrao, **(campos.get("parametros") or {})},
                data_corte=_ler_data(campos.get("data_corte"), origem),
                requisicoes_por_minuto=campos.get("requisicoes_por_minuto"),
            )
        )
    return tuple(modelos)


def _ler_data(valor: Any, origem: str) -> date | None:
    """O YAML já entrega `2024-06-01` como date; texto entre aspas também é aceito."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except ValueError as erro:
        mensagem = f"{origem}: data_corte inválida '{valor}' (use AAAA-MM-DD)"
        raise ErroDeConfiguracao(mensagem) from erro


def _exigir_consistencia(
    provedores: Mapping[str, ConfigProvedor], modelos: tuple[ConfigModelo, ...], origem: str
) -> None:
    ids = [modelo.id for modelo in modelos]
    repetidos = sorted({modelo_id for modelo_id in ids if ids.count(modelo_id) > 1})
    if repetidos:
        raise ErroDeConfiguracao(f"{origem}: ids repetidos {repetidos}")
    for modelo in modelos:
        if modelo.provedor not in provedores:
            raise ErroDeConfiguracao(
                f"{origem}: '{modelo.id}' usa o provedor '{modelo.provedor}', "
                "que não está em provedores.yaml"
            )
