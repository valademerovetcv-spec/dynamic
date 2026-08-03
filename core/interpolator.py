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
        Расчёт перемещения для одного канала.
        
        Args:
            tugriki_vals: массив значений динамики
            calib_tugriki: калибровочные значения датчика
            calib_disp: калибровочные перемещения
            
        Returns:
            np.array: массив рассчитанных перемещений
        """
        result = np.empty(len(tugriki_vals))
        for i, t in enumerate(tugriki_vals):
            d = Interpolator.interp_linear(t, calib_tugriki, calib_disp)
            result[i] = d if d is not None else 0.0
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
