# Copeeq / foto2word

Фото бумажного документа → аккуратный редактируемый Word (.docx): дословный текст, структура,
правки от руки, оформление по профилю типа документа.

Подробности устройства проекта: [архитектура](docs/ARCHITECTURE.md).

[Открыть демо Copeeq](https://valkohappy.github.io/copeeq/)

Демо опубликовано через GitHub Pages. Обработка, вход, оплата и скачивание работают
как локальная имитация; данные сбрасываются при перезагрузке страницы.

Copeeq является интерфейсом сервиса, foto2word отвечает за распознавание и сборку документов.
За основу интерфейса взят оригинальный экспорт Copeeq v5 из Claude Design. Его блоки,
иллюстрации документов, анимации и иконки сохранены. Шаблоны разделены в
`frontend/src/templates/`, картинки и runtime находятся в `frontend/public/`.
В копии исправлены мобильная вёрстка и подпись расчёта стоимости.

## Запуск

```bash
uv sync
npm ci --prefix frontend     # Node.js 22+
npm run build --prefix frontend
uv run f2w serve              # веб-сервис: http://127.0.0.1:8000
```

После сборки оригинальный Copeeq доступен по `/app/` в режиме мокапа. Ключ нейросети
для просмотра не нужен. Страницы, обработка, редактор, вход и платежи работают как
локальные демонстрационные сценарии исходного экспорта. Реальные AI-запросы, отправка
документов и списание денег из Copeeq не выполняются. Кнопки скачивания показывают
демонстрационное уведомление, а не создают готовый документ.

`frontend/build.mjs` собирает ES-модули и шаблоны в страницу для браузера. Блоки, картинки
и демонстрационные сценарии сохранены. Подключение интерфейса к backend отложено.

Ядро foto2word сохранено отдельно: API доступен по `/api/docs`, прежний технический
интерфейс по `/classic`. Их запуск обработки требует настройки провайдера в `.env`
по примеру `.env.example`. Мокап `/app/` их не вызывает.

Команды:

| Команда | Что делает |
|---|---|
| `f2w serve` | Веб-сервис: загрузка/съёмка фото, вопросы (тип, правки, опечатки), правка текста, превью, скачивание |
| `f2w convert PHOTO... -o OUT.docx` | То же из командной строки. `--mode faithful\|standard`, `--review`, `--no-corrections`, `--provider`, `--save-model` |
| `f2w render MODEL.json -o OUT.docx` | Пересобрать Word из сохранённой модели без нейросети |
| `f2w eval [--cases DIR]` | Прогнать эталонный набор, посчитать метрики, отчёт в `evals/runs/<время>/` |
| `f2w eval --predictions DIR` | Пересчитать метрики по сохранённым ответам (бесплатно) |
| `f2w synth --count 50` | Сгенерировать синтетические фото с известным ответом (`evals/synthetic/`) |
| `f2w schema` | JSON-схема модели документа |

Провайдеры (`F2W_PROVIDER`): `openai` (Responses API), `anthropic` (Claude), `compatible` — любой
OpenAI-совместимый сервер с vision (OpenRouter, Yandex AI Studio, vLLM, Ollama). Примеры в `.env.example`.

Самопроверка (`--review` / галочка на сайте) рендерит документ через Word (Windows) или LibreOffice
и просит модель сравнить его с фото. Сверка значений (ИНН, даты, паспорт, телефон) работает всегда;
второй независимый распознаватель — Yandex Vision OCR, если заданы `F2W_YANDEX_*`.

## Разработка

```bash
uv run pytest          # тесты (без сети: ответы моделей подменяются)
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy            # strict-проверка src/ и tests/
npm test --prefix frontend # целостность мокапа и отсутствие интеграции API
```

## Устройство кода

```
src/foto2word/
  domain/          модель документа, правки, патчи самопроверки, профили, валидаторы — без внешних сервисов
  application/     сценарии: ConvertDocument (анализ/сборка), ReviewLoop, DocumentVerifier, SessionService;
                   порты VisionModel, DocumentReviewer, DocumentRenderer, Previewer, SecondReader, SessionStore
  infrastructure/  providers/ (база + OpenAI, Claude, OpenAI-совместимые; общие промпты), rendering/ (docx),
                   raster/ (рисование страниц, карандаш, «камера»), preview (Word/LibreOffice → PDF → картинки),
                   ocr/ (Yandex Vision), profiles/ (YAML), session_store, images, config
  evaluation/      метрики, прогон, отчёт
  synthetic/       генератор документов с известным ответом
  web/             FastAPI, оригинальный Copeeq (copeeq/, сборка), прежний UI (static/)
  composition.py   сборка зависимостей — единственное место, знающее конкретные классы
  cli/             команды f2w
evals/             формат eval-набора; реальные документы и результаты исключены из git
frontend/src/      domain (правила), controllers (сценарии и представления), infrastructure,
                   templates (экраны и блоки), styles; composition.js (сборка зависимостей)
frontend/public/   исходные изображения, иконки, DocSheet и runtime Claude Design
frontend/tests/    сценарии мокапа, ограничения архитектуры, сохранность разметки
```

Новый провайдер = наследник `StructuredVisionModel` (три метода: формат текста, формат картинки,
один запрос) в `infrastructure/providers/` + строка в `composition.PROVIDERS`. Новый тип блока = класс в `domain/document.py` + рендерер в
`infrastructure/rendering/blocks.py` + отрисовка в `infrastructure/raster/page.py`. Новый тип документа = YAML в `profiles/`.
