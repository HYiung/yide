基于Gemini的店务收银管理系统 | AI代码调改/Django+小程序框架

智能扫码录入与查价系统(网页)、智能扫码入货/线上商城购物/订单接收提醒/收银结算(小程序)

自动化记账/库存、事务安全、实时经营报表(数据可视化)、后台数据判断与存储

完成网页端与小程序端的数据互通，调试仿真

## 本地安装与测试

建议使用 Python 3.10 运行 Django 3.2.x；如果系统默认 Python 太新，可以显式使用 `python3.10` 创建虚拟环境。

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python yide/manage.py check
python yide/manage.py test
```

如果当前网络环境无法访问 PyPI，需要先配置一个可以访问的代理或包镜像；确认 `python -m pip install Django==3.2.23` 能成功后，再运行上面的 Django 检查和测试命令。

## 运行配置

微信小程序登录鉴权不要把 AppID 和 Secret 写进代码，建议通过环境变量传入：

```bash
export WECHAT_APPID="你的微信小程序AppID"
export WECHAT_SECRET="你的微信小程序Secret"
export DJANGO_SECRET_KEY="生产环境随机密钥"
export DJANGO_ALLOWED_HOSTS="127.0.0.1,localhost,你的服务器域名"
python yide/manage.py runserver 0.0.0.0:8000
```
