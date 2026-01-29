import os
import json
import base64
import asyncio
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta
from nonebot import require, on_command, get_bot, get_driver
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.typing import T_State
from nonebot.plugin import PluginMetadata
from nonebot.permission import SUPERUSER
from nonebot.exception import FinishedException

__plugin_meta__ = PluginMetadata(
    name="无线电日志(QSO)",
    description="HAM无线电通联日志管理工具",
    usage="发送 'qso帮助' 查看使用说明",
    type="application",
    supported_adapters={"~onebot.v11"},
)

require("nonebot_plugin_tortoise_orm")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_htmlrender")

from nonebot_plugin_tortoise_orm import add_model
from nonebot_plugin_apscheduler import scheduler
from .config import plugin_config
from .utils import parse_line
from .render import logs_to_image

# 数据库连接
db_url = (
    f"mysql://{plugin_config.qso_db_user}:{str(plugin_config.qso_db_password)}@"
    f"{plugin_config.qso_db_host}:{plugin_config.qso_db_port}/{plugin_config.qso_db_name}"
)

from . import model
# 注册模块，连接名为 "ham"
add_model(model.__name__, db_name="ham", db_url=db_url)
DB_NAME = "ham"

# --- 启动钩子：导入中继 (修复版) ---
driver = get_driver()
@driver.on_startup
async def init_relays():
    # 给数据库连接一点反应时间
    await asyncio.sleep(1)
    
    from .model import HamRelay
    try:
        # 修复：使用 exists() 替代 count()，避开 ORM 路由 Bug
        if await HamRelay.all().limit(1).exists():
            return
    except Exception:
        # 如果查询报错，说明可能表刚建好，继续尝试导入
        pass

    json_path = Path(__file__).parent / "relays.json"
    if not json_path.exists(): return
    
    print("[HAM] 正在初始化中继数据库...")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        count = 0
        for item in data:
            dtl = f"RX:{item.get('下行','')} TX:{item.get('上行','')}"
            if item.get('发射亚音'): dtl += f" T:{item['发射亚音']}"
            if item.get('接收亚音'): dtl += f" R:{item['接收亚音']}"
            if item.get('模式'): dtl += f" [{item['模式']}]"
            
            # 修复：使用逐条创建，最稳妥的方式
            await HamRelay.create(
                keyword=item.get("省","未知"), 
                name=item.get("名称","未知"), 
                details=dtl, 
                contributor="System"
            )
            count += 1
            
        print(f"[HAM] 成功导入 {count} 条中继数据")
    except Exception as e:
        print(f"[HAM] 中继导入遇到问题 (可尝试发送'重载中继库'修复): {e}")

# --- 指令定义 ---
qso_cmd = on_command("qso", aliases={"记录", "添加log", "QSO"}, priority=5, block=True)
help_cmd = on_command("qso帮助", aliases={"qsohelp"}, priority=5, block=True)
reg_cmd = on_command("注册呼号", priority=5, block=True)
unbind_cmd = on_command("解绑呼号", aliases={"注销呼号"}, priority=5, block=True)
view_cmd = on_command("查看qso", priority=5, block=True)
export_cmd = on_command("导出qso", priority=5, block=True)
mod_cmd = on_command("修改qso", priority=5, block=True)
del_cmd = on_command("删除qso", priority=5, block=True)
set_cmd = on_command("设置", aliases={"preset"}, priority=5, block=True)
tz_cmd = on_command("修改时区", aliases={"set_timezone"}, priority=5, block=True)

relay_query = on_command("查中继", aliases={"中继查询", "查询中继"}, priority=5, block=True)
relay_add = on_command("添加中继", priority=5, block=True)
relay_del = on_command("删中继", aliases={"删除中继"}, priority=5, block=True)
relay_import = on_command("重载中继库", permission=SUPERUSER, priority=1, block=True)

wl_add = on_command("开启本群QSO", permission=SUPERUSER, priority=1, block=True)
wl_del = on_command("关闭本群QSO", permission=SUPERUSER, priority=1, block=True)

# --- 权限与工具函数 ---
async def check_permission(event: MessageEvent, respond: bool = False):
    from .model import HamGroupWhiteList 
    if not isinstance(event, GroupMessageEvent): return True
    gid = str(event.group_id)
    if await HamGroupWhiteList.filter(group_id=gid).exists(): return True
    if respond: await get_bot().send(event, "⚠️ 本群未开启 QSO 功能。\n请管理员发送 '开启本群QSO' 激活。")
    return False

async def get_user(event: MessageEvent):
    from .model import HamUser
    return await HamUser.filter(user_id=event.get_user_id()).first()

# ================= 业务逻辑 =================

async def logic_view(event: MessageEvent):
    from .model import QsoLog
    user = await get_user(event)
    if not user: await get_bot().send(event, "❌ 未注册"); return

    logs = await QsoLog.filter(owner=user).order_by('-time').limit(20)
    if not logs: await get_bot().send(event, "暂无记录。"); return
    
    logs = sorted(logs, key=lambda x: x.time)
    
    display_data = []
    tz_name = "UTC"
    if user.timezone == "UTC+8": tz_name = "BJT"
        
    for i, log in enumerate(logs, 1):
        show_time = log.time
        if user.timezone == "UTC+8": show_time += timedelta(hours=8)
        
        display_data.append({
            "serial": i, "id": log.id, "callsign": log.callsign,
            "freq": log.freq, "rst": log.rst, "qth": log.qth,
            "rig": log.rig, "antenna": log.antenna, "power": log.power,
            "time_str": show_time.strftime("%Y-%m-%d %H:%M"), "sat_name": log.sat_name
        })
    pic = await logs_to_image(display_data, title=f"{user.callsign} ({user.timezone})", time_col_name=f"{tz_name}时间")
    if pic: await get_bot().send(event, MessageSegment.image(pic))

async def logic_export(event: MessageEvent):
    path = await generate_excel_file(event.get_user_id())
    if path:
        try:
            file_bytes = path.read_bytes()
            b64 = base64.b64encode(file_bytes).decode()
            file_seg = MessageSegment(type="file", data={"file": f"base64://{b64}", "name": path.name})
            await get_bot().send(event, file_seg)
        except Exception as e: await get_bot().send(event, f"发送失败：{e}")
    else: await get_bot().send(event, "无记录")

async def logic_delete(event: MessageEvent, msg_args: str):
    from .model import QsoLog
    user = await get_user(event)
    if not user: await get_bot().send(event, "未注册"); return
    raw = msg_args.replace("删除", "").strip()
    ids = []
    if "-" in raw:
        try: s, e = map(int, raw.split("-")); ids = list(range(s, e+1))
        except: pass
    elif raw.isdigit(): ids = [int(raw)]
    if not ids: await get_bot().send(event, "请指定ID (例: 10 或 10-15)"); return
    
    count = await QsoLog.filter(id__in=ids, owner=user).delete()
    if count: await get_bot().send(event, f"🗑️ 删除 {count} 条记录")
    else: await get_bot().send(event, "未找到记录")

async def logic_unbind(event: MessageEvent):
    from .model import HamUser
    user = await HamUser.get_or_none(user_id=event.get_user_id())
    if not user: await get_bot().send(event, "未注册"); return
    await user.delete()
    await get_bot().send(event, f"👋 已注销")

# ================= 主入口 =================
@qso_cmd.handle()
async def _(event: MessageEvent, state: T_State, args: Message = CommandArg()):
    if not await check_permission(event, respond=False): return
    text = args.extract_plain_text().strip()
    if not text: await help_handler(event); await qso_cmd.finish()
    
    parts = text.split()
    cmd = parts[0].lower()
    if cmd in ["查看", "list"]: await logic_view(event); await qso_cmd.finish()
    elif cmd in ["导出", "excel"]: await logic_export(event); await qso_cmd.finish()
    elif cmd in ["删除", "del"]: await logic_delete(event, " ".join(parts[1:])); await qso_cmd.finish()
    elif cmd in ["修改", "edit"]: await qso_cmd.finish("请用: 修改qso <ID>")
    elif cmd in ["解绑", "注销"]: await logic_unbind(event); await qso_cmd.finish()
    
    user = await get_user(event)
    if not user: await qso_cmd.finish("请先注册！")
    state["user"] = user
    config = {"my_rig": user.my_rig, "my_power": user.my_power}
    valid_data, errs = [], []
    for line in text.split('\n'):
        if not line.strip(): continue
        ok, res = parse_line(line, config)
        if ok: valid_data.append(res)
        else: errs.append(f"❌ {line} -> {res}")
    if not valid_data: await qso_cmd.finish(f"格式错误:\n" + "\n".join(errs))
    
    state["valid_data"] = valid_data
    state["error_msg"] = "\n".join(errs)
    await qso_cmd.send(f"✅ 解析 {len(valid_data)} 条\n-----------------\n请确认制式:\n1️⃣ UTC\n2️⃣ 北京时间(UTC+8)")

@qso_cmd.got("time_choice")
async def confirm_time(event: MessageEvent, state: T_State):
    from .model import QsoLog
    try:
        choice = event.get_message().extract_plain_text().strip()
        is_bj = "2" in choice
        user = state["user"]
        now = datetime.utcnow()
        for item in state["valid_data"]:
            t = item.get('datetime_obj') or now
            if item.get('datetime_obj') and is_bj: t -= timedelta(hours=8)
            
            await QsoLog.create(owner=user, callsign=item['callsign'], freq=item['freq'],
                rst=item['rst'], qth=item['qth'], rig=item['rig'], antenna=item['antenna'],
                power=item['power'], sat_name=item['sat_name'], time=t,
                input_timezone="UTC+8" if is_bj else "UTC")
        msg = f"🎉 已保存 {len(state['valid_data'])} 条!"
        if state["error_msg"]: msg += f"\n⚠️ 未导入:\n{state['error_msg']}"
        await qso_cmd.finish(msg)
    except FinishedException: raise
    except Exception as e: await qso_cmd.finish(f"💥 错误: {e}")

# ================= 辅助指令 =================
@help_cmd.handle()
async def help_handler(event: MessageEvent):
    if not await check_permission(event, respond=True): return
    await get_bot().send(event, "📻 无线电日志 📻\n1️⃣ 注册: 注册呼号 <呼号>\n2️⃣ 设置: 设置 设备 <名> 功率 <值>\n3️⃣ 记录: QSO <呼号> [日期] [时间] <频率> <RST> [设备] [天馈] [功率] [QTH]\n4️⃣ 查询: 查中继 <地名>\n5️⃣ 管理: 查看 | 导出 | 修改 <ID> | 删除 <ID>")

@reg_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    from .model import HamUser
    if not await check_permission(event, respond=True): return
    call = args.extract_plain_text().strip().upper()
    if not call: await reg_cmd.finish("请输入呼号")
    if await HamUser.filter(user_id=event.get_user_id()).exists(): await reg_cmd.finish("已注册")
    if await HamUser.filter(callsign=call).exists(): await reg_cmd.finish("已被绑定")
    await HamUser.create(user_id=event.get_user_id(), callsign=call)
    await reg_cmd.finish(f"🎉 注册成功: {call}")

@set_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    if not await check_permission(event): return
    user = await get_user(event)
    if not user: await set_cmd.finish("未注册")
    txt = args.extract_plain_text().strip()
    parts = txt.split()
    if not parts: await set_cmd.finish(f"当前预设:\n设备: {user.my_rig}\n功率: {user.my_power}\n\n修改例: 设置 设备 K5 功率 5W")
    iter_parts = iter(parts)
    updated = []
    for k in iter_parts:
        val = next(iter_parts, None)
        if not val: break
        if k in ["设备", "rig"]: user.my_rig = val; updated.append("设备")
        elif k in ["功率", "power"]: user.my_power = val; updated.append("功率")
    if updated: await user.save(); await set_cmd.finish(f"✅ 已更新: {', '.join(updated)}")

@mod_cmd.handle()
async def _(event: MessageEvent, state: T_State, args: Message = CommandArg()):
    from .model import QsoLog
    if not await check_permission(event): return
    user = await get_user(event)
    if not user: await mod_cmd.finish("未注册")
    msg = args.extract_plain_text().strip()
    if not msg.isdigit(): await mod_cmd.finish("请指定ID")
    log = await QsoLog.filter(id=int(msg), owner=user).first()
    if not log: await mod_cmd.finish("找不到记录")
    state["log"] = log
    await mod_cmd.send(f"修改 #{log.id}\n当前: {log.callsign} {log.freq}\n发送修改内容(换行分隔):\n频率 438.500")

@mod_cmd.got("content")
async def _(event: MessageEvent, state: T_State):
    lines = event.get_message().extract_plain_text().strip().split('\n')
    changes = {}
    map_keys = {"呼号":"callsign", "频率":"freq", "信号":"rst", "QTH":"qth", "设备":"rig", "天馈":"antenna", "功率":"power"}
    for l in lines:
        p = l.split(maxsplit=1)
        if len(p)==2 and p[0].upper() in map_keys: changes[map_keys[p[0].upper()]] = p[1]
    if not changes: await mod_cmd.finish("❌ 无效修改")
    log = state["log"]
    for k,v in changes.items(): setattr(log, k, v)
    await log.save()
    await mod_cmd.finish("✅ 修改成功")

@relay_query.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    if not await check_permission(event, respond=True): return
    from .model import HamRelay
    from tortoise.expressions import Q
    k = args.extract_plain_text().strip()
    if not k: await relay_query.finish("请指定关键词")
    
    # 模糊查询 + 限制数量
    res = await HamRelay.filter(Q(keyword__contains=k)|Q(name__contains=k)).limit(10).all()
    
    if not res: await relay_query.finish("未找到，请去HamCQ查询")
    msg = f"📡 '{k}' 结果:\n" + "\n".join([f"[{r.keyword}] {r.name}\n{r.details}" for r in res])
    await relay_query.finish(msg)

@relay_import.handle()
async def _(event: MessageEvent):
    from .model import HamRelay
    await HamRelay.all().delete()
    # 重新触发导入
    count = 0
    json_path = Path(__file__).parent / "relays.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                dtl = f"RX:{item.get('下行','')} TX:{item.get('上行','')}"
                if item.get('发射亚音'): dtl += f" T:{item['发射亚音']}"
                if item.get('模式'): dtl += f" [{item['模式']}]"
                await HamRelay.create(keyword=item.get("省",""), name=item.get("名称",""), details=dtl)
                count += 1
    await relay_import.finish(f"✅ 重载完成: {count}条")

@tz_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    if not await check_permission(event): return
    user = await get_user(event)
    if not user: await tz_cmd.finish("未注册")
    arg = args.extract_plain_text().strip().upper()
    if arg in ["UTC", "1"]: user.timezone = "UTC"; await user.save(); await tz_cmd.finish("✅ 已设为 UTC")
    elif arg in ["UTC+8", "8", "CN", "2"]: user.timezone = "UTC+8"; await user.save(); await tz_cmd.finish("✅ 已设为 UTC+8")
    else: await tz_cmd.finish("请发送：修改时区 UTC 或 UTC+8")

# 其他指令保持不变 (unbind, del, wl_add, wl_del, export, backup)
# 为节省篇幅，请保留上一次回复中的这些函数代码，它们是正确的。
# 重点是上面的 init_relays 和 relay_import 修复。
# ... (unbind_cmd, wl_add, wl_del, generate_excel_file, auto_backup 代码同上) ...