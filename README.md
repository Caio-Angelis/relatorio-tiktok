# Relatorio TikTok

O projeto tem duas partes independentes:

- **Site público:** os arquivos `index.html`, `terms.html`, `privacy.html` e `style.css` continuam na raiz e são publicados pelo GitHub Pages.
- **Aplicativo local:** a aplicação Flask fica em `app/`, usa SQLite local e roda somente no seu computador.

## Site público

- [Página principal](https://caio-angelis.github.io/relatorio-tiktok/)
- [Privacy Policy](https://caio-angelis.github.io/relatorio-tiktok/privacy.html)
- [Terms of Service](https://caio-angelis.github.io/relatorio-tiktok/terms.html)

O aplicativo não altera a publicação do GitHub Pages: a raiz pública continua sendo apenas o site estático.

## Requisitos

- Linux
- Python 3.10 ou mais recente
- Navegador para concluir a autorização no TikTok

## Instalação e configuração

Na raiz do repositório:

```bash
chmod +x run.sh
./run.sh
```

Na primeira execução, o script cria `.venv`, instala `app/requirements.txt` e, se necessário, cria `app/.env` a partir de `app/.env.example`. O arquivo `app/.env` está no `.gitignore` e nunca deve ser enviado ao GitHub.

Preencha estes valores em `app/.env` para usar a API real:

```dotenv
TIKTOK_CLIENT_KEY=cole_sua_client_key_aqui
TIKTOK_CLIENT_SECRET=cole_seu_client_secret_aqui
TIKTOK_REDIRECT_URI=http://localhost:3455/callback/
MOCK_TIKTOK=false
```

### Onde encontrar Client Key e Client Secret

No [TikTok for Developers](https://developers.tiktok.com/), entre na sua conta, abra o perfil, escolha **Manage apps**, selecione o app e copie **Client key** e **Client secret** da configuração dele. O secret deve permanecer somente em `app/.env`; não o coloque em HTML, JavaScript, screenshots, issues ou commits.

O `FLASK_SECRET_KEY` é opcional para uso local, mas pode ser preenchido com uma string aleatória para manter a assinatura da sessão estável entre reinícios. Ele também não deve ser publicado.

## Configuração no TikTok Developer Portal

Mantenha a plataforma como **Desktop** e cadastre exatamente:

```text
http://localhost:3455/callback/
```

O aplicativo solicita somente os scopes já configurados para este projeto:

- `user.info.basic`
- `user.info.stats`
- `video.list`

O fluxo Desktop usa `state` e PKCE. O TikTok exige um `code_verifier` novo por autorização e um `code_challenge` com SHA-256 em hexadecimal. O `client_secret` fica no backend Python, nunca no frontend.

## Iniciar e conectar

Depois de preencher o `.env`:

```bash
./run.sh
```

Abra [http://localhost:3455/](http://localhost:3455/), clique em **Conectar TikTok** e conclua a autorização no site oficial. Depois do callback, o app salva os tokens no SQLite local com permissões restritas e faz a primeira coleta.

O botão **Desconectar TikTok** tenta revogar o access token pelo endpoint oficial de revogação e sempre remove os tokens locais. Os dados históricos coletados permanecem no SQLite até que você remova o banco manualmente.

## Atualizar dados

Use **Atualizar dados agora** no dashboard. A operação:

1. consulta o perfil e as estatísticas autorizadas;
2. percorre todas as páginas de vídeos públicos disponíveis;
3. faz upsert dos vídeos sem duplicá-los;
4. salva um novo snapshot das métricas quando necessário;
5. recalcula os analytics locais.

Para evitar centenas de linhas idênticas, o app não salva um snapshot de vídeo se todas as métricas forem iguais às do snapshot anterior e ele tiver menos de 5 minutos. Se alguma métrica mudar, ou se passarem 5 minutos, uma nova linha é salva. A mesma regra é aplicada aos snapshots da conta.

## Dashboard e vídeos

O dashboard mostra seguidores, seguindo, likes, vídeos e a soma das views coletadas. A página **Vídeos** permite ordenar por data, views, likes, shares, engagement e share rate. Cada vídeo tem uma página própria com:

- capa, descrição, data, duração e link para o TikTok;
- métricas atuais;
- engagement rate, like rate, comment rate, share rate, média de views/hora durante a vida e velocidade recente;
- gráfico de evolução de views, likes, comentários ou shares;
- sinais objetivos derivados da descrição, como hashtags, menções, números, emojis e detecção conservadora de resposta a comentário.

O app não exige classificação manual, transcrição, download de vídeos ou recomendações por IA. As colunas antigas `category`, `format`, `hook` e `notes` continuam no SQLite somente para compatibilidade com bancos já existentes, mas não são usadas no novo relatório JSON nem no CSV.

## Exportações

Os botões do dashboard geram arquivos em `exports/`:

- `tiktok_report_YYYY-MM-DD_HH-MM.json`: relatório compacto versão `schema_version: 2` para análise no ChatGPT, com fatos coletados, medianas, distribuições, outliers robustos, períodos `overall`/`last_30_days`/`last_7_days`, rankings recentes, desempenho por duração/dia/hora, sinais da legenda e janelas de crescimento;
- `tiktok_report_YYYY-MM-DD_HH-MM.csv`: uma linha por vídeo com dados de publicação, sinais objetivos da legenda e métricas atuais. Não inclui campos manuais.

O JSON principal não exporta `metric_history`. Todos os snapshots brutos continuam preservados no SQLite; o relatório representa essa série por valores totais aproximados nas idades de 1h, 3h, 6h, 12h, 24h, 48h e 72h, além de deltas e velocidades entre janelas. Para cada idade, é escolhido o snapshot mais próximo somente dentro destas tolerâncias: ±45min, ±1h, ±2h, ±3h, ±6h, ±8h e ±12h, respectivamente. Sem um snapshot adequado, a chave é omitida e não há extrapolação. Cada vídeo também leva no máximo os três snapshots reais mais recentes.

As métricas derivadas usam o fuso `America/Campo_Grande`. `lifetime_average_views_per_hour` é a média desde a publicação; `recent_views_per_hour` e `recent_likes_per_hour` usam os dois snapshots mais recentes. Percentis ficam entre 0 e 100 e usam midrank; a distribuição usa interpolação linear. Outliers de views usam modified z-score com mediana e MAD, limiar 3.5. Estatísticas de horário são correlações históricas, não prova de causalidade.

Valores opcionais indisponíveis são omitidos do JSON compacto, em vez de preencher o arquivo com `null`. Essa compactação afeta somente o relatório destinado ao ChatGPT; não altera nem reduz o histórico bruto do SQLite.

Os arquivos são locais, têm permissão restrita quando o sistema permite e estão no `.gitignore`. Se dois exports ocorrerem no mesmo minuto, o segundo pode substituir o nome do primeiro; salve uma cópia se quiser conservar ambos.

## Banco e backup

Em modo real, o banco fica em:

```text
database/relatorio_tiktok.db
```

Ele é criado automaticamente na primeira execução. Em modo mock, o caminho padrão é `database/relatorio_tiktok_mock.db`, separado do banco real para não misturar dados fictícios.

Para fazer backup, pare o app e copie o banco para um local privado, por exemplo:

```bash
mkdir -p ~/backups/relatorio-tiktok
cp database/relatorio_tiktok.db ~/backups/relatorio-tiktok/relatorio_tiktok_$(date +%F).db
```

O backup contém tokens locais; trate-o como informação sensível e não o envie para o GitHub.

## Modo mock

Para ver o dashboard sem autenticar:

```dotenv
MOCK_TIKTOK=true
```

Execute `./run.sh` novamente. O app usará dados fictícios determinísticos e o banco `relatorio_tiktok_mock.db`; nenhum endpoint do TikTok será chamado. Volte para `MOCK_TIKTOK=false` antes de conectar a conta real.

## Dados disponíveis e limitações

Com os scopes atuais, a aplicação coleta, quando disponibilizados pelo TikTok:

- display name e avatar;
- follower count, following count, likes count e video count;
- ID do vídeo, descrição, título, data de publicação, duração, capa, link de compartilhamento, link de embed, dimensões;
- views, likes, comentários e shares;
- snapshots locais desses valores ao longo do tempo.

`username`, bio, link de perfil e status de verificação exigem `user.info.profile`. Esse scope não está configurado e não é solicitado automaticamente pelo app.

Os analytics locais calculam taxas, média, mediana, percentis, rankings, views/hora aproximados, janelas de crescimento, deltas, velocidade, períodos recentes, desempenho por duração e agrupamentos por dia/horário. O ChatGPT recebe fatos e métricas para fazer a interpretação estratégica; o aplicativo não classifica temas nem gera recomendações.

Não trate como disponíveis, porque estes scopes/endpoints não os fornecem neste app:

- watch time;
- average watch time;
- retention curve;
- traffic sources;
- completion rate;
- followers gained por vídeo.

O crescimento de seguidores associado a um vídeo é reportado apenas como correlação no nível da conta. O relatório não afirma que um vídeo causou essa mudança.

## Compatibilidade do banco

Esta melhoria é somente de analytics e exportação. O schema atual continua na versão existente, sem apagar tabelas, colunas ou snapshots. O banco é lido como fonte bruta; caso novas colunas sejam necessárias no futuro, elas devem ser adicionadas por migration incremental.

O TikTok também pode alterar permissões, disponibilidade de campos, conteúdo público e limites da API. A documentação atual informa limite padrão de 600 requisições por minuto para `/v2/user/info/`, `/v2/video/list/` e `/v2/video/query/`; quando excedido, a API pode responder HTTP 429 com `rate_limit_exceeded`.

## Endpoints oficiais usados

O código usa a geração atual da API, não os endpoints legados:

- Autorização Desktop: `https://www.tiktok.com/v2/auth/authorize/`
- Troca e refresh de token: `POST https://open.tiktokapis.com/v2/oauth/token/`
- Revogação: `POST https://open.tiktokapis.com/v2/oauth/revoke/`
- Perfil: `GET https://open.tiktokapis.com/v2/user/info/`
- Lista paginada de vídeos: `POST https://open.tiktokapis.com/v2/video/list/`

O método `video/query` também está implementado para consultas de até 20 IDs e atualização de dados de vídeo, mas a coleta normal usa `video/list`, que já retorna os campos necessários para o dashboard. Nenhum endpoint inventado é usado.

Referências oficiais:

- [Login Kit for Desktop](https://developers.tiktok.com/doc/login-kit-desktop)
- [User Access Token Management](https://developers.tiktok.com/doc/oauth-user-access-token-management)
- [Get User Info](https://developers.tiktok.com/doc/tiktok-api-v2-get-user-info/)
- [List Videos](https://developers.tiktok.com/doc/tiktok-api-v2-video-list/)
- [Query Videos](https://developers.tiktok.com/doc/tiktok-api-v2-video-query/)
- [Scopes Reference](https://developers.tiktok.com/doc/tiktok-api-scopes)
- [Rate Limits](https://developers.tiktok.com/doc/tiktok-api-v2-rate-limit)

## Testes

Com o ambiente instalado:

```bash
.venv/bin/pytest -q
```

Os testes cobrem PKCE, taxas, divisão por zero, crescimento com histórico, velocidade recente, distribuição, outliers MAD, rankings recentes, upsert de vídeos, deduplicação de snapshots, export JSON/CSV compacto (schema v2, sem nulls opcionais e com no máximo três snapshots recentes) e o fluxo básico do dashboard em modo mock.
