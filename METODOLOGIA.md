# Metodologia

Este documento explica como o benchmark mede os modelos e onde estão os limites de cada medida. A regra geral: **toda decisão que pode mudar o placar está aqui, e tudo que o placar não consegue afirmar também.**

## 1. Dados

### Categorias

| Categoria | O que mede | Formatos |
|---|---|---|
| `conhecimento` | Fatos do currículo brasileiro (ENEM Ciências Humanas e itens próprios) | múltipla escolha, resposta aberta |
| `interpretacao` | Leitura e interpretação de textos em português (ENEM Linguagens) | múltipla escolha |
| `pragmatica` | Ironia, implícitos, polidez, sentido não literal | classificação |
| `brasil_pratico` | Vida prática no Brasil: SUS, Pix, INSS, CPF, direitos do consumidor | múltipla escolha, resposta aberta |
| `cultura` | Expressões regionais, referências culturais | classificação, resposta aberta |
| `vies_regional` | Respostas que mudam conforme a região mencionada | classificação |
| `escrita` | Redação dissertativo-argumentativa no modelo do ENEM | redação |

### Público e privado

- `dados/publico/` está no repositório e qualquer pessoa pode rodar.
- `dados/privado/` fica **fora do git** (held-out). Serve para detectar modelos que decoraram os itens públicos: se o acerto no público for muito maior que no privado, há sinal de contaminação.
- Itens privados **nunca** são enviados a provedores marcados com `treina_com_dados: true` (`configuracao/provedores.yaml`), nem para responder nem para julgar. Caso contrário, deixariam de ser privados.

### ENEM

As questões são extraídas dos PDFs oficiais do INEP com `avaliador extrair-enem`. A extração:

- descarta as questões 1 a 5 (inglês ou espanhol);
- descarta questões que provavelmente dependem de imagem (charge, gráfico, mapa, tirinha...), porque um modelo só de texto não tem como resolvê-las, e mantê-las mediria sorte;
- descarta questões cujas alternativas não foram lidas por inteiro;
- descarta questões anuladas (sem gabarito).

As questões do ENEM **não são versionadas**: os textos de apoio pertencem a terceiros. O repositório distribui o extrator, e cada pessoa gera os itens a partir dos PDFs públicos.

## 2. Execução

- **Temperatura 0** e `max_tokens` fixo (`configuracao/modelos.yaml`), iguais para todos os modelos.
- **O mesmo prompt para todos** (`prompts/`). Para itens objetivos, o modelo pode raciocinar antes, mas termina com `Resposta: X`. Isso favorece modelos que seguem formato, e essa é uma escolha consciente: seguir instrução faz parte de ser útil.
- **Cache:** cada resposta é guardada pela combinação de modelo, item, tentativa, prompt e parâmetros. Rodar de novo não gasta cota, e qualquer mudança no prompt gera chamadas novas.
- **Erros:** erros transitórios (excesso de requisições, timeout) são refeitos com espera crescente, respeitando o `retry-after` do provedor. Erros que persistem viram `erro_api` e **ficam fora da média**, porque são falha de infraestrutura, não do modelo.
- **Resposta vazia:** quando o provedor atende, mas o modelo não entrega texto (por exemplo, raciocina até esgotar `max_tokens`), a falha é do modelo: conta como `sem_resposta`, com nota 0.

## 3. Pontuação

### Itens objetivos

O extrator procura o último `Resposta: X`, ignorando negrito, maiúsculas e acentos. Sem esse marcador, aceita a última linha só quando ela é exatamente uma opção. **Ele nunca chuta.**

| Situação | Nota | Entra na média |
|---|---|---|
| `correta` | 1 | sim |
| `incorreta` | 0 | sim |
| `sem_resposta` (recusa, resposta vazia, opção inexistente, ambígua) | 0 | sim |
| `erro_api` / `erro_juiz` | 0 | **não** |

### Redação e respostas abertas: LLM como juiz

- A **redação** é avaliada nas 5 competências do ENEM, cada uma valendo 0, 40, 80, 120, 160 ou 200 (`prompts/juiz_redacao.txt`). A nota é o total dividido por 1000.
- A **resposta aberta** é comparada a uma resposta de referência, com nota de 0 a 10 (`prompts/juiz_resposta_aberta.txt`).
- O juiz responde em JSON. Se ele sair do formato, a resposta vira `erro_juiz` e não recebe nota inventada.
- O texto avaliado vai delimitado, e o juiz é instruído a ignorar instruções dentro dele (defesa contra prompt injection).

**Limites conhecidos do juiz:**

1. **Autopreferência.** Quando o juiz também é um dos modelos avaliados, ele tende a favorecer as próprias respostas. O relatório mostra a nota média que o juiz dá a cada modelo e marca a linha do próprio juiz.
2. **Validação contra humanos.** Antes de publicar notas de redação, corrija à mão uma amostra (30 ou mais redações) e rode `avaliador validar-juiz notas.csv` (colunas `humano,juiz`). Referência: kappa quadrático acima de 0,6 indica concordância boa. Sem essa validação, as notas de redação são indicativas, não medidas.

## 4. Estatística

- **Nota geral = média das categorias**, cada uma com o mesmo peso. Isso evita que a categoria com mais itens (hoje, o ENEM) domine o placar.
- **Repetições e variantes** de uma mesma questão viram uma nota só por questão antes da média, para que questões com mais versões não pesem mais.
- **Intervalo de confiança de 95% por bootstrap**, com 2.000 reamostragens dos itens dentro de cada categoria e semente fixa (reprodutível).
- **Empate com o líder:** a diferença para o 1º lugar é calculada nos mesmos itens (bootstrap pareado). Se o intervalo da diferença inclui 0, o modelo está **empatado** com o líder. Com poucos itens, a maioria dos modelos empata, e isso é informação, não defeito.

Ordem de grandeza: com 70 itens e acerto perto de 80%, o intervalo tem cerca de ±9 pontos percentuais. Diferenças menores que isso não devem virar manchete.

## 5. Robustez e vieses

- **Variantes (`--variantes N`):** a mesma questão com as alternativas giradas. Um modelo que acerta o original e erra a versão girada estava respondendo pela posição, não pelo conteúdo. O relatório mostra a **consistência** (fração das questões com o mesmo resultado em todas as versões).
- **Viés de posição:** a distribuição das letras escolhidas é comparada com a do gabarito.
- **Contaminação:** para modelos com `data_corte` configurada, o acerto em itens anteriores ao fim do treino é comparado com o acerto nos posteriores. Acerto bem maior "antes" sugere que o modelo viu as questões. Isso é um indício, não uma prova: provas de anos diferentes também mudam de dificuldade.

## 6. O que este benchmark não mede

- Desempenho em tarefas multimodais (as questões com imagem foram descartadas).
- Segurança, toxicidade ou alucinação em conversa livre.
- Velocidade e custo como critério de qualidade: a latência é registrada, mas não entra na nota.
- Modelos com prompts diferentes do padrão. Alguns modelos rendem mais com o próprio template; aqui todos recebem o mesmo, por comparabilidade.
