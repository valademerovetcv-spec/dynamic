"""Компоненты пользовательского интерфейса."""
from ui.styles import BG, PANEL_BG, HEADER_BG, CHANNEL_COLORS

import tkinter as tk
from tkinter import ttk


def create_treeview(parent):
    """Создает Treeview с прокруткой."""
    container = ttk.Frame(parent)
    container.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    tree = ttk.Treeview(container, show="headings", selectmode="browse")
    vsb = ttk.Scrollbar(container, orient=tk.VERTICAL, command=tree.yview)
    hsb = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    container.grid_rowconfigure(0, weight=1)
    container.grid_columnconfigure(0, weight=1)
    return tree


def populate_treeview(tree, df):
    """Заполняет Treeview данными из DataFrame."""
    import pandas as pd
    
    tree.delete(*tree.get_children())
    if df is None or df.empty:
        return
    cols = list(df.columns)
    tree["columns"] = cols
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=130, minwidth=80, anchor=tk.CENTER)
    for i, (_, row) in enumerate(df.iterrows()):
        vals = [str(v) if pd.notna(v) else "" for v in row]
        tag = "even" if i % 2 == 0 else "odd"
        tree.insert("", tk.END, values=vals, tags=(tag,))
    tree.tag_configure("even", background="#f8fafc")
    tree.tag_configure("odd", background="#ffffff")


def create_channel_toggles(parent, channels, callback, title="Слои:", vars_dict=None):
    """Создает панель переключателей каналов."""
    for w in parent.winfo_children():
        w.destroy()
    
    if not channels:
        return {}
    
    from ui.styles import BG, CHANNEL_COLORS
    
    ttk.Label(parent, text=title, background=BG,
              font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(4, 4))
    
    channel_vars = {} if vars_dict is None else vars_dict
    for i, ch_name in enumerate(channels.keys()):
        import numpy as np
        # Проверяем, является ли канал нулевым (для dynamics_channels)
        is_zero = False
        if hasattr(channels, 'get') and ch_name in channels:
            ch_data = channels[ch_name]
            is_zero = np.all(ch_data == 0) if hasattr(ch_data, '__len__') else False
        
        var = tk.BooleanVar(value=not is_zero)
        channel_vars[ch_name] = var
        color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
        cb = tk.Checkbutton(parent, text=ch_name, variable=var,
                            bg=BG, fg=color, selectcolor=BG,
                            activebackground=BG, activeforeground=color,
                            font=("Segoe UI", 9, "bold"),
                            command=callback)
        cb.pack(side=tk.LEFT, padx=2)
    
    return channel_vars
