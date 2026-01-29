from datetime import datetime
from tortoise import fields
from tortoise.models import Model

# 用户表
class HamUser(Model):
    user_id = fields.CharField(pk=True, max_length=20, description="QQ号")
    callsign = fields.CharField(max_length=20, unique=True, description="本台呼号")
    reg_time = fields.DatetimeField(auto_now_add=True)
    timezone = fields.CharField(max_length=10, default="UTC+8") 
    
    # 个人预设
    my_grid = fields.CharField(max_length=10, null=True)
    my_rig = fields.CharField(max_length=100, null=True)
    my_power = fields.CharField(max_length=20, null=True)

    class Meta:
        table = "ham_users"
        app = "ham"

# 群白名单表
class HamGroupWhiteList(Model):
    group_id = fields.CharField(pk=True, max_length=20, description="群号")
    add_time = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "ham_group_whitelist"
        app = "ham"

# 中继数据表
class HamRelay(Model):
    id = fields.IntField(pk=True)
    keyword = fields.CharField(max_length=20, index=True)
    name = fields.CharField(max_length=50)
    details = fields.CharField(max_length=200)
    contributor = fields.CharField(max_length=20, default="System")

    class Meta:
        table = "ham_relays"
        app = "ham"

# QSO 日志表
class QsoLog(Model):
    id = fields.IntField(pk=True)
    
    # 外键使用短名引用
    owner = fields.ForeignKeyField('ham.HamUser', related_name='logs')
    
    callsign = fields.CharField(max_length=20)
    freq = fields.CharField(max_length=20)
    rst = fields.CharField(max_length=10)
    
    qth = fields.CharField(max_length=100, default="-")
    rig = fields.CharField(max_length=100, default="-")
    antenna = fields.CharField(max_length=100, default="-") # 天馈
    power = fields.CharField(max_length=20, default="-")
    
    # 卫星专用
    sat_name = fields.CharField(max_length=20, null=True)
    
    time = fields.DatetimeField(default=datetime.utcnow)
    input_timezone = fields.CharField(max_length=10, default="UTC+8") 

    class Meta:
        table = "qso_logs"
        app = "ham"