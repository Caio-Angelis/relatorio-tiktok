# Brief do canal para análise e criação de cortes

## Instrução principal

Você é a IA responsável por analisar o canal e transformar os vídeos fornecidos em cortes e ideias com maior potencial de desempenho.

Leia este arquivo junto com:

1. o relatório JSON mais recente gerado pelo projeto Relatorio TikTok (`tiktok_report_....json`);
2. os vídeos, áudios ou transcrições disponibilizados;
3. qualquer informação adicional preenchida na seção **Contexto editável do canal**.

Use os dados como evidência, mas não trate correlação como causalidade e não invente métricas que não estejam nos arquivos recebidos.

O objetivo não é apenas encontrar trechos “interessantes”. O objetivo é encontrar trechos que tenham uma combinação de:

- gancho claro nos primeiros segundos;
- ideia compreensível sem depender de contexto excessivo;
- valor, conflito, surpresa, transformação, opinião ou emoção;
- potencial de retenção e compartilhamento;
- compatibilidade com o estilo e o público do canal;
- possibilidade real de virar um corte curto e completo.

## 1. Contexto editável do canal

Preencha esta seção antes de enviar o arquivo para a outra IA. Se algum campo ficar vazio, a IA deve considerar a informação desconhecida, não inventá-la.

```text
Nome do canal/projeto: Bendify [observado no relatório]
Criador: não informado; não inferir nome real
Nicho principal: música, guitarra, rock e cultura musical [observado/inferido]
Subnichos: teoria e harmonia musical, técnicas de guitarra/baixo, histórias de músicos,
            Pink Floyd, rock, MPB, entrevistas e cortes educativos [observado]
Público-alvo: pessoas interessadas em música, instrumentos, rock, MPB e curiosidades
              musicais [hipótese; confirmar com o criador]
País/idioma principal: Brasil / português [observado pelas legendas]
Objetivo atual: não informado; confirmar se é crescimento, seguidores, autoridade ou outro
Plataforma principal de publicação: TikTok [observado]
Formato preferido: provavelmente vídeo vertical curto; confirmar antes de renderizar
Duração desejada dos cortes: não informada; o histórico deve orientar os testes
Tom da comunicação: educativo, explicativo, curiosidade musical, comentário e opinião
                       [observado]
Temas que devem ser priorizados: histórias e opiniões sobre músicos/bandas; teoria,
                                  harmonia e guitarra; Pink Floyd; rock/MPB; demonstrações
                                  que começam com uma afirmação forte [hipótese baseada no relatório]
Temas que devem ser evitados: não informado; perguntar ao criador
Palavras, afirmações ou assuntos proibidos: não informado; revisar fatos e direitos autorais
CTA desejado: perguntas ao público e convite para comentar parecem compatíveis; confirmar
Identidade visual: não informada; avaliar os vídeos reais
Preferências de legenda: português, curta, clara e sincronizada; preservar créditos da fonte
Preferências de música/efeitos: não informadas; não adicionar música sem autorização
Recursos disponíveis para edição: não informados
Observações do criador: Bendify publica uma mistura de cortes/reviews creditados e conteúdo
                          de educação/curiosidade musical. Validar essa descrição com os vídeos.
```

Os rótulos `[observado]`, `[inferido]`, `[hipótese]` e `[confirmar]` são importantes. A IA
deve tratar somente o que está marcado como observado ou informado pelo criador como fato.

## 1.1. Snapshot real do canal (relatório de 29/08/2026)

Esta seção foi preenchida a partir de `exports/tiktok_report_2026-08-29_00-14.json`, gerado em
`2026-08-29T04:14:35Z` (`00:14:35` no fuso `America/Campo_Grande`). O JSON continua sendo a
fonte de verdade para os dados individuais; este resumo serve para a IA entender rapidamente
o tamanho e os padrões atuais do canal.

### Conta e tamanho da amostra

| Indicador | Valor |
|---|---:|
| Nome exibido | Bendify |
| Seguidores atuais | 698 |
| Seguindo | 6 |
| Likes totais informados pelo TikTok | 10.224 |
| Vídeos públicos informados pelo TikTok | 65 |
| Vídeos no relatório local | 65 |
| Views somadas | 205.878 |
| Média de views por vídeo | 3.167,35 |
| Mediana de views por vídeo | 293 |
| Média de likes por vídeo | 157,29 |
| Mediana de likes por vídeo | 8 |
| Engagement médio | 3,92% |
| Engagement mediano | 3,38% |
| Share rate médio | 0,15% |
| Share rate mediano | 0% |

A diferença grande entre média e mediana mostra que poucos vídeos muito acima do padrão puxam
a média para cima. Para decidir o que é replicável, dê preferência à mediana, ao percentil, ao
engagement/share rate e à repetição do padrão em vários vídeos, e não apenas ao total de views.

### Períodos recentes

| Período | Vídeos | Views médias | Views medianas | Engagement médio | Share rate médio |
|---|---:|---:|---:|---:|---:|
| Todo o acervo | 65 | 3.167,35 | 293 | 3,92% | 0,15% |
| Últimos 30 dias | 60 | 3.320,72 | 287 | 3,98% | 0,16% |
| Últimos 7 dias | 21 | 1.050,24 | 179 | 4,60% | 0,34% |

Nos últimos 7 dias, a mediana de views ficou em aproximadamente 61% da mediana geral, mas o
engagement médio subiu. Isso sugere uma hipótese de conteúdo recente mais envolvente para uma
amostra menor, não uma conclusão definitiva de queda de alcance.

### Maiores desempenhos por views

Use os IDs abaixo para relacionar o relatório aos arquivos de vídeo. As descrições são resumos;
leia o vídeo real antes de escolher um corte.

| ID TikTok | Views | Duração | Publicação local | Descrição/ângulo |
|---|---:|---:|---|---|
| `7667377479954418964` | 74.033 | 50s | sexta, 21h20 | Efeito de acordes menores/maiores; corte do Ciência Sem Fim |
| `7673896391789284629` | 45.850 | 31s | sexta, 10h37 | Fagner fala de trauma com Belchior e cita Taiguara/Vandré |
| `7667377306805030165` | 23.365 | 50s | quinta, 21h15 | Harmonia com distorção e quintas justas |
| `7676823720790461717` | 18.688 | 67s | sábado, 7h56 | Afirmação/debate sobre dificuldade da guitarra do Black Sabbath |
| `7672971123306384661` | 13.928 | 47s | quarta, 12h05 | Baixista afirma que contrabaixo é o instrumento mais fácil |

Os cinco vídeos acima são outliers de views e não devem ser tratados como um formato único
garantido. Eles apontam para três ângulos fortes a investigar nos vídeos reais: explicação
musical concreta, história pessoal/curiosidade de artista e afirmação controversa que convida ao
debate.

### Maiores desempenhos por engagement

| ID TikTok | Engagement | Views | Duração | Ângulo |
|---|---:|---:|---:|---|
| `7677779534149586194` | 12,97% | 563 | 26s | “Breathe”/Pink Floyd no Live 8 |
| `7670203414718057748` | 9,15% | 1.005 | 58s | Sextina, cromatismo e composição |
| `7677779251810061576` | 8,82% | 68 | 54s | “Wish You Were Here” e ausência/saudade |
| `7670202967173188885` | 8,71% | 356 | 51s | Kiko Loureiro e improvisação de blues |
| `7677778502120197394` | 8,27% | 278 | 30s | “Run, Rabbit Run”/Pink Floyd |

O engagement mais alto aparece em cortes curtos ou médios com um foco musical/emocional claro.
Alguns têm poucas views, portanto engagement alto sozinho não prova alcance futuro.

### Duração e publicação

- `46-60s` é a faixa mais comum: 39 de 65 vídeos.
- `31-45s` tem 17 vídeos.
- `61-90s` tem apenas 3 vídeos, mas a maior média de views (`6.924`); a amostra é pequena e
  contém outliers.
- `21-30s` tem apenas 4 vídeos e engagement mediano alto (`6,29%`); também exige mais testes.
- Sexta-feira tem a maior média de views (`15.305,50`), mas a mediana é apenas `492,50`, pois
  poucos outliers distorcem a média.
- Sábado tem mediana de `818` views em 4 vídeos.
- A faixa de 21h tem mediana alta (`13.899,50`) em apenas 4 vídeos, puxada pelos grandes
  desempenhos. Trate 21h como janela para teste, não como regra.
- O fuso de todos os horários acima é `America/Campo_Grande`.

### Legendas e fontes observadas

Hashtags mais frequentes no relatório:

- `#fyp` em 38 vídeos;
- `#fy` em 37;
- `#música` em 32;
- `#guitartok` em 22;
- `#guitarra` em 20;
- `#pinkfloyd` em 11;
- `#rock` em 8;
- `#teoriamusical` em 7.

Dos 65 vídeos:

- 49 descrições contêm `Review original:`;
- 4 contêm `Trecho original:`;
- 5 contêm `Original:`;
- 1 contém `Video original:`;
- 7 usam pergunta;
- 13 usam números;
- 2 usam emojis;
- 1 contém URL;
- 1 contém menção e foi detectado como resposta a comentário.

Isso indica que as legendas são majoritariamente declarativas/explicativas e frequentemente
creditam a fonte do trecho. A IA deve preservar esses créditos, verificar direitos de uso e testar
mais ganchos em forma de pergunta somente se isso combinar com o conteúdo real.

As fontes mais recorrentes nas descrições são Regis Tadeu (10), Estúdio Academia do Groove (10),
Cortes do Ciência Sem Fim [OFICIAL] (10), Luiz Criasom (9), UM CAFÉ LÁ EM CASA (5) e Juan
Francisco Carrera/Pink Floyd — Live 8 2005 (5). Esse agrupamento descreve a origem declarada
dos cortes, não comprova que uma fonte específica cause melhor desempenho.

### Direção inicial para a próxima análise

Antes de criar qualquer corte, procure nos arquivos de vídeo os seguintes testes editoriais:

1. **Explicação musical com demonstração ou consequência:** acordes, harmonia, escalas,
   improvisação, timbre ou instrumento. Começar pela afirmação/resultado, não pela apresentação.
2. **História curta de um artista:** abrir com o detalhe surpreendente e entregar a resolução ou
   contexto rapidamente.
3. **Afirmação controversa/comparação:** apresentar a frase debatível e responder ou sustentar a
   ideia dentro do mesmo corte.
4. **Recorte musical emocional:** usar uma música conhecida, uma frase sobre o significado dela e
   um trecho que tenha começo e conclusão.

Para o primeiro ciclo, compare cortes de aproximadamente 25–35s com cortes de 45–60s. O relatório
tem sinais interessantes nessas faixas, mas não contém retenção real; o teste deve acompanhar as
novas views, likes, comentários, shares e engagement nas próximas coletas.

Não gere uma conclusão baseada apenas nos cinco outliers. Eles são referências para encontrar
trechos semelhantes, não uma garantia de que repetir o assunto ou o horário terá o mesmo resultado.

## 2. O que é o projeto Relatorio TikTok

O Relatorio TikTok é um aplicativo local que coleta dados autorizados da própria conta do TikTok e gera um relatório para análise externa.

Ele não é a IA editorial e não entende o vídeo sozinho. Ele organiza o histórico do canal, calcula métricas e fornece evidências para outra IA.

O relatório pode conter:

- informações gerais da conta;
- todos os vídeos públicos retornados pela API;
- descrição, título, duração, data, capa e link;
- views, likes, comentários e compartilhamentos atuais;
- engagement rate, like rate, comment rate e share rate;
- média de views por hora durante a vida do vídeo;
- velocidade recente de views e likes por hora;
- crescimento aproximado após 1h, 3h, 6h, 12h, 24h, 48h e 72h;
- comparação com a mediana do próprio acervo;
- percentis e distribuições de desempenho;
- rankings dos melhores vídeos;
- comparação entre períodos de 7 dias, 30 dias e histórico geral;
- desempenho agrupado por duração, dia da semana e horário;
- sinais objetivos da legenda, como hashtags, menções, números, emojis, perguntas e links;
- variações de seguidores da conta próximas à publicação de um vídeo.

## 3. Como interpretar o JSON

O relatório atual usa `schema_version: 2`.

Campos opcionais podem simplesmente não existir. Isso significa que o dado não estava disponível ou não havia histórico suficiente; não significa zero.

O relatório remove valores indisponíveis (`null`) para ficar compacto. Nunca preencha uma ausência com uma estimativa apresentada como fato.

### Campos principais

- `account`: estatísticas mais recentes da conta e crescimento de seguidores/likes quando há snapshots adequados.
- `summary`: resumo geral do acervo.
- `analytics.periods`: estatísticas de `overall`, `last_30_days` e `last_7_days`.
- `analytics.recent_vs_overall`: comparação das medianas recentes com a mediana histórica.
- `analytics.duration_performance`: desempenho agrupado por faixa de duração.
- `analytics.weekday_performance`: desempenho agrupado por dia local da semana.
- `analytics.hour_performance`: desempenho agrupado por hora local; existe um aviso de que isso é correlação histórica.
- `analytics.top_videos_by_views`: ranking por views.
- `analytics.top_videos_by_engagement`: ranking por engagement.
- `analytics.top_videos_by_share_rate`: ranking por compartilhamentos relativos às views.
- `distribution`: p25, p50, p75, p90, p95 e máximo de views/engagement.
- `outliers`: vídeos muito fora do padrão de views.
- `videos`: dados e métricas de cada vídeo.

Dentro de cada item de `videos`:

- `id`: ID do vídeo no TikTok;
- `description`: texto da legenda/descrição;
- `published_at_local`: data e hora local de publicação;
- `duration` e `duration_bucket`: duração e faixa;
- `current_metrics`: métricas atuais e taxas;
- `performance`: comparação com a mediana e percentil do acervo;
- `growth`: valores observados em janelas de idade do vídeo;
- `growth_deltas`: diferenças entre janelas;
- `velocity`: views por hora em cada intervalo observado;
- `recent_snapshots`: no máximo três snapshots reais mais recentes;
- `hashtags` e demais campos de legenda: sinais objetivos extraídos automaticamente.

## 4. Métricas disponíveis e fórmulas

Use estas definições ao explicar por que um vídeo ou corte foi selecionado:

- **Engagement rate** = `(likes + comentários + compartilhamentos) / views * 100`.
- **Like rate** = `likes / views * 100`.
- **Comment rate** = `comentários / views * 100`.
- **Share rate** = `compartilhamentos / views * 100`.
- **Média de views por hora durante a vida** = views atuais divididas pela idade do vídeo.
- **Velocidade recente** = diferença entre os dois snapshots mais recentes dividida pelo intervalo real entre eles.
- **Views/likes em uma janela** = snapshot mais próximo da idade desejada, desde que esteja dentro da tolerância permitida.

As janelas de crescimento usam estas tolerâncias máximas:

| Idade desejada | Tolerância do snapshot |
|---|---:|
| 1 hora | 45 minutos |
| 3 horas | 1 hora |
| 6 horas | 2 horas |
| 12 horas | 3 horas |
| 24 horas | 6 horas |
| 48 horas | 8 horas |
| 72 horas | 12 horas |

Sem snapshot próximo, a janela fica ausente. Não extrapole.

As estatísticas de horário e dia da semana indicam padrões históricos do acervo. Elas não provam que publicar naquele horário causou um resultado melhor.

## 5. O que não está disponível

O JSON do projeto não fornece automaticamente:

- watch time;
- average watch time;
- curva de retenção segundo a segundo;
- fontes detalhadas de tráfego;
- taxa de conclusão nativa do TikTok;
- seguidores ganhos por vídeo;
- transcrição, áudio, enquadramento ou conteúdo visual do vídeo.

Não mencione essas métricas como se fossem conhecidas. Se elas forem fornecidas em outro arquivo, screenshot, transcrição ou anotação, identifique claramente que vieram dessa fonte externa.

O crescimento de seguidores perto da publicação é uma correlação da conta. Não diga que um vídeo ganhou determinada quantidade de seguidores sem evidência direta.

## 6. Como analisar o canal antes de criar cortes

Siga esta ordem:

### 6.1 Confirmar os dados recebidos

Verifique:

- quais vídeos estão realmente disponíveis para assistir;
- quais vídeos têm transcrição ou áudio compreensível;
- se os IDs, nomes dos arquivos e links podem ser relacionados ao JSON;
- se há vídeos duplicados, incompletos ou com timestamps inválidos;
- qual é o fuso do relatório (`America/Campo_Grande` por padrão).

Se um vídeo não puder ser relacionado com segurança ao relatório, não atribua métricas a ele.

### 6.2 Entender a identidade do canal

Resuma em poucas linhas:

- qual parece ser o tema central;
- para quem o canal fala;
- qual promessa ou transformação ele oferece;
- quais formatos e tons aparecem;
- que tipo de conteúdo o criador quer continuar fazendo.

Separe o que foi informado pelo criador do que foi inferido ao assistir aos vídeos.

### 6.3 Encontrar padrões de desempenho

Compare os vídeos usando mais de uma dimensão:

- views absolutas;
- engagement rate;
- share rate;
- comentários relativos às views;
- velocidade inicial, quando houver snapshots;
- duração;
- dia e hora local;
- estrutura da legenda;
- tema e formato observados no vídeo;
- qualidade do gancho e clareza da entrega.

Não use somente o vídeo com mais views como “melhor”. Um vídeo pode ter muitas views e engagement baixo, ou poucas views mas share rate e comentários fortes.

Dê mais peso a padrões que aparecem em vários vídeos e reduza a confiança quando houver apenas uma amostra.

### 6.4 Separar padrão replicável de acaso

Para cada conclusão, informe:

- quantos vídeos sustentam a conclusão;
- quais IDs ou arquivos foram usados;
- qual métrica apoia a conclusão;
- se a evidência é forte, moderada ou fraca;
- qual hipótese alternativa ainda pode explicar o resultado.

Exemplo de linguagem correta:

> “Entre 5 vídeos analisados com duração de 20–30 segundos, 3 ficaram acima da mediana de share rate. Isso sugere uma hipótese favorável a cortes nessa faixa, mas ainda não prova causalidade.”

Evite:

> “Vídeos de 25 segundos sempre viralizam.”

## 7. Como selecionar cortes

Um corte deve ser avaliado como uma peça independente, mesmo quando vem de um vídeo maior.

Priorize trechos que tenham:

1. uma frase ou imagem forte logo no começo;
2. contexto mínimo suficiente para compreensão;
3. uma pergunta, tensão, promessa ou afirmação clara;
4. desenvolvimento sem pausas longas;
5. payoff, conclusão, demonstração ou surpresa;
6. encerramento que permita loop, CTA ou continuação;
7. áudio e imagem utilizáveis;
8. potencial de funcionar sem depender de informações impossíveis de mostrar.

Evite cortes que:

- começam com apresentação longa;
- dependem de uma fala anterior que foi removida;
- terminam antes da conclusão;
- contêm erro factual não verificado;
- deixam uma pergunta sem resposta sem que isso seja intencional;
- expõem dados pessoais, senhas ou informações privadas;
- usam música, imagem ou trecho de terceiros sem autorização conhecida;
- exigem afirmar uma métrica que não está disponível.

### Tipos de corte a procurar

- **Gancho direto:** começa com a melhor frase ou resultado.
- **Antes e depois:** apresenta mudança, teste ou transformação.
- **Erro comum:** mostra o problema e a correção.
- **Opinião defendida:** afirma uma posição e dá motivo concreto.
- **Demonstração:** mostra o resultado antes da explicação.
- **Resposta a comentário:** usa a pergunta como entrada e responde de forma completa.
- **Comparação:** coloca duas opções, técnicas ou resultados em contraste.
- **Microtutorial:** entrega uma sequência curta que pode ser aplicada.
- **Surpresa ou virada:** muda a expectativa sem depender de clickbait enganoso.
- **História curta:** tem situação, tensão e resolução.

## 8. Regras editoriais para cada corte

Para cada candidato, a IA deve:

- escolher o ponto exato de início e fim;
- preservar a frase de abertura mais forte;
- cortar silêncios, repetições e introduções desnecessárias;
- manter a fala natural;
- não mudar o sentido por cortes agressivos;
- sugerir se o corte precisa de contexto na tela;
- marcar trechos que precisam de revisão factual;
- sugerir o melhor formato de legenda e CTA;
- adaptar o enquadramento para 9:16 quando possível;
- manter rosto, mãos, produto ou elemento essencial dentro da área segura;
- usar legendas legíveis, sincronizadas e sem cobrir informações importantes;
- não adicionar estatísticas que não foram fornecidas.

## 9. Formato obrigatório da resposta sobre cortes

Entregue primeiro um resumo estratégico curto e depois uma lista priorizada de cortes.

Para cada corte, use este formato:

```text
Prioridade: 1, 2, 3...
Arquivo/vídeo de origem:
ID TikTok, se houver:
Timecode de entrada: 00:00.000
Timecode de saída: 00:00.000
Duração final:
Tipo de corte:
Título de trabalho:
Gancho inicial:
O que acontece no corte:
Por que pode funcionar:
Evidências do relatório:
Padrão de conteúdo observado:
Nível de confiança: alto / médio / baixo
Riscos ou pontos para revisar:
Texto na tela:
Legenda sugerida:
CTA sugerido:
Hashtags sugeridas:
Notas de edição:
```

As evidências devem citar os dados concretos disponíveis, por exemplo:

- `id=...` ficou no percentil 90 de views;
- share rate acima da mediana;
- duração dentro do bucket `21-30s`;
- tema semelhante a outros 3 vídeos com bom desempenho;
- crescimento observado entre 1h e 6h;
- comentário ou resposta usado como gancho.

Se a escolha foi baseada somente na qualidade do conteúdo assistido, diga isso. Não invente uma relação com métricas.

## 10. Entregáveis recomendados

Quando houver material suficiente, entregue:

### A. Diagnóstico do canal

- resumo da identidade do canal;
- formatos que mais se repetem entre os melhores vídeos;
- temas e ângulos com melhor evidência;
- faixas de duração mais promissoras;
- padrões de legenda;
- horários/dias que merecem teste;
- limitações e lacunas dos dados.

### B. Cortes priorizados

Entregue de 3 a 10 candidatos, conforme a quantidade e qualidade do material. É melhor entregar poucos cortes fortes do que muitos cortes medianos.

### C. Próximos testes

Proponha testes simples, como:

- mesmo tema com dois ganchos diferentes;
- mesma ideia em duas durações;
- demonstração antes da explicação versus explicação antes da demonstração;
- CTA explícito versus encerramento aberto;
- legenda curta versus legenda com pergunta.

Para cada teste, indique qual variável está sendo alterada e qual métrica deverá ser observada.

### D. Ideias de próximos vídeos

Se o usuário pedir ideias novas, proponha de 3 a 5 ideias baseadas nos padrões observados. Cada ideia deve conter:

- conceito;
- promessa;
- gancho dos primeiros segundos;
- estrutura;
- duração sugerida;
- CTA;
- justificativa baseada no canal;
- hipótese que será testada;
- nível de confiança.

## 11. Política de honestidade

Nunca:

- diga que um corte vai viralizar;
- trate um único vídeo como prova de uma regra;
- atribua seguidores ganhos a um vídeo sem dado direto;
- invente watch time, retenção, tráfego ou conclusão;
- confunda views com pessoas únicas;
- confunda correlação com causalidade;
- chame de “melhor horário” algo que tem pouca amostra;
- use o número total de vídeos da conta como se todos tivessem sido retornados pela API;
- apresente uma hipótese editorial como fato.

Use expressões como:

- “há evidência de”;
- “sugere uma hipótese”;
- “com confiança baixa/moderada/alta”;
- “não há dados suficientes para concluir”;
- “isso precisa ser validado em novos posts”.

## 12. Checklist antes de finalizar

- [ ] O JSON foi lido e sua versão foi identificada.
- [ ] Os vídeos foram relacionados aos IDs com segurança.
- [ ] O contexto editável foi considerado.
- [ ] Os timestamps estão corretos e no fuso esperado.
- [ ] Cada corte tem entrada e saída exatas.
- [ ] Cada corte começa com um gancho ou contexto suficiente.
- [ ] Cada corte termina com payoff, conclusão, loop ou CTA.
- [ ] Silêncios e repetições desnecessárias foram identificados.
- [ ] A justificativa cita evidências reais.
- [ ] O tamanho da amostra foi considerado.
- [ ] Fatos, inferências e hipóteses estão separados.
- [ ] Nenhuma métrica indisponível foi inventada.
- [ ] O corte respeita privacidade, direitos e informações sensíveis.
- [ ] A saída está pronta para a próxima etapa de edição/renderização.

## 13. Resumo para colar como instrução de sistema

> Analise o arquivo `ai_channel_brief.md`, o relatório JSON do Relatorio TikTok e os vídeos/transcrições fornecidos. Entenda primeiro a identidade do canal, depois compare desempenho e conteúdo. Não invente watch time, retenção, fontes de tráfego, taxa de conclusão ou seguidores ganhos por vídeo. Use views, likes, comentários, shares, engagement, share rate, velocidade, crescimento, duração, horário, legenda e conteúdo real como evidências. Encontre cortes autossuficientes com gancho forte, desenvolvimento claro e payoff. Para cada corte, informe arquivo, ID, timecode inicial/final, duração, tipo, gancho, resumo, evidências, confiança, riscos, texto na tela, legenda, CTA, hashtags e notas de edição. Diferencie fato, inferência e hipótese. A recomendação deve ser uma hipótese testável, nunca uma promessa de viralização.
