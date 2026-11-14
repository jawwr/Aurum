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

- измерения `category`, `subcategory`, `account`, `tag`, `type`, `total`;
- метрики `sum` и `count`;
- фильтры `transaction_type`, `account_id`, `start_date`, `end_date`, `granularity`;
- гранулярность `day`, `week`, `month` для временного измерения `total`.

Спецификация сохраняет текущие финансовые правила: split-транзакции проходят
через `category_rollup`, `category` выполняет rollup в верхнюю категорию,
`subcategory` оставляет листовые категории, а `count` считает уникальную
транзакцию внутри каждого итогового элемента.

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
  bucket.

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
`categorical`, Line — с `time_series`. Поэтому Backend может отдать в manifest
совместимые измерения, метрики и DataSpec без SQL-логики в диаграммах.

## Конфигурация и API

Сохранённая конфигурация `DashboardWidget` содержит `data_source` и `data_spec`.
Для старых виджетов миграция
`backend/alembic/versions/d2f7a1b8c904_add_data_source_to_dashboard_widgets.py`
заполняет значения `transactions` и `analytics`; существующие поля диаграммы
остаются совместимыми.

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
            "total": "time_series"
          },
          "required_by_dimension": {
            "total": [
              "transaction_type",
              "granularity"
            ]
          },
          "forbidden_by_dimension": {
            "type": [
              "transaction_type",
              "granularity"
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
            "line"
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
и спецификации отправляются в конфигурации.

## Поток данных

1. Frontend получает manifest и отправляет конфигурацию виджета.
2. `dashboard_widget_service` проверяет диаграмму, источник, спецификацию и
   существование `account_id`.
3. При чтении виджета сервис добавляет границы выбранного месяца.
4. DataSpec выполняет запросы и возвращает Dataset.
5. Diagram преобразует Dataset в `DiagramData`.
6. API сериализует точки, включая ключ, идентификатор, цвет, иконку и временной
   bucket.

Числа не сохраняются в таблице виджетов и вычисляются заново при чтении.

## Расширение системы

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
ORM-зависимости Diagram, правила Pie/Bar/Line, обратную совместимость старого
payload и manifest. `backend/tests/test_widget_account_filter.py` проверяет
перенос account-фильтра через DataSpec, включая split-транзакции, rollup и
уникальный `count`.
