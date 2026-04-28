# Тестовый сервер CounterStack

**Endpoint:** `counter-stack.rutsh.com:9017`

Публичный, без регистрации/токена. Используется для smoke и debug.
SLO 2 мс **не гарантируется** — реальная квалификация гоняется в
изолированной сети с другим сервером (см. правила `/quals`).

## Авторизация в `hello`

- `hello.p.token` — принимается любая строка, включая пустую.
  Реальная квала запускает контейнер изолированно и токен передаёт
  платформа.
- `hello.p.agent_name` — любая строка, не обязана быть
  зарегистрирована на сайте.

## Известные серверные проблемы

См. `../bug-report-01.md`. На 2026-04-28 сервер silent-FIN'ит
после валидного `ready{config_name:...}`, не доходя до `match_start`.

Phase 1 закрыт через mock-server (`tests/mock_server.py`); live-smoke
возобновляем после фикса.

## Запуск smoke

```bash
python -m champion counter-stack.rutsh.com:9017 --log-level=DEBUG
```

Ожидаемое поведение при работающем сервере:
1. handshake `hello → welcome → ready{config_name}` (берём первый из
   `welcome.available_configs`);
2. `match_start` со `seed`;
3. поток `tick`-сообщений (1 каждые 2 мс при идеальной сети);
4. при `keepalive.ping` в тике — отвечаем `pong`;
5. `match_end` → exit 0.

## Наблюдённые тайминги

- Connect → welcome: ~280 мс (через интернет).
- Размер `welcome` envelope с 7 пресетами в `available_configs`:
  ~800 байт.
