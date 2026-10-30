# PIMO - агент-аналитик

Текст требований -> LLM строит формальную модель (конечный автомат) -> Model Checker (TLA+/TLC)
проверяет её -> LLM объясняет результат на языке требований.

Сервисы:
- `core` (порт 8000) - Core API: регистрация, чаты, агент. Swagger: http://localhost:8000/docs
- `checker` (порт 8001) - Model Checker: validator, compiler, TLC, parser
- `db` - PostgreSQL
- LLM - LiteLLM МАИ (`https://api-ai.mai.ru/v1`), модель `qwen3.8-27b`

## Запуск через Docker

```bash
cp .env.example .env        # вписать LLM_API_KEY
docker compose up --build
```

Нужен файл сертификата `core/certs/api-ai.mai.ru.pem` (лежит в репозитории, как обновить - ниже).

Проверить агента из консоли внутри контейнера:

```bash
docker compose exec core python -m app.agent.cli "Заявку можно отменить до исполнения. ..."
```

## Запуск без Docker

Нужны Python 3.11+ и Java 11+. Без `DATABASE_URL` Core использует SQLite.

```bash
# терминал 1: checker
cd checker && pip install -r requirements.txt
python -m uvicorn app.api:app --port 8001

# терминал 2: core
cd core && pip install -r requirements.txt
set -a; source ../.env; set +a
python -m uvicorn app.main:app --port 8000
```

Агент без фронта и Core API:

```bash
cd core && set -a; source ../.env; set +a
python -m app.agent.cli --models                       # модели, доступные по ключу
python -m app.agent.cli --show-model "текст требований"
```

## Сертификат api-ai.mai.ru

Сертификат сервера МАИ выдан Russian Trusted CA, которого нет в списке Python, поэтому без
настройки будет `CERTIFICATE_VERIFY_FAILED`. В систему ничего ставить не нужно: клиент LLM
доверяет только файлу из `LLM_CA_FILE`, в котором лежит сертификат самого сервера.

Когда МАИ обновит сертификат, снять его заново:

```bash
cd core
openssl s_client -connect api-ai.mai.ru:443 -servername api-ai.mai.ru </dev/null 2>/dev/null \
  | openssl x509 -out certs/api-ai.mai.ru.pem
openssl x509 -in certs/api-ai.mai.ru.pem -noout -subject -fingerprint -sha256 -enddate
```

## Агент (`core/app/agent/`)

- `service.py` - `run_agent(history)`. LLM вызывает инструмент `check_behavior` (tool calling),
  агент отправляет модель в checker. При `MODEL_INVALID` LLM исправляет модель (до 3 раз).
  После вердикта инструмент отключается (`tool_choice="none"`), LLM только объясняет результат
  и модель сама не меняет.
- `prompts.py` - системный промпт и описание инструмента.
- `cli.py` - запуск из консоли.

Токены: в LLM уходят последние 10 сообщений чата (старые обрезаются), результат checker'а
сжимается, расход пишется в лог и в `AgentReply.usage`.

Если модель не поддерживает tool calling: `LLM_USE_TOOLS=false`, тогда она присылает JSON текстом.

## Тесты

```bash
cd core && python -m pytest -q
```

LLM в тестах подменяется, ключ не нужен. Если запущен checker на `localhost:8001`, дополнительно
проходят acceptance-тесты из ТЗ через TLC (модели в `checker/examples/`).
