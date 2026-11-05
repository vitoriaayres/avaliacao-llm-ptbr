"""Pontuação objetiva: a opção extraída bate ou não com o gabarito."""

from __future__ import annotations

from avaliador.dominio import Formato, Item, Pontuacao, Resposta
from avaliador.pontuacao.base import Situacao
from avaliador.pontuacao.extrator_alternativa import extrair_opcao


class PontuadorExato:
    """Para múltipla escolha (letras) e classificação (rótulos)."""

    nome = "exato"

    def pontuar(self, item: Item, resposta: Resposta) -> Pontuacao:
        extraida = None
        if resposta.vazia:
            situacao = Situacao.SEM_RESPOSTA
        elif not resposta.sucesso:
            situacao = Situacao.ERRO_API
        else:
            opcoes = item.letras if item.formato is Formato.MULTIPLA_ESCOLHA else item.rotulos
            extraida = extrair_opcao(resposta.texto, opcoes)
            if extraida is None:
                situacao = Situacao.SEM_RESPOSTA
            elif extraida == item.resposta_correta:
                situacao = Situacao.CORRETA
            else:
                situacao = Situacao.INCORRETA
        return Pontuacao(
            item_id=item.id,
            modelo_id=resposta.modelo_id,
            pontuador=self.nome,
            nota=1.0 if situacao is Situacao.CORRETA else 0.0,
            tentativa=resposta.tentativa,
            detalhes={
                "situacao": situacao.value,
                "extraida": extraida,
                "gabarito": item.resposta_correta,
            },
        )
