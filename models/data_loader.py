"""
Модуль для загрузки и обработки данных динамики.
Обеспечивает обратную совместимость через фасад.
"""
import numpy as np
import pandas as pd
from scipy import interpolate

from .loaders import ExcelLoader, CSVLoader, XLSXLoader
from .analyzers import SignalAnalyzer


class DataLoader(ExcelLoader, CSVLoader, XLSXLoader):
    """Фасад для загрузки данных из Excel, CSV, XLSX файлов."""
    
    def __init__(self):
        # Инициализация общих атрибутов
        self.source_data = None
        self.calib_data = None
        self.result_df = None
        self.dynamics_channels = None
        self.calib_channels = None
        self.dynamics_time = None
        self.calib_disp = None
        self.result_channels = None
        self.result_channels_raw = None
        self.magnet_position = None
        self.magnet_info = ""
        self.calib_branches = None
        self.trimmed_calib = None
        self._magnet_intersections = {}
        self._magnet_x = None
        self.temp_data = None
        self.temp_channels = None
        self.temp_time = None
        self.zero_point = None
        self.auto_zero_point = None
        self.manual_zero_point = None
        self.channel_mins = None
        self.channel_baselines = None
        self.per_layer_calib = {}
        self._per_layer_magnet_x = {}
        self._per_layer_all_intersections = {}
        self._per_layer_selected_sensor = {}
        self._per_layer_intersections = {}
        self._per_layer_auto_range = {}
        self._magnet_auto_range = None
        self._per_layer_calib_info = {}
        self._per_layer_manual = {}
        self._global_calib_info = {}
        self._global_calib_manual = {}
        self._overlap_range = None
    
    def calculate_displacement(self, dynamics_channel, calib_sensor, 
                               calib_disp, calib_tug, zero_point=None):
        """Расчёт перемещения по данным динамики и калибровки."""
        dyn = np.asarray(dynamics_channel, dtype=float)
        tug = np.asarray(calib_tug, dtype=float)
        disp = np.asarray(calib_disp, dtype=float)

        if zero_point is None:
            zero_point = SignalAnalyzer.find_baseline(dyn)

        dyn_centered = dyn - zero_point

        idx_min, idx_peak = SignalAnalyzer.find_rising_indices(tug)
        tug_eff = tug[idx_min:idx_peak + 1]
        disp_eff = disp[idx_min:idx_peak + 1]

        if len(tug_eff) < 3:
            return dyn_centered * 0.0

        f_interp = interpolate.interp1d(tug_eff, disp_eff, kind='linear',
                                         bounds_error=False, fill_value='extrapolate')
        result = f_interp(dyn_centered)

        return np.round(result, 3)

    def calculate_all_layers(self, zero_point=None):
        """Расчёт перемещений для всех слоёв."""
        if not self.dynamics_channels or not self.calib_channels:
            return None

        if self.calib_disp is None:
            return None

        first_calib_key = list(self.calib_channels.keys())[0]
        calib_tug = self.calib_channels[first_calib_key]

        results = {}
        for layer_name, dyn_channel in self.dynamics_channels.items():
            disp = self.calculate_displacement(
                dyn_channel, first_calib_key,
                self.calib_disp, calib_tug, zero_point
            )
            results[layer_name] = disp

        self.result_channels = results
        if self.dynamics_time is not None:
            first_key = list(results.keys())[0]
            self.result_df = pd.DataFrame({
                "Время, мсек": self.dynamics_time,
                "Перемещение, мм": results[first_key]
            })
        return results

    def find_magnet_position(self, calib_sensor, calib_disp, calib_tug,
                             dynamics_channel, zero_point=None):
        """Определение положения магнита."""
        tug = np.asarray(calib_tug, dtype=float)
        disp = np.asarray(calib_disp, dtype=float)
        dyn = np.asarray(dynamics_channel, dtype=float)

        if zero_point is None:
            zero_point = SignalAnalyzer.find_baseline(dyn)
        dyn_centered = dyn - zero_point

        y_target = float(np.mean(dyn_centered))

        idx_min, idx_peak = SignalAnalyzer.find_rising_indices(tug)
        tug_eff = tug[idx_min:idx_peak + 1]
        disp_eff = disp[idx_min:idx_peak + 1]

        if len(tug_eff) < 3:
            self.magnet_position = None
            self.magnet_info = "Недостаточно данных калибровки"
            return None

        f_interp = interpolate.interp1d(tug_eff, disp_eff, kind='linear',
                                         bounds_error=False, fill_value='extrapolate')

        try:
            position = float(f_interp(y_target))
            self.magnet_position = np.round(position, 3)
            self.magnet_info = f"Положение: {self.magnet_position:.3f} мм"
            return self.magnet_position
        except Exception:
            self.magnet_position = None
            self.magnet_info = "Ошибка интерполяции"
            return None

    def get_overlap_range(self, calib_tug, dyn_channel, zero_point=None):
        """Определение диапазона перекрытия калибровки и динамики."""
        return SignalAnalyzer.get_overlap_range(calib_tug, dyn_channel, zero_point)
