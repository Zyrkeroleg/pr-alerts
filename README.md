# pr-alerts

Telegram-алерты о PR-событиях в отслеживаемом репозитории (по умолчанию `Eksiled/jobbot`).
Запуск — GitHub Actions каждые 10 минут, состояние хранится в Actions cache.

События: новый PR, ревью (аппрув / запрос правок / комментарий), мерж, закрытие без мержа, новые коммиты в PR.

## Secrets (Settings -> Secrets and variables -> Actions)

- `GH_PAT` — classic PAT со скоупом `repo` (read-доступ к отслеживаемому репо)
- `TG_TOKEN` — токен Telegram-бота
- `TG_CHAT_ID` — id чата/группы, куда слать алерты

Репозиторий для слежения задаётся переменной `REPO` в `.github/workflows/pr-alerts.yml`.

## Локальный запуск

```
GH_TOKEN=... TG_TOKEN=... TG_CHAT_ID=... REPO=owner/repo python pr_alert_bot.py
```
