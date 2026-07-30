# Рефакторинг проекта "Динамика"

## Структура модулей

Проект был декомпозирован на следующие модули:

```
/workspace/
├── models/              # Модули данных
│   ├── __init__.py
│   └── data_loader.py   # Загрузка данных из Excel, CSV, XLSX
│
├── core/                # Ядро приложения (расчётная логика)
│   ├── __init__.py
│   └── calculator.py    # Расчёт перемещений, калибровка
│
├── ui/                  # UI компоненты
│   ├── __init__.py
│   ├── components/      # Базовые компоненты (панели, кнопки, таблицы)
│   │   └── __init__.py
│   └── tabs/            # Вкладки приложения
│       └── __init__.py
│
├── utils/               # Вспомогательные утилиты
│   └── __init__.py      # Стилизация приложения
│
├── calc.py              # Обёртка для обратной совместимости
└── app.py               # Главное приложение (требует дальнейшего рефакторинга)
```

## Изменения

### 1. models/data_loader.py
- Выделен класс `DataLoader` для загрузки данных
- Методы загрузки: `load_excel`, `load_dynamics_csv`, `load_calibration_csv`, и т.д.
- Удалены методы расчёта (перенесены в `core/calculator.py`)
- Сохранены только методы обработки данных: `_find_baseline`, `_find_rising_indices`

### 2. core/calculator.py  
- Новый класс `Calculator` для всей расчётной логики
- Принимает `DataLoader` в конструкторе
- Методы расчёта: `calculate`, `calculate_all_channels`, `calculate_per_layer`
- Методы управления калибровкой: `set_manual_zero`, `set_layer_manual`, и т.д.

### 3. calc.py (обратная совместимость)
- Обёртка над новыми модулями
- Класс `DataLoaderWithCalc` наследует `DataLoader` и делегирует расчёты `Calculator`
- Старый код, импортирующий `from calc import DataLoader`, продолжит работать

### 4. utils/__init__.py
- Функция `style_application()` для стилизации Tkinter приложения
- Вынесены все константы цветов и настройки стилей

## Преимущества новой структуры

1. **Разделение ответственности**: 
   - `models` — только загрузка и хранение данных
   - `core` — только бизнес-логика и расчёты
   - `ui` — только отображение

2. **Тестируемость**: Каждый модуль можно тестировать независимо

3. **Расширяемость**: Легко добавить новые форматы данных или алгоритмы расчёта

4. **Читаемость**: Код разделён на логические блоки по ~500-700 строк

## Следующие шаги

Для завершения рефакторинга рекомендуется:

1. **Вынести UI компоненты из app.py**:
   - `DinamikaApp` → `ui/main_app.py`
   - Методы `_build_*` → `ui/components/toolbar.py`, `ui/components/tabs.py`
   - Обработчики событий → `ui/handlers/`

2. **Создать facade**:
   - `services/dynamics_service.py` — объединяет `DataLoader` и `Calculator`

3. **Добавить конфигурацию**:
   - `config/settings.py` — вынести константы и настройки

## Использование

```python
# Новый способ (рекомендуемый)
from models.data_loader import DataLoader
from core.calculator import Calculator

loader = DataLoader()
loader.load_excel("data.xlsx")

calculator = Calculator(loader)
calculator.calculate()

# Старый способ (для обратной совместимости)
from calc import DataLoader

loader = DataLoader()
loader.load_excel("data.xlsx")
loader.calculate()
```
