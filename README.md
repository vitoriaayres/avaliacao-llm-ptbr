# Avaliação de LLMs em português brasileiro

Benchmark aberto para medir como modelos de linguagem se saem em **português do Brasil**: questões do ENEM, interpretação de texto, ironia e implícitos, vida prática no Brasil e redação no modelo do ENEM.

Tudo roda com **acesso gratuito**: Groq, Ollama local, GPU do Kaggle e, opcionalmente, Gemini, OpenRouter, Mistral e GitHub Models.

## Resultados

Primeira rodada, em novembro de 2026: 73 questões do ENEM 2024 (40 de conhecimento e 33 de interpretação), com temperatura 0 e os mesmos prompt e `max_tokens` para todos os modelos.

| Posição | Modelo | Geral | IC de 95% | Conhecimento | Interpretação |
|---|---|---|---|---|---|
| 1 | Qwen3.8 27B | 97,0% | 92,4 a 100 | 100% | 93,9% |
| 2 | GPT-OSS 120B | 93,9% | 87,9 a 98,5 | 100% | 87,9% |
| 3 | GPT-OSS 20B | 89,7% | 82,1 a 95,7 | 97,5% | 81,8% |

**Os três modelos estão estatisticamente empatados:** com 73 questões, a ordem acima não aponta um vencedor. A nota geral é a média das categorias.

- O GPT-OSS 20B não entregou resposta em 2 questões: raciocinou até esgotar o limite de tokens, mesmo quando testado com 6500. Essas questões contam como nota 0.
- A rodada cobre só questões de texto do ENEM. Ainda não há redação, pragmática ou vida prática no Brasil no placar.
- Todas as questões são posteriores à data de corte dos GPT-OSS, então não há grupo anterior para medir contaminação. O Qwen não tem data de corte configurada.

## Por que outro benchmark

Os placares populares são em inglês, e traduzir questões não mede o que importa para quem usa os modelos no Brasil: entender a norma culta e o falar regional, a cultura, as instituições e os implícitos da língua. Este projeto tenta medir isso com o rigor que costuma faltar em comparações informais:

- **Intervalo de confiança em toda nota.** Com dezenas de itens, uma diferença de 3 pontos é ruído, e o placar diz isso explicitamente.
- **Itens privados (held-out)** para detectar contaminação, e que nunca são enviados a provedores que treinam com os dados.
- **Variantes com alternativas giradas** para separar quem sabe a resposta de quem tem preferência por uma letra.
- **LLM como juiz com limites declarados:** rubrica das 5 competências do ENEM, detecção de autopreferência e validação contra notas humanas.

Detalhes e limitações em [METODOLOGIA.md](METODOLOGIA.md).

## Como rodar

```bash
git clone https://github.com/vitoriaayres/avaliacao-llm-ptbr.git
cd avaliacao-llm-ptbr
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev,ferramentas,painel]"
cp .env.exemplo .env                                 # e preencha GROQ_API_KEY (grátis em console.groq.com)
```

```bash
avaliador validar                                    # confere o dataset
avaliador modelos                                    # chaves e cota restante por modelo
avaliador executar --limite 20 --nome teste          # 20 itens por categoria, todos os modelos
avaliador pontuar teste                              # placar com IC de 95%
avaliador exportar teste                             # leaderboard.json para o painel
streamlit run painel/app.py                          # painel interativo
```

### Questões do ENEM

As questões não ficam no repositório, porque os textos de apoio têm direitos de terceiros. Gere-as a partir dos PDFs oficiais do [INEP](https://www.gov.br/inep/pt-br/areas-de-atuacao/avaliacao-e-exames-educacionais/enem/provas-e-gabaritos):

```bash
avaliador extrair-enem prova_2024_dia1_azul.pdf gabarito_2024_dia1_azul.pdf --ano 2024 --data-prova 2024-11-03
```

### Modelos maiores na GPU do Kaggle

Abra [`kaggle/avaliar_no_kaggle.ipynb`](kaggle/avaliar_no_kaggle.ipynb) no Kaggle com GPU ligada. O notebook instala o Ollama, baixa o modelo e roda o benchmark.

## Como contribuir com itens

O maior gargalo é ter **itens bons**. Rode `avaliador novo-item`: o comando faz as perguntas no terminal, valida o item contra o esquema e o salva em `dados/publico/<categoria>/itens_proprios.jsonl`. Use `--privado` para itens que não devem ser publicados.

Bons itens são inequívocos (uma resposta defensável), específicos do Brasil e com fonte. As categorias mais carentes hoje são `pragmatica`, `brasil_pratico`, `cultura` e `vies_regional`.

## Estrutura

```
avaliador/
  dominio/        Item, Resposta e Pontuacao (tipos imutáveis e validados)
  dados/          carga e validação do dataset (JSON Schema + regras por formato)
  infraestrutura/ cache SQLite, limitador de taxa e logs
  provedores/     cliente único via LiteLLM, com nova tentativa só para erros transitórios
  execucao/       montagem de prompt e executor (cache, cota, privacidade)
  pontuacao/      extrator de alternativa, juiz, variantes e vieses
  analise/        placar, bootstrap, concordância e contaminação
  ferramentas/    extrator do ENEM, novo item e leaderboard
configuracao/     provedores, modelos e juízes (YAML)
prompts/          templates de prompt e do juiz
painel/           painel em Streamlit
```

## Licença

Código sob [MIT](LICENSE). Itens próprios em `dados/publico/` sob CC BY 4.0. Questões do ENEM: © INEP e autores dos textos de apoio, geradas localmente e não redistribuídas.
