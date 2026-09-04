# Развёртывание astro-mcp для claude.ai

Кратко: **бесплатный claude.ai позволяет подключить один сторонний MCP-сервер**
(custom connector), но только **удалённый** — по публичному HTTPS-адресу.
Локальный stdio-сервер для этого не подходит, поэтому astro-mcp умеет работать
по HTTP-транспорту (streamable HTTP), а этот файл описывает, где и как
развернуть его бесплатно.

[English summary](#english-summary) is at the bottom.

---

## Как это работает

- Бесплатный план claude.ai: **1 кастомный коннектор** (Settings → Connectors →
  *Add custom connector*). Нужен публичный URL вида `https://<хост>/mcp`,
  авторизация не обязательна.
- Сервер — stateless: каждый HTTP-запрос самодостаточен, поэтому он корректно
  работает за любым прокси/балансировщиком (Render, Koyeb, Cloud Run) и
  переживает «засыпание» инстанса.
- Эфемериды (2 МБ, 1800–2400 гг.) уже зашиты в Docker-образ — ничего
  дополнительно скачивать не нужно.

Дальше — варианты от самого простого к самому гибкому.

## Вариант A — общий инстанс (ноль усилий)

Подключись к уже развёрнутому публичному инстансу:

> **URL коннектора:** `https://astro-mcp.onrender.com/mcp`
> *(плейсхолдер — автор публикует здесь URL своего общего инстанса после
> первого деплоя)*

1. Открой claude.ai → **Settings → Connectors → Add custom connector**
   (или в чате: *Customize → Connectors → «+»*).
2. Вставь URL коннектора (адрес **обязательно заканчивается на `/mcp`**).
3. Authentication: **No authentication** → *Create* / *Connect*.
4. Готово — в новом чате будут доступны все 14 инструментов
   (`calculate_natal_chart`, `calculate_transits`, …).

Минусы общего инстанса: он делит лимиты со всеми пользователями (геокодинг —
макс. 1 запрос/сек на инстанс) и иногда «спит» (см. [Troubleshooting](#troubleshooting)).

## Вариант B — свой инстанс на Render (~5 минут, без карты)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/DrewCyber/astro-mcp)

Render Free: Docker-сервис, 750 часов/месяц (хватает на 24/7), регистрация
через GitHub, **банковская карта не нужна**. Инстанс засыпает после 15 минут
без трафика и просыпается по запросу (~50 секунд).

1. Нажми кнопку **Deploy to Render** выше.
2. Войди через GitHub (или создай аккаунт — бесплатный, без карты).
3. Подтверди имя сервиса (`astro-mcp`) → **Apply**. Render сам соберёт образ
   из `Dockerfile` и `render.yaml` (~3–5 минут).
4. После деплоя скопируй адрес сервиса, например
   `https://astro-mcp-abc123.onrender.com`.
5. Подключи в claude.ai URL **`https://astro-mcp-abc123.onrender.com/mcp`**
   (шаги как в варианте A).

### Как не давать инстансу засыпать

Бесплатный [UptimeRobot](https://uptimerobot.com) пингует `/health` каждые
10 минут — инстанс не засыпает и укладывается в 750 часов/месяц:

1. Зарегистрируйся на uptimerobot.com (бесплатно).
2. **Add New Monitor** → тип *HTTP(s)* → URL
   `https://astro-mcp-abc123.onrender.com/health` → интервал 10 минут.

## Вариант C — быстрый тест через cloudflared-туннель (без аккаунта)

Поднимает сервер локально и даёт временный публичный URL — удобно проверить
коннектор до настоящего деплоя. URL живёт, пока работает туннель.

```bash
git clone https://github.com/DrewCyber/astro-mcp && cd astro-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
bash scripts/download_ephe.sh
export EPHE_PATH="$(pwd)/ephe" ASTRO_MCP_TRANSPORT=http
python -m astro_mcp            # слушает http://127.0.0.1:8080/mcp
```

В другом терминале (нужен установленный [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)):

```bash
cloudflared tunnel --url http://localhost:8080
```

cloudflared напечатает адрес вида `https://random-words.trycloudflare.com` —
подключай в claude.ai `https://random-words.trycloudflare.com/mcp`.
Адрес меняется при каждом перезапуске туннеля.

## Вариант D — Google Cloud Run (продвинутый, всегда-бесплатные лимиты)

Требует Google Cloud-аккаунт **с привязанной картой** (списаний не будет при
лёгком использовании: всегда-бесплатно 2 млн запросов/мес, масштабирование до
нуля, cold start ~5–15 сек).

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT
gcloud run deploy astro-mcp \
  --source . \
  --region europe-north1 \
  --allow-unauthenticated \
  --memory 512Mi --cpu 1 \
  --max-instances 1
```

Cloud Run сам использует `Dockerfile` и передаёт `PORT`/`HOST`. Результат:
`https://astro-mcp-xxxx-uc.a.run.app` → коннектор
`https://astro-mcp-xxxx-uc.a.run.app/mcp`.

## Вариант E — Koyeb

1. Зарегистрируйся на [koyeb.com](https://www.koyeb.com) (бесплатный тариф).
2. **Create Service → GitHub** → выбери свой форк репозитория.
3. Builder: *Dockerfile*; Instance: **Free**; в настройках Web service
   укажи порт `8080` и health check `/health`.
4. После деплоя подключи `https://<твой-хост>.koyeb.app/mcp`.

## Любой другой Docker-хост

Готовый образ опубликован в GitHub Container Registry — ничего собирать не нужно:

```bash
docker run -d -p 8080:8080 ghcr.io/drewcyber/astro-mcp:latest   # → http://<хост>:8080/mcp
```

Доступны теги: `latest`, `1.1` (мажор.минор), `1.1.0` (точная версия). На
Apple Silicon образ (linux/amd64) запускается через Rosetta/QEMU «как есть».

Если хочется собрать самостоятельно:

```bash
docker build -t astro-mcp .                       # на Apple Silicon: добавь --platform linux/amd64
docker run -d -p 8080:8080 astro-mcp              # → http://<хост>:8080/mcp
```

Переменные образа: `ASTRO_MCP_TRANSPORT=http`, `HOST=0.0.0.0`, `PORT=8080`,
`EPHE_PATH=/app/ephe`, `GEOCODE_CACHE_PATH=/tmp/geocode.json` — менять не нужно.

---

## Ограничения, о которых стоит знать

- **Даты расчётов: 1800–2400 гг.** Вне диапазона инструменты вернут
  `EPHEMERIS_OUT_OF_RANGE`.
- **Геокодинг** (город → координаты) идёт через публичный Nominatim:
  максимум 1 запрос/сек на инстанс. Для интенсивного использования передавай
  координаты и часовую зону явно (`birth_location: {lat, lon, tz}`) или
  настрой `GEOCODING_PROVIDER=opencage` + `OPENCAGE_API_KEY` в панели хостинга.
- **Приватность:** через общий инстанс проходят тексты твоих запросов к
  инструментам (даты рождения, города). Если это важно — разверни личный
  инстанс (вариант B).

## Troubleshooting

| Симптом | Причина и решение |
|---|---|
| «Authorization with the MCP server failed» | URL не заканчивается на `/mcp`; выбран не *No authentication*; сервер спит — открой `https://<хост>/health` в браузере и дождись `{"status":"ok"}` |
| Первый вызов инструмента висит или падает по таймауту | Бесплатный инстанс проснулся по твоему запросу (~50 сек на Render): открой `/health`, дождись ответа, повтори вызов; либо настрой UptimeRobot |
| Инструменты не видны в чате | Коннектор добавлен, но выключен: *Customize → Connectors* → включи переключатель astro-mcp |
| `EPHEMERIS_OUT_OF_RANGE` | Дата вне 1800–2400 гг. — это ограничение файлов эфемерид |
| Геокодинг не отвечает | Лимит Nominatim (1 req/с) или блокировка User-Agent; передавай `{lat, lon, tz}` явно или настрой OpenCage |

---

## English summary

The free claude.ai plan allows **one custom connector** — a remote MCP server
reachable at a public HTTPS URL. astro-mcp ships a Docker image with the
streamable-HTTP transport (stateless, session-free) listening on `/mcp`, with
ephemeris data baked in.

1. **Shared instance** — connect the public URL published at the top of this
   file (Settings → Connectors → *Add custom connector*, choose
   *No authentication*; the URL must end with `/mcp`).
2. **Your own free instance (recommended)** — click the
   [**Deploy to Render**](https://render.com/deploy?repo=https://github.com/DrewCyber/astro-mcp)
   button, sign in with GitHub (no credit card), and connect
   `https://<your-service>.onrender.com/mcp`. Free tier: 750 h/month, sleeps
   after 15 min idle (keep awake with a free UptimeRobot ping to `/health`).
3. **Quick test** — run locally (`ASTRO_MCP_TRANSPORT=http python -m astro_mcp`)
   and expose it with `cloudflared tunnel --url http://localhost:8080`; connect
   the printed `https://…trycloudflare.com/mcp` URL.
4. **Advanced** — run the published image anywhere Docker runs:
   `docker run -d -p 8080:8080 ghcr.io/drewcyber/astro-mcp:latest`
   (connect `http://<host>:8080/mcp`; tags: `latest`, `1.1`, `1.1.0`).
   The same Dockerfile also deploys to Google Cloud Run
   (`gcloud run deploy astro-mcp --source . --allow-unauthenticated`) or Koyeb.

Limits: calculations cover 1800–2400; geocoding is rate-limited to 1 req/s
per instance (pass explicit `{lat, lon, tz}` or configure OpenCage for heavy
use); free tiers cold-start in ~5–60 s after idle.
