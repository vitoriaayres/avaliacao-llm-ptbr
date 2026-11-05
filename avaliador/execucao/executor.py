"""Roda itens em modelos, aproveitando o cache e respeitando cota e privacidade."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from avaliador.configuracao import ConfigModelo, Configuracao
from avaliador.dominio import Formato, Item, Resposta, UsoTokens, Visibilidade
from avaliador.execucao.montador_prompt import montar_mensagens
from avaliador.infraestrutura import CacheRespostas, CotaDiariaEsgotada, gerar_chave
from avaliador.provedores import ClienteLLM

_registro = logging.getLogger(__name__)

NOME_ARQUIVO_RESPOSTAS = "respostas.jsonl"


@dataclass(slots=True)
class ResumoExecucao:
    respondidas: int = 0
    do_cache: int = 0
    com_erro: int = 0
    bloqueadas_por_privacidade: int = 0
    puladas_sem_cota: int = 0
    modelos_sem_chave: list[str] = field(default_factory=list)
    provedores_sem_cota: set[str] = field(default_factory=set)

    def contabilizar(self, resposta: Resposta) -> None:
        self.respondidas += 1
        self.do_cache += resposta.veio_do_cache
        self.com_erro += not resposta.sucesso


class Executor:
    """Para cada modelo e item: usa o cache se houver, senão chama o provedor."""

    def __init__(
        self,
        configuracao: Configuracao,
        cliente: ClienteLLM,
        cache: CacheRespostas,
        templates: Mapping[Formato, str],
        *,
        repeticoes: int = 1,
    ) -> None:
        if repeticoes < 1:
            raise ValueError(f"repeticoes deve ser ao menos 1, recebido {repeticoes}")
        self._configuracao = configuracao
        self._cliente = cliente
        self._cache = cache
        self._templates = templates
        self._repeticoes = repeticoes

    def executar(
        self, itens: Sequence[Item], modelos: Sequence[ConfigModelo], destino: Path
    ) -> ResumoExecucao:
        """Grava uma linha por resposta em `destino`; rodar de novo retoma pelo cache."""
        resumo = ResumoExecucao()
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", encoding="utf-8") as arquivo:
            for modelo in modelos:
                for resposta in self._executar_modelo(modelo, itens, resumo):
                    resumo.contabilizar(resposta)
                    arquivo.write(json.dumps(asdict(resposta), ensure_ascii=False) + "\n")
        return resumo

    def _executar_modelo(
        self, modelo: ConfigModelo, itens: Sequence[Item], resumo: ResumoExecucao
    ) -> Iterator[Resposta]:
        provedor = self._configuracao.provedor_de(modelo)
        if not provedor.disponivel:
            _registro.warning(
                "%s: %s vazia no .env; modelo pulado", modelo.id, provedor.variavel_chave
            )
            resumo.modelos_sem_chave.append(modelo.id)
            return
        for item in itens:
            if item.visibilidade is Visibilidade.PRIVADO and provedor.treina_com_dados:
                resumo.bloqueadas_por_privacidade += 1
                continue
            mensagens = montar_mensagens(item, self._templates)
            for tentativa in range(1, self._repeticoes + 1):
                resposta = self._responder(modelo, item, mensagens, tentativa, resumo)
                if resposta is not None:
                    yield resposta

    def _responder(
        self,
        modelo: ConfigModelo,
        item: Item,
        mensagens: list[dict[str, str]],
        tentativa: int,
        resumo: ResumoExecucao,
    ) -> Resposta | None:
        chave = gerar_chave(modelo.id, item.id, tentativa, mensagens, modelo.parametros)
        guardada = self._cache.obter(chave)
        if guardada is not None:
            return guardada
        if modelo.provedor in resumo.provedores_sem_cota:
            resumo.puladas_sem_cota += 1
            return None
        try:
            resposta = self._cliente.responder(modelo, item.id, mensagens, tentativa)
        except CotaDiariaEsgotada as erro:
            _registro.warning("%s; o resto fica para amanhã (o cache guarda o progresso)", erro)
            resumo.provedores_sem_cota.add(modelo.provedor)
            resumo.puladas_sem_cota += 1
            return None
        if resposta.sucesso:
            self._cache.guardar(chave, resposta)
        _registro.info("%s %s: %s", modelo.id, item.id, "ok" if resposta.sucesso else "erro")
        return resposta


def ler_respostas(caminho: Path) -> list[Resposta]:
    respostas = []
    with caminho.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            if linha.strip():
                campos = json.loads(linha)
                campos["uso"] = UsoTokens(**campos["uso"])
                respostas.append(Resposta(**campos))
    return respostas
