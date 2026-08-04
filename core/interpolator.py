"""
Модуль для линейной интерполяции и расчёта перемещений.
"""
import numpy as np


class Interpolator:
    """Класс для интерполяции значений перемещения."""

    @staticmethod
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
        tugriki_vals = np.asarray(tugriki_vals, dtype=float)
        calib_tugriki = np.asarray(calib_tugriki, dtype=float)
        calib_disp = np.asarray(calib_disp, dtype=float)
        
        n_calib = len(calib_tugriki)
        if n_calib < 2:
            return np.zeros_like(tugriki_vals)
        
        # Векторизованная интерполяция через searchsorted
        # Сортируем калибровочные данные по tugriki (если ещё не отсортированы)
        sort_idx = np.argsort(calib_tugriki)
        calib_tug_sorted = calib_tugriki[sort_idx]
        calib_disp_sorted = calib_disp[sort_idx]
        
        # Находим индексы интерполяции для всех значений одновременно
        indices = np.searchsorted(calib_tug_sorted, tugriki_vals, side='right')
        
        # Ограничиваем индексы допустимым диапазоном
        indices = np.clip(indices, 1, n_calib - 1)
        
        # Получаем соседние точки для интерполяции
        t0 = calib_tug_sorted[indices - 1]
        t1 = calib_tug_sorted[indices]
        d0 = calib_disp_sorted[indices - 1]
        d1 = calib_disp_sorted[indices]
        
        # Вычисляем интерполяцию
        denom = t1 - t0
        # Избегаем деления на ноль
        mask = denom != 0
        result = np.where(mask, d0 + (tugriki_vals - t0) * (d1 - d0) / denom, d0)
        
        # Обработка граничных случаев (за пределами калибровки)
        below_mask = tugriki_vals <= calib_tug_sorted[0]
        above_mask = tugriki_vals >= calib_tug_sorted[-1]
        
        result = np.where(below_mask, calib_disp_sorted[0], result)
        result = np.where(above_mask, calib_disp_sorted[-1], result)
        
        return np.round(result, 3)

    @staticmethod
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
        tugriki_vals = np.asarray(tugriki_vals, dtype=float)
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
        
        disp = np.asarray(disp, dtype=float)
        tug = np.asarray(tug, dtype=float)
        min_idx, peak_idx = MagnetLocator.find_rising_indices(tug)

        cal_disp = disp[min_idx:peak_idx + 1]
        cal_tug = tug[min_idx:peak_idx + 1]

        if range_left is not None:
            m = cal_disp >= range_left
            cal_disp = cal_disp[m]
            cal_tug = cal_tug[m]
        if range_right is not None:
            m = cal_disp <= range_right
            cal_disp = cal_disp[m]
            cal_tug = cal_tug[m]

        return cal_disp, cal_tug
