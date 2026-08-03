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
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active

        max_col = ws.max_column or 25
        row1 = [ws.cell(row=1, column=c).value for c in range(1, max_col + 1)]
        row2 = [ws.cell(row=2, column=c).value for c in range(1, max_col + 1)]

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
            wb.close()
            return self._load_excel_legacy(path)

        dyn_section = 0

        time_col = []
        for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                min_col=dyn_section + 1, max_col=dyn_section + 1,
                                values_only=True):
            if row[0] is not None:
                time_col.append(row[0])
        n_time = len(time_col)

        dyn_channels = {}
        for c in range(dyn_section + 2, cal_section + 1):
            ch_name = ws.cell(row=2, column=c).value
            if not ch_name:
                continue
            vals = []
            for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                    min_col=c, max_col=c, values_only=True):
                if row[0] is not None:
                    vals.append(float(row[0]))
            n = min(n_time, len(vals))
            if n > 0 and not all(v == 0 for v in vals[:n]):
                dyn_channels[ch_name] = np.array(vals[:n])

        self.dynamics_time = np.array(time_col[:n_time]) if n_time > 0 else None
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

        cal_disp = []
        for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                min_col=cal_section + 1, max_col=cal_section + 1,
                                values_only=True):
            if row[0] is not None:
                cal_disp.append(float(row[0]))
        nc = len(cal_disp)
        cal_disp_name = ws.cell(row=2, column=cal_section + 1).value or "Перемещение, мм"

        end_cal = res_section if res_section else max_col
        cal_channels = {}
        for c in range(cal_section + 2, end_cal + 1):
            ch_name = ws.cell(row=2, column=c).value
            if not ch_name:
                continue
            ch_vals = []
            for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                    min_col=c, max_col=c, values_only=True):
                if row[0] is not None:
                    ch_vals.append(float(row[0]))
            n = min(nc, len(ch_vals))
            if n > 0 and not all(v == 0 for v in ch_vals[:n]):
                cal_channels[ch_name] = np.round(np.array(ch_vals[:n]), 3)

        self.calib_disp = np.array(cal_disp[:nc]) if nc > 0 else None
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

        if res_section is not None:
            res_time = []
            for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                    min_col=res_section + 1, max_col=res_section + 1,
                                    values_only=True):
                if row[0] is not None:
                    res_time.append(row[0])
            nr = len(res_time)

            self.result_channels = {}
            for c in range(res_section + 2, max_col + 1):
                ch_name = ws.cell(row=2, column=c).value
                if not ch_name:
                    continue
                ch_vals = []
                for row in ws.iter_rows(min_row=3, max_row=ws.max_row,
                                        min_col=c, max_col=c, values_only=True):
                    if row[0] is not None:
                        ch_vals.append(float(row[0]))
                n = min(nr, len(ch_vals))
                if n > 0:
                    self.result_channels[ch_name] = np.round(np.array(ch_vals[:n]), 3)

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

        wb.close()
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
        df = pd.read_excel(path, header=None)
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

    def load_calibration_xlsx(self, path):
        """Загрузка калибровочных данных из XLSX."""
        df = pd.read_excel(path, header=None)
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

    def load_temperature_xlsx(self, path):
        """Загрузка температурных данных из XLSX."""
        df = pd.read_excel(path, header=0)
        df.columns = [c.strip() for c in df.columns]
        date_col = df.columns[0]
        dates = pd.to_datetime(df[date_col], format="%d.%m.%Y %H:%M", errors="coerce")
        if dates.isna().all():
            dates = pd.to_datetime(df[date_col], errors="coerce")
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

    def load_calibration_for_layer(self, path, layer_name):
        """Загрузка калибровки для конкретного слоя."""
        if path.lower().endswith('.xlsx'):
            df = pd.read_excel(path, header=None)
        else:
            df = pd.read_csv(path, sep=";", header=None, decimal=",")
        df = df.sort_values(by=0).reset_index(drop=True)
        disp_col = np.round(df.iloc[:, 0].values.astype(float), 3)
        tug_cols = {}
        for i in range(1, df.shape[1]):
            col_name = f"Датчик Холла {i}"
            vals = np.round(df.iloc[:, i].values.astype(float), 3)
            if not np.all(vals == 0):
                tug_cols[col_name] = vals
        self.per_layer_calib[layer_name] = {"disp": disp_col, "tug": tug_cols}
