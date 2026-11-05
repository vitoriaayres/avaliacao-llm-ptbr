"""Transforma um item em mensagens de chat usando os templates de prompts/."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from avaliador.dominio import Formato, Item

PASTA_PADRAO = Path(__file__).resolve().parents[2] / "prompts"


def carregar_templates(pasta: Path = PASTA_PADRAO) -> dict[Formato, str]:
    """Um template por formato, em `<formato>.txt`; a falta de qualquer um é erro."""
    templates = {}
    for formato in Formato:
        caminho = pasta / f"{formato}.txt"
        texto = caminho.read_text(encoding="utf-8").strip() if caminho.exists() else ""
        if not texto:
            raise FileNotFoundError(f"template ausente ou vazio: {caminho}")
        templates[formato] = texto
    return templates


def montar_mensagens(item: Item, templates: Mapping[Formato, str]) -> list[dict[str, str]]:
    conteudo = templates[item.formato].format(
        texto_base=f"{item.texto_base.strip()}\n\n" if item.texto_base else "",
        enunciado=item.enunciado,
        alternativas="\n".join(f"{a.letra}) {a.texto}" for a in item.alternativas),
        rotulos=", ".join(item.rotulos),
    )
    return [{"role": "user", "content": conteudo}]
