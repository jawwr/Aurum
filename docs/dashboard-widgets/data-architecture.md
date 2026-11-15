# Архитектура данных аналитических виджетов

## Назначение

Dashboard widgets разделяют получение финансовых данных и их визуализацию.
Сейчас зарегистрирован один источник — `transactions` — и одна спецификация
`analytics`. Добавление другого источника не требует изменения `PieDiagram`,
`BarDiagram` или `LineDiagram`.

## Основные уровни

### DataSource

`DataSource` идентифицирует источник и регистрирует классы его спецификаций.
Реестр находится в `backend/app/services/data_sources.py`:

```python
DATA_SOURCE_REGISTRY = {"transactions": TransactionDataSource()}
```

`TransactionDataSource` не выбирает способ отображения. Он предоставляет
`TransactionAnalyticsDataSpec`, а `create_spec()` создаёт проверенную
конфигурацию спецификации и передаёт ей источник. Общие возможности источника:
`filter_query()` применяет SQL-ограничения транзакций до агрегации,
`validate_references()` проверяет существование счёта при сохранении виджета.

### DataSpec

`DataSpec` описывает доступные измерения, метрики, фильтры, тип результата и
условия обязательности параметров по измерению, проверяет конфигурацию и
выполняет запросы источника. Реализованная
`TransactionAnalyticsDataSpec` поддерживает:

- измерения `category`, `subcategory`, `account`, `tag`, `type`,
  `item`, `total`;
- метрики `sum` и `count`;
- фильтры `transaction_type`, `account_id`, `start_date`, `end_date`, `granularity`;
- гранулярность `day`, `week`, `month` для временного измерения `total`.

Спецификация сохраняет текущие финансовые правила: split-транзакции проходят
через `category_rollup`, `category` выполняет rollup в верхнюю категорию,
`subcategory` оставляет листовые категории, а `count` считает уникальную
транзакцию внутри каждого итогового элемента. Измерение `item`
(«без группировки») не агрегирует вовсе: одна строка — одна транзакция с её
суммой, только метрика `sum` (запрет `count` объявлен в
`forbidden_metrics_by_dimension` и попадает в manifest), `transaction_type`
остаётся необязательным фильтром, порядок — newest-first. Для категорий,
подкатегорий, счетов, тегов и временного итога `transaction_type` также можно не задавать:
`null` означает все типы операций; при заданном значении фильтр применяется
до агрегации. Для измерения `type` фильтр запрещён, поскольку оно само
группирует данные по типу операции.

При построении List для метрики `sum` DataSpec сохраняет направление суммы:
расходы возвращаются отрицательными, доходы и переводы — положительными.
Для этого SQL-запрос использует `CASE` по `Transaction.type` и явный
`CAST(... AS NUMERIC(14, 2))` до передачи значения в Dataset. Это исключает
сортировку строковых/положительных исходных `amount` и даёт ListDiagram
обычный числовой порядок: `value_desc` от большего к меньшему,
`value_asc` от меньшего к большему. Для Pie/Bar/Line сохраняются прежние
значения и финансовые контракты.

### Dataset

`backend/app/services/dataset.py` содержит источник-независимый результат.
`DatasetItem` включает:

- необязательный `element_id` исходной сущности;
- стабильный `key`;
- название `name`;
- `value` агрегирования;
- необязательные `icon`, `color`;
- `time_bucket` для временного ряда;
- `series_key` для нескольких рядов.

`element_id=None` используется для вычисленных элементов вроде `Other` и для
временных итогов, которые не являются одной сохранённой сущностью. Dataset не
ссылается на `Transaction`, `Category` или другую ORM-модель.

### Diagram

`backend/app/services/diagrams.py` содержит только преобразования Dataset:

- `PieDiagram` сортирует значения, оставляет восемь крупнейших секторов и
  объединяет хвост в `Other`;
- `BarDiagram` сортирует точки по убыванию значения;
- `LineDiagram` принимает временной Dataset с одним рядом и сортирует его по
  bucket;
- `ListDiagram` строит вертикальный список строк: сортировка и лимит
  задаются опциями `visualization.options` (`sort`:
  `none`/`value_asc`/`value_desc`, `limit`, по умолчанию 5) и валидируются
  на Backend — см. `docs/dashboard-widgets/list-widget.md`.

Диаграммы не импортируют ORM-модели, не строят SQL и не применяют финансовые
фильтры. Метод `render(dataset)` — единственный путь получения данных для
визуализации.

## Реестры

- `DATA_SOURCE_REGISTRY` регистрирует источники по идентификатору.
- `DATA_SPEC_REGISTRY` предоставляет плоский адресуемый индекс пар
  `source_id/spec_id`, а `DataSource.spec_classes` регистрирует DataSpec внутри
  источника.
- `DIAGRAM_REGISTRY` регистрирует поддерживаемые формы диаграмм по `WidgetType`.

При регистрации проверяются непустые идентификаторы и отсутствие дубликатов;
для получения источника используется `get_data_source()`, а для добавления
новой спецификации — `register_data_spec()`.

Совместимость вычисляется по типу Dataset: Pie и Bar работают с
`categorical`, Line — с `time_series`. Дополнительно Pie и Bar исключают
измерение `item` (сырые строки транзакций не являются осмысленной группой для
этих диаграмм), а List оставляет его доступным. Поэтому Backend может отдать
в manifest совместимые измерения, метрики и DataSpec без SQL-логики в
диаграммах.

Ограничение `item` действует для предлагаемых в manifest вариантов. Старые
сохранённые pie/bar с `item` по-прежнему принимаются и отображаются: данные не
мигрируются и не отбрасываются. При редактировании в форме нужно выбрать
поддерживаемую группировку. Старое имя измерения `transaction` схема читает
как `item` и сохраняет под актуальным именем.

## Хранение конфигурации

Все пользовательские виджеты Dashboard хранятся одним JSON-документом, а не
отдельными строками. Для этого используется уже существующая singleton-строка
`app_settings` с `id = 1`: новая колонка `dashboard_config` имеет тип PostgreSQL
`JSONB`. Новая система пользователей или отдельное владение Dashboard не
создаётся — сохраняется существующая область общих пользовательских данных
приложения.

В базе хранится только конфигурация. Результаты запросов, точки диаграмм,
агрегированные суммы и другие вычисленные значения в `dashboard_config` не
записываются.

Текущий документ имеет версию схемы `1`:

```json
{
  "schema_version": 1,
  "widgets": [
    {
      "id": "stable-widget-id",
      "title": "Расходы по категориям",
      "data_source": "transactions",
      "data_spec": "analytics",
      "query": {
        "dimension": "category",
        "metric": "sum",
        "filters": {
          "transaction_type": "expense",
          "account_id": null
        },
        "granularity": null
      },
      "visualization": {
        "type": "pie",
        "options": {}
      }
    }
  ]
}
```

Основные правила хранения:

- `schema_version` обязателен и сейчас должен быть равен `1`;
- `widgets` — упорядоченный массив, его порядок является порядком Dashboard;
- `id` каждого виджета — стабильная непустая строка, ID не повторяются;
- `data_source` и `data_spec` определяют источник и спецификацию данных;
- параметры запроса находятся внутри `query`, фильтры — внутри `query.filters`;
- параметры отображения находятся внутри `visualization`;
- backend запрещает неизвестные поля через Pydantic `extra="forbid"`;
- новые поля конфигурации добавляются через версию схемы и явные модели, а не
  через произвольный JSON.

Миграция
`backend/alembic/versions/7c1d2e3f4a56_store_dashboard_as_json.py` выполняет
перенос старых строк `dashboard_widgets`: сортирует их по `sort_order`,
переносит существующие числовые ID как строковые, преобразует плоские поля в
`query` и `visualization`, затем удаляет старую таблицу. Вычисленные данные не
переносятся. Downgrade сначала проверяет, что все документы можно представить
старой схемой, и прерывается с ошибкой вместо молчаливой потери новых полей.

## Конфигурация и API

Сохранённая конфигурация `DashboardConfig` и вычисленные данные разделены в
ответе API. Endpoint типов виджетов остаётся capability-manifest и не хранит
пользовательские настройки.

`GET /api/dashboard/widgets/types` возвращает:

```json
{
  "data_sources": [
    {
      "id": "transactions",
      "specifications": [
        {
          "id": "analytics",
          "dimensions": [
            "category",
            "subcategory",
            "account",
            "tag",
            "type",
            "item",
            "total"
          ],
          "metrics": [
            "sum",
            "count"
          ],
          "filters": [
            "transaction_type",
            "account_id",
            "start_date",
            "end_date",
            "granularity"
          ],
          "required_parameters": [
            "dimension",
            "metric"
          ],
          "dimension_kinds": {
            "category": "categorical",
            "item": "categorical",
            "total": "time_series"
          },
          "required_by_dimension": {
            "total": [
              "granularity"
            ]
          },
          "forbidden_by_dimension": {
            "type": [
              "transaction_type",
              "granularity"
            ],
            "item": [
              "granularity"
            ]
          },
          "forbidden_metrics_by_dimension": {
            "item": [
              "count"
            ]
          },
          "filter_options": {
            "transaction_type": [
              "expense",
              "income",
              "transfer"
            ],
            "granularity": [
              "day",
              "week",
              "month"
            ]
          },
          "compatible_diagrams": [
            "pie",
            "bar",
            "line",
            "list"
          ]
        }
      ]
    }
  ],
  "diagrams": [
    {
      "type": "pie",
      "dataset_kind": "categorical",
      "allowed_dimensions": [
        "category",
        "subcategory",
        "account",
        "tag",
        "type"
      ],
      "allowed_metrics": [
        "sum",
        "count"
      ],
      "needs_granularity": false,
      "compatible_data_specs": [
        "transactions:analytics"
      ]
    },
    {
      "type": "bar",
      "dataset_kind": "categorical",
      "allowed_dimensions": [
        "category",
        "subcategory",
        "account",
        "tag",
        "type"
      ],
      "allowed_metrics": [
        "sum",
        "count"
      ],
      "needs_granularity": false,
      "compatible_data_specs": [
        "transactions:analytics"
      ]
    },
    {
      "type": "line",
      "dataset_kind": "time_series",
      "allowed_dimensions": [
        "total"
      ],
      "allowed_metrics": [
        "sum",
        "count"
      ],
      "needs_granularity": true,
      "compatible_data_specs": [
        "transactions:analytics"
      ]
    },
    {
      "type": "list",
      "dataset_kind": "categorical",
      "allowed_dimensions": [
        "category",
        "subcategory",
        "account",
        "tag",
        "type",
        "item"
      ],
      "allowed_metrics": [
        "sum",
        "count"
      ],
      "needs_granularity": false,
      "compatible_data_specs": [
        "transactions:analytics"
      ]
    }
  ]
}
```

В `diagrams` Backend также сообщает поддерживаемые измерения, метрики,
необходимость гранулярности и ключи совместимых DataSpec. Frontend использует
этот manifest для списка источников, chart types и полей формы. В
`frontend/src/components/dashboard/AddWidgetModal.tsx` источник выбирается из
`data_sources`; при изменении источника выбор диаграммы и зависимые поля
сбрасываются. Для диаграммы используется первая совместимая спецификация
выбранного источника; при редактировании предпочтение отдаётся сохранённой
спецификации. Отдельного селектора спецификации нет. Идентификаторы источника
и спецификации отправляются в конфигурации. Метрики фильтруются по
выбранному измерению через `forbidden_metrics_by_dimension` из manifest,
так что форма не предлагает пару измерение+метрика, которую Backend
отверг бы.

## GET и PUT Dashboard

`GET /api/dashboard/widgets?year=2026&month=9` возвращает сохранённую
конфигурацию отдельно от рассчитанных данных:

```json
{
  "config": {
    "schema_version": 1,
    "widgets": [
      {
        "id": "stable-widget-id",
        "title": "Расходы по категориям",
        "data_source": "transactions",
        "data_spec": "analytics",
        "query": {
          "dimension": "category",
          "metric": "sum",
          "filters": {"transaction_type": "expense", "account_id": null},
          "granularity": null
        },
        "visualization": {"type": "pie", "options": {}}
      }
    ]
  },
  "widgets": [
    {
      "id": "stable-widget-id",
      "data": {
        "points": [
          {
            "label": "Продукты",
            "value": "125.00",
            "key": "category:7",
            "element_id": 7,
            "color": "#1baf7a",
            "icon": "shopping-basket",
            "time_bucket": null,
            "series_key": null
          }
        ]
      }
    }
  ]
}
```

`year` и `month` влияют только на вычисляемые `widgets.data`; сохранённый
`config` от периода не зависит. Повторный GET пересчитывает данные заново.

`PUT /api/dashboard/widgets?year=2026&month=9` принимает полный документ
`DashboardConfig`, а не отдельный виджет. Backend валидирует всю структуру,
каждый DataSource/DataSpec, совместимость с Diagram и ссылки вроде
`account_id`, затем атомарно заменяет весь JSONB-документ и возвращает свежие
данные. При ошибке валидации или commit частичное сохранение не выполняется.
Старые `POST`, `PATCH` и `DELETE` для отдельных виджетов больше не являются
источником истины.

## Поток данных и SQL-запросы

1. Frontend получает manifest и GET сохранённого Dashboard.
2. Backend читает `app_settings.dashboard_config` и валидирует документ.
3. `dashboard_widget_service` строит DataSpec из `query` и проверяет источник,
   спецификацию, диаграмму и ссылки на сущности.
4. При чтении сервис добавляет границы выбранного месяца как временные
   параметры, не изменяя сохранённый JSON.
5. DataSpec выполняет SQL-запросы и возвращает Dataset.
6. Diagram преобразует Dataset в `DiagramData`.
7. API сериализует точки, включая ключ, идентификатор, цвет, иконку и bucket.

SQL-логика находится в `TransactionAnalyticsDataSpec` и
`TransactionDataSource`, а не в route или Diagram. Общий
`filter_query()` применяет фильтры до агрегации:

- `transaction_type` ограничивает `Transaction.type`;
- `start_date`/`end_date` ограничивают `Transaction.date`;
- `account_id` ограничивает `Transaction.account_id`.

Затем DataSpec выбирает группировку: `category` использует category rollup,
`subcategory` сохраняет листовые категории, `account` группирует по счетам,
`tag` соединяет таблицы тегов, `type` группирует по типам, `item`
вовсе не группирует — по одной строке на транзакцию с её суммой (порядок
newest-first, иконка/цвет от категории), а `total` использует
`date_trunc(granularity, Transaction.date)`. `sum` использует сумму, `count`
сохраняет правила подсчёта транзакций конкретного измерения (для
`item` метрика `count` запрещена). Split-транзакции
и фильтрация до агрегации тем самым сохраняют текущую финансовую семантику.

Для raw-измерения `item` SQL также выбирает signed amount непосредственно в
строке транзакции. Порядок `sort: none` остаётся `date DESC, id DESC`; когда
ListDiagram применяет `value_asc` или `value_desc`, он сравнивает уже
числовые signed-значения Dataset, а не положительный исходный `amount` и не
его абсолютную величину.

Для `year=2026&month=9` передаются даты `2026-09-01` и `2026-09-30`; для
временных виджетов дополнительно применяется `day`, `week` или `month`.
Числа не сохраняются в JSONB и вычисляются заново при каждом GET или PUT.

## Расширение системы

### Saved и draft конфигурации на Frontend

`frontend/src/hooks/useDashboardWidgets.ts` после GET создаёт две независимые
копии:

- `savedConfig` — последнее состояние, подтверждённое Backend;
- `draftConfig` — текущая рабочая копия;
- `isDirty` — результат сравнения двух JSON-документов.

Добавление, редактирование и удаление меняют только `draftConfig`; отдельные
POST/PATCH/DELETE-запросы не выполняются. Кнопка сохранения отправляет весь
draft через PUT, после успешного ответа повторяет GET и только затем заменяет
обе локальные копии. При ошибке draft остаётся неизменным. Кнопка отката
заменяет draft копией `savedConfig`. Конфигурация Dashboard не восстанавливается
из `localStorage`.

При `isDirty` используется стандартный `beforeunload` для закрытия и
перезагрузки страницы. Текущий `BrowserRouter` приложения не поддерживает
штатный blocker API data-router, поэтому собственная имитация предупреждения
для SPA-переходов не добавляется.

### Новый DataSource

1. Создайте класс `DataSource` с уникальным `id`.
2. Реализуйте и зарегистрируйте его DataSpec-классы в `spec_classes`.
3. Добавьте экземпляр в `DATA_SOURCE_REGISTRY`.
4. Опишите миграцию, если конфигурация требует новых сохраняемых полей.
5. Добавьте тесты регистрации, manifest, валидации и Dataset.

Существующие Diagram менять не нужно, если новая спецификация возвращает
поддерживаемый `Dataset.kind`.

### Новая DataSpec

Унаследуйте `DataSpec`, задайте `id`, `dimensions`, `metrics`,
`supported_filters`, `dimension_kinds` и правила параметров, реализуйте
`validate_config()` и `fetch()`. Запросы и преобразование ORM-результатов
должны оставаться внутри DataSpec. Совместимость будет вычислена по типу
Dataset и объявленным типам измерений.

### Новая Diagram

Унаследуйте `Diagram`, задайте `type`, `dataset_kind` и реализуйте
`render(dataset)`. Зарегистрируйте класс в `DIAGRAM_REGISTRY`, добавьте его в
manifest и тесты сортировки, агрегации и обработки Dataset. Запросы к БД и
знания о финансовых сущностях в Diagram не добавляются.

## Тестовое покрытие

`backend/tests/test_dashboard_widget_architecture.py` проверяет регистрацию
источника и спецификации, валидацию конфигурации, общий Dataset, отсутствие
ORM-зависимости Diagram, правила Pie/Bar/Line/List, GET/PUT-разделение конфигурации
и данных, порядок, атомарность невалидного сохранения, ссылки и manifest.
`backend/tests/test_dashboard_widget_queries.py` проверяет SQL-агрегации и
фильтрацию до агрегации, включая split-транзакции, rollup, временные bucket'ы
и `count`. `frontend/src/api/dashboardWidgets.test.ts` проверяет полный PUT,
а `frontend/src/lib/dashboardConfig.test.ts` — clone, upsert, удаление и
порядок локального draft. List-виджет покрыт тестами из
`docs/dashboard-widgets/list-widget.md`.
