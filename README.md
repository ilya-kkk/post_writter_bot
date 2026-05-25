# Post Writer Bot

MVP Telegram-бота для генерации постов после короткого анализа аудитории.

## Запуск

1. Скопируйте env:

```bash
cp .env.example .env
```

2. Укажите `BOT_TOKEN` в `.env`.

3. Запустите сервисы:

```bash
docker compose up --build
```

API healthcheck:

```bash
curl http://localhost:8000/health
```

Если `OPENAI_API_KEY` не задан, бот использует mock LLM-ответы. Это удобно для проверки MVP-воронки без расходов на API.
Если `BOT_TOKEN` пустой, контейнеры `bot` и `scheduler` стартуют, но polling и отправка followup-сообщений отключаются.

## Env

- `BOT_TOKEN` - токен Telegram-бота.
- `DATABASE_URL` - PostgreSQL DSN, по умолчанию docker-compose использует локальный Postgres.
- `REDIS_URL` - Redis DSN для RQ.
- `OPENAI_API_KEY` - ключ OpenAI или совместимого API.
- `OPENAI_BASE_URL` - опциональный base URL для OpenAI-compatible endpoint.
- `OPENAI_MODEL` - модель, по умолчанию `gpt-4o-mini`.
- `FOLLOWUP_FAST_MODE` - `true` включает короткие интервалы догрева для тестов.
- `MOCK_PAYMENTS` - `true` включает mock-оплаты.
- `APP_ENV` - окружение, по умолчанию `local`.

## Проверка сценария

1. Напишите боту `/start`.
2. Выберите сценарий.
3. Отправьте описание ниши или 3-5 примеров постов.
4. Дождитесь анализа аудитории.
5. Подтвердите анализ.
6. Выберите идею.
7. Получите бесплатный пост.
8. Выберите тариф.
9. Нажмите `Оплатить / mock paid`.

Проверить таблицы и тарифы:

```bash
docker compose exec db psql -U postgres -d post_writer_bot -c "\dt"
docker compose exec db psql -U postgres -d post_writer_bot -c "select * from tariffs;"
```

Проверить основные таблицы после ручного сценария:

```sql
select * from users;
select * from projects;
select * from audience_profiles;
select * from ideas;
select * from posts;
select * from payments;
select * from subscriptions;
select * from followup_events;
```

## Fast followup mode

Для ускоренной проверки догрева установите:

```env
FOLLOWUP_FAST_MODE=true
```

В этом режиме followup-сообщения планируются через минуты, а не часы.
По умолчанию fast-mode использует интервалы 2, 5, 10, 20, 30 и 47 минут.
