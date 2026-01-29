import pandas as pd
from nonebot_plugin_htmlrender import html_to_pic

async def logs_to_image(logs, title="QSO LOGS", time_col_name="UTC时间"):
    if not logs: return None

    data = []
    for log in logs:
        # 如果是卫星通联，频率显示卫星名
        freq_display = log['freq']
        if log.get('sat_name'):
            freq_display = f"{log['sat_name']} ({log['freq']})"

        data.append({
            "序号": log['serial'],
            "对方呼号": log['callsign'],
            "频率/卫星": freq_display,
            "RST": log['rst'],
            "设备": log['rig'],
            "天馈": log['antenna'],
            "功率": log['power'],
            "QTH": log['qth'],
            time_col_name: log['time_str']
        })

    df = pd.DataFrame(data)
    cols = ["序号", "对方呼号", "频率/卫星", "RST", "设备", "天馈", "功率", "QTH", time_col_name]
    df = df.reindex(columns=cols)
    
    table_html = df.to_html(index=False, classes="fl-table", border=0)

    css = """
    <html>
    <head>
    <style>
        body { font-family: "Microsoft YaHei", sans-serif; padding: 20px; background-color: #f2f2f2; }
        h2 { text-align: center; color: #333; margin-bottom: 20px; font-size: 24px; }
        .fl-table {
            border-radius: 8px; font-size: 14px; font-weight: normal; border: none;
            border-collapse: collapse; width: 100%; max-width: 100%; 
            white-space: nowrap; background-color: white; overflow: hidden;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }
        .fl-table td, .fl-table th { text-align: center; padding: 12px 15px; }
        .fl-table td { border-right: 1px solid #f8f8f8; font-size: 14px; color: #333; }
        .fl-table thead th { color: #ffffff; background: #324960; font-weight: bold; }
        .fl-table thead th:nth-child(odd) { background: #4FC3A1; }
        .fl-table tr:nth-child(even) { background: #F8F8F8; }
        .fl-table td:nth-child(1) { color: #555; font-weight: bold; } 
    </style>
    </head>
    <body>
        <h2>""" + title + """</h2>
        """ + table_html + """
    </body>
    </html>
    """
    pic = await html_to_pic(html=css, viewport={"width": 1250, "height": 800})
    return pic