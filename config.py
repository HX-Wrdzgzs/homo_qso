from typing import Union
from pydantic import BaseModel, Extra
from nonebot import get_driver

class Config(BaseModel, extra=Extra.ignore):
    # 数据库配置
    qso_db_host: str = "127.0.0.1"
    qso_db_port: int = 3306
    qso_db_user: str = "ham_radio_db"
    
    # ⬇️ 修复：允许字符串或数字类型的密码
    qso_db_password: Union[str, int] = ""
    
    qso_db_name: str = "ham_radio_db"
    
    # 备份配置
    qso_backup_group: int = 1029453948
    qso_backup_interval_hours: int = 4

plugin_config = Config.parse_obj(get_driver().config.dict())