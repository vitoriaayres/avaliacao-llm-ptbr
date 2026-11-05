"""Contrato dos pontuadores e a aplicação do pontuador certo a cada resposta."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from avaliador.dominio import Formato, Item, Pontuacao, Resposta

NOME_ARQUIVO_PONTUACOES = "pontuacoes.jsonl"


class Situacao(StrEnum):
    CORRETA = "correta"
    INCORRETA = "incorreta"
    SEM_RESPOSTA = "sem_resposta"  # o modelo não entregou texto ou uma opção válida
    AVALIADA = "avaliada"  # nota dada pelo juiz
    ERRO_API = "erro_api"  # a chamada do modelo falhou; não é culpa do modelo
    ERRO_JUIZ = "erro_juiz"  # o juiz falhou ou respondeu fora do formato


# Falhas de infraestrutura não dizem nada sobre o modelo: ficam fora das médias.
SITUACOES_FORA_DA_MEDIA = frozenset({Situacao.ERRO_API, Situacao.ERRO_JUIZ})


class Pontuador(Protocol):
    nome: str

    def pontuar(self, item: Item, resposta: Resposta) -> Pontuacao: ...


@dataclass(frozen=True, slots=True)
class ResultadoPontuacao:
    pontuacoes: tuple[Pontuacao, ...]
    ids_sem_item: tuple[str, ...]  # respostas cujo item não está mais no dataset
    sem_pontuador: int  # respostas de formatos ainda sem pontuador (ex.: redação até a Parte 7)


def pontuar_respostas(
    itens: Iterable[Item],
    respostas: Iterable[Resposta],
    pontuadores: Mapping[Formato, Pontuador],
) -> ResultadoPontuacao:
    por_id = {item.id: item for item in itens}
    pontuacoes: list[Pontuacao] = []
    ids_sem_item: set[str] = set()
    sem_pontuador = 0
    for resposta in respostas:
        item = por_id.get(resposta.item_id)
        if item is None:
            ids_sem_item.add(resposta.item_id)
        elif item.formato not in pontuadores:
            sem_pontuador += 1
        else:
            pontuacoes.append(pontuadores[item.formato].pontuar(item, resposta))
    return ResultadoPontuacao(tuple(pontuacoes), tuple(sorted(ids_sem_item)), sem_pontuador)


def salvar_pontuacoes(pontuacoes: Iterable[Pontuacao], caminho: Path) -> None:
    with caminho.open("w", encoding="utf-8") as arquivo:
        for pontuacao in pontuacoes:
            linha = {
                "item_id": pontuacao.item_id,
                "modelo_id": pontuacao.modelo_id,
                "pontuador": pontuacao.pontuador,
                "nota": pontuacao.nota,
                "tentativa": pontuacao.tentativa,
                "detalhes": dict(pontuacao.detalhes),
            }
            arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")


def ler_pontuacoes(caminho: Path) -> list[Pontuacao]:
    with caminho.open(encoding="utf-8") as arquivo:
        return [Pontuacao(**json.loads(linha)) for linha in arquivo if linha.strip()]
