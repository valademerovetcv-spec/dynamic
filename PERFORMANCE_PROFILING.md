# Профилирование производительности

## Добавленное логирование времени выполнения

В модули `core/calculator.py` и `core/interpolator.py` добавлен декоратор `@profile_time`, который логирует время выполнения ключевых функций для выявления узких мест.

### Функции с логированием времени:

#### В `core/calculator.py`:
- `_update_zero_and_baselines()` - обновление нулевой точки и базовых линий
- `_find_overlap_region()` - поиск области перекрытия калибровочных кривых
- `_find_layer_overlap()` - поиск перекрытия для конкретного слоя
- `_trim_to_overlap()` - обрезка калибровочных данных до области перекрытия
- `_resolve_calib_by_intersections()` - выбор датчика по методу пересечений
- `_find_magnet_by_intersections()` - нахождение положения магнита
- `_calc_single_channel()` - расчёт перемещения для одного канала
- `calculate()` - основной метод расчёта
- `calculate_all_channels()` - расчёт для всех каналов
- `calculate_per_layer_magnet()` - расчёт положения магнита для каждого слоя
- `_calc_magnet_worker()` - вспомогательный метод для расчёта магнита
- `_calc_layer_worker()` - вспомогательный метод для расчёта слоя
- `calculate_per_layer()` - расчёт перемещений для каждого слоя

#### В `core/interpolator.py`:
- `interp_linear()` - линейная интерполяция
- `calc_single_channel()` - векторизованный расчёт для одного канала
- `calc_single_channel_optimized()` - оптимизированный расчёт с кэшированием
- `calc_multi_channels_vectorized()` - векторизованный расчёт для нескольких каналов
- `prepare_calib_branch()` - подготовка калибровочных данных
- `clear_cache()` - очистка кэша
- `prepare_calib_cached()` - подготовка данных с кэшированием

## Использование

### 1. Базовое логирование

```python
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from core.calculator import Calculator
from models.data_loader import DataLoader

loader = DataLoader()
# ... загрузка данных ...

calc = Calculator(loader)
result = calc.calculate()
```

В логах появятся сообщения вида:
```
2026-08-05 14:20:36,912 - INFO - calc_single_channel_optimized выполнено за 0.39 мс
2026-08-05 14:20:36,915 - INFO - calculate_all_channels выполнено за 15.23 мс
```

### 2. Расширенное логирование для отладки

```python
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
)
logger = logging.getLogger('performance')
logger.setLevel(logging.INFO)
```

### 3. Запись логов в файл

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='performance.log',
    filemode='w'
)
```

### 4. Анализ узких мест

После запуска программы проанализируйте логи:
- Функции с временем > 100 мс - кандидаты на оптимизацию
- Функции, вызываемые часто (> 100 раз) даже с малым временем - могут давать существенную задержку
- Суммарное время всех вызовов функции = среднее время × количество вызовов

## Пример анализа

```
_find_magnet_by_intersections выполнено за 245.67 мс  ← Узкое место!
_calc_single_channel выполнено за 0.15 мс
calculate_all_channels выполнено за 312.45 мс
```

В данном примере `_find_magnet_by_intersections` занимает ~79% времени `calculate_all_channels`.

## Рекомендации по оптимизации

1. **Кэширование**: Если функция вызывается много раз с одинаковыми параметрами
2. **Векторизация**: Замена циклов на операции NumPy
3. **Параллелизация**: Для независимых вычислений (уже реализовано в `calculate_per_layer`)
4. **Предварительные вычисления**: Кэширование промежуточных результатов

## Отключение логирования

Для продакшена можно отключить логирование производительности:

```python
logging.getLogger('core.calculator').setLevel(logging.WARNING)
logging.getLogger('core.interpolator').setLevel(logging.WARNING)
```
