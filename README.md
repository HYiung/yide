# 一得书苑 · 店务收银管理系统

**Django 5.2 + 微信小程序 | EdgeOne Pages 部署**

智能扫码查价与收银系统，配套线上商城 H5。支持扫码录入、库存管理、在线下单、订单核销、实时看板与数据可视化。

## 功能总览

- **网页端收银台**（扫码查价/录入/收银 + 实时仪表盘看板 + Chart.js）
- **线上商城 H5**（浏览/购物车/下单，手机优先，响应式）
- **商品扫码入库**（支持条码枪/手动输入/外部 API 自动查商品名）
- **AI 视觉识别入库**（拍照 → AI 识别 → 自动填充商品信息）
- **库存管理**（自动扣减、低库存提醒）
- **订单管理**（待取货 → 核销完成，核销时自动扣库存+记销售）
- **数据看板**（今日营收/销量趋势/分类分布/低库存预警）
- **管理员后台**（Django Admin 增强后台）
- **小程序收银台**（店长用：实时看板 + 购物车 + 订单核销 + 进货录入）

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Django 5.2 + PostgreSQL (Neon Cloud) |
| 前端（收银台） | 原生 HTML/CSS/JS + Chart.js 4 |
| 前端（商城） | 原生 HTML/CSS/JS（手机优先） |
| 小程序 | 微信原生小程序 |
| 部署 | EdgeOne Pages (SCF)，GitHub push 自动部署 |
| 语音 | Web SpeechSynthesis API |
| AI 识别 | OpenAI 兼容 API（默认 DeepSeek） |

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

# 店长入口密码（收银台+管理后台）
export SHOPKEEPER_PASSWORD="yide888"

# 微信小程序（可选，仅小程序需要）
export WECHAT_APPID="你的小程序AppID"
export WECHAT_SECRET="你的小程序Secret"

# AI 视觉识别（可选，仅拍照入库需要）
export AI_VISION_API_KEY="你的API密钥"
export AI_VISION_BASE_URL="https://api.deepseek.com/v1"
export AI_VISION_MODEL="deepseek-chat"
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

## 页面路由

| 路径 | 内容 | 访问控制 |
|------|------|---------|
| `/` | 🛍️ 线上商城 H5（浏览/购物车/下单） | 公开 |
| `/cashier/` | 🏪 收银台 + Chart.js 看板 | 密码登录 |
| `/cashier/login/` | 🔐 店长登录页 | 公开 |
| `/cashier/logout/` | 🚪 退出登录 | 公开 |
| `/admin/` | ⚙️ 管理后台 | 密码登录后自动登录 |
| `/api/*` | 全部 API | 公开 |

店长入口流程：商城页顶部 🔑 → 输入密码（默认 `yide888`）→ 自动登录 → 收银台

## API 端点

### 收银/扫码
| 端点 | 功能 |
|---|---|
| `GET /add_item/?barcode=` | 扫码录入商品到购物车 |
| `GET /get_product_by_barcode/?barcode=` | 查价（本地+外部API） |
| `GET /get_cart_status/` | 查看当前购物车 |
| `GET /reset_cart/` | 清空购物车（不扣库存） |
| `GET /checkout_cart/` | 结账（扣库存+记销售） |
| `POST /api/quick_add_product/` | 入库商品 |

### 统计/看板
| 端点 | 功能 |
|---|---|
| `GET /get_today_stats/` | 今日营收总额和销量 |
| `GET /api/dashboard_stats/` | 完整看板（趋势/分类/低库存） |
| `GET /api/dashboard_all/` | ⭐ 综合看板（合并5个接口） |
| `GET /api/today_detail/` | 今日销售明细 |
| `GET /api/get_new_order_count/` | 待取货数 + 低库存数 |

### 商城
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
| `POST /api/ai_recognize/` | 🤖 AI 视觉识别商品 |
| `GET /api/health/` | 全量健康检查 |
| `GET /api/auto_categorize/` | 一键自动分类 |
| `GET /api/seed_products/` | 一键部署示例商品 |

## 目录结构

```
cloud-functions/              # EdgeOne 部署根目录
├── 79fd0c008639aab602732813e35d784f.txt  # 微信域名验证
├── [[default]].py            # WSGI 入口 + 诊断端点
└── api/
    ├── requirements.txt
    ├── yide/
    │   ├── settings.py       # Django 配置
    │   └── urls.py           # 主路由
    └── web/
        ├── views.py          # 全部 API + 3 个页面 HTML
        ├── models.py         # Product / CartItem / SaleHistory / Order / AdminUser
        ├── admin.py          # 彩色增强管理后台
        └── urls.py           # 路由

yide_xcx/                     # 微信小程序
├── pages/
│   ├── index/                # 收银台（看板+购物车+核销）
│   └── product/              # 进货录入（扫码+AI拍照）
├── utils/api.js              # 请求封装
└── components/custom-tab-bar # 底部导航
```

## 外部商品查询数据源

扫码不匹配本地条码时，依次并行查询：

| 来源 | 类型 | 覆盖范围 |
|------|------|---------|
| Open Library | 书籍数据库 | ISBN 书籍 |
| Google Books | 书籍数据库 | ISBN 书籍+定价 |
| barcode-list.com | 全球商品库 | 有限 |
| Open Food Facts | 全球商品库 | 食品为主 |
| upcitemdb.com | 全球商品库 | 有限 |
| Bing / DuckDuckGo | 搜索引擎 | 商品名解析 |

> ⚠️ 中国 69 开头商品条码在免费公共数据库中暂无数据，需手动录入名称价格，录入一次后自动匹配。

## 部署（EdgeOne Pages）

项目根目录 `edgeone.json` 配置了 Pages 部署，入口文件为 `cloud-functions/[[default]].py`。GitHub push 到 main 分支自动触发部署。

```bash
npm i -g edgeone-cli
eo pages deploy
```

## 常见问题

**Q: 页面滑动卡死？**
> 手机浏览器 bfcache（往返缓存）会保存 JS 状态。代码已通过 `pageshow` 事件+ `Cache-Control` 头+HTML meta 标签三重保障禁止缓存。如果还有问题，清除该网站浏览器数据后重新访问。

**Q: 小程序请求返回 `dp9fjin...` 404 错误？**
> EdgeOne 将双斜杠 `//` 识别为内部路径。使用 `https://yide.dpdns.org`（不加 `/`）。

**Q: 语音播报丢失商品名首字？**
> Chrome SpeechSynthesis 中文首字缺失 bug。已内置预热机制。

## 项目信息

- 开发环境：Windows + WSL2 Ubuntu 20.04
- 数据库：Neon PostgreSQL（云）
- 部署：EdgeOne Pages（腾讯云）
- 域名：yide.dpdns.org
