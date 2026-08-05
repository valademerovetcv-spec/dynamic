"""
Модуль для загрузки данных из различных форматов файлов.
"""
import numpy as np
import pandas as pd
import openpyxl


class ExcelLoader:
    """Загрузка данных из Excel файлов."""
    
    def load_excel(self, path):
        """Загрузка данных из Excel файла (основной формат)."""
        # Быстрая загрузка через pandas с оптимизациями
        # Используем openpyxl в режиме read_only для ускорения чтения больших файлов
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.active
        
        # Читаем все данные сразу в память через генератор - быстрее чем iter_rows
        all_data = list(ws.iter_rows(values_only=True))
        wb.close()
        
        if len(all_data) < 2:
            return self._load_excel_legacy(path)
        
        # Конвертируем в numpy массив для быстрой обработки
        data_array = np.array(all_data, dtype=object)
        
        max_col = data_array.shape[1]
        
        # Получаем заголовки из первых двух строк
        row1 = data_array[0].tolist()
        row2 = data_array[1].tolist()
        
        # Находим секции
        cal_section = None
        for c, name in enumerate(row2):
            if name and "Перемещение" in str(name):
                cal_section = c
                break
        
        res_section = None
        for c, val in enumerate(row1):
            if val == "Динамика в мм":
                res_section = c
                break
        
        if cal_section is None:
            return self._load_excel_legacy(path)
        
        dyn_section = 0
        
        # Извлекаем все данные одним срезом из numpy массива - это быстрее
        data_values = data_array[2:].astype(float)
        
        # Время (первый столбец)
        time_raw = data_values[:, dyn_section]
        time_mask = ~np.isnan(time_raw)
        time_col = time_raw[time_mask]
        n_time = len(time_col)
        
        # Каналы динамики (между dyn_section и cal_section)
        dyn_channels = {}
        for c in range(dyn_section + 1, cal_section):
            ch_name = row2[c] if c < len(row2) else None
            if not ch_name:
                continue
            ch_raw = data_values[:, c]
            ch_mask = ~np.isnan(ch_raw)
            ch_vals = ch_raw[ch_mask]
            n = min(n_time, len(ch_vals))
            if n > 0:
                arr = ch_vals[:n]
                if not np.all(arr == 0):
                    dyn_channels[ch_name] = arr
        
        self.dynamics_time = time_col if n_time > 0 else None
        self.dynamics_channels = dyn_channels if dyn_channels else None

        if self.dynamics_time is not None and self.dynamics_channels:
            first_key = list(self.dynamics_channels.keys())[0]
            self.source_data = pd.DataFrame({
                "Время, мсек": self.dynamics_time,
                "Слои": self.dynamics_channels[first_key]
            })
        elif n_time > 0:
            self.source_data = pd.DataFrame({"Время, мсек": self.dynamics_time})
        else:
            self.source_data = None

        # Калибровочные данные
        if cal_section + 1 < max_col:
            cal_disp_raw = data_values[:, cal_section]
            cal_disp_mask = ~np.isnan(cal_disp_raw)
            cal_disp = cal_disp_raw[cal_disp_mask]
            nc = len(cal_disp)
            cal_disp_name = row2[cal_section + 1] if cal_section + 1 < len(row2) else "Перемещение, мм"
            
            end_cal = res_section if res_section else max_col
            cal_channels = {}
            for c in range(cal_section + 1, min(end_cal, max_col)):
                ch_name = row2[c] if c < len(row2) else None
                if not ch_name:
                    continue
                ch_raw = data_values[:, c]
                ch_mask = ~np.isnan(ch_raw)
                ch_vals = ch_raw[ch_mask]
                n = min(nc, len(ch_vals))
                if n > 0:
                    arr = np.round(ch_vals[:n], 3)
                    if not np.all(arr == 0):
                        cal_channels[ch_name] = arr
            
            self.calib_disp = cal_disp[:nc] if nc > 0 else None
            self.calib_channels = cal_channels if cal_channels else None
            
            if self.calib_disp is not None and self.calib_channels:
                first_key = list(self.calib_channels.keys())[0]
                self.calib_data = pd.DataFrame({
                    cal_disp_name: self.calib_disp,
                    first_key: self.calib_channels[first_key]
                })
            elif nc > 0:
                self.calib_data = pd.DataFrame({cal_disp_name: self.calib_disp})
            else:
                self.calib_data = None
        else:
            self.calib_disp = None
            self.calib_channels = None
            self.calib_data = None
        
        # Результаты если есть
        if res_section is not None and res_section + 1 < max_col:
            res_raw = data_values[:, res_section]
            res_mask = ~np.isnan(res_raw)
            res_time = res_raw[res_mask]
            nr = len(res_time)
            
            self.result_channels = {}
            for c in range(res_section + 1, max_col):
                ch_name = row2[c] if c < len(row2) else None
                if not ch_name:
                    continue
                ch_raw = data_values[:, c]
                ch_mask = ~np.isnan(ch_raw)
                ch_vals = ch_raw[ch_mask]
                n = min(nr, len(ch_vals))
                if n > 0:
                    self.result_channels[ch_name] = np.round(ch_vals[:n], 3)
            
            if nr > 0:
                first_key = list(self.result_channels.keys())[0] if self.result_channels else None
                self.result_df = pd.DataFrame({
                    "Время, мсек": res_time[:nr],
                    "Перемещение, мм": self.result_channels[first_key][:nr] if first_key else [0]*nr
                })
            else:
                self.result_df = None
                self.result_channels = {}
        else:
            self.result_df = None
            self.result_channels = {}
        
        return self.source_data, self.calib_data

    def _load_excel_legacy(self, path):
        """Загрузка устаревшего формата Excel файлов."""
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active

        time_col, tugriki_col = [], []
        for row in ws.iter_rows(min_row=3, max_row=ws.max_row, min_col=1, max_col=2, values_only=True):
            if row[0] is not None and row[1] is not None:
                time_col.append(row[0])
                tugriki_col.append(row[1])
        n = min(len(time_col), len(tugriki_col))
        self.source_data = pd.DataFrame({
            "Время, мсек": time_col[:n],
            "Датчик Холла": tugriki_col[:n]
        })

        calib_disp, calib_tugriki = [], []
        for row in ws.iter_rows(min_row=3, max_row=ws.max_row, min_col=4, max_col=5, values_only=True):
            if row[0] is not None and row[1] is not None:
                calib_disp.append(row[0])
                calib_tugriki.append(row[1])
        nc = min(len(calib_disp), len(calib_tugriki))
        self.calib_data = pd.DataFrame({
            "Перемещение, мм": calib_disp[:nc],
            "Датчик Холла": calib_tugriki[:nc]
        })

        wb.close()
        return self.source_data, self.calib_data


class CSVLoader:
    """Загрузка данных из CSV файлов."""
    
    def load_dynamics_csv(self, path):
        """Загрузка данных динамики из CSV."""
        df = pd.read_csv(path, sep=";", header=None, decimal=",")
        df = df.sort_values(by=0).reset_index(drop=True)
        time_col = df.iloc[:, 0].values
        self.dynamics_time = time_col
        self.dynamics_channels = {}
        for i in range(1, df.shape[1]):
            col_name = f"Слой {i}"
            ch_vals = df.iloc[:, i].values.astype(float)
            if np.all(ch_vals == 0):
                continue
            self.dynamics_channels[col_name] = ch_vals
        self.source_data = pd.DataFrame({
            "Время, мсек": time_col,
            "Слои": df.iloc[:, 1].values
        })
        return self.dynamics_time, self.dynamics_channels

    def load_calibration_csv(self, path):
        """Загрузка калибровочных данных из CSV."""
        df = pd.read_csv(path, sep=";", header=None, decimal=",")
        df = df.sort_values(by=0).reset_index(drop=True)
        disp_col = np.round(df.iloc[:, 0].values.astype(float), 3)
        self.calib_disp = disp_col
        self.calib_channels = {}
        for i in range(1, df.shape[1]):
            col_name = f"Слой {i}"
            ch_vals = np.round(df.iloc[:, i].values.astype(float), 3)
            if np.all(ch_vals == 0):
                continue
            self.calib_channels[col_name] = ch_vals
        self.calib_data = pd.DataFrame({
            "Перемещение, мм": disp_col,
            "Датчик Холла": df.iloc[:, 1].values
        })
        return self.calib_disp, self.calib_channels

    def load_temperature_csv(self, path):
        """Загрузка температурных данных из CSV."""
        df = pd.read_csv(path, sep=";", header=0, decimal=",")
        df.columns = [c.strip() for c in df.columns]
        date_col = df.columns[0]
        dates = pd.to_datetime(df[date_col], format="%d.%m.%Y %H:%M")
        self.temp_time = dates
        self.temp_channels = {}
        idx = 1
        for col in df.columns[1:]:
            vals = pd.to_numeric(df[col], errors="coerce").values
            if np.all(vals == 0):
                continue
            self.temp_channels[f"Слой {idx}"] = vals
            idx += 1
        self.temp_data = df.iloc[:, 1:].copy()
        return self.temp_time, self.temp_channels


class XLSXLoader:
    """Загрузка данных из XLSX файлов (без заголовков)."""
    
    def load_dynamics_xlsx(self, path):
        """Загрузка данных динамики из XLSX."""
        # Оптимизированная загрузка с явным указанием типов
        df = pd.read_excel(path, header=None, dtype=float)
        df = df.sort_values(by=0).reset_index(drop=True)
        time_col = df.iloc[:, 0].to_numpy(dtype=float)
        self.dynamics_time = time_col
        self.dynamics_channels = {}
        for i in range(1, df.shape[1]):
            col_name = f"Слой {i}"
            ch_vals = df.iloc[:, i].to_numpy(dtype=float)
            if np.all(ch_vals == 0):
                continue
            self.dynamics_channels[col_name] = ch_vals
        self.source_data = pd.DataFrame({
            "Время, мсек": time_col,
            "Слои": df.iloc[:, 1].to_numpy(dtype=float)
        })
        return self.dynamics_time, self.dynamics_channels

    def load_calibration_xlsx(self, path):
        """Загрузка калибровочных данных из XLSX."""
        # Оптимизированная загрузка с явным указанием типов
        df = pd.read_excel(path, header=None, dtype=float)
        df = df.sort_values(by=0).reset_index(drop=True)
        disp_col = np.round(df.iloc[:, 0].to_numpy(dtype=float), 3)
        self.calib_disp = disp_col
        self.calib_channels = {}
        for i in range(1, df.shape[1]):
            col_name = f"Слой {i}"
            ch_vals = np.round(df.iloc[:, i].to_numpy(dtype=float), 3)
            if np.all(ch_vals == 0):
                continue
            self.calib_channels[col_name] = ch_vals
        self.calib_data = pd.DataFrame({
            "Перемещение, мм": disp_col,
            "Датчик Холла": df.iloc[:, 1].to_numpy(dtype=float)
        })
        return self.calib_disp, self.calib_channels

    def load_temperature_xlsx(self, path):
        """Загрузка температурных данных из XLSX."""
        # Оптимизированная загрузка с явным указанием типов
        df = pd.read_excel(path, header=0, dtype={'date': str})  # Дата как строка для парсинга
        df.columns = [c.strip() for c in df.columns]
        date_col = df.columns[0]
        dates = pd.to_datetime(df[date_col], format="%d.%m.%Y %H:%M", errors="coerce")
        if dates.isna().all():
            dates = pd.to_datetime(df[date_col], errors="coerce")
        self.temp_time = dates
        self.temp_channels = {}
        idx = 1
        for col in df.columns[1:]:
            vals = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float)
            if np.all(vals == 0):
                continue
            self.temp_channels[f"Слой {idx}"] = vals
            idx += 1
        self.temp_data = df.iloc[:, 1:].copy()
        return self.temp_time, self.temp_channels

    def load_calibration_for_layer(self, path, layer_name):
        """Загрузка калибровки для конкретного слоя."""
        # Инициализируем словарь если он ещё не создан
        if not hasattr(self, 'per_layer_calib') or self.per_layer_calib is None:
            self.per_layer_calib = {}
        
        # Инициализируем словари для информации о калибровке
        if not hasattr(self, '_per_layer_calib_info') or self._per_layer_calib_info is None:
            self._per_layer_calib_info = {}
        
        if not hasattr(self, '_per_layer_auto_range') or self._per_layer_auto_range is None:
            self._per_layer_auto_range = {}
        
        # Быстрая загрузка файла
        if path.lower().endswith('.xlsx'):
            # Используем pandas с оптимизациями для xlsx
            df = pd.read_excel(path, header=None, dtype=float)
        else:
            # Для CSV используем быстрое чтение
            df = pd.read_csv(path, sep=";", header=None, decimal=",", dtype=float)
        
        # Сортируем и сбрасываем индекс
        df = df.sort_values(by=0).reset_index(drop=True)
        
        # Извлекаем данные
        disp_col = np.round(df.iloc[:, 0].to_numpy(dtype=float), 3)
        tug_cols = {}
        for i in range(1, df.shape[1]):
            col_name = f"Датчик Холла {i}"
            vals = np.round(df.iloc[:, i].to_numpy(dtype=float), 3)
            if not np.all(vals == 0):
                tug_cols[col_name] = vals
        
        # Сохраняем данные
        self.per_layer_calib[layer_name] = {"disp": disp_col, "tug": tug_cols}
        
        # Вычисляем автоматический диапазон перекрытия
        auto_left, auto_right = self._find_layer_overlap(disp_col, tug_cols)
        self._per_layer_auto_range[layer_name] = (auto_left, auto_right)
        
        # Сохраняем информацию о загруженной калибровке для быстрого доступа
        sensor_names = list(tug_cols.keys())
        if sensor_names:
            self._per_layer_calib_info[layer_name] = {
                "sensor": sensor_names[0],
                "range_left": auto_left,
                "range_right": auto_right,
                "auto_sensor": sensor_names[0],
                "auto_range_left": auto_left,
                "auto_range_right": auto_right,
                "manual_sensor": False,
                "manual_range": False,
                "magnet_x": None,
            }
    
    def _find_rising_range(self, disp, values):
        """Поиск основного возрастающего участка на калибровочной кривой."""
        tug = np.asarray(values, dtype=float)
        d = np.asarray(disp, dtype=float)
        n = min(len(tug), len(d))
        if n < 3:
            return (float(np.min(d)), float(np.max(d)))
        
        # Находим все участки монотонного возрастания сигнала датчика
        diff = np.diff(tug[:n])
        
        # Ищем непрерывные участки где diff > 0
        rising_segments = []
        start_idx = None
        
        for i in range(len(diff)):
            if diff[i] > 0:
                if start_idx is None:
                    start_idx = i
            else:
                if start_idx is not None:
                    # Завершаем текущий участок
                    rising_segments.append((start_idx, i))
                    start_idx = None
        
        # Если последний участок продолжается до конца
        if start_idx is not None:
            rising_segments.append((start_idx, len(diff)))
        
        # Если не нашли ни одного участка возрастания, возвращаем полный диапазон
        if not rising_segments:
            return (float(np.min(d)), float(np.max(d)))
        
        # Выбираем самый длинный участок возрастания
        longest_segment = max(rising_segments, key=lambda x: x[1] - x[0])
        rising_start, rising_end = longest_segment
        
        # Возвращаем диапазон перемещений соответствующий основному участку возрастания
        return (float(d[rising_start]), float(d[rising_end]))
    
    def _merge_rising_ranges(self, ranges):
        """Объединение нескольких диапазонов в общий."""
        if not ranges:
            return (0.0, 0.0)
        
        valid_ranges = [r for r in ranges if r is not None]
        if not valid_ranges:
            return (0.0, 0.0)
        
        left = max(r[0] for r in valid_ranges)
        right = min(r[1] for r in valid_ranges)
        
        if left >= right:
            # Если нет перекрытия, берём средний диапазон
            left = np.mean([r[0] for r in valid_ranges])
            right = np.mean([r[1] for r in valid_ranges])
        
        return (left, right)
    
    def _find_layer_overlap(self, disp, tug_dict):
        """Поиск области перекрытия для конкретного слоя."""
        ranges = [self._find_rising_range(disp, tv) for tv in tug_dict.values()]
        return self._merge_rising_ranges(ranges)
