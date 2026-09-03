# Contexto completo do projeto — Relatorio TikTok

> Documento de handoff para outra IA ou pessoa desenvolvedora. Ele descreve o estado do repositório após a implementação da camada de IA local em 2026-08-31. O código e os testes são a fonte de verdade; atualize este arquivo junto com mudanças de arquitetura ou de contrato.

## 1. Resumo executivo

O **Relatorio TikTok** é um projeto pessoal para coletar e analisar, localmente, dados autorizados da própria conta TikTok do usuário.

O repositório contém duas partes independentes:

1. **Site público estático**, na raiz, publicado pelo GitHub Pages. Ele apresenta o produto e hospeda Privacy Policy e Terms of Service exigidos para a integração com o TikTok.
2. **Aplicativo local Flask**, em `app/`, executado apenas no computador do usuário. Ele faz OAuth Desktop com PKCE, consulta a API oficial do TikTok, grava tokens e histórico em SQLite, calcula analytics determinísticos, oferece uma camada opcional de IA 100% local e exporta relatórios JSON/CSV.

Por padrão a IA fica desligada. Quando habilitada, o app baixa temporariamente um vídeo por vez, transcreve com faster-whisper, extrai frames, classifica com Qwen3-VL e cruza os dados semânticos com os fatos/métricas locais. Não há inferência remota, scraping manual, scheduler externo ou backend hospedado.

## 2. Objetivos e limites do produto

### O que o projeto faz

- Autoriza a própria conta do usuário pelo OAuth oficial do TikTok.
- Coleta perfil, estatísticas da conta, vídeos públicos e métricas dos vídeos.
- Preserva snapshots históricos locais para medir evolução.
- Mostra dashboard, lista de vídeos e detalhe com gráfico histórico.
- Calcula taxas, medianas, percentis, outliers, rankings e janelas de crescimento.
- Exporta JSON compacto voltado a análise externa e CSV tabular.
- Oferece modo mock determinístico, sem chamadas ao TikTok.
- Pode analisar semanticamente a biblioteca com um worker persistente local e gerar insights cacheados.

### O que deliberadamente não faz

- Não acessa senha do TikTok.
- Não coleta dados de outras contas sem autorização.
- Não inventa métricas ausentes.
- Não afirma causalidade a partir de dia, horário ou crescimento de seguidores.
- Não disponibiliza watch time, average watch time, retention curve, traffic sources, completion rate ou followers gained por vídeo, pois os scopes/endpoints usados não fornecem esses dados.
- Não exige `user.info.profile`; portanto username, bio, link do perfil e verificação ficam indisponíveis.
- Não envia automaticamente banco, tokens ou exports a serviços externos.
- Não envia vídeos, áudio, transcrições ou prompts a APIs de inferência.

## 3. Estado atual verificado

- Repositório remoto: `https://github.com/Caio-Angelis/relatorio-tiktok.git`.
- Branch: `main`, alinhada a `origin/main` no momento desta documentação.
- Último commit observado: `3c1bf53 Document report v2 and velocity metrics`.
- Stack: Python 3.10+, Flask 3, SQLite, Jinja, JavaScript puro e Chart.js via CDN.
- Testes históricos: **18 testes passando** em 2026-08-14; a suíte atual inclui os testes de IA e foi verificada com **35 testes passando**.
- Existem bancos e exports locais ignorados pelo Git. Eles são dados reais/de demonstração do usuário e não devem ser inspecionados, alterados ou commitados sem necessidade explícita.
- A implementação da camada IA e este handoff podem aparecer como mudanças locais até o próximo commit; bancos, exports, cache e segredos continuam ignorados.

## 4. Estrutura do repositório

```text
TikTokRelatorio/
├── README.md                         documentação de uso para humanos
├── ai_context.md                     este handoff técnico
├── run.sh                            bootstrap e execução do app local
├── index.html                        landing page pública
├── privacy.html                      política de privacidade pública
├── terms.html                        termos de serviço públicos
├── style.css                         CSS exclusivo do site público
├── tiktok9DI4...txt                  arquivo público de verificação do TikTok
├── app/
│   ├── __init__.py
│   ├── app.py                        factory Flask, rotas e integração da UI
│   ├── config.py                     leitura de ambiente e resolução de paths
│   ├── database.py                   schema SQLite e camada de acesso a dados
│   ├── tiktok_api.py                 OAuth/API, validação e normalização
│   ├── sync_service.py               tokens, refresh, coleta e persistência
│   ├── analytics.py                  métricas derivadas determinísticas
│   ├── exporter.py                   contrato JSON v2 e exportação CSV
│   ├── mock_tiktok.py                API fictícia determinística
│   ├── requirements.txt
│   ├── requirements-ai.txt           dependências opcionais de GPU/IA
│   ├── ai/                            pipeline, worker e estratégia local
│   ├── .env.example                  configuração segura de exemplo
│   ├── templates/                    páginas Jinja do app local
│   ├── static/                       CSS e JavaScript do app local
│   └── tests/                        suíte pytest
├── setup_ai.sh                        setup explícito de modelos/dependências
├── database/
│   └── .gitkeep                      bancos `*.db` locais são ignorados
└── exports/
    └── .gitkeep                      relatórios JSON/CSV locais são ignorados
```

Importante: `style.css` na raiz pertence ao site público; `app/static/style.css` pertence ao dashboard local. Não misturar os dois.

## 5. Como executar

Na raiz:

```bash
chmod +x run.sh
./run.sh
```

O `run.sh`:

1. exige `python3`;
2. cria `.venv` se não existir;
3. ativa o ambiente;
4. atualiza `pip` e instala `app/requirements.txt` em toda execução;
5. cria `app/.env` a partir de `app/.env.example` se necessário e encerra para o usuário configurá-lo;
6. executa `python -m app.app`.

O servidor escuta somente em `127.0.0.1:3455`, com `debug=False`.

Para testar:

```bash
.venv/bin/pytest -q
```

Dependências diretas:

- `Flask>=3.0,<4`
- `python-dotenv>=1.0,<2`
- `requests>=2.31,<3`
- `pytest>=8.0,<9`

Não há `pyproject.toml`, linter, formatter, type checker, pipeline de CI, Node/npm ou etapa de build frontend configurados.

## 6. Configuração e ambiente

`app/config.py` carrega primeiro `app/.env` e depois `.env` na raiz sem sobrescrever valores já carregados. `settings_from_env()` também aceita overrides, usados pelos testes.

| Variável | Padrão/função |
|---|---|
| `TIKTOK_CLIENT_KEY` | credencial do app TikTok; obrigatória no modo real |
| `TIKTOK_CLIENT_SECRET` | segredo do app; apenas backend/local |
| `TIKTOK_REDIRECT_URI` | `http://localhost:3455/callback/` |
| `TIKTOK_SCOPES` | `user.info.basic,user.info.stats,video.list` |
| `MOCK_TIKTOK` | `false`; aceita `1`, `true`, `yes` ou `on` |
| `FLASK_SECRET_KEY` | opcional; se vazio, muda aleatoriamente a cada processo |
| `APP_TIMEZONE` | `America/Campo_Grande` |
| `REQUEST_TIMEOUT` | `30` segundos |
| `TIKTOK_DATABASE_PATH` | banco real ou mock padrão em `database/` |
| `TIKTOK_EXPORTS_DIR` | `exports/` |
| `AI_ENABLED` | `false`; habilita apenas após `./setup_ai.sh` |
| `AI_DEVICE` | `cuda`; não há fallback silencioso para CPU |
| `AI_WHISPER_MODEL` / `AI_WHISPER_COMPUTE_TYPE` | `large-v3-turbo` / `float16` |
| `AI_VISION_MODEL` / `AI_VISION_DTYPE` | `Qwen/Qwen3-VL-8B-Instruct` / `bfloat16` |
| `AI_TEMP_DIR` | `tmp/tiktok_ai` |
| `AI_DELETE_TEMP_FILES` | `true`; remove o diretório do vídeo após sucesso |
| `AI_MAX_FRAMES` / `AI_MAX_IMAGE_SIDE` | `12` / `896` |
| `AI_DOWNLOAD_COOKIES_BROWSER` | vazio; aceita `chrome` ou `firefox` via yt-dlp |
| `AI_AUTO_ANALYZE_NEW_VIDEOS` | `false`; sync apenas deixa pendências visíveis por padrão |

Paths relativos são resolvidos contra a raiz do repositório e convertidos em paths absolutos.

Banco padrão:

- modo real: `database/relatorio_tiktok.db`;
- modo mock: `database/relatorio_tiktok_mock.db`.

Nunca registrar em logs, documentação ou commits os valores de `app/.env`, access tokens, refresh tokens ou dados privados dos bancos/exports.

## 7. Arquitetura e fluxo de dados

```text
Navegador local
    │
    ▼
Flask/Jinja (`app/app.py`)
    │
    ├── OAuth/API ──► `TikTokAPI` ──► endpoints oficiais do TikTok
    │
    ├── sincronização ──► `SyncService`
    │                         │
│                         ▼
    ├────────────────────► `Database` ──► SQLite local
    │                         │
    │                         ▼
    ├── páginas/exports ◄── analytics determinísticos
    │
    └── worker subprocesso ◄── fila IA SQLite
             │
             ├── yt-dlp → tmp/tiktok_ai/<id>/video.mp4
             ├── FFmpeg → WAV + frames temporários
             ├── faster-whisper large-v3-turbo (CUDA FP16)
             └── Qwen/Qwen3-VL-8B-Instruct (Transformers CUDA BF16)
                              │
                              ▼
                       JSON v2 / CSV / insights locais
```

Fluxo normal:

1. O usuário inicia `/auth/tiktok`.
2. O backend gera `state`, `code_verifier` e `code_challenge`, guardando estado/verifier na sessão Flask.
3. O TikTok redireciona para `/callback/` com `code` e `state`.
4. O backend valida `state`, troca o code por tokens e os salva no SQLite.
5. `SyncService.sync()` coleta perfil e todas as páginas de vídeos.
6. A conta e os vídeos são normalizados.
7. O banco faz upsert de metadados dos vídeos e acrescenta snapshots de métricas.
8. Dashboard e exportador leem vídeos + históricos e calculam analytics em memória.

Não existe job periódico. Novos snapshots só aparecem quando o usuário conecta, abre o dashboard mock pela primeira vez ou aciona **Atualizar dados agora**.

## 8. Responsabilidade de cada módulo

### `app/app.py`

- Cria e configura o Flask via `create_app(test_config=None)`.
- Inicializa banco, API real, API mock e `SyncService`.
- Expõe os objetos em `app.extensions` para testes/integrações.
- Define helpers de templates para números, percentuais, datas e URLs externas seguras.
- Gera e valida CSRF para todos os POSTs da UI/API local.
- Implementa OAuth, sincronização, páginas e downloads.
- Há também `app = create_app()` no import do módulo; importar `app.app` inicializa o banco padrão, além de disponibilizar a factory.

### `app/config.py`

- Centraliza configuração.
- Escolhe banco mock separado automaticamente.
- Resolve paths e oferece overrides de teste.

### `app/tiktok_api.py`

- Contém endpoints e fields oficiais.
- Gera PKCE/state.
- Encapsula requests HTTP e erros do TikTok em `TikTokAPIError`.
- Normaliza strings, inteiros, perfil e vídeos.
- Pagina `video/list` com `max_count=20` e proteção contra cursor inválido/repetido.
- Implementa `video/query` para até 20 IDs, embora o sync normal use `video/list`.

### `app/sync_service.py`

- Centraliza persistência e renovação dos tokens.
- Renova access token 120 segundos antes da expiração.
- Em erro 401/`invalid_token`/`token_expired`, tenta um refresh e uma única repetição.
- Limpa tokens quando o refresh expirou ou foi invalidado.
- Faz a coleta completa e retorna `SyncSummary`.
- Ao desconectar, tenta revogar remotamente, mas sempre remove os tokens locais.

### `app/database.py`

- Camada simples sobre `sqlite3`, sem ORM.
- Ativa foreign keys e `busy_timeout=5000` em cada conexão.
- Cria diretório/banco automaticamente.
- Tenta aplicar permissão `0600` ao banco.
- Usa `PRAGMA user_version`; schema atual é versão 2.

### `app/ai/`

- `config.py`: constantes de modelos/status e diagnóstico sem carregamento de pesos.
- `schemas.py`: `VideoSemanticAnalysis`, `StrategicIdea` e `StrategicReport` com Pydantic; há fallback mínimo apenas para o Flask/tests sem requirements de IA.
- `downloader.py`: `yt-dlp` por biblioteca Python, URL validada, ID seguro, cookies opcionais via `cookiesfrombrowser` e fallback MP4 local validado.
- `media.py`: `ffprobe`, FFmpeg mono/16 kHz, seleção de até 12 timestamps com viés nos primeiros 5s, resize sem upscale, average hash e limpeza segura.
- `transcriber.py`: uma instância reutilizável de faster-whisper `large-v3-turbo`, CUDA/FP16, idioma, segmentos e janelas 3s/5s.
- `vision.py`: uma instância reutilizável de `Qwen/Qwen3-VL-8B-Instruct` via Transformers, `torch.bfloat16`, `model.eval()` e `torch.inference_mode()`; sem GGUF/4-bit/bitsandbytes.
- `classifier.py`: prompt versionado, entrada sem métricas, parsing JSON sem regex ingênua, validação/normalização Pydantic e uma tentativa local de reparo.
- `pipeline.py`: download → áudio/transcrição → frames → classificação → checkpoint SQLite → limpeza, isolando falha por vídeo.
- `strategist.py`: analytics semânticos, score determinístico documentado, fingerprint/cache e recomendações prioritárias/experimentais no mesmo Qwen em modo texto.
- `worker.py`: CLI, subprocesso único, lock `fcntl`, recuperação de estados interrompidos, pausa após o vídeo atual e self-test sintético.
- `mock.py`: análises sintéticas determinísticas para `MOCK_TIKTOK=true`, sem carregar modelos.

### `app/analytics.py`

- Funções puras/determinísticas de cálculo.
- Não grava no banco e não chama APIs.
- Enriquece cada vídeo e agrega estatísticas do acervo.

### `app/exporter.py`

- Carrega conta, vídeos, todos os snapshots de conta e todo histórico de cada vídeo.
- Gera relatório JSON compacto `schema_version: 2` e CSV.
- Tenta aplicar permissão `0600` aos arquivos.

### `app/mock_tiktok.py`

- Fornece uma conta fictícia e 12 vídeos determinísticos.
- As datas são relativas ao momento da chamada; textos e métricas-base são determinísticos.
- Nunca deve usar o banco real por padrão.

## 9. Rotas Flask

| Método e rota | Função |
|---|---|
| `GET /` | dashboard, analytics gerais e 10 vídeos recentes |
| `GET /videos` | lista completa; sort por `recent`, `oldest`, `views`, `likes`, `shares`, `engagement` ou `share_rate` |
| `GET /videos/<int:video_id>` | detalhe, métricas e histórico para Chart.js |
| `POST /videos/<int:video_id>/metadata` | endpoint legado para `category`, `format`, `hook`, `notes`; não aparece mais na UI |
| `GET /settings` | scopes, paths e endpoints; nunca mostra segredos |
| `GET /auth/tiktok` | inicia OAuth Desktop |
| `GET /callback/` | callback OAuth; aceita também sem barra final |
| `POST /auth/disconnect` | revoga quando possível e apaga tokens locais |
| `POST /api/sync` | coleta perfil/vídeos; retorna JSON |
| `POST /api/export/json` | gera JSON e retorna URL de download |
| `POST /api/export/csv` | gera CSV e retorna URL de download |
| `GET /ai` | fila, runtime, contagens e controles da IA local |
| `GET /ai/insights` | relatório cacheado/determinístico de padrões e recomendações |
| `GET /api/ai/status` | status JSON do worker, progresso, GPU/configuração e contagens |
| `POST /api/ai/analyze-library` | cria a fila e inicia `python -m app.ai.worker --batch` |
| `POST /api/ai/pause` / `POST /api/ai/continue` | solicita pausa segura após vídeo atual ou retoma |
| `POST /api/ai/retry-failed` | reencaminha falhas para a fila |
| `POST /api/ai/videos/<id>/analyze` | análise individual; não repete `completed` |
| `POST /api/ai/videos/<id>/reanalyze` | reanálise individual explícita |
| `POST /api/ai/videos/<id>/local-file` | fallback validado para MP4 local absoluto |
| `POST /api/ai/insights` / `POST /api/ai/generate-insights` | inicia geração estratégica no worker |
| `GET /exports/<filename>` | baixa apenas arquivo simples existente no diretório de exports |

Todos os POSTs exigem CSRF, lido do header `X-CSRF-Token` ou campo de formulário. O JavaScript obtém o token da meta tag no template base.

## 10. Integração TikTok

Endpoints:

- autorização: `https://www.tiktok.com/v2/auth/authorize/`;
- token/refresh: `POST https://open.tiktokapis.com/v2/oauth/token/`;
- revogação: `POST https://open.tiktokapis.com/v2/oauth/revoke/`;
- perfil: `GET https://open.tiktokapis.com/v2/user/info/`;
- lista de vídeos: `POST https://open.tiktokapis.com/v2/video/list/`;
- consulta por IDs: `POST https://open.tiktokapis.com/v2/video/query/`.

Scopes atuais:

- `user.info.basic`;
- `user.info.stats`;
- `video.list`.

Detalhe incomum e essencial: o fluxo Desktop do TikTok usado aqui exige `code_challenge` como SHA-256 em **hexadecimal**, não base64url. `code_verifier` usa somente caracteres unreserved e tem 64 caracteres por padrão.

Campos de vídeo solicitados:

- ID, criação, capa, URL de compartilhamento, descrição, título e duração;
- dimensões, embed HTML/link;
- likes, comentários, shares e views.

O código limita/normaliza strings, converte contagens em inteiros não negativos e ignora vídeos sem ID.

## 11. Banco SQLite e semântica dos dados

Schema version: `2`. A migration incremental cria as tabelas de IA abaixo
quando um banco v1 existente é aberto; nenhuma tabela histórica é apagada.

### `auth_tokens`

Uma única linha (`id = 1`) com access token, refresh token, expirações epoch, open ID, scope, tipo e data de atualização.

### `account_snapshots`

Histórico append-only de:

- `collected_at`, `open_id`, `display_name`, `username`, `avatar_url`;
- `bio_description`, `profile_deep_link`, `is_verified`;
- `follower_count`, `following_count`, `likes_count`, `video_count`.

Vários campos existem no schema, mas ficam nulos com os scopes atuais.

### `videos`

Uma linha por `tiktok_video_id` único. Guarda metadados relativamente estáveis:

- descrição, título, publicação e duração;
- capa, share URL, embed HTML/link e dimensões;
- `created_at`/`updated_at` locais;
- campos legados `category`, `format`, `hook`, `notes`.

Os quatro campos manuais são preservados no upsert para compatibilidade com bancos antigos, mas não aparecem na UI atual nem nos exports.

### `video_metrics`

Histórico append-only por vídeo:

- `collected_at`;
- `view_count`, `like_count`, `comment_count`, `share_count`.

Possui FK para `videos.tiktok_video_id` com cascade delete.

### `video_ai_analysis`

Uma linha por `tiktok_video_id`, com `status`, modelo/prompt usados, texto e
segmentos da transcrição, idioma/probabilidade, janelas da transcrição,
`analysis_json` completo validado, alguns campos indexados (`primary_topic`,
`content_type`, `format`, `hook_type`, `hook_text`, `summary`, `confidence`),
timestamps, `attempts` e `last_error`. Os estados são `pending`,
`downloading`, `transcribing`, `extracting_frames`, `analyzing`, `completed`,
`download_failed`, `transcription_failed` e `analysis_failed`.

### `ai_jobs`

Singleton (`id=1`) com estado da fila, flag `stop_requested`, PID, vídeo/etapa
atuais, contagens, timestamps e último erro. O lockfile `tmp/tiktok_ai/worker.lock`
usa lock advisory do Linux; um lock órfão é liberado pelo sistema e os estados
intermediários voltam a `pending` na próxima execução.

### `ai_insight_reports`

Relatórios estratégicos locais com `input_fingerprint`, modelo, versão do
prompt, data e `report_json`. Se o fingerprint dos vídeos analisados, análises
estruturadas e métricas mudar, um novo relatório pode ser gerado; caso
contrário o último é reutilizado.

### Regra fundamental

As métricas atuais **não ficam em `videos`**. `Database.get_videos()` e `get_video()` fazem join com a linha mais recente de `video_metrics` usando o maior `id` de cada vídeo. Alterações futuras não devem começar a gravar contagens diretamente em `videos`.

### Deduplicação de snapshots

Para conta e vídeo:

- se o último snapshot tiver menos de 5 minutos **e** todos os valores relevantes forem idênticos, não salva;
- se qualquer valor mudar, salva mesmo dentro dos 5 minutos;
- se os valores forem iguais mas já passaram 5 minutos, salva.

As datas persistidas são ISO UTC, normalmente no formato `YYYY-MM-DDTHH:MM:SSZ`. `create_time` de vídeo é epoch Unix.

Qualquer mudança de schema deve ser incremental, baseada em `PRAGMA user_version`, sem apagar dados históricos ou substituir bancos do usuário.

## 12. Analytics: fórmulas e decisões

### Taxas por vídeo

- `engagement_rate = (likes + comments + shares) / views * 100`;
- `like_rate = likes / views * 100`;
- `comment_rate = comments / views * 100`;
- `share_rate = shares / views * 100`.

Se views for zero/ausente, a taxa fica indisponível (`None`) em vez de dividir por zero.

### Tempo e velocidade

- `lifetime_average_views_per_hour`: views atuais divididas pela idade total do vídeo.
- `recent_views_per_hour` e `recent_likes_per_hour`: diferença entre os dois snapshots reais mais recentes dividida pelo intervalo real em horas.
- O fuso padrão de agrupamento/publicação é `America/Campo_Grande`; timestamps UTC também são preservados.

### Janelas de idade do vídeo

Idades-alvo: `1h`, `3h`, `6h`, `12h`, `24h`, `48h`, `72h`.

Tolerâncias máximas para escolher o snapshot mais próximo:

| Idade | Tolerância |
|---|---|
| 1h | ±0,75h (45 min) |
| 3h | ±1h |
| 6h | ±2h |
| 12h | ±3h |
| 24h | ±6h |
| 48h | ±8h |
| 72h | ±12h |

Não há extrapolação. Se nenhum snapshot estiver dentro da tolerância, o valor fica ausente no JSON compacto. Views e likes usam todas as janelas; comments e shares usam 24h, 48h e 72h. Deltas são calculados entre janelas consecutivas; velocidade de views também é calculada por intervalo.

### Sinais objetivos da legenda

Extraídos por regex/contagem, sem interpretação semântica:

- hashtags únicas normalizadas com `casefold`;
- caracteres, palavras, hashtags e menções;
- presença de pergunta, exclamação, números, emojis e URL;
- detecção conservadora de resposta a comentário em português/inglês.

### Comparação relativa

Para views, engagement e share rate:

- razão em relação à mediana da conta;
- percentil midrank de 0 a 100;
- empates recebem rank médio;
- uma única amostra recebe percentil 100.

Distribuições incluem `p25`, `p50`, `p75`, `p90`, `p95` e `max`, usando interpolação linear na posição `(n - 1) * p`.

Outliers de views usam modified z-score absoluto com mediana/MAD e limiar `3.5`. Se MAD for zero, valores diferentes da mediana são marcados.

### Agregações

- períodos `overall`, `last_30_days`, `last_7_days`;
- total, média e mediana de views/likes/engagement/share rate;
- comparação da mediana recente com a geral somente quando ambos os grupos têm ao menos 2 vídeos;
- agrupamentos por duração, dia da semana e hora local;
- rankings geral, últimos 30 dias e últimos 7 dias, limitados a 10 itens.

Buckets de duração: `0-20s`, `21-30s`, `31-45s`, `46-60s`, `61-90s`, `90s+`.

### Conta e seguidores

O relatório procura snapshots de conta próximos de 24h, 7d e 30d atrás para calcular crescimento. Também correlaciona seguidores próximos à publicação e 24h/48h depois. Isso é explicitamente correlação no nível da conta, nunca atribuição causal a um vídeo.

## 13. Contrato de exportação

### JSON

Nome: `exports/tiktok_report_YYYY-MM-DD_HH-MM.json`.

Contrato atual: `schema_version: 2`. Ordem de alto nível:

```text
schema_version
generated_at
source                 # `tiktok` ou `mock`
timezone
account
summary
analytics
distribution
outliers
methodology
limitations
videos[]
```

Cada vídeo pode conter:

- identidade, descrição, publicação UTC/local, duração, faixa, idade e URL;
- sinais objetivos da legenda;
- `current_metrics` com contagens, taxas e velocidades;
- `performance` relativo à conta;
- `growth`, `growth_deltas` e `velocity`, somente quando houver dados;
- correlações de seguidores, quando houver snapshots adequados;
- no máximo os 3 snapshots reais mais recentes.

Política de compactação: `_compact()` remove recursivamente chaves com `None` e dicionários que se tornam vazios. Listas vazias e valores booleanos `false`, zero ou strings válidas permanecem. Por isso, consumidores não devem esperar todas as chaves opcionais.

O JSON não contém:

- tokens;
- histórico bruto completo (`metric_history`);
- campos manuais antigos;
- métricas inexistentes da API.

### CSV

Nome: `exports/tiktok_report_YYYY-MM-DD_HH-MM.csv`.

Uma linha por vídeo, com publicação, duração, URL, hashtags, sinais básicos, métricas atuais, taxas e velocidades. Não inclui campos manuais nem histórico.

### Cuidado com nomes

A resolução do nome é de um minuto. Dois exports do mesmo tipo no mesmo minuto sobrescrevem o mesmo arquivo. Isso é comportamento atual documentado, não um identificador único.

## 14. Interface local

- Idioma principal: português do Brasil.
- Visual escuro com acentos inspirados no TikTok.
- `base.html` contém navegação, status de conexão, flash messages, CSRF e footer.
- Dashboard mostra dados da conta, totais, vídeos recentes e ações de sync/export.
- `/videos` oferece ordenação e cards.
- detalhe do vídeo usa Chart.js 4.4.7 via jsDelivr apenas quando existe histórico e mostra a análise IA local quando disponível.
- `app/static/app.js` executa sync/export via `fetch`, baixa o arquivo gerado, ordena vídeos e monta o gráfico.
- `app/static/app.js` também inicia/pausa/retoma a fila IA e atualiza `/api/ai/status` a cada aproximadamente 2 segundos.
- URLs externas só são renderizadas se tiverem esquema HTTP/HTTPS e host.
- O frontend não recebe client secret nem tokens.

O endpoint legado de metadata manual ainda existe no backend, mas o formulário foi removido de `video_detail.html`. Os testes garantem que os campos `category`, `format`, `hook` e `notes` não reapareçam na interface atual. A análise IA usa controles separados e transcrição recolhível.

## 15. Site público

Os arquivos públicos na raiz são independentes do Flask:

- `index.html`: apresentação em inglês;
- `privacy.html`: Privacy Policy, atualizada em 10 de agosto de 2026;
- `terms.html`: Terms of Service;
- `style.css`: estilos dessas três páginas;
- `tiktok9DI4BPdOZpXaSmIBwcsKNrvERCCWT4ul.txt`: verificação de domínio/app do TikTok.

URL documentada: `https://caio-angelis.github.io/relatorio-tiktok/`.

Não mover o app Flask para a raiz nem substituir `index.html`, pois isso pode quebrar o GitHub Pages e a verificação/revisão do TikTok.

## 16. Segurança e privacidade

- Segredos ficam em `app/.env`, ignorado pelo Git.
- Bancos e exports são ignorados e tentam usar permissão `0600`.
- OAuth usa `state` validado com `hmac.compare_digest` e PKCE.
- POSTs usam CSRF com comparação constante.
- Cookies são `HttpOnly`, `SameSite=Lax` e `Secure=False` porque o servidor é HTTP em localhost.
- Se `FLASK_SECRET_KEY` estiver vazio, a chave aleatória invalida a sessão ao reiniciar; para OAuth/sessões estáveis, configure uma chave local.
- Erros nunca devem incluir tokens. `TikTokAPIError` preserva mensagem, code, log ID e HTTP status, mas não credenciais.
- Download de export usa `secure_filename`, resolve o path e exige que o arquivo esteja diretamente no diretório configurado.
- Desconectar preserva snapshots históricos; remove apenas tokens. A exclusão do banco é manual.
- Backups do SQLite também contêm tokens enquanto houver conta conectada e devem ser tratados como sensíveis.

## 17. Modo mock

Ativar em `app/.env`:

```dotenv
MOCK_TIKTOK=true
```

Características:

- nenhuma chamada de rede ao TikTok;
- banco separado `database/relatorio_tiktok_mock.db`;
- conta `Relatorio TikTok Demo` e 12 vídeos;
- ao abrir `/`, se ainda não houver snapshot de conta, o app chama sync automaticamente;
- ações de sync e export funcionam normalmente;
- ao abrir páginas do app, `app/ai/mock.py` preenche análises semânticas sintéticas para os 12 vídeos sem carregar modelos reais;
- antes de conectar conta real, retornar a `MOCK_TIKTOK=false`.

## 18. Cobertura de testes

### `test_tiktok_api.py`

- formato PKCE hexadecimal e parâmetros/scopes;
- paginação de vídeos e `max_count=20`.

### `test_database.py`

- upsert sem duplicar vídeo;
- preservação dos campos manuais legados;
- deduplicação de snapshots;
- leitura ilimitada de snapshots da conta.

### `test_analytics.py`

- taxas e divisão por zero;
- sinais de legenda e resposta conservadora;
- faixas de duração;
- crescimento com histórico suficiente;
- janelas, tolerâncias, timezone, deltas e velocidade;
- ausência em vez de extrapolação;
- períodos, medianas, distribuições e agrupamentos;
- outliers MAD;
- rankings recentes;
- percentis e correlações de seguidores.

### `test_exporter.py`

- JSON/CSV compactos;
- schema v2 e ordem inicial;
- ausência de tokens/campos manuais/nulls opcionais;
- máximo de 3 snapshots recentes;
- presença de metodologia e velocidades.

### `test_app.py`

- fluxo básico do dashboard em modo mock;
- CSRF, sync, exports, lista e detalhe;
- ausência dos campos manuais na UI.

### `test_ai.py`

- migration v2 e tabelas de análises/jobs/relatórios;
- inserção/update de status, tentativas, cache de `completed`, retry e limpeza;
- seleção de timestamps, clips curtos, average-hash e janelas 3s/5s;
- parser JSON, validação, segunda tentativa de correção e falhas isoladas do pipeline;
- analytics por tema/hook/combo, níveis de amostra e score;
- cache do estrategista, export compacto, páginas IA, status endpoint e CSRF.

Ao alterar analytics ou exports, teste tanto o valor calculado quanto a política de omissão de chaves. Um `None` interno pode desaparecer completamente do JSON.

## 19. Arquivos ignorados e dados locais

O `.gitignore` cobre:

- `.env` e variantes, preservando `.env.example`;
- ambientes virtuais, caches e artefatos Python;
- `*.db`, sidecars do SQLite e `database/*.db`;
- `exports/*.json`, `exports/*.csv`, temporários;
- `tiktok_report_*.json`/`*.csv` na raiz, legado de export local;
- `tmp/tiktok_ai/` e `.cache/huggingface/` (mídia, lock, logs e checkpoints);
- cobertura e caches de ferramentas.

Há arquivos locais gerados nessas pastas no ambiente atual. Não adicionar exemplos reais ao Git. Para fixtures, criar dados inteiramente sintéticos sob `tmp_path`, como os testes existentes.

## 20. Pontos de atenção e dívida técnica conhecida

- O app é single-user/local e o schema de tokens força uma única conta. Não assumir suporte multiusuário.
- A sincronização TikTok continua síncrona na requisição HTTP e percorre todas as páginas; a análise pesada de IA usa o worker separado descrito na seção 25.
- O módulo `app.app` instancia um app global no import, podendo tocar o banco padrão durante imports de teste/ferramenta.
- Não há transação única envolvendo perfil, todos os vídeos e todos os snapshots; cada método abre sua própria conexão.
- O schema tem campos de perfil e metadata manual que o produto atual não usa. Preservá-los evita quebrar bancos antigos.
- `video/query` existe, mas não participa do sync padrão.
- Chart.js é uma dependência remota da página de detalhe; o restante do app não precisa de Node.
- O nome de export pode colidir dentro do mesmo minuto.
- O README é detalhado e deve permanecer coerente com este arquivo, `.env.example`, rotas e contrato v2.
- Textos metodológicos do JSON estão em inglês; UI local em português; site público/legal em inglês. Essa mistura é intencional no estado atual.
- Métricas negativas recebidas da API são normalizadas para zero; entradas inválidas tornam-se indisponíveis.
- Ordenação por engagement/share rate acontece em Python; ordenações por data/contagens acontecem no SQL.

## 21. Regras para futuras alterações

Antes de modificar o projeto:

1. Ler `README.md`, este arquivo e os módulos/testes relacionados.
2. Não ler nem expor `app/.env`, tokens ou dados reais sem solicitação explícita.
3. Preservar a separação entre site público e app local.
4. Preservar bancos existentes com migrations incrementais.
5. Manter métricas brutas no SQLite e analytics derivados em `analytics.py`.
6. Não atribuir ao TikTok campos que os scopes atuais não oferecem.
7. Não extrapolar janelas sem snapshot dentro da tolerância.
8. Tratar horários e seguidores como correlação, não causalidade.
9. Ao mudar o JSON, decidir conscientemente se há mudança de schema e atualizar testes, README e este arquivo.
10. Manter tokens, campos manuais e histórico bruto fora do relatório compacto, salvo nova decisão explícita de produto.
11. Rodar `.venv/bin/pytest -q` depois das mudanças.
12. Conferir `git status` para não incluir bancos, exports ou segredos.

## 22. Critérios de conclusão para mudanças comuns

### Nova métrica derivada

- Implementar em `analytics.py` como função determinística.
- Definir comportamento para ausência/zero.
- Adicionar teste unitário.
- Expor no template/export apenas se fizer parte do produto.
- Atualizar metodologia e documentação se alterar interpretação.

### Novo campo da API

- Confirmar que o endpoint e os scopes realmente o fornecem.
- Adicionar ao field list e normalização.
- Criar migration incremental se precisar persistência.
- Preservar bancos antigos.
- Testar payload ausente, inválido e válido.

### Alteração do JSON

- Preservar `schema_version: 2` somente se compatível; aumentar a versão em quebra de contrato.
- Manter `_compact()` e a ausência de segredos.
- Atualizar `test_exporter.py`, README e este documento.

### Alteração de OAuth/segurança

- Manter state, PKCE, segredo apenas no backend e CSRF nos POSTs.
- Não registrar payloads de token.
- Testar expiração, refresh e revogação quando possível.

## 23. Comandos rápidos de diagnóstico

```bash
# Listar apenas arquivos relevantes/versionados
git ls-files

# Ver estado sem tocar nos dados locais
git status --short

# Executar testes
.venv/bin/pytest -q

# Iniciar o app
./run.sh

# Testar sem TikTok: definir MOCK_TIKTOK=true em app/.env e reiniciar
```

## 24. Fonte de verdade por assunto

| Assunto | Arquivo principal |
|---|---|
| instalação e operação | `README.md`, `run.sh` |
| ambiente e paths | `app/config.py`, `app/.env.example` |
| rotas e segurança web | `app/app.py` |
| OAuth e contrato TikTok | `app/tiktok_api.py` |
| refresh e coleta | `app/sync_service.py` |
| schema e persistência | `app/database.py` |
| fórmulas e metodologia | `app/analytics.py` |
| IA local, worker e estratégia | `app/ai/` |
| schema JSON/CSV | `app/exporter.py` |
| experiência do dashboard | `app/templates/`, `app/static/` |
| presença pública/legal | HTML/CSS na raiz |
| comportamento esperado | `app/tests/` |

Se uma próxima IA precisar responder “por que isso foi feito assim?”, os comentários no código, os testes e os commits recentes (`9ef40f1` a `3c1bf53`) registram a evolução para analytics determinísticos e relatório compacto v2.

## 25. Camada de IA local (implementada em 2026-08-31)

### Fluxo operacional

Depois de uma sincronização, `Database.ensure_ai_analysis_rows()` cria uma
linha `pending` para cada vídeo que ainda não possui análise. A rota
`POST /api/ai/analyze-library` grava um job singleton no SQLite e inicia um
subprocesso com `python -m app.ai.worker --batch`; ela não executa os pesos
dentro da request Flask. O worker adquire `tmp/tiktok_ai/worker.lock`, carrega
uma vez o faster-whisper e uma vez o Qwen3-VL, e percorre a fila em série:

```text
pending
  → downloading (yt-dlp/share_url)
  → transcribing (FFmpeg WAV mono 16 kHz → faster-whisper CUDA FP16)
  → extracting_frames (timestamps iniciais + distribuição até o fim)
  → analyzing (frames + transcrição → Qwen3-VL CUDA BF16)
  → completed (analysis_json + campos indexados)
```

Falhas ficam como `download_failed`, `transcription_failed` ou
`analysis_failed`, com `last_error`, e não interrompem os demais vídeos.
Cada vídeo limpa áudio/frames no `finally`; após erro, o MP4 também é
removido. Em sucesso, `AI_DELETE_TEMP_FILES=true` remove a pasta inteira.

### Modelos e privacidade

O modelo visual obrigatório é exatamente `Qwen/Qwen3-VL-8B-Instruct`, carregado
com Transformers, `torch_dtype=torch.bfloat16`, `eval()` e
`torch.inference_mode()`. A transcrição usa exatamente faster-whisper
`large-v3-turbo`, `device=cuda` e `compute_type=float16`. Não há Qwen Thinking,
GGUF, llama.cpp, AWQ, GPTQ, 4-bit, bitsandbytes, OpenAI, Gemini, Anthropic,
Alibaba, Hugging Face Inference API ou outro serviço de inferência remota.

`setup_ai.sh` é o instalador explícito da camada pesada: cria/reutiliza `.venv`,
verifica Python, FFmpeg, ffprobe, `nvidia-smi`, CUDA/VRAM, instala
`app/requirements-ai.txt`, cria temporários, baixa/reutiliza o cache Hugging
Face de ambos os modelos e testa carregamento. `run.sh` continua um bootstrap
leve do Flask e não reinstala PyTorch nem checkpoints.

### Schema e cache semântico

`VideoSemanticAnalysis` em `app/ai/schemas.py` é o contrato Pydantic validado
antes de persistir. O classificador recebe descrição/título/duração, idioma,
transcrição completa/segmentos e frames ordenados com timestamps, mas não
recebe views, likes, shares, comentários, engagement ou percentis. O prompt
fixo tem `CLASSIFIER_PROMPT_VERSION="1"`; saída inválida passa por uma segunda
tentativa local de correção e então vira `analysis_failed`.

`app/analytics.py::semantic_analytics()` cruza somente análises `completed`
com `videos`, o último `video_metrics` e históricos usados pelo analytics
existente. Agrupa por tema, tipo, formato, gancho, pessoas, bandas,
duração+tipo, tema+gancho e formato+gancho. Cada linha expõe amostra, média,
mediana, taxas, percentil médio, melhor/pior vídeo, janelas históricas quando
existem e `evidence_level` (caso isolado, sinal preliminar, padrão possível ou
evidência interna mais útil).

`strategist.py` cria um payload compacto sem transcrições completas, calcula
antes um score determinístico documentado (0,55 mediana de views relativa +
0,20 share rate relativo + 0,15 engagement relativo + 0,10 amostra, com fator
de recência até 1,15) e só então chama o mesmo Qwen3-VL em modo texto. O
relatório contém até cinco ideias prioritárias e cinco experimentais, com
evidências provenientes do payload. O fingerprint do payload é salvo em
`ai_insight_reports`; refresh da página não chama o modelo novamente.

### Worker, controles e fallback

`GET /api/ai/status` informa `enabled`, `ready`, `worker_running`, total,
completed, pending, failed, vídeo/etapa atuais e `stop_requested`. **Pausar**
apenas grava a flag; o worker termina o vídeo atual antes de encerrar. **Continuar**
inicia outro worker. O PID é combinado com lock advisory; se o PID morreu, a
próxima execução devolve `downloading`, `transcribing`, `extracting_frames` e
`analyzing` para `pending`. O cache impede reanálise quando ID, modelo e
prompt não mudaram; reanálise individual/biblioteca inteira é explícita.

O endpoint `POST /api/ai/videos/<id>/local-file` aceita somente caminho
absoluto, arquivo `.mp4` existente e até 2 GB; o worker valida novamente e
copia o arquivo para o diretório temporário do ID. É apenas fallback para
download, não fluxo principal, e o caminho não entra no banco/export.

### UI, export e mock

`/ai` mostra GPU/modelo, contagens, progress bar e polling de 2 segundos. `/ai`
e `/ai/insights` aparecem na navegação; `/videos` mostra badge IA e o detalhe
mostra classificação, estrutura, CTA, resumo e transcrição recolhível. Todos
os POSTs usam o CSRF existente. No modo mock, `app/ai/mock.py` cria dados
semânticos sintéticos sem carregar modelos reais.

O export JSON v2 permanece compatível: cada vídeo recebe opcionalmente apenas
`ai_analysis` com tema, tipo, formato, gancho, texto do gancho, resumo e
confiança. Segmentos/transcrição completa, raw output e mídia ficam fora do
JSON compacto e do CSV.

### Testes e limitações reais

Além dos 18 testes históricos, `app/tests/test_ai.py` cobre migration,
persistência, cache de `completed`, retry/attempts, sampling/deduplicação,
janelas de transcrição, parsing/reparo JSON, falhas isoladas e limpeza,
analytics semânticos, cache de relatório, export, CSRF e páginas. A suíte
verificada nesta implementação tem 35 testes passando. O comando
`python -m app.ai.worker --self-test` usa áudio/frames sintéticos e exige a
instalação real de CUDA, faster-whisper e Qwen; no ambiente de desenvolvimento
sem esses pacotes ele falha claramente, sem fallback para CPU e sem abrir o
banco real.
