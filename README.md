# counterstack-champion

С нуля написанный Python-агент для квалификационной арены
[CounterStack](https://example.com) — поднимаем вживую на
мастер-классе.

Цель к концу занятия: агент подключается к qual-серверу, играет
полный матч и сабмитится на платформу с не-тривиальным результатом.

## Быстрый старт (на занятии)

```bash
uv venv
source .venv/bin/activate
uv pip install -e '.[dev]'
pytest                            # baseline smoke
python -m champion --help         # CLI surface
```

## Куда смотреть

- **`backlog.md`** — пошаговый roadmap. Начинаем с Phase 1.
- **`CLAUDE.md`** — engineering-правила проекта.
- **`AI.md`** — рабочая тетрадь нетривиальных находок (заполняется
  по ходу занятия).

Эти три файла — указатели; реальное содержимое лежит в `.claude/`
(намеренно gitignored, см. `CLAUDE.md` про "почему").

## Спецификация протокола

Публичная версия — на сайте CounterStack (`/spec.html`). Перед
Phase 1 прочитать §11 (transport) и §13 (envelope-формат
сообщений).
