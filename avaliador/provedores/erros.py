"""Classificação dos erros dos provedores: o que vale tentar de novo e o que não vale."""

from __future__ import annotations

import litellm
import openai

# Toda exceção do LiteLLM herda desta; qualquer outra coisa é bug nosso e deve estourar.
ErroDoProvedor = openai.APIError

_TRANSITORIOS = (
    litellm.RateLimitError,
    litellm.Timeout,
    litellm.APIConnectionError,
    litellm.ServiceUnavailableError,
    litellm.InternalServerError,
)


def espera_sugerida(erro: Exception) -> float | None:
    """Segundos pedidos pelo provedor no cabeçalho retry-after, se ele mandou."""
    resposta = getattr(erro, "response", None)
    valor = resposta.headers.get("retry-after") if resposta is not None else None
    try:
        return float(valor) if valor else None
    except ValueError:  # retry-after também pode vir como data HTTP; aí usamos o backoff
        return None


def eh_transitorio(erro: Exception) -> bool:
    """Excesso de requisições, timeout e instabilidade passam; chave errada não passa."""
    return isinstance(erro, _TRANSITORIOS)
