"""LLM como juiz: redação (5 competências do ENEM) e resposta aberta (nota de 0 a 10)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from avaliador.configuracao import ConfigModelo, ConfigProvedor
from avaliador.dominio import Formato, Item, Pontuacao, Resposta, Visibilidade
from avaliador.execucao.montador_prompt import PASTA_PADRAO
from avaliador.infraestrutura import CacheRespostas, gerar_chave
from avaliador.pontuacao.base import Situacao
from avaliador.provedores import ClienteLLM

ARQUIVOS_DO_JUIZ = {
    Formato.REDACAO: "juiz_redacao.txt",
    Formato.RESPOSTA_ABERTA: "juiz_resposta_aberta.txt",
}
NOTAS_POR_COMPETENCIA = range(0, 201, 40)


class AvaliacaoInvalida(ValueError):
    """O juiz respondeu, mas fora do formato pedido."""


def carregar_templates_do_juiz(pasta: Path = PASTA_PADRAO) -> dict[Formato, str]:
    templates = {}
    for formato, nome in ARQUIVOS_DO_JUIZ.items():
        caminho = pasta / nome
        texto = caminho.read_text(encoding="utf-8").strip() if caminho.exists() else ""
        if not texto:
            raise FileNotFoundError(f"template do juiz ausente ou vazio: {caminho}")
        templates[formato] = texto
    return templates


class PontuadorJuiz:
    """Pede a nota a outro modelo; a avaliação vai para o cache como qualquer resposta."""

    nome = "juiz"

    def __init__(
        self,
        cliente: ClienteLLM,
        juiz: ConfigModelo,
        provedor: ConfigProvedor,
        templates: Mapping[Formato, str],
        cache: CacheRespostas | None = None,
    ) -> None:
        self._cliente = cliente
        self._juiz = juiz
        self._provedor = provedor
        self._templates = templates
        self._cache = cache

    def pontuar(self, item: Item, resposta: Resposta) -> Pontuacao:
        if resposta.vazia:
            return self._pontuacao(item, resposta, Situacao.SEM_RESPOSTA)
        if not resposta.sucesso:
            return self._pontuacao(item, resposta, Situacao.ERRO_API)
        if item.visibilidade is Visibilidade.PRIVADO and self._provedor.treina_com_dados:
            motivo = f"item privado não é enviado a {self._provedor.nome}"
            return self._pontuacao(item, resposta, Situacao.ERRO_JUIZ, motivo=motivo)
        avaliacao = self._consultar(item, resposta)
        if not avaliacao.sucesso:
            return self._pontuacao(item, resposta, Situacao.ERRO_JUIZ, motivo=avaliacao.erro)
        try:
            nota, detalhes = _LEITORES[item.formato](avaliacao.texto)
        except AvaliacaoInvalida as erro:
            return self._pontuacao(item, resposta, Situacao.ERRO_JUIZ, motivo=str(erro))
        return self._pontuacao(item, resposta, Situacao.AVALIADA, nota, **detalhes)

    def _consultar(self, item: Item, resposta: Resposta) -> Resposta:
        conteudo = self._templates[item.formato].format(
            enunciado=item.enunciado,
            texto_base=f"{item.texto_base.strip()}\n\n" if item.texto_base else "",
            referencia=item.resposta_referencia
            or item.resposta_correta
            or "(sem referência: avalie pela correção factual)",
            resposta=resposta.texto,
        )
        mensagens = [{"role": "user", "content": conteudo}]
        id_avaliacao = f"juiz:{item.id}:{resposta.modelo_id}"
        chave = gerar_chave(
            self._juiz.id, id_avaliacao, resposta.tentativa, mensagens, self._juiz.parametros
        )
        if self._cache is not None and (guardada := self._cache.obter(chave)) is not None:
            return guardada
        avaliacao = self._cliente.responder(self._juiz, id_avaliacao, mensagens, resposta.tentativa)
        if avaliacao.sucesso and self._cache is not None:
            self._cache.guardar(chave, avaliacao)
        return avaliacao

    def _pontuacao(
        self,
        item: Item,
        resposta: Resposta,
        situacao: Situacao,
        nota: float = 0.0,
        **detalhes: Any,
    ) -> Pontuacao:
        return Pontuacao(
            item_id=item.id,
            modelo_id=resposta.modelo_id,
            pontuador=self.nome,
            nota=nota,
            tentativa=resposta.tentativa,
            detalhes={"situacao": situacao.value, "juiz": self._juiz.id, **detalhes},
        )


def ler_json_da_avaliacao(texto: str) -> dict[str, Any]:
    """Último objeto JSON do texto: o juiz às vezes escreve antes ou usa bloco ```json."""
    decodificador = json.JSONDecoder()
    inicios = [posicao for posicao, caractere in enumerate(texto) if caractere == "{"]
    for inicio in reversed(inicios):
        try:
            objeto, _ = decodificador.raw_decode(texto, inicio)
        except json.JSONDecodeError:
            continue
        if isinstance(objeto, dict):
            return objeto
    raise AvaliacaoInvalida("o juiz não devolveu um JSON")


def ler_avaliacao_de_redacao(texto: str) -> tuple[float, dict[str, Any]]:
    dados = ler_json_da_avaliacao(texto)
    competencias = {}
    for numero in range(1, 6):
        valor = dados.get(f"c{numero}")
        if isinstance(valor, bool) or not isinstance(valor, int | float):
            raise AvaliacaoInvalida(f"c{numero} ausente ou não numérica: {valor!r}")
        if valor not in NOTAS_POR_COMPETENCIA:
            raise AvaliacaoInvalida(f"c{numero} = {valor}, mas só vale 0, 40, 80, 120, 160 ou 200")
        competencias[f"c{numero}"] = int(valor)
    total = sum(competencias.values())
    justificativa = str(dados.get("justificativa", ""))
    return total / 1000, {**competencias, "total": total, "justificativa": justificativa}


def ler_avaliacao_de_resposta_aberta(texto: str) -> tuple[float, dict[str, Any]]:
    dados = ler_json_da_avaliacao(texto)
    valor = dados.get("nota")
    if isinstance(valor, bool) or not isinstance(valor, int | float) or not 0 <= valor <= 10:
        raise AvaliacaoInvalida(f"nota deve ir de 0 a 10, recebido {valor!r}")
    return valor / 10, {"nota_juiz": valor, "justificativa": str(dados.get("justificativa", ""))}


_LEITORES: dict[Formato, Callable[[str], tuple[float, dict[str, Any]]]] = {
    Formato.REDACAO: ler_avaliacao_de_redacao,
    Formato.RESPOSTA_ABERTA: ler_avaliacao_de_resposta_aberta,
}
