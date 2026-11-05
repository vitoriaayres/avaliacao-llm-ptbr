---
title: Execução e pontuação
type: subsystem
created: 2026-11-05
updated: 2026-11-05
sources:
  - code: avaliador/execucao/executor.py
  - code: avaliador/pontuacao/exato.py
  - code: avaliador/pontuacao/juiz.py
  - code: avaliador/pontuacao/base.py
  - code: avaliador/dominio/resposta.py
  - code: avaliador/provedores/cliente.py
  - code: avaliador/cli.py
  - code: configuracao/modelos.yaml
verified_at: 21a03a2
---

# Execução e pontuação

Uma rodada tem três comandos: `avaliador executar` gera `resultados/<nome>/respostas.jsonl`, `avaliador pontuar` gera `pontuacoes.jsonl` e `placar.csv`, e `avaliador exportar` publica `resultados/publicados/leaderboard.json` para o painel.

## Execução

O executor percorre modelo por item. Se a chave já está no cache, reaproveita a resposta; senão, chama o provedor. Só respostas com sucesso entram no cache, então uma nova execução refaz as falhas. A chave combina modelo, item, tentativa, mensagens e parâmetros.

> ⚠️ `executar` abre `respostas.jsonl` com `"w"` e recria o arquivo (`avaliador/execucao/executor.py`). Para retomar uma rodada, repita `--nome` com **todos** os modelos dela. Rodar só um modelo apaga do arquivo as respostas dos outros, mesmo que elas continuem no cache.

> ⚠️ Mudar `max_tokens` ou outro parâmetro muda a chave do cache e refaz todas as respostas do modelo. O Qwen tem limite de 1 requisição por minuto em `configuracao/modelos.yaml`, então 76 questões levam cerca de 76 minutos.

> ⚠️ O limite de tokens por minuto da Groq considera o `max_tokens` pedido. Em testes com o GPT-OSS 20B, chamadas seguidas com limites altos receberam `RateLimitError` no limite de 8000 tokens por minuto. Testes manuais precisam de pausa entre as chamadas.

## Pontuação

Situações `erro_api` e `erro_juiz` ficam fora da média, porque indicam falha de infraestrutura. Resposta vazia é falha do modelo: a propriedade `Resposta.vazia` faz os pontuadores exato e juiz registrarem `sem_resposta`, com nota 0, e o juiz nem é chamado.

> ⚠️ `Resposta.vazia` compara o campo `erro` com o texto `ERRO_RESPOSTA_VAZIA` (`avaliador/dominio/resposta.py`), e esse texto fica salvo nos `respostas.jsonl` antigos. Se ele mudar, respostas vazias já gravadas voltam a contar como `erro_api` e saem da média.

> ⚠️ Sem `--prefixo-item`, `pontuar` inclui as questões de exemplo que estiverem na rodada. O placar do ENEM 2024 usa `--sem-juiz --prefixo-item enem-2024-`, e `exportar` herda esse recorte porque lê `pontuacoes.jsonl`.

## Caso conhecido

Na rodada `enem-2024`, o GPT-OSS 20B não respondeu `enem-2024-q030` e `enem-2024-q031`. Ele esgotou 2048 tokens raciocinando e repetiu o resultado com 4096 e 6500. Por isso o limite não foi aumentado: a metodologia exige o mesmo `max_tokens` para todos, e o aumento não resolveu. A causa exata do raciocínio longo não foi confirmada (unverified).
