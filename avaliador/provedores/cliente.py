"""Cliente único para todos os provedores, via LiteLLM."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import litellm

from avaliador.configuracao import ConfigModelo, ConfigProvedor
from avaliador.dominio import ERRO_RESPOSTA_VAZIA, Resposta, UsoTokens
from avaliador.infraestrutura import CacheRespostas, LimitadorDeTaxa, LimitesProvedor
from avaliador.provedores.erros import ErroDoProvedor, eh_transitorio, espera_sugerida

litellm.suppress_debug_info = True
_registro = logging.getLogger(__name__)

# Acima disso o provedor está pedindo horas (cota do dia); não vale travar a execução.
ESPERA_MAXIMA_S = 60.0

Mensagens = Sequence[Mapping[str, str]]


def criar_limitadores(
    provedores: Mapping[str, ConfigProvedor],
    cache: CacheRespostas | None = None,
    modelos: Iterable[ConfigModelo] = (),
) -> dict[str, LimitadorDeTaxa]:
    """Um limitador por provedor (descontando o que o cache registrou hoje) e um por modelo
    que tenha limite próprio, com o id do modelo como chave."""
    hoje = datetime.now(UTC).date()
    # shortcut: o cache só guarda sucessos, então chamadas que falharam hoje não entram na conta.
    limitadores = {
        nome: LimitadorDeTaxa(
            nome,
            provedor.limites,
            ja_usadas_hoje=cache.requisicoes_do_dia(f"{nome}/", hoje) if cache else 0,
        )
        for nome, provedor in provedores.items()
    }
    for modelo in modelos:
        if modelo.requisicoes_por_minuto:
            limites = LimitesProvedor(requisicoes_por_minuto=modelo.requisicoes_por_minuto)
            limitadores[modelo.id] = LimitadorDeTaxa(modelo.id, limites)
    return limitadores


class ClienteLLM:
    """Faz a chamada respeitando os limites e refaz só os erros transitórios."""

    def __init__(
        self,
        provedores: Mapping[str, ConfigProvedor],
        limitadores: Mapping[str, LimitadorDeTaxa],
        *,
        completar: Callable[..., Any] = litellm.completion,
        dormir: Callable[[float], None] = time.sleep,
        max_retentativas: int = 3,
        espera_base_s: float = 2.0,
        timeout_s: float = 120.0,
    ) -> None:
        self._provedores = provedores
        self._limitadores = limitadores
        self._completar = completar
        self._dormir = dormir
        self._max_retentativas = max_retentativas
        self._espera_base_s = espera_base_s
        self._timeout_s = timeout_s

    def responder(
        self, modelo: ConfigModelo, item_id: str, mensagens: Mensagens, tentativa: int = 1
    ) -> Resposta:
        """Lança CotaDiariaEsgotada se o provedor esgotou a cota; outros erros viram Resposta."""
        provedor = self._provedores[modelo.provedor]
        limitador = self._limitadores[modelo.provedor]
        limitador_do_modelo = self._limitadores.get(modelo.id)
        retentativa = 0
        while True:
            limitador.aguardar_vez()
            if limitador_do_modelo is not None:
                limitador_do_modelo.aguardar_vez()
            inicio = time.perf_counter()
            try:
                bruta = self._completar(
                    model=modelo.id,
                    messages=[dict(mensagem) for mensagem in mensagens],
                    api_key=provedor.chave,
                    timeout=self._timeout_s,
                    **modelo.parametros,
                )
            except ErroDoProvedor as erro:
                if eh_transitorio(erro) and retentativa < self._max_retentativas:
                    backoff = self._espera_base_s * 2**retentativa
                    espera = min(max(backoff, espera_sugerida(erro) or 0), ESPERA_MAXIMA_S)
                    _registro.warning(
                        "%s: %s; nova tentativa em %.0fs", modelo.id, type(erro).__name__, espera
                    )
                    self._dormir(espera)
                    retentativa += 1
                    continue
                _registro.error("%s em %s: %s", modelo.id, item_id, erro)
                return Resposta(
                    item_id=item_id,
                    modelo_id=modelo.id,
                    texto=None,
                    latencia_ms=_ms_desde(inicio),
                    tentativa=tentativa,
                    erro=f"{type(erro).__name__}: {erro}",
                )
            return _converter(bruta, item_id, modelo.id, tentativa, _ms_desde(inicio))


def _converter(
    bruta: Any, item_id: str, modelo_id: str, tentativa: int, latencia_ms: float
) -> Resposta:
    texto = bruta.choices[0].message.content or None
    uso = getattr(bruta, "usage", None)
    return Resposta(
        item_id=item_id,
        modelo_id=modelo_id,
        texto=texto,
        latencia_ms=latencia_ms,
        uso=UsoTokens(
            entrada=getattr(uso, "prompt_tokens", 0) or 0,
            saida=getattr(uso, "completion_tokens", 0) or 0,
        ),
        tentativa=tentativa,
        erro=None if texto else ERRO_RESPOSTA_VAZIA,
    )


def _ms_desde(inicio: float) -> float:
    return (time.perf_counter() - inicio) * 1000
