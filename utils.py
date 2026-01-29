import re
from datetime import datetime
from .sat_data import SAT_DB

def parse_line(line: str, user_config: dict = None):
    """
    智能解析 QSO 文本
    """
    # 预处理：全大写，替换中文标点
    line = line.upper().replace("：", ":").replace("，", " ")
    params = line.split()
    
    if len(params) < 2: return False, "参数不足"

    data = {
        "callsign": None,
        "freq": None,
        "rst": "59",
        "datetime_obj": None,
        "sat_name": None,
        "extra": [] # 存放未识别的文本（设备、功率、QTH等）
    }

    # 正则库
    re_freq = r'^(\d{1,4}\.\d{3,4})$' 
    re_freq_lazy = r'^(\d{5,9})$'
    re_rst = r'^([1-5][1-9][1-9]?|[+-]\d{1,2})$'
    re_call = r'[A-Z0-9/]{3,10}'

    # 1. 扫描参数
    skip_indices = []
    
    for i, token in enumerate(params):
        # 卫星
        if token in SAT_DB:
            data["sat_name"] = token
            data["freq"] = SAT_DB[token]['rx'] # 默认记下行
            skip_indices.append(i)
            continue
            
        # 标准频率
        if re.match(re_freq, token):
            data["freq"] = token
            skip_indices.append(i)
            continue
            
        # 懒人频率 (438500 -> 438.500)
        match_lazy = re.match(re_freq_lazy, token)
        if match_lazy:
            val = match_lazy.group(1)
            if len(val) >= 5: 
                mhz = float(val) / (10 ** (len(val)-3))
                data["freq"] = f"{mhz:.3f}"
                skip_indices.append(i)
                continue

        # RST (排除常用数字呼号混淆)
        if re.match(re_rst, token) and token not in ["73", "88"] and len(token) <= 3:
            data["rst"] = token
            skip_indices.append(i)
            continue
            
        # 时间日期解析 (含年份补全)
        dt_str = token.replace(".", "-").replace("/", "-")
        if "-" in dt_str or ":" in dt_str:
            formats = ["%Y-%m-%d", "%m-%d", "%H:%M", "%Y-%m-%d-%H:%M"]
            # 简单尝试合并前后 token 解析完整日期时间略显复杂，这里只解析单个 token
            # 如果日期和时间是分开的（2025.1.1 12:30），需要在上层逻辑合并
            pass 

    # 重新整理逻辑：由于时间和日期可能分开，我们保留原有的位置锚点逻辑更稳妥
    # 回退到锚点逻辑，但加入智能识别
    
    # --- 呼号识别 ---
    data["callsign"] = params[0] # 默认第一个是呼号
    if not re.match(r'^[A-Z0-9/]{3,10}$', data["callsign"]):
        return False, f"呼号格式错误: {data['callsign']}"

    # --- 频率锚点 ---
    freq_idx = -1
    for i, p in enumerate(params):
        if re.match(re_freq, p) or re.match(re_freq_lazy, p):
            freq_idx = i
            break
            
    # 如果没找到频率，看有没有卫星名
    if freq_idx == -1 and data["sat_name"]:
        # 卫星模式，频率已自动填入，不需要锚点
        pass
    elif freq_idx == -1:
        return False, "未找到频率 (43x.xxx)"

    # --- 数据提取 ---
    if freq_idx != -1:
        # 处理懒人频率
        if re.match(re_freq_lazy, params[freq_idx]):
            val = params[freq_idx]
            mhz = float(val) / (10 ** (len(val)-3))
            data["freq"] = f"{mhz:.3f}"
        else:
            data["freq"] = params[freq_idx]

        # 尝试找 RST (通常在频率后面)
        if len(params) > freq_idx + 1 and re.match(re_rst, params[freq_idx+1]):
            data["rst"] = params[freq_idx+1]
            extra_start = freq_idx + 2
        else:
            extra_start = freq_idx + 1

        # 时间 (在呼号和频率之间)
        time_tokens = params[1:freq_idx]
        if time_tokens:
            t_str = " ".join(time_tokens).replace(".", "-").replace("/", "-")
             # 年份补全
            if "-" in t_str:
                parts = t_str.split(" ")[0].split("-")
                if len(parts) == 2: t_str = f"{datetime.now().year}-{t_str}"
                elif len(parts) == 3 and len(parts[0]) == 2: t_str = "20" + t_str
            
            formats = ["%Y-%m-%d %H:%M", "%H:%M", "%Y-%m-%d"]
            for fmt in formats:
                try:
                    dt = datetime.strptime(t_str, fmt)
                    now = datetime.now()
                    if "%Y" not in fmt: dt = dt.replace(year=now.year, month=now.month, day=now.day)
                    elif "%H" not in fmt: dt = dt.replace(hour=0, minute=0, second=0)
                    data["datetime_obj"] = dt
                    break
                except: continue
        
        # 尾部参数 (设备/天馈/功率/QTH)
        data["extra"] = params[extra_start:]

    # 解析尾部参数
    rig = "-"
    ant = "-"
    power = "-"
    qth = "-"
    
    # 填充预设
    if user_config:
        rig = user_config.get("my_rig") or "-"
        power = user_config.get("my_power") or "-"
        # QTH通常指对方的，不用己方预设

    extra = data["extra"]
    if len(extra) >= 1: rig = extra[0]
    if len(extra) >= 2: ant = extra[1]
    if len(extra) >= 3: 
        raw_p = extra[2]
        try:
            float(raw_p.upper().replace("W", ""))
            power = raw_p + "W" if not raw_p.upper().endswith("W") else raw_p.upper()
        except:
            power = raw_p
    if len(extra) >= 4: qth = " ".join(extra[3:])

    return True, {
        "callsign": data["callsign"],
        "datetime_obj": data["datetime_obj"],
        "freq": data["freq"],
        "rst": data["rst"],
        "sat_name": data["sat_name"],
        "rig": rig,
        "antenna": ant,
        "power": power,
        "qth": qth
    }