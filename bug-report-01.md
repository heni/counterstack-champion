# bug-report-01: тестовый сервер молча FIN'ит после валидного `ready`

**Дата:** 2026-04-28
**Статус:** ✅ **RESOLVED** (2026-04-28, фикс на стороне сервера).

После фикса проверили full match echo-агентом на `default`-пресете:
6200 тиков / 12.5 с ≈ 496 Hz, 62 keepalive-ping / 62 pong, чистый
`match_end{reason: "qualification_topout"}`, exit 0. Подробные числа —
в `.claude/AI.md` → «Phase 1 — connect & echo».

Регрессионный тест на silent-FIN-сценарий оставлен в
`tests/test_agent.py::test_handshake_fails_on_silent_fin` —
если сервер снова начнёт так себя вести, мы увидим это сразу.

---

**Сервер:** `counter-stack.rutsh.com:9017`
**Версия протокола в `welcome`:** 5
**SPEC, на который опираемся:** http://counter-stack.rutsh.com/spec.html (v0.5, 2026-04-25)
**Затронутая площадка:** публичный тестовый сервер из раздела «Тестовый сервер» правил квалификации.

## Симптом

После валидного `hello → welcome → ready{config_name: <любой из welcome.available_configs>}`
сервер закрывает TCP-соединение (FIN, 0 байт payload) **без отправки**
`match_start`, `error` или `match_end`. Никаких сообщений после `welcome`
клиент не получает.

Соединение закрывается чисто (FIN, не RST). Никаких logs со стороны
клиента, никаких сообщений по протоколу — просто исчезает.

## Ожидаемое поведение (по SPEC §11.2)

```
S→C  match_start {seed, config, initial_state}
... серия тиков ...
S→C  match_end
```

Либо, при ошибке (по SPEC §11.7), сообщения вида
`error + match_end{reason: "..."}` и затем закрытие.

## Фактическое поведение

Только TCP-FIN после нашего `ready`. Ни одного байта от сервера.

## Минимальное воспроизведение

### Скрипт (Python 3, stdlib-only)

```python
import socket, time, json

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10.0)
s.connect(("counter-stack.rutsh.com", 9017))
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

s.sendall(b'{"t":"hello","p":{"agent_name":"alice","token":"","protocol_version":5}}\n')
time.sleep(0.3)
welcome = s.recv(8192)
print("[welcome]", json.loads(welcome.decode().strip())["p"]["match_id"])

s.sendall(b'{"t":"ready","p":{"config_name":"pentris-7"}}\n')

buf = b""
deadline = time.monotonic() + 5.0
while time.monotonic() < deadline:
    try:
        c = s.recv(8192)
    except socket.timeout:
        print("[timeout] received", len(buf), "B"); break
    if not c:
        print("[FIN] received", len(buf), "B before close"); break
    buf += c
print("[payload]", buf.decode(errors="replace") or "<empty>")
s.close()
```

### Наблюдаемый вывод (типичный):

```
[welcome] m-0000001c
[FIN] received 0 B before close
[payload] <empty>
```

### Полученное `welcome.p` (для сверки):

```json
{
  "match_id": "m-XXXXXXXX",
  "protocol_version": 5,
  "available_configs": [
    {"name":"default","mode":"qualification","field_width":12,"field_height":20,"match_duration_seconds":180},
    {"name":"human","mode":"qualification","field_width":12,"field_height":20,"match_duration_seconds":180},
    {"name":"i-biased","mode":"qualification","field_width":12,"field_height":20,"match_duration_seconds":60},
    {"name":"i-classic-rate","mode":"qualification","field_width":12,"field_height":20,"match_duration_seconds":60},
    {"name":"pentris-7","mode":"qualification","field_width":12,"field_height":20,"match_duration_seconds":60},
    {"name":"pentris-7-score-based","mode":"qualification","field_width":12,"field_height":20},
    {"name":"score-based","mode":"qualification","field_width":12,"field_height":20}
  ]
}
```

## Контрастные случаи (помогают локализовать)

Один и тот же сценарий до `ready`. Меняется только содержимое `ready`:

| `ready` payload | Что отвечает сервер | По SPEC? |
|---|---|---|
| `{"t":"ready","p":{}}` | `error{code:"config_required", message:"payload for \`ready\` invalid: missing field \`config_name\`"}` + `match_end{reason:"config_required",score:{own:0}}` | ✅ §11.3.1 |
| `{"t":"ready","q":"info","p":{"config_name":"default"}}` | `error{message:"message \`ready\` expects queue None, got Some(Info)"}` + `match_end{reason:"config_required",score:{own:0}}` | ✅ §11.3.1 |
| `{"t":"ready","p":{"config_name":"<любой_валидный>"}}` | **silent FIN, 0 байт** | ❌ ожидаем `match_start` |
| `{"t":"ready","p":{"config_name":"default","version":5}}` (лишнее поле) | silent FIN, 0 байт | ❌ ожидаем игнор unknown-полей или error |

Паттерн: **валидный** `ready` (тот, что должен запустить матч) приводит
к молчаливому FIN. Все варианты с явной ошибкой парсинга обрабатываются
корректно — сервер шлёт `error + match_end` и закрывает по правилам §11.7.

## Что проверено и не помогло

Все варианты дают одинаковый silent-FIN на валидном `ready`:

- Все 7 значений `config_name` из `welcome.available_configs`:
  `default`, `human`, `i-biased`, `i-classic-rate`, `pentris-7`,
  `pentris-7-score-based`, `score-based`.
- `agent_name` — пробовали `champion`, `test`, `alice`, `champion-test`.
- `token` — пробовали `""`, `"test"`, `"test_token_123"`, `"any"`.
- Задержка между `welcome` и `ready` — пробовали 0 мс, 300 мс, 2 с
  (всё внутри дефолтного `ready_timeout_seconds=60`).
- `protocol_version` как int `5` — все остальные варианты (например,
  string `"5"`) тоже молчаливо FIN'ятся, но у int-варианта SPEC вообще
  явно требует int, так что это нормально.

### Keepalive — отдельно проверено, не причина

В реальной FIN-сессии у нашего агента счётчик `ticks=0` к моменту
закрытия — keepalive-таймер на стороне сервера физически не успевает
стартовать (по SPEC §11.6 он считается в тиках, а тики появляются
только после `match_start`).

Дополнительно: keepalive-логика клиента изолированно проверена на
localhost-mock'е (тот же `champion.agent.Agent`, скриптованный сервер
вместо реального). На синтетический `tick.p.keepalive.ping.nonce=777`
агент за <200 мс отдаёт байт-в-байт:

```
{"t":"pong","p":{"nonce":777},"q":"keepalive"}\n
```

Содержимое полей соответствует SPEC §11.3.5 (`t=pong, q=keepalive,
p.nonce`). JSON-порядок ключей `t,p,q` vs `t,q,p` неважен — серверный
parser order-agnostic (видим по структуре diagnose-сообщений вида
`expects queue None, got Some(Info)` — это serde-флейвор Rust).

## Гипотеза

Похоже, что серверный handler `ready`-message успешно проходит валидацию
конверта и payload'а, отвечает каким-то OK-путём (сервер начинает
запускать match-worker), и сразу после этого worker / соединение
крашится без записи финального `match_end`. То есть сбой не в парсере
ready (он работает корректно — см. error-ветки выше), а в дальнейшем
шаге инициализации матча.

Чисто гипотетически, кандидаты:
- `match_start.p.initial_state` сериализация падает на каком-то поле.
- Спавн первой фигуры по PRNG (Xoshiro256++ + SplitMix64) ловит panic
  в `unwrap()` или `try_into`.
- Какой-то background tick-loop стартует и сразу падает; supervisor
  закрывает соединение, не успев отправить error+match_end.

Если у вас есть серверные логи на момент `m-0000001c` (или любого
match_id из этого окна), они должны указать на конкретную точку паники.

## Контекст / зачем это нам

Готовим Python-агента к квале, на этапе Phase 1 «connect & echo» нужно
просто увидеть поток тиков для дальнейших фаз. Без `match_start` мы не
можем валидировать ни обработку keepalive, ни tick-loop, ни SLO-метрики.

Отчёт собран на стороне Phase-1-агента (`feature/phase-1-connect-echo`
ветка, `python -m champion`-запуск через uv-venv, Python 3.12.3,
Linux 6.8.0).

## Что от вас нужно

1. Подтверждение, что баг воспроизводится у вас (или контр-репро,
   если у вас валидный `ready` уходит в `match_start`).
2. Если нужна дополнительная диагностика — готов прислать pcap или
   tee-логи raw-bytes.
