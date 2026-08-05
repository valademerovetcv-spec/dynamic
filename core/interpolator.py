"""
Модуль для линейной интерполяции и расчёта перемещений.
Оптимизированная версия с кэшированием и векторизацией.
"""
import numpy as np
from functools import lru_cache
import time
import logging
from functools import wraps

# Настройка логирования
logger = logging.getLogger(__name__)


def profile_time(func):
    """Декоратор для логирования времени выполнения функции."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info(f"{func.__name__} выполнено за {elapsed*1000:.2f} мс")
        return result
    return wrapper


class Interpolator:
    """Класс для интерполяции значений перемещения с оптимизацией."""
    
    # Кэш для отсортированных калибровочных данных
    _calib_cache = {}
    _cache_max_size = 128
    
    @staticmethod
    @profile_time
    def interp_linear(target, tug_vals, disp_vals):
        """
        Линейная интерполяция перемещения по значению датчика.
        
        Args:
            target: целевое значение датчика
            tug_vals: массив значений датчика (отсортированный)
            disp_vals: массив перемещений (соответствующий tug_vals)
            
        Returns:
            float: интерполированное перемещение или None
        """
        n = len(tug_vals)
        if n < 2:
            return None
        
        idx = np.argmin(np.abs(tug_vals - target))
        if idx == n - 1:
            t0, t1 = tug_vals[-2], tug_vals[-1]
            d0, d1 = disp_vals[-2], disp_vals[-1]
        else:
            t0, t1 = tug_vals[idx], tug_vals[idx + 1]
            d0, d1 = disp_vals[idx], disp_vals[idx + 1]
        
        res1 = t0 - t1
        if res1 == 0:
            return d0
        
        del1 = (d0 - d1) / res1
        del2 = target - t0
        del3 = del1 * del2
        return round(d0 + del3, 3)

    @staticmethod
    @profile_time
    def calc_single_channel(tugriki_vals, calib_tugriki, calib_disp):
        """
        Расчёт перемещения для одного канала с использованием векторизованной интерполяции.
        
        Args:
            tugriki_vals: массив значений динамики
            calib_tugriki: калибровочные значения датчика
            calib_disp: калибровочные перемещения
            
        Returns:
            np.array: массив рассчитанных перемещений
        """
        tugriki_vals = np.asarray(tugriki_vals, dtype=np.float64)
        calib_tugriki = np.asarray(calib_tugriki, dtype=np.float64)
        calib_disp = np.asarray(calib_disp, dtype=np.float64)
        
        n_calib = len(calib_tugriki)
        if n_calib < 2:
            return np.zeros_like(tugriki_vals)
        
        # Векторизованная интерполяция через searchsorted
        sort_idx = np.argsort(calib_tugriki)
        calib_tug_sorted = calib_tugriki[sort_idx]
        calib_disp_sorted = calib_disp[sort_idx]
        
        # Находим индексы интерполяции для всех значений одновременно
        indices = np.searchsorted(calib_tug_sorted, tugriki_vals, side='right')
        indices = np.clip(indices, 1, n_calib - 1)
        
        # Получаем соседние точки для интерполяции
        t0 = calib_tug_sorted[indices - 1]
        t1 = calib_tug_sorted[indices]
        d0 = calib_disp_sorted[indices - 1]
        d1 = calib_disp_sorted[indices]
        
        # Вычисляем интерполяцию
        denom = t1 - t0
        mask = denom != 0
        result = np.where(mask, d0 + (tugriki_vals - t0) * (d1 - d0) / denom, d0)
        
        # Обработка граничных случаев (за пределами калибровки)
        below_mask = tugriki_vals <= calib_tug_sorted[0]
        above_mask = tugriki_vals >= calib_tug_sorted[-1]
        
        result = np.where(below_mask, calib_disp_sorted[0], result)
        result = np.where(above_mask, calib_disp_sorted[-1], result)
        
        return np.round(result, 3)

    @staticmethod
    @profile_time
    def calc_single_channel_optimized(tugriki_vals, calib_tugriki, calib_disp):
        """
        Оптимизированный расчёт перемещения с кэшированием сортировки калибровки.
        
        Args:
            tugriki_vals: массив значений динамики
            calib_tugriki: калибровочные значения датчика (уже отсортированные)
            calib_disp: калибровочные перемещения (соответствующие отсортированным calib_tugriki)
            
        Returns:
            np.array: массив рассчитанных перемещений
        """
        tugriki_vals = np.asarray(tugriki_vals, dtype=np.float64)
        n_calib = len(calib_tugriki)
        
        if n_calib < 2:
            return np.zeros_like(tugriki_vals)
        
        # Находим индексы интерполяции для всех значений одновременно
        indices = np.searchsorted(calib_tugriki, tugriki_vals, side='right')
        indices = np.clip(indices, 1, n_calib - 1)
        
        # Получаем соседние точки для интерполяции
        t0 = calib_tugriki[indices - 1]
        t1 = calib_tugriki[indices]
        d0 = calib_disp[indices - 1]
        d1 = calib_disp[indices]
        
        # Вычисляем интерполяцию
        denom = t1 - t0
        mask = denom != 0
        result = np.where(mask, d0 + (tugriki_vals - t0) * (d1 - d0) / denom, d0)
        
        # Обработка граничных случаев
        below_mask = tugriki_vals <= calib_tugriki[0]
        above_mask = tugriki_vals >= calib_tugriki[-1]
        
        result = np.where(below_mask, calib_disp[0], result)
        result = np.where(above_mask, calib_disp[-1], result)
        
        return np.round(result, 3)
    
    @staticmethod
    @profile_time
    def calc_multi_channels_vectorized(tugriki_matrix, calib_tugriki, calib_disp):
        """
        Векторизованный расчёт перемещений для нескольких каналов одновременно.
        
        Args:
            tugriki_matrix: 2D массив [n_channels, n_samples] значений динамики
            calib_tugriki: калибровочные значения датчика (1D массив)
            calib_disp: калибровочные перемещения (1D массив)
            
        Returns:
            np.array: 2D массив [n_channels, n_samples] рассчитанных перемещений
        """
        tugriki_matrix = np.asarray(tugriki_matrix, dtype=np.float64)
        calib_tugriki = np.asarray(calib_tugriki, dtype=np.float64)
        calib_disp = np.asarray(calib_disp, dtype=np.float64)
        
        if tugriki_matrix.ndim == 1:
            tugriki_matrix = tugriki_matrix.reshape(1, -1)
        
        n_channels, n_samples = tugriki_matrix.shape
        n_calib = len(calib_tugriki)
        
        if n_calib < 2:
            return np.zeros_like(tugriki_matrix)
        
        # Сортируем калибровочные данные один раз
        sort_idx = np.argsort(calib_tugriki)
        calib_tug_sorted = calib_tugriki[sort_idx]
        calib_disp_sorted = calib_disp[sort_idx]
        
        # Предварительно выделяем память для результата
        result = np.empty((n_channels, n_samples), dtype=np.float64)
        
        # Векторизованная интерполяция для всех каналов
        for ch in range(n_channels):
            tug_ch = tugriki_matrix[ch]
            indices = np.searchsorted(calib_tug_sorted, tug_ch, side='right')
            indices = np.clip(indices, 1, n_calib - 1)
            
            t0 = calib_tug_sorted[indices - 1]
            t1 = calib_tug_sorted[indices]
            d0 = calib_disp_sorted[indices - 1]
            d1 = calib_disp_sorted[indices]
            
            denom = t1 - t0
            mask = denom != 0
            ch_result = np.where(mask, d0 + (tug_ch - t0) * (d1 - d0) / denom, d0)
            
            # Граничные случаи
            below_mask = tug_ch <= calib_tug_sorted[0]
            above_mask = tug_ch >= calib_tug_sorted[-1]
            ch_result = np.where(below_mask, calib_disp_sorted[0], ch_result)
            ch_result = np.where(above_mask, calib_disp_sorted[-1], ch_result)
            
            result[ch] = np.round(ch_result, 3)
        
        return result

    @staticmethod
    def extract_rising_branch(disp, tug, range_left=None, range_right=None):
        """
        Извлечение восходящей ветви калибровки.
        
        Args:
            disp: массив перемещений
            tug: массив значений датчика
            range_left: левая граница диапазона (опционально)
            range_right: правая граница диапазона (опционально)
            
        Returns:
            tuple: (cal_disp, cal_tug) - отфильтрованные массивы
        """
        from .magnet_locator import MagnetLocator
        
        disp = np.asarray(disp, dtype=np.float64)
        tug = np.asarray(tug, dtype=np.float64)
        min_idx, peak_idx = MagnetLocator.find_rising_indices(tug)

        cal_disp = disp[min_idx:peak_idx + 1].copy()
        cal_tug = tug[min_idx:peak_idx + 1].copy()

        if range_left is not None:
            m = cal_disp >= range_left
            cal_disp = cal_disp[m]
            cal_tug = cal_tug[m]
        if range_right is not None:
            m = cal_disp <= range_right
            cal_disp = cal_disp[m]
            cal_tug = cal_tug[m]

        return cal_disp, cal_tug
    
    @staticmethod
    @profile_time
    def prepare_calib_branch(disp, tug, range_left=None, range_right=None):
        """
        Предварительная подготовка калибровочных данных с кэшированием.
        Возвращает уже отсортированные данные для быстрой интерполяции.
        
        Args:
            disp: массив перемещений
            tug: массив значений датчика
            range_left: левая граница диапазона (опционально)
            range_right: правая граница диапазона (опционально)
            
        Returns:
            dict: {
                'cal_disp': отсортированные перемещения,
                'cal_tug': отсортированные значения датчика,
                'disp_raw': сырые перемещения (для статистики),
                'tug_raw': сырые значения (для статистики)
            }
        """
        from .magnet_locator import MagnetLocator
        
        disp = np.asarray(disp, dtype=np.float64)
        tug = np.asarray(tug, dtype=np.float64)
        min_idx, peak_idx = MagnetLocator.find_rising_indices(tug)

        # Извлекаем восходящий участок
        disp_raw = disp[min_idx:peak_idx + 1]
        tug_raw = tug[min_idx:peak_idx + 1]
        
        cal_disp = disp_raw.copy()
        cal_tug = tug_raw.copy()

        # Фильтрация по диапазону
        if range_left is not None:
            m = cal_disp >= range_left
            cal_disp = cal_disp[m]
            cal_tug = cal_tug[m]
        if range_right is not None:
            m = cal_disp <= range_right
            cal_disp = cal_disp[m]
            cal_tug = cal_tug[m]

        # Сортируем по значениям датчика для быстрой интерполяции
        sort_idx = np.argsort(cal_tug)
        cal_disp_sorted = cal_disp[sort_idx]
        cal_tug_sorted = cal_tug[sort_idx]
        
        return {
            'cal_disp': cal_disp_sorted,
            'cal_tug': cal_tug_sorted,
            'disp_raw': disp_raw,
            'tug_raw': tug_raw,
        }
    
    @staticmethod
    @profile_time
    def clear_cache():
        """Очистка кэша калибровочных данных."""
        Interpolator._calib_cache.clear()
    
    @staticmethod
    @profile_time
    def prepare_calib_cached(sensor_name, disp, tug, range_left=None, range_right=None):
        """
        Подготовка калибровочных данных с кэшированием по имени сенсора.
        
        Args:
            sensor_name: уникальное имя сенсора для кэширования
            disp: массив перемещений
            tug: массив значений датчика
            range_left: левая граница диапазона (опционально)
            range_right: правая граница диапазона (опционально)
            
        Returns:
            dict: подготовленные калибровочные данные
        """
        # Создаём ключ кэша
        cache_key = (sensor_name, range_left, range_right)
        
        if cache_key in Interpolator._calib_cache:
            return Interpolator._calib_cache[cache_key]
        
        # Подготавливаем данные
        result = Interpolator.prepare_calib_branch(disp, tug, range_left, range_right)
        
        # Кэшируем результат
        if len(Interpolator._calib_cache) >= Interpolator._cache_max_size:
            # Удаляем oldest entry при переполнении
            Interpolator._calib_cache.pop(next(iter(Interpolator._calib_cache)))
        
        Interpolator._calib_cache[cache_key] = result
        return result
