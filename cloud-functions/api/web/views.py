import base64
import json
import hmac
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout, get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import webassets
from .catalog import LOW_STOCK_THRESHOLD, auto_categorize_queryset, low_stock_queryset
from .models import AdminUser, CartItem, Order, OrderItem, Product, SaleHistory
from .services import complete_order

logger = logging.getLogger(__name__)


def serve_web_asset(request, path):
    """输出内嵌的 CSS / JS 资源（见 webassets.py 顶部说明）。

    EdgeOne 只部署 .py 文件，static/ 目录下的资源会被剥离，所以这里直接
    从 Python 模块读内容返回，而不是交给 staticfiles finder。
    """
    asset = webassets.ASSETS.get(path)
    if asset is None:
        return HttpResponse(status=404)
    content, content_type = asset
    response = HttpResponse(content, content_type=content_type)
    # URL 里带了 ?v=<内容哈希>，内容一变 URL 就变，可以放心长缓存
    if request.GET.get('v') == webassets.VERSION:
        response['Cache-Control'] = 'public, max-age=31536000, immutable'
    else:
        response['Cache-Control'] = 'no-cache'
    return response


def _with_asset_version(html):
    """给页面 HTML 里的 /assets/... 资源地址补上 ?v=<版本号>"""
    for path in webassets.ASSETS:
        bare = '/assets/' + path
        html = html.replace('"%s"' % bare, '"%s"' % webassets.url(path))
    return html


def admin_logout(request):
    """后台退出后回店长入口，而不是 Django 默认的 admin 登录页。

    在 yide/urls.py 里注册在 admin/ 之前，覆盖 AdminSite 自带的登出视图
    （后台右上角「退出」是 POST 到 admin:logout，所以这里不做方法限制）。
    """
    auth_logout(request)
    return redirect('cashier_login')


def now_local():
    """返回 Asia/Shanghai 时区的当前时间（用于兼容 EdgeOne UTC 环境）"""
    return timezone.localtime(timezone.now())


def get_request_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_json_body(request):
    """安全解析 JSON body，返回 (data_dict, error_response)"""
    try:
        return json.loads(request.body or '{}'), None
    except json.JSONDecodeError:
        return None, JsonResponse({'status': 'fail', 'msg': '请求数据格式不正确'})




def is_shopkeeper_request(request):
    """Return True for authenticated staff or requests carrying the shopkeeper API token."""
    if request.user.is_authenticated and request.user.is_staff:
        return True

    expected = getattr(settings, 'SHOPKEEPER_API_TOKEN', '')
    provided = request.headers.get('X-Shopkeeper-Token')
    if expected and provided and hmac.compare_digest(provided, expected):
        return True

    return False


def require_shopkeeper_api(request):
    if is_shopkeeper_request(request):
        return None
    if not getattr(settings, 'SHOPKEEPER_API_TOKEN', '') and not settings.DEBUG:
        return JsonResponse({'status': 'fail', 'msg': '店长 API Token 未配置，敏感接口已禁用'}, status=503)
    return JsonResponse({'status': 'fail', 'msg': '需要店长权限'}, status=403)

def _line_total_expr():
    """复用：price * quantity 表达式，避免重复定义"""
    return ExpressionWrapper(
        F('price') * F('quantity'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )


def _today_sales_stats():
    """复用：获取今日营收总额和总销量"""
    now = now_local()
    today = now.date()
    stats = SaleHistory.objects.filter(
        sale_date__date=today
    ).aggregate(
        total=Sum(_line_total_expr()),
        count=Sum('quantity')
    )
    return {
        'total_amount': float(stats['total'] or 0),
        'today_count': int(stats['count'] or 0),
    }


def _daily_revenue(days=7):
    """复用：获取最近 N 天的每日营收趋势"""
    now = now_local()
    today = now.date()
    result = []
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        day_stats = SaleHistory.objects.filter(
            sale_date__date=day
        ).aggregate(total=Sum(_line_total_expr()))
        result.append({
            'date': day.strftime('%m/%d'),
            'total': float(day_stats['total'] or 0)
        })
    return result


def serialize_order(order):
    items = []
    for item in order.items.select_related('product').all():
        items.append({
            'product_id': item.product_id,
            'name': item.product.name,
            'count': item.count,
            'price': str(item.product.price),
        })

    return {
        'id': order.id,
        'customer_name': order.customer_name,
        'total_price': str(order.total_price),
        'order_sn': order.order_sn,
        'create_time': timezone.localtime(order.create_time).strftime('%Y-%m-%d %H:%M'),
        'items': items,
    }


def check_role(request):
    code = request.GET.get('code')
    if not code and request.method == 'POST':
        try:
            data = json.loads(request.body)
            code = data.get('code')
        except (json.JSONDecodeError, TypeError, AttributeError):
            code = request.POST.get('code')

    appid = getattr(settings, 'WECHAT_APPID', '')
    secret = getattr(settings, 'WECHAT_SECRET', '')

    if not code or not appid or not secret:
        logger.warning("微信登录参数缺失，缺省为普通顾客")
        return JsonResponse({'role': 'customer'})

    url = (f"https://api.weixin.qq.com/sns/jscode2session"
           f"?appid={appid}&secret={secret}&js_code={code}&grant_type=authorization_code")

    try:
        res = requests.get(url, timeout=5).json()
        openid = res.get('openid')
        if not openid:
            logger.warning("微信登录返回无 openid: %s", res)
            return JsonResponse({'role': 'customer'})

        is_admin = AdminUser.objects.filter(openid=openid).exists()
        role = 'admin' if is_admin else 'customer'
        logger.info("用户角色判定: openid=%s -> %s", openid[:8], role)
        return JsonResponse({'role': role})

    except Exception as e:
        logger.error("请求微信接口失败: %s", e)
        return JsonResponse({'role': 'customer'})


# 页面渲染：显示收银台网页
# ⚠️ EdgeOne 不会部署 .html 模板文件，所以内联 HTML
CASHIER_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>一得书苑 · 收银台 + 看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<link rel="stylesheet" href="/assets/web/css/cashier.css">
</head>
<body>
<div class="header">
  <h1>📖 一得书苑 · 收银台</h1>
  <p id="header-sub">扫码录入 · 一键收银 · 实时看板</p>
</div>
<div class="stats-row">
  <div class="stat-card">
    <div class="stat-icon green">💰</div>
    <div class="stat-body">
      <div class="stat-label">今日营收</div>
      <div class="stat-value green" id="s-today-revenue">￥0.00</div>
    </div>
    <span class="click-hint">详情 ▸</span>
  </div>
  <div class="stat-card">
    <div class="stat-icon orange">📦</div>
    <div class="stat-body">
      <div class="stat-label">今日销量</div>
      <div class="stat-value orange" id="s-today-count">0 件</div>
    </div>
    <span class="click-hint">详情 ▸</span>
  </div>
  <div class="stat-card">
    <div class="stat-icon red">📋</div>
    <div class="stat-body">
      <div class="stat-label">待取货</div>
      <div class="stat-value red" id="s-pending">-</div>
    </div>
    <span class="click-hint">详情 ▸</span>
  </div>
  <div class="stat-card">
    <div class="stat-icon blue">⚠️</div>
    <div class="stat-body">
      <div class="stat-label">低库存</div>
      <div class="stat-value blue" id="s-lowstock">-</div>
    </div>
    <span class="click-hint">详情 ▸</span>
  </div>
</div>
<div class="main-content">
  <div class="scan-section">
    <div class="card">
      <div class="card-title">🔍 扫码查价 / 录入</div>
      <div class="scan-input-row">
        <input type="text" id="barcode-input" autofocus placeholder="请扫码商品条码..." />
        <div class="mode-btn" id="modeToggle" onclick="toggleMode()">🔍 查价</div>
      </div>
      <div class="product-display" id="productDisplay">
        <div class="p-name" id="p-name">等待扫码...</div>
        <div class="p-price" id="p-price">-</div>
      </div>
      <div class="action-btns">
        <button class="btn-checkout" onclick="doCheckout()">💳 结账</button>
        <button class="btn-reset" onclick="resetAll()">🗑️ 清空</button>
      </div>
    </div>
    <div class="card">
      <div class="card-title">📜 扫码记录</div>
      <div class="log-area" id="logArea">
        <div class="empty-state" id="emptyLog">暂无记录，扫码后将显示在此处</div>
      </div>
      <div id="cartSummary" style="display:none;margin-top:12px;padding-top:12px;border-top:2px dashed #e8e8e8;font-size:15px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="color:#999;">已录入 <strong id="cartCount">0</strong> 件商品</span>
          <span style="font-weight:800;font-size:20px;color:#f5222d;" id="cartTotal">￥0.00</span>
        </div>
      </div>
    </div>
  </div>
  <div class="dashboard-section">
    <div class="chart-grid">
      <div class="chart-card">
        <div class="chart-title">📈 近 7 日营收趋势</div>
        <canvas id="revenueChart"></canvas>
      </div>
      <div class="chart-card">
        <div class="chart-title">🧩 商品分类分布</div>
        <canvas id="categoryChart"></canvas>
      </div>
    </div>
    <div class="card">
      <div class="card-title">📦 低库存提醒</div>
      <div id="stockList"><div class="empty-state">暂无低库存商品</div></div>
    </div>
  </div>
</div>

<script src="/assets/web/js/cashier.js" defer></script>

<!-- Modal -->
<div class="modal-overlay" id="modalOverlay" onclick="closeModal(event)">
  <div class="modal-box" id="modalBox">
    <div class="modal-header">
      <span class="modal-title" id="modalTitle">详情</span>
      <span class="modal-close" onclick="closeModal()">✕</span>
    </div>
    <div class="modal-body" id="modalBody"><div class="modal-loading">加载中...</div></div>
  </div>
</div>

<!-- Admin Bar -->
<div class="admin-bar">
  <a href="/admin/">⚙️ 管理后台</a>
  <a href="/cashier/logout/">🚪 退出登录</a>
</div>

</body>
</html>"""
# ============================================================
# 线上商城 H5 — 顾客线上下单页面（位于根路径 /）
# ============================================================
MALL_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>一得书苑 · 线上商城</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 100 100%27><text y=%27.9em%27 font-size=%2790%27>📖</text></svg>">
<link rel="stylesheet" href="/assets/web/css/mall.css">
</head>
<body>

<!-- Header -->
<div class="mall-header">
  <h1>🛍️ 一得书苑 · 线上商城</h1>
  <div class="header-btn-group">
    <button class="header-btn" id="orderQueryBtn" title="查订单">📋</button>
    <a href="/cashier/" class="header-btn" title="店长入口">🔑</a>
  </div>
</div>

<!-- Search -->
<div class="search-bar">
  <div class="search-box">
    <input type="text" id="searchInput" placeholder="搜索商品名称…" autocomplete="off">
    <span class="search-clear" id="clearBtn" style="display:none">✕</span>
    <button id="searchBtn">🔍</button>
  </div>
</div>

<!-- Categories -->
<div class="category-bar" id="categoryBar"></div>

<!-- Loading -->
<div class="loading-tip" id="loadingTip">
  <div class="loading-spinner"></div>
  <div>加载中...</div>
</div>

<!-- Product Grid -->
<div class="product-grid" id="productGrid"></div>

<!-- Empty -->
<div class="empty-tip" id="emptyTip" style="display:none">
  <span class="empty-icon">📭</span>
  该分类暂无商品
</div>

<!-- Offline Banner -->
<div class="offline-banner" id="offlineBanner">⚠️ 网络异常，部分功能可能不可用</div>

<!-- Cart Detail Overlay -->
<div class="overlay" id="cartOverlay"></div>

<!-- Cart Detail Panel -->
<div class="cart-panel" id="cartPanel">
  <div class="cart-panel-header">
    <span class="title">🛒 已选商品</span>
    <span class="clear-cart-btn" id="clearCartBtn">🗑️ 清空</span>
  </div>
  <div class="cart-list" id="cartList"></div>
</div>

<!-- Order Modal -->
<div class="overlay" id="orderOverlay"></div>
<div class="modal-panel" id="orderPanel">
  <h2>📋 确认订单</h2>
  <div class="order-summary" id="orderSummary"></div>
  <div class="name-input-wrap">
    <label>👤 取货人姓名</label>
    <input type="text" id="customerName" placeholder="请输入您的姓名" autocomplete="name">
  </div>
  <div class="modal-actions">
    <button class="btn-cancel" id="orderCancel">取消</button>
    <button class="btn-confirm" id="orderSubmit">✅ 提交订单</button>
  </div>
</div>

<!-- Success Modal -->
<div class="overlay" id="successOverlay"></div>
<div class="modal-panel success-modal" id="successPanel">
  <span class="success-icon">🎉</span>
  <h2>下单成功！</h2>
  <div class="order-no">订单号：<span id="orderSn"></span></div>
  <div class="tips">请到柜台出示姓名核对后付款取货 🏪</div>
  <button class="btn-primary" id="successDone">好的</button>
</div>

<!-- Share QR Modal -->
<div class="overlay" id="shareOverlay"></div>
<div class="modal-panel success-modal" id="sharePanel" style="max-width:420px;">
  <span class="success-icon">📤</span>
  <h2>分享一得书苑</h2>
  <div style="text-align:center;margin:16px 0;">
    <img src="/qr.png" alt="商城二维码" style="width:260px;height:auto;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.1);">
    <div style="font-size:13px;color:var(--text-secondary);margin-top:8px;">微信扫一扫 · 在线选书下单</div>
  </div>
  <button class="btn-primary" id="shareDoneBtn">好的</button>
</div>

<!-- Order Query Modal -->
<div class="overlay" id="queryOverlay"></div>
<div class="modal-panel" id="queryPanel" style="max-height:70vh;">
  <h2>📋 查订单</h2>
  <div style="margin-bottom:16px;">
    <label style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:6px;">👤 输入下单时留的姓名</label>
    <div style="display:flex;gap:8px;">
      <input type="text" id="queryNameInput" placeholder="请输入姓名" autocomplete="name" style="flex:1;padding:10px 12px;border:1px solid var(--border);border-radius:8px;font-size:15px;outline:none;">
      <button id="querySubmitBtn" style="padding:10px 20px;background:var(--green);color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;">查询</button>
    </div>
  </div>
  <div id="queryResult"></div>
  <div style="margin-top:12px;text-align:center;">
    <button class="btn-cancel" id="queryCloseBtn" style="padding:10px 24px;border:none;border-radius:8px;font-size:14px;cursor:pointer;background:var(--bg);color:var(--text);">关闭</button>
  </div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<!-- Bottom Cart Bar (fixed, shows when cart has items) -->
<div class="cart-bar hidden" id="cartBar">
  <div class="cart-info" id="cartBarInfo">
    <div class="cart-icon-wrap">
      <span>🛒</span>
      <span class="cart-badge-num" id="cartBadge">0</span>
    </div>
    <div class="cart-price-wrap">
      <span class="total-text">合计</span>
      <span class="price-num" id="cartTotal">0.00</span>
    </div>
  </div>
  <button class="settle-btn" id="settleBtn">去结算</button>
</div>

<!-- Shopkeeper Entrance (always visible at bottom) -->
<div class="shopkeeper-bar">🏪 到店取货 · 提交后到柜台报姓名付款取货 · <a href="javascript:void(0)" id="shareBtn" style="color:var(--green);text-decoration:none;font-weight:600;">📤 分享商城</a></div>

<script src="/assets/web/js/mall.js" defer></script>
</body>
</html>"""

def mall_home(request):
    from django.http import HttpResponse
    from web.qr_code_data import QR_CODE_BASE64
    # /qr.png → data:image/png;base64,... 内联，避免 EdgeOne/CDN 导致二维码加载失败
    qr_uri = f"data:image/png;base64,{QR_CODE_BASE64}"
    html = _with_asset_version(MALL_HTML)
    html = html.replace('src="/qr.png"', f'src="{qr_uri}"')
    response = HttpResponse(html)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


def cash_register(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect('cashier_login')
    response = HttpResponse(_with_asset_version(CASHIER_HTML))
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


# ============================================================
# 店长入口登录（单密码 + 自动登录 Django admin）
# ============================================================
CASHIER_LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>一得书苑 · 店长入口</title>
<link rel="stylesheet" href="/assets/web/css/cashier-login.css">
</head>
<body data-login-error="__LOGIN_ERROR__">
<div class="login-card">
  <span class="login-icon">🔐</span>
  <div class="login-title">店长入口</div>
  <div class="login-sub">请输入密码进入收银台与后台管理</div>
  <form class="login-form" method="POST" action="/cashier/login/" id="loginForm">
    <input type="password" name="password" id="passwordInput" placeholder="输入密码" autocomplete="off" autofocus>
    <button type="submit" class="login-btn">🔑 进入</button>
    <div class="login-error" id="errorMsg"></div>
  </form>
</div>
<div class="back-link">
  <a href="/">← 返回线上商城</a>
</div>

<script src="/assets/web/js/cashier-login.js" defer></script>
</body>
</html>"""


@csrf_exempt
def cashier_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('cashier')

    if request.method == 'POST':
        pwd = request.POST.get('password', '')
        if pwd == settings.SHOPKEEPER_PASSWORD:
            User = get_user_model()
            shopkeeper, created = User.objects.get_or_create(
                username='shopkeeper',
                defaults={
                    'is_staff': True,
                    'is_superuser': True,
                    'email': 'shopkeeper@yide.local',
                }
            )
            if created:
                shopkeeper.set_unusable_password()
                shopkeeper.save()
            else:
                # 确保权限不变（防止手动修改）
                changed = False
                if not shopkeeper.is_staff:
                    shopkeeper.is_staff = True; changed = True
                if not shopkeeper.is_superuser:
                    shopkeeper.is_superuser = True; changed = True
                if changed:
                    shopkeeper.save()

            auth_login(request, shopkeeper, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('cashier')

        request.session['cashier_login_error'] = True
        return redirect('cashier_login')

    has_error = bool(request.session.pop('cashier_login_error', False))
    html = _with_asset_version(CASHIER_LOGIN_HTML)
    response = HttpResponse(html.replace('__LOGIN_ERROR__', 'true' if has_error else 'false'))
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response


def cashier_logout(request):
    auth_logout(request)
    return redirect('/cashier/login/')


# API 接口：根据条码查商品
def _estimate_price_from_db(name):
    """从数据库中类似商品估算价格，返回 Decimal 或 None"""
    if not name:
        return None
    try:
        # 提取关键词（取前6个字）
        keywords = name[:6]
        similar = Product.objects.filter(name__icontains=keywords, price__gt=0)
        if similar.exists():
            from django.db.models import Avg
            avg = similar.aggregate(avg_price=Avg('price'))['avg_price']
            if avg:
                return round(float(avg), 2)
    except Exception:
        pass
    return None


def _lookup_barcode_external(barcode):
    """
    条码不在本地库时，尝试从多个外部开放 API 并行查询商品信息。
    返回 dict 或 None。
    """
    barcode = barcode.strip()
    is_isbn = (barcode.startswith('978') or barcode.startswith('979')) and len(barcode) == 13

    # ── ISBN 书籍：并行查 Open Library（书名）+ Google Books（书名+零售价）──
    if is_isbn:
        name = None
        price = None
        try:
            with ThreadPoolExecutor(max_workers=2) as ex:
                ol_fut = ex.submit(_fetch_isbn_openlibrary, barcode)
                gb_fut = ex.submit(_fetch_isbn_googlebooks, barcode)
                # 先等 Open Library
                try:
                    ol_name = ol_fut.result(timeout=12)
                    if ol_name:
                        name = ol_name
                except Exception:
                    pass
                # 再等 Google Books
                try:
                    gb_result = gb_fut.result(timeout=12)
                    if gb_result:
                        if not name:
                            name = gb_result.get('name')
                        price = gb_result.get('price')
                except Exception:
                    pass
        except Exception:
            # ThreadPoolExecutor 不可用（如某些 serverless 环境）→ 降级为串行
            pass

        if not name:
            name = _fetch_isbn_openlibrary(barcode)
        if not name:
            gb_result = _fetch_isbn_googlebooks(barcode)
            if gb_result:
                name = gb_result.get('name')
                price = gb_result.get('price')

        if name:
            return {
                'name': name,
                'category': 'books',
                'barcode': barcode,
                'price_estimate': price,
            }

    # ── 通用条码：并行查多个数据源，取最先查到结果的 ──
    try:
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {
                ex.submit(_fetch_barcodelist, barcode): 1,
                ex.submit(_fetch_openfoodfacts, barcode): 2,
                ex.submit(_fetch_upcitemdb, barcode): 3,
                ex.submit(_fetch_bing_search, barcode): 4,
                ex.submit(_fetch_duckduckgo_search, barcode): 5,
            }
            for future in as_completed(futures, timeout=20):
                result = future.result()
                if result:
                    return {
                        'name': result,
                        'category': 'others',
                        'barcode': barcode,
                        'price_estimate': _estimate_price_from_db(result),
                    }
    except Exception:
        pass

    # 降级：串行尝试
    for fetcher in (_fetch_barcodelist, _fetch_openfoodfacts, _fetch_upcitemdb, _fetch_bing_search, _fetch_duckduckgo_search):
        try:
            result = fetcher(barcode)
            if result:
                return {
                    'name': result,
                    'category': 'others',
                    'barcode': barcode,
                    'price_estimate': _estimate_price_from_db(result),
                }
        except Exception:
            continue

    return None


def _fetch_isbn_openlibrary(barcode):
    """Open Library API — 查 ISBN 书名+作者（免费、无需密钥）"""
    try:
        resp = requests.get(f'https://openlibrary.org/isbn/{barcode}.json', timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json()
        title = data.get('title', '')
        if not title:
            return None
        authors = data.get('authors', [])
        author_names = []
        for a in authors:
            key = a.get('key', '')
            if key:
                try:
                    a_resp = requests.get(f'https://openlibrary.org{key}.json', timeout=5)
                    if a_resp.status_code == 200:
                        author_names.append(a_resp.json().get('name', ''))
                except Exception:
                    pass
        author_str = ' / '.join(author_names) if author_names else ''
        full_name = f'{title}（{author_str}）' if author_str else title
        logger.info("OpenLibrary 查到 ISBN %s → %s", barcode, full_name)
        return full_name
    except requests.Timeout:
        logger.warning("OpenLibrary 查询 %s 超时", barcode)
    except Exception as e:
        logger.warning("OpenLibrary 查询 %s 异常: %s", barcode, e)
    return None


def _fetch_isbn_googlebooks(barcode):
    """Google Books API — 查 ISBN 书名+零售价（公共端点，有限额）"""
    try:
        resp = requests.get(
            f'https://www.googleapis.com/books/v1/volumes?q=isbn:{barcode}',
            timeout=8
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        items = data.get('items', [])
        if not items:
            return None
        vol = items[0].get('volumeInfo', {})
        title = vol.get('title', '')
        if not title:
            return None
        authors = vol.get('authors', [])
        full_name = f'{title}（{" / ".join(authors)}）' if authors else title
        # 零售价
        price = None
        try:
            sale_info = items[0].get('saleInfo', {})
            if sale_info.get('isEbook') or sale_info.get('saleability') != 'NOT_FOR_SALE':
                list_price = sale_info.get('listPrice', {})
                if list_price.get('amount'):
                    price = round(float(list_price['amount']), 2)
        except Exception:
            pass
        logger.info("GoogleBooks 查到 %s → %s, price=%s", barcode, full_name, price)
        return {'name': full_name, 'price': price}
    except requests.Timeout:
        logger.warning("GoogleBooks 查询 %s 超时", barcode)
    except Exception as e:
        logger.warning("GoogleBooks 查询 %s 异常: %s", barcode, e)
    return None


def _fetch_barcodelist(barcode):
    """barcode-list.com 免费 API — 通用条码查询（无密钥，有频率限制）"""
    try:
        resp = requests.get(
            f'https://barcode-list.com/api/v2/barcode/{barcode}',
            timeout=8,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get('status') != 'ok' or not data.get('product'):
            return None
        p = data['product']
        name = (p.get('name') or '').strip()
        brand = (p.get('brand') or '').strip()
        result = f'{brand} {name}' if name and brand else (brand or name or None)
        if result:
            logger.info("BarcodeList.com 查到 %s → %s", barcode, result)
        return result
    except Exception as e:
        logger.warning("BarcodeList.com 查询 %s 异常: %s", barcode, e)
    return None


def _fetch_openfoodfacts(barcode):
    """Open Food Facts API — 通用条码查询（免费、覆盖广）"""
    try:
        resp = requests.get(
            f'https://world.openfoodfacts.org/api/v2/product/{barcode}.json',
            timeout=8,
            headers={'User-Agent': 'YideBookstore/1.0'}
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get('status') != 1:
            return None
        p = data.get('product', {})
        name = (p.get('product_name') or p.get('generic_name') or '').strip()
        brand = (p.get('brands') or '').strip()
        result = f'{brand} {name}' if name and brand else (brand or name or None)
        if result:
            logger.info("OpenFoodFacts 查到 %s → %s", barcode, result)
        return result
    except Exception as e:
        logger.warning("OpenFoodFacts 查询 %s 异常: %s", barcode, e)
    return None


def _fetch_upcitemdb(barcode):
    """upcitemdb.com — 免费 trial API（覆盖全球，有限额）"""
    try:
        resp = requests.get(
            f'https://api.upcitemdb.com/prod/trial/lookup?upc={barcode}',
            timeout=8,
            headers={'User-Agent': 'YideBookstore/1.0'}
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        items = data.get('items', [])
        if items:
            title = (items[0].get('title') or '').strip()
            if title:
                logger.info("UPCItemDB 查到 %s → %s", barcode, title)
                return title
    except Exception as e:
        logger.warning("UPCItemDB 查询 %s 异常: %s", barcode, e)
    return None


def _fetch_bing_search(barcode):
    """Bing 搜索 — 作为最后手段，从搜索结果中解析商品名"""
    try:
        resp = requests.get(
            f'https://www.bing.com/search?q={barcode}',
            timeout=8,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
        )
        if resp.status_code != 200:
            return None
        html = resp.text
        # Bing 搜索结果通常在 <h2><a href="...">标题</a></h2> 中
        import re
        # 找第一个非广告、非购物结果的标题
        matches = re.findall(r'<h2>.*?<a[^>]*>(.*?)</a>.*?</h2>', html, re.DOTALL)
        for m in matches:
            # 清理 HTML 标签
            name = re.sub(r'<[^>]+>', '', m).strip()
            # 至少5个字符才可能是商品名
            if len(name) >= 5 and '条码' not in name:
                logger.info("Bing搜索 查到 %s → %s", barcode, name[:60])
                return name[:60]
    except Exception as e:
        logger.warning("Bing搜索 查询 %s 异常: %s", barcode, e)
    return None


def _fetch_duckduckgo_search(barcode):
    """DuckDuckGo 搜索 — 不封禁、覆盖中文搜索结果"""
    try:
        resp = requests.get(
            f'https://html.duckduckgo.com/html/?q={barcode}',
            timeout=8,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
        )
        if resp.status_code != 200:
            return None
        html = resp.text
        # DuckDuckGo results in <a class="result__a" href="...">标题</a>
        matches = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
        for m in matches:
            name = re.sub(r'<[^>]+>', '', m).strip()
            # 过滤太短或明显不是商品名的结果
            if len(name) >= 5 and '条码' not in name and 'barcode' not in name.lower():
                logger.info("DuckDuckGo搜索 查到 %s → %s", barcode, name[:60])
                return name[:60]
    except Exception as e:
        logger.warning("DuckDuckGo搜索 查询 %s 异常: %s", barcode, e)
    return None


def get_product_by_barcode(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    barcode = request.GET.get('barcode')
    if not barcode:
        return JsonResponse({'status': 'fail', 'msg': '条码不能为空'})

    barcode = barcode.strip()
    product = Product.objects.filter(barcode=barcode).first()
    if product:
        return JsonResponse({
            'status': 'success',
            'name': product.name,
            'price': str(product.price),  # Decimal 需要转字符串
            'stock': product.stock,
            'category': product.category,  # 返回分类，让前端能回显
            'from_db': True,
        })

    # 本地没有 → 查外部 API
    ext = _lookup_barcode_external(barcode)
    if ext and ext.get('name'):
        ext['status'] = 'success'
        ext['from_db'] = False
        ext['price_estimate'] = ext.get('price_estimate')
        return JsonResponse(ext, json_dumps_params={'ensure_ascii': False})

    return JsonResponse({'status': 'fail', 'msg': '未找到商品'})


# 小程序获取当前清单的接口
def get_cart_status(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    items = CartItem.objects.select_related('product').all().order_by('-added_at')
    data = []
    total = Decimal('0.00')
    for i in items:
        data.append({
            'id': i.product_id,
            'name': i.product.name,
            'price': str(i.product.price),
            'quantity': i.quantity,
            'remaining_stock': i.product.stock,
            'category': i.product.category,
            'added_at': timezone.localtime(i.added_at).strftime('%H:%M:%S') if i.added_at else '',
        })
        total += i.product.price * i.quantity
    return JsonResponse({'items': data, 'total': str(total)})


# 扫码枪调用的接口：负责向购物车添加商品
def add_item(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    barcode = request.GET.get('barcode')
    if not barcode:
        return JsonResponse({'status': 'fail', 'msg': '条码不能为空'})

    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(barcode=barcode)
            item, created = CartItem.objects.select_for_update().get_or_create(product=product)
            target_quantity = 1 if created else item.quantity + 1

            if product.stock < target_quantity:
                if created:
                    item.delete()
                return JsonResponse({'status': 'fail', 'msg': '库存不足'})

            if not created:
                item.quantity = target_quantity
                item.save(update_fields=['quantity'])

        return JsonResponse({
            'status': 'success',
            'name': product.name,
            'price': str(product.price),
            'current_qty': target_quantity,
            'remaining_stock': product.stock
        })
    except Product.DoesNotExist:
        return JsonResponse({'status': 'fail', 'msg': '未找到商品'})


# 按钮 A：单纯清空（网页端用，用于扫错重来）
def reset_cart(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    CartItem.objects.all().delete()
    return JsonResponse({'status': 'success', 'msg': '账单已重置'})


# 删除购物车中的单个商品（按条码或商品ID）
def remove_cart_item(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    barcode = request.GET.get('barcode')
    product_id = request.GET.get('product_id')
    if barcode:
        deleted, _ = CartItem.objects.filter(product__barcode=barcode).delete()
    elif product_id:
        deleted, _ = CartItem.objects.filter(product_id=product_id).delete()
    else:
        return JsonResponse({'status': 'fail', 'msg': '请提供 barcode 或 product_id'})
    return JsonResponse({'status': 'success', 'msg': '已移除', 'deleted': deleted})


# 修改购物车中某个商品的数量（按条码或商品ID）
def update_cart_item(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    barcode = request.GET.get('barcode')
    product_id = request.GET.get('product_id')
    qty = request.GET.get('quantity')
    try:
        quantity = int(qty)
    except (TypeError, ValueError):
        return JsonResponse({'status': 'fail', 'msg': 'quantity 必须是整数'})

    if quantity <= 0:
        # 数量 <= 0 视为删除
        if barcode:
            CartItem.objects.filter(product__barcode=barcode).delete()
        elif product_id:
            CartItem.objects.filter(product_id=product_id).delete()
        else:
            return JsonResponse({'status': 'fail', 'msg': '请提供 barcode 或 product_id'})
        return JsonResponse({'status': 'success', 'msg': '已移除'})

    try:
        with transaction.atomic():
            if barcode:
                product = Product.objects.select_for_update().get(barcode=barcode)
            else:
                product = Product.objects.select_for_update().get(pk=product_id)

            if product.stock < quantity:
                return JsonResponse({'status': 'fail', 'msg': f'{product.name} 库存不足，仅剩 {product.stock}'})

            item, created = CartItem.objects.select_for_update().get_or_create(product=product)
            item.quantity = quantity
            item.save(update_fields=['quantity'])

        return JsonResponse({
            'status': 'success',
            'name': product.name,
            'price': str(product.price),
            'quantity': quantity,
            'remaining_stock': product.stock
        })
    except Product.DoesNotExist:
        return JsonResponse({'status': 'fail', 'msg': '未找到商品'})


# 按钮 B：正式结账（小程序端用，扣库存+记账）
def checkout_cart(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    cart_items = CartItem.objects.select_related('product').all()
    if not cart_items.exists():
        return JsonResponse({'status': 'fail', 'msg': '账单为空'})

    try:
        with transaction.atomic():
            locked_cart_items = []
            for item in cart_items.select_for_update():
                product = Product.objects.select_for_update().get(pk=item.product_id)
                if product.stock < item.quantity:
                    return JsonResponse({
                        'status': 'fail',
                        'msg': f'{product.name} 库存不足，当前库存 {product.stock}，需要 {item.quantity}'
                    })
                locked_cart_items.append((item, product))

            for item, product in locked_cart_items:
                SaleHistory.objects.create(
                    product_name=product.name,
                    price=product.price,
                    quantity=item.quantity
                )

                product.stock -= item.quantity
                product.save(update_fields=['stock'])

            cart_items.delete()

        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'fail', 'msg': str(e)})


# 今日营业额
def get_today_stats(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    stats = _today_sales_stats()
    return JsonResponse({
        'status': 'success',
        'total_amount': round(stats['total_amount'], 2),
        'today_count': stats['today_count'],
    })


# ─── AI 视觉识别商品 ─────────────────────────────────────
@csrf_exempt
def ai_recognize_product(request):
    """
    接收小程序上传的图片，调用视觉 AI 识别商品信息。
    返回建议的 name / category / barcode / price_estimate。
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'fail', 'msg': '仅支持 POST'})

    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error

    api_key = getattr(settings, 'AI_VISION_API_KEY', '')
    base_url = getattr(settings, 'AI_VISION_BASE_URL', 'https://api.openai.com/v1')
    model = getattr(settings, 'AI_VISION_MODEL', 'gpt-4o')

    if not api_key:
        logger.warning("AI_VISION_API_KEY 未配置，跳过视觉识别")
        return JsonResponse({
            'status': 'fail',
            'msg': 'AI 视觉识别未配置，请在环境变量中设置 AI_VISION_API_KEY'
        })

    # 获取上传的图片文件
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'status': 'fail', 'msg': '请上传商品图片'})

    # 限制文件大小（最大 5MB，考虑 EdgeOne SCF 限制）
    max_size = 5 * 1024 * 1024
    if image_file.size > max_size:
        logger.warning("图片太大: %d bytes (max %d)", image_file.size, max_size)
        return JsonResponse({'status': 'fail', 'msg': '图片太大，请压缩后上传（最大 5MB）'})

    try:
        # 读取图片并转 base64
        image_data = image_file.read()
        image_b64 = base64.b64encode(image_data).decode('utf-8')
        content_type = image_file.content_type or 'image/jpeg'

        # 构造视觉 AI 请求
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        # 分类映射：让 AI 输出英文分类 key
        category_options = ['books', 'pens', 'papers', 'stationery', 'correction', 'others']
        category_desc = '名著书籍, 书写工具, 本册纸品, 学生文具, 修正粘合, 其他用品'

        payload = {
            'model': model,
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        '你是一个文具书店的商品识别助手。根据用户提供的商品图片，'
                        '识别出商品信息并以 JSON 格式返回。'
                        '注意：如果你在图片中看到条形码或二维码，请读出其中的数字/字母作为 barcode。'
                    )
                },
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': (
                                '请仔细查看这张商品图片，返回以下 JSON 字段（只输出 JSON，不要多余文字）：\n'
                                '{\n'
                                f'  "name": "商品名称（中文，简洁准确）",\n'
                                f'  "category": "分类英文key，从 {category_options} 中选择，含义：{category_desc}",\n'
                                f'  "barcode": "如果图片中有条码或二维码，填写识别出的内容，否则留空字符串",\n'
                                f'  "price_estimate": 预估售价（整数元，如不确定填 null）\n'
                                f'}}\n'
                                '注意：category 必须从上述列表中选一个，不确定填 "others"。'
                            )
                        },
                        {
                            'type': 'image_url',
                            'image_url': {
                                'url': f'data:{content_type};base64,{image_b64}'
                            }
                        }
                    ]
                }
            ],
            'max_tokens': 500,
            'temperature': 0.1,
        }

        # 去掉 base_url 尾部斜杠
        api_base = base_url.rstrip('/')
        response = requests.post(
            f'{api_base}/chat/completions',
            headers=headers,
            json=payload,
            timeout=60  # AI 视觉 API 可能较慢，给足 60 秒
        )

        if response.status_code != 200:
            logger.error("AI 视觉 API 返回异常: %s %s", response.status_code, response.text[:500])
            return JsonResponse({
                'status': 'fail',
                'msg': f'AI 识别服务暂时不可用（{response.status_code}）'
            })

        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')

        # 尝试从返回内容中提取 JSON
        json_match = re.search(r'[{].*[}]', content, re.DOTALL)
        if not json_match:
            logger.error("AI 返回无法解析: %s", content[:300])
            return JsonResponse({
                'status': 'fail',
                'msg': 'AI 未能识别该商品，请换个角度或手动录入'
            })

        try:
            recognized = json.loads(json_match.group())
        except json.JSONDecodeError:
            logger.error("JSON 解析失败: %s", content[:300])
            return JsonResponse({
                'status': 'fail',
                'msg': '识别结果解析失败，请手动录入'
            })

        name = (recognized.get('name') or '').strip()
        category = (recognized.get('category') or 'others').strip().lower()
        barcode = (recognized.get('barcode') or '').strip()
        price_estimate = recognized.get('price_estimate')

        # 校验分类
        if category not in category_options:
            category = 'others'

        # 如果已有同名商品，尝试补全信息
        existing = None
        if name:
            existing = Product.objects.filter(name__icontains=name).first()
        if not existing and barcode:
            existing = Product.objects.filter(barcode=barcode).first()

        result_data = {
            'status': 'success',
            'name': name,
            'category': category,
            'barcode': barcode,
            'price_estimate': price_estimate,
        }

        if existing:
            result_data['exists'] = True
            result_data['current_stock'] = existing.stock
            result_data['existing_price'] = str(existing.price)
            # AI 识别名称用作参考，但优先用数据库中的
            if not name:
                result_data['name'] = existing.name
            result_data['existing_name'] = existing.name

        logger.info("AI 识别结果: name=%s category=%s barcode=%s", name, category, barcode)
        return JsonResponse(result_data, json_dumps_params={'ensure_ascii': False})

    except requests.Timeout:
        logger.error("AI 视觉 API 超时")
        return JsonResponse({'status': 'fail', 'msg': 'AI 识别超时，请重试'})
    except Exception as e:
        logger.error("AI 视觉识别异常: %s", e, exc_info=True)
        return JsonResponse({'status': 'fail', 'msg': '识别出错，请手动录入'})


# 小程序扫码入库（适合日常补货/新书上架）
def quick_add_product(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    barcode = request.GET.get('barcode')
    name = request.GET.get('name')
    price = request.GET.get('price')
    category = request.GET.get('category', 'others')
    image_url = request.GET.get('image_url', '').strip()

    try:
        stock = int(request.GET.get('stock', 0))
        price_value = Decimal(str(price)).quantize(Decimal('0.01'))
    except (TypeError, ValueError, InvalidOperation):
        return JsonResponse({'status': 'fail', 'msg': '价格或库存格式不正确'})

    if not barcode or not name:
        return JsonResponse({'status': 'fail', 'msg': '条码和名称不能为空'})
    if stock <= 0:
        return JsonResponse({'status': 'fail', 'msg': '入库数量必须大于0'})
    if price_value < 0:
        return JsonResponse({'status': 'fail', 'msg': '价格不能为负数'})

    # 校验分类有效性
    valid_categories = ['books', 'pens', 'papers', 'stationery', 'correction', 'others']
    if category not in valid_categories:
        category = 'others'

    with transaction.atomic():
        product, created = Product.objects.select_for_update().get_or_create(
            barcode=barcode,
            defaults={
                'name': name,
                'price': price_value,
                'stock': 0,
                'category': category,
                'image_url': image_url,
            }
        )

        if not created:
            product.name = name
            product.price = price_value
            product.category = category

        # 更新图片链接（新旧商品都允许更新）
        if image_url:
            product.image_url = image_url

        # 增加库存
        product.stock += stock
        product.save(update_fields=['name', 'price', 'stock', 'category', 'image_url'])

    return JsonResponse({
        'status': 'success',
        'is_new': created,
        'current_stock': product.stock
    })


def get_mall_products(request):
    limit = min(max(get_request_int(request.GET.get('limit'), 50), 1), 200)
    cat = request.GET.get('category', 'all')
    search = (request.GET.get('search', '') or '').strip()[:100]

    VALID_CATEGORIES = dict(Product.CATEGORY_CHOICES)

    # 非法分类直接返回空列表，避免误查全量
    if cat != 'all' and cat not in VALID_CATEGORIES:
        return JsonResponse({
            'status': 'success',
            'list': [],
            'total_count': 0,
            'limit': limit,
            'category_counts': {},
        }, json_dumps_params={'ensure_ascii': False})

    # 基础查询：必须有库存
    query = Product.objects.filter(stock__gt=0)

    # 如果不是”全部”，则增加分类过滤条件
    if cat != 'all':
        query = query.filter(category=cat)

    # 名称搜索
    if search:
        query = query.filter(name__icontains=search)

    total_count = query.count()

    # 分类商品数量（仅全部 + 无搜索时返回，前端做角标用）
    category_counts = {}
    if cat == 'all' and not search:
        for c_key, _ in Product.CATEGORY_CHOICES:
            cnt = Product.objects.filter(category=c_key, stock__gt=0).count()
            if cnt > 0:
                category_counts[c_key] = cnt

    products = query.values('id', 'name', 'price', 'category', 'stock', 'create_time', 'image_url')
    # 按录入时间倒序（新品在前）
    products = products.order_by('-create_time')[:limit]

    return JsonResponse({
        'status': 'success',
        'list': list(products),
        'total_count': total_count,
        'limit': limit,
        'category_counts': category_counts,
    }, json_dumps_params={'ensure_ascii': False})


# 根据商品名称关键词自动分类（供管理员一键整理用）
# 关键词规则集中在 catalog.py，供 views/admin 共用。

@csrf_exempt
def auto_categorize_products(request):
    """一键自动分类：根据商品名称关键词分配分类（仅店长可用）"""
    if request.method != 'POST':
        return JsonResponse({'status': 'fail', 'msg': '请使用POST请求'}, status=405)
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error

    count = auto_categorize_queryset(Product.objects.all())
    return JsonResponse({'status': 'success', 'updated': count})


# 推荐样品商品数据（供店主一键部署到云端）
# 按6大分类体系组织：名著书籍/书写工具/本册纸品/学生文具/修正粘合/其他用品
SEED_PRODUCTS = [
    # ========== 📚 名著书籍 ==========
    ('9787012345671', '新华字典', 25.00, 20, 'books'),
    ('9787012345672', '小学生作文精选', 18.00, 15, 'books'),
    ('9787012345673', '英语四六级词汇', 35.00, 10, 'books'),
    ('9787012345674', '描红字帖', 8.00, 30, 'books'),
    ('9787012345675', '古诗词名篇', 22.00, 12, 'books'),
    ('9787012345676', '成语故事大全', 28.00, 10, 'books'),
    ('9787012345677', '儿童绘本（动物世界）', 15.00, 15, 'books'),

    # ========== 🖊️ 书写工具 ==========
    ('6923456700011', '晨光中性笔 0.5mm 黑', 3.00, 100, 'pens'),
    ('6923456700012', '晨光中性笔 0.5mm 红', 3.00, 50, 'pens'),
    ('6923456700013', '2B铅笔（含橡皮头）', 2.00, 80, 'pens'),
    ('6923456700014', '荧光笔（黄色）', 4.50, 30, 'pens'),
    ('6923456700015', '马克笔12色套装', 18.00, 15, 'pens'),
    ('6923456700016', '英雄钢笔', 25.00, 10, 'pens'),
    ('6923456700017', '中性笔芯 0.5mm 黑（20支装）', 10.00, 40, 'pens'),
    ('6923456700018', '圆珠笔 蓝', 2.00, 50, 'pens'),
    ('6923456700019', '自动铅笔 0.5mm', 5.00, 30, 'pens'),

    # ========== 📓 本册纸品 ==========
    ('6923456700041', 'A5笔记本 横线', 6.00, 50, 'papers'),
    ('6923456700042', 'A4文件袋（透明）', 3.00, 40, 'papers'),
    ('6923456700101', '英语练习本', 2.00, 60, 'papers'),
    ('6923456700102', '方格算术本', 2.00, 60, 'papers'),
    ('6923456700103', '便利贴（彩色）', 3.50, 30, 'papers'),
    ('6923456700109', 'A4复印纸（500张）', 25.00, 10, 'papers'),
    ('6923456700110', '草稿本', 3.00, 30, 'papers'),

    # ========== 📐 学生文具 ==========
    ('6923456700021', '4B绘图橡皮', 2.50, 40, 'stationery'),
    ('6923456700022', '美术橡皮擦（可塑）', 3.50, 25, 'stationery'),
    ('6923456700023', '磨砂橡皮擦', 3.00, 30, 'stationery'),
    ('6923456700045', '尺子 15cm', 2.00, 30, 'stationery'),
    ('6923456700043', '学生剪刀', 5.00, 20, 'stationery'),
    ('6923456700104', '圆规套装', 8.00, 15, 'stationery'),
    ('6923456700105', '卷笔刀', 3.00, 25, 'stationery'),
    ('6923456700106', '订书机（小号）', 8.00, 10, 'stationery'),
    ('6923456700107', '订书钉（小盒）', 2.00, 20, 'stationery'),
    ('6923456700111', '长尾夹（彩色混合）', 4.00, 15, 'stationery'),
    ('6923456700112', '回形针（100枚）', 2.00, 20, 'stationery'),

    # ========== 📦 修正粘合 ==========
    ('6923456700031', '修正带 标准款', 3.50, 40, 'correction'),
    ('6923456700032', '修正带 迷你款', 2.00, 50, 'correction'),
    ('6923456700033', '修正液', 3.00, 20, 'correction'),
    ('6923456700034', '透明胶带', 2.00, 30, 'correction'),
    ('6923456700044', '固体胶棒', 2.50, 35, 'correction'),
    ('6923456700108', '双面胶', 2.00, 25, 'correction'),

    # ========== 📎 其他 ==========
    ('6923456700113', '计算器（8位）', 15.00, 5, 'others'),
    ('6923456700114', '桌面台历', 8.00, 10, 'others'),
]


@csrf_exempt
def seed_sample_products(request):
    """一键部署示例商品数据到云端数据库（仅店长可用）"""
    if request.method != 'POST':
        return JsonResponse({'status': 'fail', 'msg': '请使用POST请求'}, status=405)
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    from .models import Product
    from decimal import Decimal

    added = 0
    updated = 0
    for barcode, name, price, stock, category in SEED_PRODUCTS:
        product, created = Product.objects.get_or_create(
            barcode=barcode,
            defaults={
                'name': name,
                'price': Decimal(str(price)),
                'stock': stock,
                'category': category,
            }
        )
        if created:
            added += 1
        else:
            # 条码已存在 → 全覆盖更新（名称/价格/库存/分类全部刷新）
            product.name = name
            product.price = Decimal(str(price))
            product.stock = stock
            product.category = category
            product.save(update_fields=['name', 'price', 'stock', 'category'])
            updated += 1

    return JsonResponse({
        'status': 'success',
        'added': added,
        'updated': updated,
        'total': len(SEED_PRODUCTS),
        'msg': f'新增 {added} 个商品，补充 {updated} 个商品库存',
    })


@csrf_exempt
def submit_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'fail', 'msg': '请使用POST请求'})
    try:
        data = json.loads(request.body or '{}')
        name = (data.get('name') or '').strip()
        cart = data.get('cart')

        if not name:
            return JsonResponse({'status': 'fail', 'msg': '请输入取货人姓名'})
        if len(name) > 50:
            return JsonResponse({'status': 'fail', 'msg': '取货人姓名过长'})
        if not isinstance(cart, list):
            return JsonResponse({'status': 'fail', 'msg': '购物车数据格式不正确'})
        if not cart:
            return JsonResponse({'status': 'fail', 'msg': '购物车不能为空'})
        if len(cart) > 50:
            return JsonResponse({'status': 'fail', 'msg': '单次最多下单50种商品'})

        with transaction.atomic():
            requested_items = {}
            for item in cart:
                product_id = int(item.get('id'))
                count = int(item.get('num', 0))
                if count <= 0:
                    return JsonResponse({'status': 'fail', 'msg': '商品数量必须大于0'})
                if count > 99:
                    return JsonResponse({'status': 'fail', 'msg': '单个商品最多购买99件'})
                requested_items[product_id] = requested_items.get(product_id, 0) + count

            # 合并重复商品后再次检查上限
            for pid, cnt in requested_items.items():
                if cnt > 99:
                    return JsonResponse({'status': 'fail', 'msg': '单个商品最多购买99件'})

            order_items = []
            total = Decimal('0.00')
            products = Product.objects.select_for_update().filter(id__in=requested_items.keys())
            product_map = {product.id: product for product in products}
            if len(product_map) != len(requested_items):
                return JsonResponse({'status': 'fail', 'msg': '订单商品数据不正确'})

            for product_id, count in requested_items.items():
                product = product_map[product_id]
                if product.stock < count:
                    return JsonResponse({
                        'status': 'fail',
                        'msg': f'{product.name} 库存不足，当前库存 {product.stock}，需要 {count}'
                    })

                order_items.append((product, count))
                total += product.price * count

            # 1. 只创建订单，不扣库存
            new_order = Order.objects.create(
                customer_name=name,
                total_price=total,
                status=0  # 0: 待取货
            )
            # 2. 记录明细
            for product, count in order_items:
                OrderItem.objects.create(
                    order=new_order,
                    product=product,
                    count=count
                )
        return JsonResponse({
            'status': 'success',
            'msg': '下单成功',
            'order_sn': new_order.order_sn,
            'total': str(total)
        })
    except (Product.DoesNotExist, TypeError, ValueError, KeyError):
        return JsonResponse({'status': 'fail', 'msg': '订单商品数据不正确'})
    except Exception as e:
        return JsonResponse({'status': 'fail', 'msg': str(e)})


def get_new_order_count(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    # 查询状态为 0 (待取货) 的订单数量
    count = Order.objects.filter(status=0).count()
    low_stock_count = low_stock_queryset().count()
    return JsonResponse({'count': count, 'low_stock_count': low_stock_count})


def get_pending_orders(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    limit = min(max(get_request_int(request.GET.get('limit'), 10), 1), 50)
    orders = Order.objects.filter(status=0).prefetch_related('items__product').order_by('create_time')[:limit]
    return JsonResponse({
        'status': 'success',
        'list': [serialize_order(order) for order in orders]
    }, json_dumps_params={'ensure_ascii': False})


def get_low_stock_products(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    threshold = min(max(get_request_int(request.GET.get('threshold'), LOW_STOCK_THRESHOLD), 0), 9999)
    limit = min(max(get_request_int(request.GET.get('limit'), 10), 1), 100)
    base_query = Product.objects.filter(stock__lte=threshold)
    total_count = base_query.count()
    products = list(
        base_query.order_by('stock', 'name')[:limit]
        .values('id', 'barcode', 'name', 'stock', 'price', 'category')
    )
    return JsonResponse({
        'status': 'success',
        'threshold': threshold,
        'total_count': total_count,
        'list': products
    }, json_dumps_params={'ensure_ascii': False})


# 1. 搜索订单接口
def search_order(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    key = request.GET.get('key', '').strip()
    if not key:
        return JsonResponse({'status': 'fail', 'msg': '请输入搜索关键词'})

    # 模糊搜索：姓名包含关键字 OR 编号包含关键字
    # 且状态必须是 0 (待取货)
    order = Order.objects.filter(
        Q(customer_name__icontains=key) | Q(order_sn__icontains=key),
        status=0
    ).first()

    if order:
        return JsonResponse({
            'status': 'success',
            'order': serialize_order(order)
        }, json_dumps_params={'ensure_ascii': False})  # 关键：禁止转义中文

    return JsonResponse({'status': 'fail', 'msg': '未找到匹配订单'})


def query_my_orders(request):
    """顾客查询自己的订单（输入姓名，查所有待取货订单）"""
    name = request.GET.get('name', '').strip()
    if not name:
        return JsonResponse({'status': 'fail', 'msg': '请输入姓名'})
    orders = Order.objects.filter(
        customer_name__icontains=name,
        status=0
    ).prefetch_related('items__product').order_by('-create_time')[:10]
    return JsonResponse({
        'status': 'success',
        'list': [serialize_order(order) for order in orders]
    }, json_dumps_params={'ensure_ascii': False})


# 2. 确认取货核销接口
@csrf_exempt
def verify_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'fail', 'msg': '请使用POST请求'})

    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error

    data, err = safe_json_body(request)
    if err:
        return err

    order_id = data.get('id')
    try:
        order = Order.objects.get(id=order_id, status=0)
        complete_order(order)
        return JsonResponse({'status': 'success'})
    except Order.DoesNotExist:
        return JsonResponse({'status': 'fail', 'msg': '未找到待取货订单'})
    except ValidationError as e:
        return JsonResponse({'status': 'fail', 'msg': '; '.join(e.messages)})
    except Exception as e:
        return JsonResponse({'status': 'fail', 'msg': str(e)})


# 仪表盘统计数据（供网页端下方图表使用）
def dashboard_stats(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    now = now_local()
    today = now.date()

    # 本日营收
    today_stats = _today_sales_stats()

    # 最近7天销售趋势
    daily_revenue = _daily_revenue(7)

    # 分类销售占比（过去30天）
    month_ago = today - timedelta(days=30)
    cat_sales = (SaleHistory.objects
        .filter(sale_date__date__gte=month_ago)
        .values('product_name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:5])
    top_products = [{'name': s['product_name'], 'qty': s['total_qty']} for s in cat_sales]

    # 分类商品数量
    cat_counts = {}
    for cat, _ in Product.CATEGORY_CHOICES:
        count = Product.objects.filter(category=cat, stock__gt=0).count()
        if count > 0:
            cat_names = dict(Product.CATEGORY_CHOICES)
            cat_counts[cat_names.get(cat, cat)] = count

    # 低库存商品
    low_stock = list(
        low_stock_queryset()
        .order_by('stock')[:10]
        .values('name', 'stock', 'price')
    )

    # 待处理订单
    pending_orders = Order.objects.filter(status=0).count()

    return JsonResponse({
        'today_revenue': round(today_stats['total_amount'], 2),
        'today_count': today_stats['today_count'],
        'daily_revenue': daily_revenue,
        'top_products': top_products,
        'category_distribution': cat_counts,
        'low_stock': low_stock,
        'pending_orders': pending_orders,
    })


# 今日销售明细（点卡片弹窗用）
def today_detail(request):
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    now = now_local()
    today = now.date()

    # 按商品分组
    grouped = (SaleHistory.objects
        .filter(sale_date__date=today)
        .values('product_name')
        .annotate(
            total_qty=Sum('quantity'),
            total_amount=Sum(_line_total_expr()),
            last_time=Max('sale_date')
        )
        .order_by('-total_amount'))

    # 原始明细
    raw = (SaleHistory.objects
        .filter(sale_date__date=today)
        .order_by('-sale_date')
        .values('product_name', 'quantity', 'price', 'sale_date')[:100])

    return JsonResponse({
        'grouped': [{
            'name': g['product_name'],
            'qty': g['total_qty'],
            'amount': float(g['total_amount']),
            'last_time': g['last_time'].strftime('%H:%M') if g['last_time'] else ''
        } for g in grouped],
        'raw': [{
            'name': r['product_name'],
            'qty': r['quantity'],
            'amount': float(r['price'] * r['quantity']),
            'time': r['sale_date'].strftime('%H:%M')
        } for r in raw],
        'total_count': sum((g['total_qty'] or 0) for g in grouped),
        'total_revenue': float(sum((g['total_amount'] or 0) for g in grouped)),
    })


# 综合看板数据接口（小程序用，合并 5 个请求为 1 个，大幅减少延迟）
def dashboard_all(request):
    """一键获取所有看板数据：购物车、今日营收、待取货、低库存"""
    auth_error = require_shopkeeper_api(request)
    if auth_error:
        return auth_error
    now = now_local()
    today = now.date()

    # 1. 购物车状态
    cart_items = CartItem.objects.select_related('product').all()
    cart_data = []
    cart_total = Decimal('0.00')
    for i in cart_items:
        cart_data.append({
            'id': i.product_id,
            'name': i.product.name,
            'price': str(i.product.price),
            'quantity': i.quantity,
            'remaining_stock': i.product.stock,
            'category': i.product.category,
            'added_at': timezone.localtime(i.added_at).strftime('%H:%M:%S') if i.added_at else '',
        })
        cart_total += i.product.price * i.quantity

    # 2. 今日营收
    today_stats = _today_sales_stats()

    # 3. 待取货订单数 & 低库存数
    pending_count = Order.objects.filter(status=0).count()
    low_stock_count = low_stock_queryset().count()

    # 4. 待取货订单列表（前5条）
    orders = Order.objects.filter(status=0).prefetch_related('items__product').order_by('create_time')[:5]

    # 5. 低库存商品列表（前5条）
    low_stock = list(
        low_stock_queryset()
        .order_by('stock', 'name')[:5]
        .values('id', 'barcode', 'name', 'stock', 'price', 'category')
    )

    return JsonResponse({
        'status': 'success',
        'cart': {
            'items': cart_data,
            'total': str(cart_total),
        },
        'today_stats': {
            'total_amount': round(today_stats['total_amount'], 2),
            'today_count': today_stats['today_count'],
        },
        'new_order': {
            'count': pending_count,
            'low_stock_count': low_stock_count,
        },
        'pending_orders': {
            'list': [serialize_order(o) for o in orders],
        },
        'low_stock': {
            'total_count': low_stock_count,
            'list': low_stock,
        },
    })


# 健康检查接口（用于部署后快速诊断，兼容 PostgreSQL / SQLite）
def health_check(request):
    diagnostics = {
        'status': 'ok',
        'debug': settings.DEBUG,
        'database': 'unknown',
        'tables': {},
        'allowed_hosts': settings.ALLOWED_HOSTS,
        # 只暴露「是否配置」和长度，绝不回显环境变量的值
        'env': {
            name: {
                'configured': bool(os.environ.get(name)),
                'length': len(os.environ.get(name) or ''),
            }
            for name in (
                'SHOPKEEPER_API_TOKEN',
                'SHOPKEEPER_PASSWORD',
                'CLOUD_DATABASE_URL',
                'DJANGO_SECRET_KEY',
                'AI_VISION_API_KEY',
            )
        },
    }

    try:
        from django.db import connection
        from django.apps import apps

        # 使用 Django introspection 而非原生的 information_schema（PostgreSQL 专属）
        table_names = connection.introspection.table_names()
        diagnostics['tables']['all'] = table_names

        # 列出关键表是否存在
        KEY_TABLES = ['web_product', 'web_order', 'web_orderitem', 'web_salehistory', 'web_cartitem', 'auth_user']
        for t in KEY_TABLES:
            diagnostics['tables'][t] = t in table_names

        # 用户数 & 商品数（表存在时再查询）
        if 'auth_user' in table_names:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            diagnostics['tables']['user_count'] = User.objects.count()

        if 'web_product' in table_names:
            from .models import Product
            diagnostics['tables']['product_count'] = Product.objects.count()

        diagnostics['database'] = 'connected'
    except Exception as e:
        diagnostics['database'] = f'degraded: {e}'
        diagnostics['status'] = 'degraded'

    return JsonResponse(diagnostics)


def wechat_verify(request):
    """微信域名所有权验证（MP 验证文件）"""
    return HttpResponse('c7075ba1e65258ad0c0c1ecb9f9bc774021f57bc', content_type='text/plain; charset=utf-8')


def serve_qr_code(request):
    """优先读取随包 PNG 文件，失败时回退到内置 base64"""
    import base64, os
    from django.http import HttpResponse
    from django.conf import settings
    png_path = os.path.join(settings.BASE_DIR, 'web', 'static', 'web', 'qr_yide_mall.png')
    if os.path.exists(png_path):
        with open(png_path, 'rb') as f:
            data = f.read()
        response = HttpResponse(data, content_type='image/png')
    else:
        from web.qr_code_data import QR_CODE_BASE64
        response = HttpResponse(base64.b64decode(QR_CODE_BASE64), content_type='image/png')
    response['Cache-Control'] = 'public, max-age=86400'
    return response
