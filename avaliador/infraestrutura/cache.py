"""Cache persistente de respostas em SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from types import TracebackType
from typing import Any

from avaliador.dominio import Resposta, UsoTokens

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS respostas (
    chave           TEXT PRIMARY KEY,
    item_id         TEXT NOT NULL,
    modelo_id       TEXT NOT NULL,
    tentativa       INTEGER NOT NULL,
    texto           TEXT NOT NULL,
    latencia_ms     REAL NOT NULL,
    tokens_entrada  INTEGER NOT NULL,
    tokens_saida    INTEGER NOT NULL,
    criado_em       TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


def gerar_chave(
    modelo_id: str,
    item_id: str,
    tentativa: int,
    mensagens: Sequence[Mapping[str, str]],
    parametros: Mapping[str, Any],
) -> str:
    """Hash de tudo que influencia a resposta: mudou qualquer coisa, a chave muda."""
    conteudo = json.dumps(
        {
            "modelo": modelo_id,
            "item": item_id,
            "tentativa": tentativa,
            "mensagens": list(mensagens),
            "parametros": dict(parametros),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


class CacheRespostas:
    """Guarda respostas bem-sucedidas para nunca gastar cota duas vezes na mesma chamada."""

    def __init__(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self._conexao = sqlite3.connect(caminho, check_same_thread=False)
        self._trava = threading.Lock()
        self._conexao.execute("PRAGMA journal_mode=WAL")
        with self._conexao:
            self._conexao.execute(_ESQUEMA)

    def obter(self, chave: str) -> Resposta | None:
        with self._trava:
            linha = self._conexao.execute(
                "SELECT item_id, modelo_id, tentativa, texto, latencia_ms, "
                "tokens_entrada, tokens_saida FROM respostas WHERE chave = ?",
                (chave,),
            ).fetchone()
        if linha is None:
            return None
        item_id, modelo_id, tentativa, texto, latencia_ms, entrada, saida = linha
        return Resposta(
            item_id=item_id,
            modelo_id=modelo_id,
            texto=texto,
            latencia_ms=latencia_ms,
            uso=UsoTokens(entrada, saida),
            tentativa=tentativa,
            veio_do_cache=True,
        )

    def guardar(self, chave: str, resposta: Resposta) -> None:
        if not resposta.sucesso:
            raise ValueError("só respostas com sucesso vão para o cache; erros devem ser refeitos")
        with self._trava, self._conexao:
            self._conexao.execute(
                "INSERT OR REPLACE INTO respostas (chave, item_id, modelo_id, tentativa, texto, "
                "latencia_ms, tokens_entrada, tokens_saida) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chave,
                    resposta.item_id,
                    resposta.modelo_id,
                    resposta.tentativa,
                    resposta.texto,
                    resposta.latencia_ms,
                    resposta.uso.entrada,
                    resposta.uso.saida,
                ),
            )

    def requisicoes_do_dia(self, prefixo_modelo: str, dia: date) -> int:
        """Respostas gravadas no dia (UTC) para modelos com esse prefixo, ex.: 'groq/'."""
        with self._trava:
            (total,) = self._conexao.execute(
                "SELECT COUNT(*) FROM respostas "
                "WHERE substr(modelo_id, 1, length(?)) = ? AND date(criado_em) = ?",
                (prefixo_modelo, prefixo_modelo, dia.isoformat()),
            ).fetchone()
        return total

    def __len__(self) -> int:
        with self._trava:
            (total,) = self._conexao.execute("SELECT COUNT(*) FROM respostas").fetchone()
        return total

    def fechar(self) -> None:
        self._conexao.close()

    def __enter__(self) -> CacheRespostas:
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        erro: BaseException | None,
        rastro: TracebackType | None,
    ) -> None:
        self.fechar()
