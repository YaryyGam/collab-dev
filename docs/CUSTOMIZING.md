# Как менять правила плагина

Почти всё поведение задано текстом и конфигом. Перед изменением определите, **какой слой** вы меняете:

| Хочу изменить… | Слой | Файл |
|---|---|---|
| Как Claude ведёт диалог: этапы, вопросы, анализ, формат разбора | 💬 правила | `plugins/collab/output-styles/collab.md` |
| Чем отличаются режимы | 💬 правила | `plugins/collab/modes/<режим>.md` |
| Что Claude делает после команды | 💬 правила | `plugins/collab/skills/<команда>/SKILL.md` |
| Что считается записью (разделы `bash` и `powershell`), длина пересказа, заголовки разбора | 🔒 параметры шлюза | `plugins/collab/config/gate.json` |
| Логику стадий и блокировок | 🔒 код | `plugins/collab/scripts/collab_gate.py` + `tests/` |
| На какие события реагирует плагин | 🔒 подключение | `plugins/collab/hooks/hooks.json` |

## Порядок работы

1. Внесите изменение.
2. Локально: `claude --plugin-dir ./plugins/collab` (в открытой сессии — `/reload-plugins`) и попробуйте на реальной задаче.
3. Если меняли `gate.json` или код: `python3 -m unittest discover -s plugins/collab/tests -v`.
4. Если меняли правила: прогоните затронутые сценарии, например
   `cd plugins/collab && claude plugin eval . --case '03-*' --scaffold --allow-tools Write Edit --trust-plugin`.
5. Поднимите `version` в `plugins/collab/.claude-plugin/plugin.json` — **без этого установленные у команды копии не обновятся.**
6. Закоммитьте; разработчики получат обновление через `/plugin` (или автоматически, если включено автообновление витрины).

## Примеры

### Сделать пересказ в `/collab:agree` длиннее

`config/gate.json`:
```json
"min_agree_words": 10
```

### Настроить напоминание «объясни изменение на пальцах»

После первого изменения каждого файла Claude получает напоминание объяснить его и дать псевдокод. Режимы, где оно действует, — `config/gate.json`:
```json
"explain_after_write_modes": ["learning", "collaborative"]
```
Пустой список `[]` выключает напоминание (правило в output style остаётся). Текст напоминания — функция `_explain_reminder` в `scripts/collab_gate.py`; как выглядит «на пальцах» — раздел «Этап 6» в `output-styles/collab.md`.

### Добавить команду, которую нужно считать записью

Например, `alembic upgrade` меняет схему БД — блокировать до согласования:
```json
"subcommand_writes": {
  "alembic": ["upgrade", "downgrade", "revision"],
  ...
}
```
Добавьте тест в `tests/test_collab_gate.py` (`BashWriteDetection.WRITES`).

### Разрешить безопасную команду, на которую срабатывает эвристика

Если, например, ваш `make lint` ошибочно не нужен в списке — просто не добавляйте `make`. Если ложное срабатывание даёт перенаправление (`cmd > /tmp/x`), добавьте цель в `safe_redirect_targets` или опишите случай в issue: эвристику лучше уточнить тестом.

### Заблокировать запись через MCP-инструмент

`gate.json` → `"write_tools": [..., "mcp__plugin_fs_files__write_file"]` и тот же инструмент в `matcher` для `PreToolUse` и `PostToolUse` в `hooks/hooks.json`.

### Изменить формат итогового разбора

Правьте раздел «Этап 7» в `output-styles/collab.md`. **Не меняйте заголовки** `## Итоговый разбор` и `### Проверка`, либо поменяйте вместе с ними `review_heading_pattern` / `verification_heading_pattern` в `gate.json` — по ним хук закрывает единицу работы.

### Добавить свой режим

1. `modes/strict.md` — опишите отличия.
2. `plugin.json` → `userConfig.default_mode.options` — добавьте `"strict"`.
3. `scripts/collab_gate.py` → `MODES = (..., "strict")`.
4. `skills/mode/SKILL.md` → `argument-hint`.
5. Тест в `Commands.test_mode_switch_injects_mode_rules`.

### Перевести правила на другой язык

Правила — обычный Markdown, Claude следует им на любом языке и отвечает на языке разработчика. При переводе сохраните смысл заголовков разбора или добавьте переводы в шаблоны `gate.json` (украинский и английский уже поддерживаются).

## Чего не делать

- Не ослабляйте шлюз ради удобства одного сценария — для этого есть `/collab:skip` и `/collab:off`.
- Не добавляйте в output style длинные справочники: он отправляется с каждым запросом и расходует контекст.
- Не храните состояние внутри `${CLAUDE_PLUGIN_ROOT}` — этот каталог заменяется при обновлении плагина.
