# 一得书苑 · 店务收银管理系统

**Django 5.2 + 微信小程序 | EdgeOne Pages 部署**

智能扫码查价与收银系统，配套微信小程序线上商城。支持扫码录入、库存管理、在线下单、订单核销、实时看板与数据可视化。

## 功能总览

- **网页端收银台**（扫码查价/录入/收银 + 实时仪表盘看板）
- **微信小程序商城**（线上浏览/购物车/下单/取货核销）
- **商品扫码入库**（支持条码枪/手动输入）
- **库存管理**（自动扣减、低库存提醒）
- **订单管理**（待取货 → 完成，核销时自动扣库存+记销售历史）
- **数据看板**（今日营收/销量趋势/分类分布/低库存预警）
- **管理员后台**（Django Admin 带看板增强）

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Django 5.2 + PostgreSQL (Neon) |
| 前端（收银台） | 原生 HTML/CSS/JS + Chart.js |
| 小程序 | 微信原生小程序 |
| 部署 | EdgeOne Pages (SCF) |
| 语音 | Web SpeechSynthesis API |

## 快速开始

### 后端

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 环境变量

```bash
export DJANGO_SECRET_KEY="你的密钥"
export DJANGO_DEBUG="True"
export CLOUD_DATABASE_URL="postgresql://user:pass@host/db"
export WECHAT_APPID="你的小程序AppID"
export WECHAT_SECRET="你的小程序Secret"
```

### 本地运行

```bash
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

### 微信小程序

项目路径：`yide_xcx/`

在微信开发者工具中打开该目录，`utils/api.js` 中的 `BASE_URL` 已配置为：
- 生产：`https://yide.dpdns.org`
- 开发：`http://192.168.1.138:8000`

切换 `DEV_MODE` 变量即可。

## API 端点

### 收银/扫码
| 端点 | 功能 |
|---|---|
| `GET /` | 收银台页面（含仪表盘看板） |
| `GET /add_item/?barcode=xxx` | 扫码录入商品到购物车 |
| `GET /get_product_by_barcode/?barcode=xxx` | 仅查价 |
| `GET /get_cart_status/` | 查看当前购物车 |
| `GET /reset_cart/` | 清空购物车 |
| `GET /checkout_cart/` | 结账（扣库存+记销售） |

### 统计/看板
| 端点 | 功能 |
|---|---|
| `GET /get_today_stats/` | 今日营收总额和销量 |
| `GET /api/dashboard_stats/` | 完整看板数据（趋势/分类/低库存） |
| `GET /api/get_new_order_count/` | 待取货订单数 + 低库存数 |

### 小程序商城
| 端点 | 功能 |
|---|---|
| `GET /api/mall_products/?category=&search=` | 商品列表 |
| `POST /api/submit_order/` | 提交订单 |
| `GET /api/pending_orders/` | 待取货订单列表 |
| `POST /api/verify_order/` | 核销取货 |
| `GET /api/search_order/?key=` | 搜索订单 |

### 工具
| 端点 | 功能 |
|---|---|
| `GET /api/health/` | 健康检查 |
| `GET /api/auto_categorize/` | 自动分类商品 |
| `GET /api/seed_products/` | 一键部署示例商品 |

## 目录结构

```
cloud-functions/          # EdgeOne 部署目录
  [[default]].py          # WSGI 入口 + 诊断端点
  api/
    yide/                 # Django 项目配置
      settings.py
      urls.py
    web/                  # 收银/商城核心 app
      views.py            # 所有 API + CASHIER_HTML（含看板）
      models.py           # Product, CartItem, SaleHistory, Order, AdminUser
      admin.py            # 带彩色标签的管理后台
      urls.py             # 路由
      templates/
        cashier.html      # 收银台模板（本地开发用）

yide_xcx/                 # 微信小程序
  pages/
    mall/                 # 线上商城
    order/                # 确认订单
    index/                # 收银舱（管理员）
    product/              # 进货入库
  utils/
    api.js                # API 请求封装
  components/
    custom-tab-bar/       # 底部导航栏（角色自适应）
```

## 部署（EdgeOne Pages）

项目根目录 `edgeone.json` 配置了 Pages 部署。入口文件为 `cloud-functions/[[default]].py`。

```bash
# 安装 EdgeOne CLI
npm i -g edgeone-cli

# 部署
eo pages deploy
```

## 常见问题

**Q: 小程序请求返回 `dp9fjin...404` 错误？**
> 检查 `utils/api.js` 中 `BASE_URL` 末尾是否有尾斜杠。EdgeOne 会将双斜杠 `//` 识别为内部路径，导致 301 重定向。应使用 `https://yide.dpdns.org`（不加 `/`）。

**Q: 语音播报丢失商品名首字？**
> Chrome SpeechSynthesis 有中文首字缺失 bug。代码已内建预热机制，自动在播报前放一个空白语音初始化引擎。

**Q: 静态文件返回 500？**
> EdgeOne 会拦截 `/static/` 前缀导致 SCF 崩溃。解决方案：将 `STATIC_URL` 改为 `/assets/`，通过 Django WSGI 管道 serve 静态文件，并配置 `insecure=True`。

## 项目信息

- 开发环境：Windows + WSL2 Ubuntu 20.04
- 数据库：Neon PostgreSQL（云）
- 部署：EdgeOne Pages（腾讯云）
- 域名：yide.dpdns.org
