# Wire-протокол: что мы реализовали

Внутренний reference на SPEC v0.5
(http://counter-stack.rutsh.com/spec.html). Этот файл — выжимка SPEC
плюс наши наблюдения, не замена.

## Транспорт

- TCP, JSON Lines (UTF-8, разделитель `\n`).
- `TCP_NODELAY=1` на сокете — обязательно (бюджет 2 мс/тик).
- `max_message_bytes = 8192` (SPEC §13.6).

## Конверт

```
{"t": "<тип>", "q": "<очередь>", "p": {...}}
```

- `q` обязательно для матчевых клиентских сообщений (`own`, `opp`,
  `info`, `keepalive`).
- `q` отсутствует во всех серверных сообщениях и в до-матчевых
  клиентских (`hello`, `ready`).
- JSON-порядок полей не важен — сервер на `serde_json` (Rust).

## Сообщения от агента (`champion.protocol`)

| `t`        | `q`         | `p`                                                              | Когда                           |
| ---------- | ----------- | ---------------------------------------------------------------- | ------------------------------- |
| `hello`    | —           | `{agent_name, token, protocol_version=5}`                        | один раз после connect          |
| `ready`    | —           | `{config_name}`                                                  | один раз после `welcome`        |
| `action`   | `own`       | `{op}` где `op ∈ {left,right,rot_cw,rot_ccw,drop,noop}`          | каждый ход (Phase 2+)           |
| `reorder`  | `opp`       | `{slot}` где `slot ∈ {0,1,2}`                                    | competition (Phase 4+)          |
| `pong`     | `keepalive` | `{nonce}`                                                        | в ответ на `tick.p.keepalive.ping` |
| `snapshot` | `info`      | `{}`                                                             | дебаг desync (Phase 2)          |
| `state`    | `info`      | `{}`                                                             | регулярная сверка (Phase 2)     |
| `scores`   | `info`      | `{}`                                                             | по необходимости                |
| `match_time` | `info`    | `{}`                                                             | по необходимости                |

## Сообщения от сервера

`welcome`, `match_start`, `tick`, `topout`, `match_end`, `error` —
полные схемы в SPEC §11.4 / §5.3.

Неизвестные `t` логируются `WARNING` и игнорируются (толерантная
обработка по SPEC §11.7).

## Жизненный цикл

```
hello → welcome → ready{config_name} → match_start
                                       → tick* (+pong на keepalive)
                                       → topout? → match_end
```

В `match-loop` любая не-`tick` message — non-fatal:
- `topout` → `INFO`, продолжаем;
- `error` → `WARNING`, продолжаем;
- неизвестные → `WARNING`, продолжаем.

## Keep-alive

SPEC §11.6:
- Период: каждые `keepalive_interval_ticks=100` тиков (200 мс при 500 Hz).
- Таймаут: `keepalive_timeout_ticks=500` тиков (1 с) — нет pong → тех.поражение.
- Ответ: `{"t":"pong","q":"keepalive","p":{"nonce":N}}` с тем же `nonce`.

Реализация в `champion.agent._handle_tick` — на каждый `tick` с
`keepalive.ping` отдаём pong; счётчик `ping_count` доступен для
SLO-репорта (Phase 5).

## Board-state query (для Phase 2)

`q=info` команда `state` → `tick.p.info.state = {own:"crc32:XXXXXXXX"}`.

CRC-32 zlib (poly `0xEDB88320`, init/xorout `0xFFFFFFFF`, reflected)
от row-major битстроки стакана: `'0'/'1'` ASCII по клеткам, длина =
`field_width × field_height` (240 байт для 12×20). Цвет/тип не
учитывается, активная фигура и PQ — тоже.

`q=info` команда `snapshot` → полный снимок обоих стаканов и PQ
(для дифа на mismatch'е).

## Реализация

- `src/champion/protocol.py` — кодек envelope, builders, валидация.
- `src/champion/net.py` — TCP/JSONL connection с recv/send-тредами,
  fast-path без буфера + fallback метрика.
- `src/champion/agent.py` — state-machine handshake → match-loop +
  keepalive.
- `src/champion/__main__.py` — CLI и logging wiring.
- `tests/mock_server.py` + `tests/test_agent.py` — scriptable
  localhost-сервер и интеграционное покрытие.
