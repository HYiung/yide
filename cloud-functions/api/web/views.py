import base64
import json
import logging
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout, get_user_model
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import AdminUser, CartItem, Order, OrderItem, Product, SaleHistory

logger = logging.getLogger(__name__)


def now_local():
    """返回 Asia/Shanghai 时区的当前时间（用于兼容 EdgeOne UTC 环境）"""
    return timezone.localtime(timezone.now())


def get_request_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
        'create_time': order.create_time.strftime('%Y-%m-%d %H:%M'),
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
<title>一得书苑 · 收银台 + 看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f0f2f5; color: #333; min-height: 100vh;
  }
  .header {
    background: linear-gradient(135deg, #07c160 0%, #06ad54 100%);
    padding: 24px 32px; color: #fff; box-shadow: 0 2px 12px rgba(7,193,96,0.3);
  }
  .header h1 { font-size: 24px; font-weight: 700; }
  .header p { font-size: 14px; opacity: 0.85; margin-top: 4px; }
  .stats-row {
    display: flex; gap: 16px; padding: 20px 32px; flex-wrap: wrap;
  }
  .stat-card {
    flex: 1; min-width: 160px; background: #fff; border-radius: 12px;
    padding: 18px 20px; box-shadow: 0 1px 6px rgba(0,0,0,0.06);
    display: flex; align-items: center; gap: 14px; cursor: pointer;
    transition: all 0.2s; position: relative;
  }
  .stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.1); }
  .stat-card:active { transform: scale(0.98); }
  .stat-card .click-hint {
    position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
    font-size: 11px; color: #ccc; opacity: 0; transition: opacity 0.2s;
  }
  .stat-card:hover .click-hint { opacity: 1; }
  .stat-icon {
    width: 44px; height: 44px; border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; flex-shrink: 0;
  }
  .stat-icon.green { background: #e8f8ee; }
  .stat-icon.orange { background: #fff3e6; }
  .stat-icon.red { background: #ffe8e8; }
  .stat-icon.blue { background: #e8f0fe; }
  .stat-body .stat-label { font-size: 12px; color: #999; }
  .stat-body .stat-value {
    font-size: 22px; font-weight: 800; margin-top: 2px;
  }
  .stat-value.green { color: #07c160; }
  .stat-value.orange { color: #fa8c16; }
  .stat-value.red { color: #f5222d; }
  .stat-value.blue { color: #1677ff; }
  .main-content {
    display: grid; grid-template-columns: 1fr 1fr; gap: 20px;
    padding: 0 32px 32px;
  }
  .scan-section { grid-column: 1 / 2; }
  .card {
    background: #fff; border-radius: 12px; padding: 24px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.06); margin-bottom: 20px;
  }
  .card-title {
    font-size: 16px; font-weight: 700; margin-bottom: 16px;
    display: flex; align-items: center; gap: 8px;
  }
  .scan-input-row {
    display: flex; gap: 10px; margin-bottom: 12px;
  }
  .scan-input-row input {
    flex: 1; height: 44px; border: 2px solid #e8e8e8; border-radius: 10px;
    padding: 0 16px; font-size: 18px; outline: none;
    transition: border-color 0.2s; letter-spacing: 2px;
  }
  .scan-input-row input:focus { border-color: #07c160; }
  .scan-input-row .mode-btn {
    height: 44px; padding: 0 18px; border: 2px solid #e8e8e8; border-radius: 10px;
    background: #fff; font-size: 14px; cursor: pointer; display: flex;
    align-items: center; gap: 6px; white-space: nowrap;
    transition: all 0.2s; color: #666; user-select: none;
  }
  .scan-input-row .mode-btn.active {
    border-color: #07c160; background: #e8f8ee; color: #07c160;
  }
  .action-btns { display: flex; gap: 10px; margin-bottom: 16px; }
  .action-btns button {
    flex: 1; height: 40px; border: none; border-radius: 10px;
    font-size: 14px; font-weight: 600; cursor: pointer;
    transition: all 0.2s; display: flex; align-items: center;
    justify-content: center; gap: 6px;
  }
  .btn-checkout {
    background: linear-gradient(135deg, #07c160, #06ad54); color: #fff;
  }
  .btn-checkout:hover { box-shadow: 0 4px 12px rgba(7,193,96,0.4); }
  .btn-reset {
    background: #fff4f4; color: #f5222d; border: 1px solid #ffe0e0 !important;
  }
  .btn-reset:hover { background: #ffe8e8; }
  .product-display {
    background: #f9fafb; border-radius: 10px; padding: 20px;
    text-align: center; margin-bottom: 16px;
    min-height: 100px; display: flex; flex-direction: column;
    justify-content: center;
  }
  .product-display .p-name {
    font-size: 22px; font-weight: 700; color: #333; margin-bottom: 6px;
  }
  .product-display .p-name .tag {
    font-size: 12px; background: #e8f8ee; color: #07c160;
    padding: 2px 8px; border-radius: 4px; margin-left: 8px;
    font-weight: 500; vertical-align: middle;
  }
  .product-display .p-price {
    font-size: 28px; font-weight: 900; color: #f5222d;
  }
  .log-area {
    max-height: 260px; overflow-y: auto; font-size: 13px;
  }
  .log-area::-webkit-scrollbar { width: 4px; }
  .log-area::-webkit-scrollbar-thumb { background: #ddd; border-radius: 2px; }
  .log-entry {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 0; border-bottom: 1px solid #f5f5f5;
  }
  .log-entry:last-child { border-bottom: none; }
  .log-entry .log-time { color: #bbb; font-size: 12px; min-width: 70px; }
  .log-entry .log-name { flex: 1; margin: 0 12px; font-weight: 500; }
  .log-entry .log-price { color: #f5222d; font-weight: 700; min-width: 60px; text-align: right; }
  .dashboard-section { grid-column: 2 / 3; display: flex; flex-direction: column; gap: 20px; }
  .chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  .chart-card {
    background: #fff; border-radius: 12px; padding: 20px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.06);
  }
  .chart-card .chart-title {
    font-size: 14px; font-weight: 700; margin-bottom: 12px; color: #666;
  }
  .chart-card canvas { width: 100% !important; height: 180px !important; }
  .stock-list { list-style: none; }
  .stock-item {
    display: flex; justify-content: space-between; padding: 8px 0;
    border-bottom: 1px solid #f5f5f5; font-size: 13px;
  }
  .stock-item:last-child { border-bottom: none; }
  .stock-item .stock-badge {
    background: #ffe8e8; color: #f5222d; padding: 2px 8px;
    border-radius: 10px; font-size: 12px; font-weight: 600;
  }
  .empty-state {
    color: #ccc; text-align: center; padding: 30px 0; font-size: 14px;
  }
  /* ===== Modal ===== */
  .modal-overlay {
    display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.45); z-index: 9999;
    justify-content: center; align-items: center;
  }
  .modal-overlay.show { display: flex; }
  .modal-box {
    background: #fff; border-radius: 16px; width: 92%; max-width: 560px;
    max-height: 80vh; display: flex; flex-direction: column;
    box-shadow: 0 20px 60px rgba(0,0,0,0.15);
    animation: modalIn 0.2s ease;
  }
  @keyframes modalIn { from { opacity: 0; transform: scale(0.95) translateY(10px); } to { opacity: 1; transform: scale(1) translateY(0); } }
  .modal-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 20px 24px; border-bottom: 1px solid #f0f0f0;
  }
  .modal-title { font-size: 18px; font-weight: 700; color: #333; }
  .modal-close {
    width: 32px; height: 32px; border-radius: 50%; background: #f5f5f5;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; font-size: 16px; color: #999; transition: all 0.2s;
  }
  .modal-close:hover { background: #e8e8e8; color: #333; }
  .modal-body { padding: 20px 24px; overflow-y: auto; min-height: 100px; }
  .modal-loading { text-align: center; color: #ccc; padding: 30px 0; }
  .modal-table { width: 100%; border-collapse: collapse; font-size: 14px; }
  .modal-table th {
    text-align: left; padding: 8px 0; color: #999; font-weight: 600;
    border-bottom: 2px solid #f0f0f0; font-size: 12px;
  }
  .modal-table td { padding: 10px 0; border-bottom: 1px solid #f5f5f5; }
  .modal-table tr:last-child td { border-bottom: none; }
  .modal-table .num { font-weight: 700; }
  .modal-table .money { color: #f5222d; font-weight: 700; }
  .modal-table .time { color: #bbb; font-size: 12px; }
  .modal-empty { text-align: center; color: #ccc; padding: 30px 0; font-size: 14px; }
  .modal-footer {
    display: flex; justify-content: space-between; padding: 14px 0 0;
    border-top: 1px solid #f0f0f0; font-weight: 700; font-size: 15px;
  }
  @media (max-width: 900px) {
    .main-content { grid-template-columns: 1fr; padding: 0 16px 16px; }
    .dashboard-section { grid-column: 1; }
    .chart-grid { grid-template-columns: 1fr; }
    .stats-row { padding: 16px; }
    .header { padding: 16px 20px; }
  }
  .admin-bar {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: #fafafa; border-top: 1px solid #f0f0f0;
    padding: 8px 16px; z-index: 100;
    display: flex; justify-content: center; gap: 20px; font-size: 13px;
  }
  .admin-bar a { color: #666; text-decoration: none; }
  .admin-bar a:hover { color: #07c160; }
  body { padding-bottom: 40px; }
</style>
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

<script>
var isCheckOnly = false;
var scanTotal = 0.0;
var scanCount = 0;
var checkoutTimer = null;
var revenueChart = null, categoryChart = null;

var input = document.getElementById('barcode-input');
var pName = document.getElementById('p-name');
var pPrice = document.getElementById('p-price');
var logArea = document.getElementById('logArea');

/* ==== Speech: prewarm + delay fix for Chrome Chinese first-char loss ==== */
(function () { if ('speechSynthesis' in window) { window.speechSynthesis.cancel(); var _w = new SpeechSynthesisUtterance(' '); window.speechSynthesis.speak(_w); } })();
function speakText(text) {
  window.speechSynthesis.cancel();
  setTimeout(function () { var u = new SpeechSynthesisUtterance(text); u.rate = 1.0; window.speechSynthesis.speak(u); }, 30);
}

function toggleMode() {
  isCheckOnly = !isCheckOnly;
  document.getElementById('modeToggle').textContent = isCheckOnly ? '🔍 查价中' : '🔍 查价';
  document.getElementById('modeToggle').classList.toggle('active', isCheckOnly);
}

function fetchWithTimeout(url, timeoutMs) {
  var ms = timeoutMs || 8000;
  return new Promise(function (resolve, reject) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); reject(new Error('timeout')); }, ms);
    fetch(url, { signal: controller.signal }).then(function (r) {
      clearTimeout(timer); resolve(r);
    }).catch(function (e) {
      clearTimeout(timer); reject(e);
    });
  });
}

function fetchJSON(url) {
  return fetchWithTimeout(url).then(function (r) { return r.json(); });
}

function updateCartSummary() {
  var el = document.getElementById('cartSummary');
  if (scanCount > 0) {
    el.style.display = '';
    document.getElementById('cartCount').textContent = scanCount;
    document.getElementById('cartTotal').textContent = '￥' + scanTotal.toFixed(2);
  } else {
    el.style.display = 'none';
  }
}

function updateStats() {
  fetchJSON('/get_today_stats/').then(function (d) {
    if (d.status !== 'success') return;
    document.getElementById('s-today-revenue').textContent = '￥' + parseFloat(d.total_amount || 0).toFixed(2);
    document.getElementById('s-today-count').textContent = (d.today_count || 0) + ' 件';
  }).catch(function () {});
  fetchJSON('/api/get_new_order_count/').then(function (d) {
    document.getElementById('s-pending').textContent = (d.count || 0) + ' 单';
    document.getElementById('s-lowstock').textContent = (d.low_stock_count || 0) + ' 个';
  }).catch(function () {});
}

function loadDashboard() {
  fetchJSON('/api/dashboard_stats/').catch(function () { return {}; }).then(function (d) {
    if (revenueChart) revenueChart.destroy();
    var ctx1 = document.getElementById('revenueChart').getContext('2d');
    revenueChart = new Chart(ctx1, {
      type: 'line',
      data: {
        labels: (d.daily_revenue || []).map(function (r) { return r.date; }),
        datasets: [{
          label: '营收',
          data: (d.daily_revenue || []).map(function (r) { return r.total; }),
          borderColor: '#07c160',
          backgroundColor: 'rgba(7,193,96,0.08)',
          fill: true, tension: 0.4,
          pointRadius: 4, pointBackgroundColor: '#07c160', borderWidth: 2
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.04)' } }, x: { grid: { display: false } } }
      }
    });
    if (categoryChart) categoryChart.destroy();
    var cats = d.category_distribution || {};
    var catLabels = Object.keys(cats);
    var catValues = catLabels.map(function (k) { return cats[k]; });
    var catColors = ['#07c160','#1677ff','#fa8c16','#f5222d','#722ed1','#13c2c2','#eb2f96'];
    var ctx2 = document.getElementById('categoryChart').getContext('2d');
    categoryChart = new Chart(ctx2, {
      type: 'doughnut',
      data: {
        labels: catLabels.length ? catLabels : ['暂无数据'],
        datasets: [{ data: catValues.length ? catValues : [1], backgroundColor: catColors.slice(0, Math.max(catLabels.length,1)), borderWidth: 0 }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 8, font: { size: 11 } } } },
        cutout: '60%'
      }
    });
    var stockEl = document.getElementById('stockList');
    var lowStock = d.low_stock || [];
    if (!lowStock.length) {
      stockEl.innerHTML = '<div class="empty-state">✅ 库存充足</div>';
    } else {
      stockEl.innerHTML = '<ul class="stock-list">' + lowStock.map(function (p) {
        return '<li class="stock-item"><span>' + p.name + '</span><span class="stock-badge">库存 ' + p.stock + '</span></li>';
      }).join('') + '</ul>';
    }
  }).catch(function () {});
}

function processBarcode(code) {
  if (!code) return;
  if (checkoutTimer) { clearTimeout(checkoutTimer); checkoutTimer = null; }  // 取消结账后的"等待扫码"倒计时
  var url = (isCheckOnly ? '/get_product_by_barcode/?barcode=' : '/add_item/?barcode=') + encodeURIComponent(code);
  fetchWithTimeout(url).then(function (r) { return r.json(); }).then(function (d) {
    if (d.status === 'success') {
      var tag = isCheckOnly ? '<span class="tag">仅查价</span>' : '<span class="tag">已录入</span>';
      pName.innerHTML = d.name + ' ' + tag;
      pPrice.textContent = '￥' + d.price;
      speakText(d.name + '，' + d.price + '元');
      if (!isCheckOnly) {
        initCartSummary();  // 从服务端全量同步，确保件数/总价/记录列表一致
      }
    } else {
      pName.textContent = '❌ ' + (d.msg || '未找到商品'); pPrice.textContent = '-';
      speakText('没找到商品');
    }
    input.value = '';
  }).catch(function () { pName.textContent = '❌ 网络错误'; pPrice.textContent = '-'; input.value = ''; });
}

function resetAll() {
  if (!confirm('确定要清空当前账单吗？')) return;
  fetchJSON('/reset_cart/').then(function (d) {
    if (d.status === 'success') {
      pName.textContent = '等待扫码...'; pPrice.textContent = '-';
      initCartSummary();  // 同步服务端空购物车到页面
    }
  });
}

function doCheckout() {
  speakText('正在处理结账');
  fetchJSON('/checkout_cart/').then(function (d) {
    if (d.status === 'success') {
      speakText('收款成功');
      pName.textContent = '✅ 结账完成'; pPrice.textContent = '-';
      initCartSummary();  // 清零总价和清空记录列表
      updateStats(); loadDashboard();
      if (checkoutTimer) clearTimeout(checkoutTimer);
      checkoutTimer = setTimeout(function () {
        pName.textContent = '等待扫码...';
        checkoutTimer = null;
      }, 3000);
    } else { alert(d.msg); }
  });
}

setInterval(function () { if (document.activeElement !== input) input.focus(); }, 1000);

input.addEventListener('keyup', function (e) {
  if (e.key !== 'Enter') return;
  var code = input.value.trim();
  if (!code) return;
  if (/^\d{18}$/.test(code) && (code.startsWith('13') || code.startsWith('28'))) {
    doCheckout(); input.value = ''; return;
  }
  processBarcode(code);
});

/* ===== Modal Functions ===== */
function openModal(title) {
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalBody').innerHTML = '<div class="modal-loading">\u52a0\u8f7d\u4e2d...</div>';
  document.getElementById('modalOverlay').classList.add('show');
}
function closeModal(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('modalOverlay').classList.remove('show');
}
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });

/* Today Revenue Detail */
function showTodayDetail() {
  openModal('\U0001F4B0 \u4eca\u65e5\u9500\u552e\u660e\u7ec6');
  fetchJSON('/api/today_detail/').then(function (d) {
    if (!d.grouped || !d.grouped.length) {
      document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\u4eca\u65e5\u6682\u65e0\u9500\u552e\u8bb0\u5f55</div>';
      return;
    }
    var html = '<table class="modal-table"><tr><th>\u5546\u54c1</th><th style="text-align:center">\u6570\u91cf</th><th style="text-align:right">\u5c0f\u8ba1</th><th style="text-align:right">\u65f6\u95f4</th></tr>';
    d.grouped.forEach(function (g) {
      html += '<tr><td>' + g.name + '</td><td class="num" style="text-align:center">\u00d7' + g.qty + '</td><td class="money" style="text-align:right">\uffe5' + g.amount.toFixed(2) + '</td><td class="time" style="text-align:right">' + g.last_time + '</td></tr>';
    });
    html += '</table>';
    html += '<div class="modal-footer"><span>\u5408\u8ba1 ' + d.total_count + ' \u4ef6</span><span style="color:#f5222d">\uffe5' + d.total_revenue.toFixed(2) + '</span></div>';
    document.getElementById('modalBody').innerHTML = html;
  }).catch(function () {
    document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\u52a0\u8f7d\u5931\u8d25</div>';
  });
}

/* Pending Orders Detail */
function showPendingOrders() {
  openModal('\U0001F4CB \u5f85\u53d6\u8d27\u8ba2\u5355');
  fetchJSON('/api/pending_orders/').then(function (d) {
    if (!d.list || !d.list.length) {
      document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\u2705 \u6682\u65e0\u5f85\u53d6\u8d27\u8ba2\u5355</div>';
      return;
    }
    var html = '';
    d.list.forEach(function (o) {
      html += '<div style="margin-bottom:16px;padding:12px;background:#fafafa;border-radius:8px;">';
      html += '<div style="display:flex;justify-content:space-between;font-weight:700;font-size:13px;"><span>#' + o.order_sn.slice(-8) + '</span><span style="color:#fa8c16">\u5f85\u53d6\u8d27</span></div>';
      html += '<div style="margin:4px 0;font-size:13px;color:#666;">\u53d6\u8d27\u4eba: ' + o.customer_name + '</div>';
      html += '<div style="font-size:12px;color:#999;margin-bottom:4px;">\u5546\u54c1:</div>';
      o.items.forEach(function (item) {
        html += '<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0;"><span>' + item.name + ' \u00d7' + item.count + '</span><span style="color:#f5222d">\uffe5' + (parseFloat(item.price) * item.count).toFixed(2) + '</span></div>';
      });
      html += '<div style="text-align:right;font-weight:700;font-size:13px;margin-top:4px;padding-top:4px;border-top:1px solid #eee;">\u5408\u8ba1: \uffe5' + o.total_price + '</div>';
      html += '</div>';
    });
    document.getElementById('modalBody').innerHTML = html;
  }).catch(function () {
    document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\u52a0\u8f7d\u5931\u8d25</div>';
  });
}

/* Low Stock Detail */
function showLowStock() {
  openModal('\u26a0\ufe0f \u4f4e\u5e93\u5b58\u5546\u54c1');
  fetchJSON('/api/low_stock_products/?threshold=5&limit=100').then(function (d) {
    if (!d.list || !d.list.length) {
      document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\u2705 \u5e93\u5b58\u5145\u8db3</div>';
      return;
    }
    var html = '<table class="modal-table"><tr><th>\u5546\u54c1</th><th style="text-align:right">\u5e93\u5b58</th><th style="text-align:right">\u4ef7\u683c</th></tr>';
    d.list.forEach(function (p) {
      var color = p.stock <= 0 ? '#f5222d' : p.stock <= 3 ? '#fa8c16' : '#52c41a';
      html += '<tr><td>' + p.name + '</td><td style="text-align:right;color:' + color + ';font-weight:700;">' + p.stock + '</td><td class="money" style="text-align:right">\uffe5' + p.price + '</td></tr>';
    });
    html += '</table>';
    html += '<div class="modal-footer"><span>\u5171 ' + d.total_count + ' \u4e2a\u5546\u54c1\u4f4e\u5e93\u5b58</span></div>';
    document.getElementById('modalBody').innerHTML = html;
  }).catch(function () {
    document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\u52a0\u8f7d\u5931\u8d25</div>';
  });
}

/* Bind stat card clicks */
(function () {
  var cards = document.querySelectorAll('.stat-card');
  if (cards.length >= 1) cards[0].onclick = showTodayDetail;
  if (cards.length >= 2) cards[1].onclick = showTodayDetail;
  if (cards.length >= 3) cards[2].onclick = showPendingOrders;
  if (cards.length >= 4) cards[3].onclick = showLowStock;
})();

function renderLogEntry(item) {
  var ts = item.added_at || new Date().toTimeString().slice(0,8);
  var e = document.createElement('div'); e.className = 'log-entry';
  var qty = item.quantity > 1 ? ' ×' + item.quantity : '';
  var sub = item.quantity > 1 ? ' (小计 ￥' + (parseFloat(item.price) * item.quantity).toFixed(2) + ')' : '';
  e.innerHTML = '<span class="log-time">' + ts + '</span><span class="log-name">' + item.name + qty + '</span><span class="log-price">￥' + item.price + sub + '</span>';
  return e;
}

function initCartSummary() {
  fetchWithTimeout('/get_cart_status/').then(function (r) { return r.json(); }).then(function (d) {
    if (d.items && d.items.length > 0) {
      scanCount = d.items.reduce(function (s, i) { return s + i.quantity; }, 0);
      scanTotal = parseFloat(d.total || 0);
      // 重建扫码记录列表，确保网页端和小程序看到的购物车一致
      logArea.innerHTML = '';
      d.items.forEach(function (item) { logArea.appendChild(renderLogEntry(item)); });
    } else {
      scanCount = 0; scanTotal = 0;
      logArea.innerHTML = '<div class="empty-state">暂无记录，扫码后将显示在此处</div>';
    }
    updateCartSummary();
  }).catch(function () {});
}

updateStats();
loadDashboard();
initCartSummary();
setInterval(updateStats, 5000);
setInterval(loadDashboard, 30000);
setInterval(initCartSummary, 5000);  // 定期和服务端同步，防止小程序清空后本地不同步
</script>

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
<title>一得书苑 · 线上商城</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  :root {
    --green: #07c160;
    --green-dark: #06ad56;
    --green-light: #e8f8ee;
    --bg: #f7f7f7;
    --card-bg: #fff;
    --text: #333;
    --text-secondary: #999;
    --border: #f0f0f0;
    --shadow: 0 2px 12px rgba(0,0,0,0.06);
    --radius: 12px;
    --safe-bottom: env(safe-area-inset-bottom, 0px);
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.5;
    padding-bottom: calc(72px + var(--safe-bottom));
    -webkit-font-smoothing: antialiased;
    min-height: 100vh;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    touch-action: manipulation;
  }

  /* ===== Header ===== */
  .mall-header {
    background: var(--green);
    color: #fff;
    padding: 16px 16px 12px;
    position: sticky;
    top: 0;
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .mall-header h1 { font-size: 18px; font-weight: 600; letter-spacing: 1px; }
  .header-admin-btn {
    position: absolute;
    right: 14px;
    top: 50%;
    transform: translateY(-50%);
    font-size: 16px;
    text-decoration: none;
    opacity: 0.55;
    color: #fff;
    padding: 6px;
    border-radius: 8px;
    transition: opacity 0.2s;
  }
  .header-admin-btn:hover { opacity: 1; }

  /* ===== Search ===== */
  .search-bar {
    padding: 10px 16px;
    background: var(--bg);
    position: sticky;
    top: 52px;
    z-index: 99;
  }
  .search-box {
    display: flex;
    gap: 8px;
    background: var(--card-bg);
    border-radius: 8px;
    padding: 4px 12px;
    align-items: center;
    box-shadow: var(--shadow);
  }
  .search-box input {
    flex: 1;
    border: none;
    outline: none;
    font-size: 14px;
    padding: 8px 0;
    background: transparent;
  }
  .search-box button {
    background: none;
    border: none;
    font-size: 18px;
    cursor: pointer;
    padding: 4px;
    color: var(--text-secondary);
  }
  .search-clear {
    font-size: 16px;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 4px;
  }

  /* ===== Category Bar ===== */
  .category-bar {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    padding: 0 16px 10px;
    background: var(--bg);
    position: sticky;
    top: 100px;
    z-index: 98;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  .category-bar::-webkit-scrollbar { display: none; }
  .cat-item {
    flex-shrink: 0;
    padding: 5px 14px;
    border-radius: 16px;
    font-size: 13px;
    background: var(--card-bg);
    color: var(--text);
    cursor: pointer;
    transition: all 0.2s;
    box-shadow: var(--shadow);
    border: 2px solid transparent;
  }
  .cat-item.active {
    background: var(--green-light);
    color: var(--green);
    border-color: var(--green);
    font-weight: 600;
  }

  /* ===== Loading ===== */
  .loading-tip {
    text-align: center;
    padding: 40px 16px;
    color: var(--text-secondary);
    font-size: 14px;
  }
  .loading-spinner {
    display: inline-block;
    width: 24px;
    height: 24px;
    border: 3px solid var(--border);
    border-top-color: var(--green);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-bottom: 8px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ===== Product Grid ===== */
  .product-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    padding: 0 16px 10px;
  }
  .product-card {
    background: var(--card-bg);
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: var(--shadow);
    display: flex;
    flex-direction: column;
  }
  .card-img-wrap {
    height: 110px;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    font-size: 48px;
  }
  .card-badge {
    position: absolute;
    top: 8px;
    left: 8px;
    padding: 2px 8px;
    border-radius: 8px;
    font-size: 11px;
    font-weight: 600;
    color: #fff;
  }
  .card-badge.hot { background: #ff4757; }
  .card-badge.low { background: #ffa502; }
  .card-info {
    padding: 10px 12px 12px;
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .card-name {
    font-size: 13px;
    font-weight: 500;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    line-height: 1.4;
    min-height: 2.8em;
  }
  .card-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: auto;
  }
  .card-price {
    font-size: 16px;
    font-weight: 700;
    color: var(--green);
  }
  .card-price::before { content: '¥'; font-size: 12px; }
  .card-stock {
    font-size: 11px;
    color: var(--text-secondary);
  }
  .card-stock.warn { color: #ffa502; }
  .btn-add-wrap {
    margin-top: 8px;
  }
  .btn-add {
    width: 100%;
    padding: 6px 0;
    background: var(--green);
    color: #fff;
    border: none;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    transition: background 0.2s;
  }
  .btn-add:active { background: var(--green-dark); }
  .btn-add.sold-out { background: #ccc; cursor: not-allowed; }

  /* ===== Empty ===== */
  .empty-tip {
    text-align: center;
    padding: 60px 16px;
    color: var(--text-secondary);
    grid-column: 1 / -1;
  }
  .empty-icon { font-size: 48px; display: block; margin-bottom: 12px; }

  /* ===== Cart Bar (bottom fixed) ===== */
  .cart-bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 24px; /* sits just above the always-visible shopkeeper-bar */
    background: var(--card-bg);
    box-shadow: 0 -2px 12px rgba(0,0,0,0.08);
    padding: 6px 16px;
    display: flex;
    align-items: center;
    gap: 12px;
    z-index: 500;
    transition: transform 0.3s;
  }
  .cart-bar.hidden { transform: translateY(100%); }

  /* ===== Always-visible bottom bar (到店取货) ===== */
  .shopkeeper-bar {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--card-bg);
    border-top: 1px solid var(--border);
    text-align: center;
    padding: 3px 16px calc(3px + var(--safe-bottom));
    color: var(--text-secondary);
    font-size: 11px;
    z-index: 490;
    line-height: 1.4;
  }
  .cart-info {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
  }
  .cart-icon-wrap {
    position: relative;
    font-size: 28px;
  }
  .cart-badge-num {
    position: absolute;
    top: -6px;
    right: -10px;
    background: var(--green);
    color: #fff;
    font-size: 11px;
    min-width: 18px;
    height: 18px;
    border-radius: 9px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    padding: 0 4px;
  }
  .cart-price-wrap {
    display: flex;
    flex-direction: column;
  }
  .total-text { font-size: 11px; color: var(--text-secondary); }
  .price-num {
    font-size: 18px;
    font-weight: 700;
    color: var(--text);
  }
  .price-num::before { content: '¥'; font-size: 13px; }
  .settle-btn {
    padding: 10px 24px;
    background: var(--green);
    color: #fff;
    border: none;
    border-radius: 22px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s;
    flex-shrink: 0;
  }
  .settle-btn:active { background: var(--green-dark); }
  .settle-btn.disabled { background: #ccc; cursor: not-allowed; }

  /* ===== Cart Detail Overlay ===== */
  .overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.45);
    z-index: 600;
    opacity: 0;
    visibility: hidden;
    pointer-events: none;  /* 防止隐藏时拦截触摸 */
    transition: all 0.25s;
  }
  .overlay.show { opacity: 1; visibility: visible; pointer-events: auto; }

  .cart-panel {
    position: fixed;
    left: 0; right: 0;
    bottom: 0;
    background: var(--card-bg);
    border-radius: 16px 16px 0 0;
    z-index: 700;
    transform: translateY(100%);
    transition: transform 0.3s ease;
    max-height: 60vh;
    display: flex;
    flex-direction: column;
    padding-bottom: var(--safe-bottom);
  }
  .cart-panel.show { transform: translateY(0); }
  .cart-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 16px 12px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  .cart-panel-header .title { font-size: 16px; font-weight: 600; }
  .clear-cart-btn {
    font-size: 13px;
    color: #ff4757;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
  }
  .clear-cart-btn:active { background: #fff5f5; }
  .cart-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px 16px;
  }
  .cart-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
  }
  .cart-item:last-child { border-bottom: none; }
  .cart-item-left { flex: 1; min-width: 0; }
  .cart-item-name {
    font-size: 14px;
    font-weight: 500;
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .cart-item-price {
    font-size: 13px;
    color: var(--text-secondary);
    margin-top: 2px;
  }
  .cart-item-emoji { font-size: 28px; flex-shrink: 0; }
  .qty-ctrl {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .qty-btn {
    width: 26px; height: 26px;
    border-radius: 50%;
    border: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    cursor: pointer;
    user-select: none;
    transition: all 0.15s;
  }
  .qty-btn:active { background: var(--border); }
  .qty-num {
    min-width: 24px;
    text-align: center;
    font-size: 14px;
    font-weight: 600;
  }
  .cart-item-subtotal {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
    min-width: 52px;
    text-align: right;
  }
  .cart-item-subtotal::before { content: '¥'; font-size: 11px; }

  /* ===== Order Modal ===== */
  .modal-panel {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) scale(0.9);
    background: var(--card-bg);
    border-radius: 16px;
    z-index: 800;
    width: 88%;
    max-width: 380px;
    max-height: 80vh;
    overflow-y: auto;
    opacity: 0;
    visibility: hidden;
    transition: all 0.25s;
    padding: 20px;
  }
  .modal-panel.show {
    opacity: 1;
    visibility: visible;
    transform: translate(-50%, -50%) scale(1);
  }
  .modal-panel h2 {
    font-size: 18px;
    text-align: center;
    margin-bottom: 16px;
  }
  .order-summary {
    background: var(--bg);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 16px;
  }
  .order-item {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    padding: 4px 0;
  }
  .order-item .name { color: var(--text); }
  .order-item .sub { color: var(--text-secondary); }
  .order-total {
    display: flex;
    justify-content: space-between;
    padding: 8px 0 0;
    margin-top: 8px;
    border-top: 1px solid var(--border);
    font-size: 16px;
    font-weight: 700;
  }
  .order-total .val { color: var(--green); }
  .order-total .val::before { content: '¥'; font-size: 12px; }
  .name-input-wrap {
    margin-bottom: 16px;
  }
  .name-input-wrap label {
    display: block;
    font-size: 13px;
    color: var(--text-secondary);
    margin-bottom: 6px;
  }
  .name-input-wrap input {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 15px;
    outline: none;
    transition: border-color 0.2s;
  }
  .name-input-wrap input:focus { border-color: var(--green); }
  .modal-actions {
    display: flex;
    gap: 10px;
  }
  .modal-actions button {
    flex: 1;
    padding: 12px;
    border: none;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s;
  }
  .btn-cancel { background: var(--bg); color: var(--text); }
  .btn-cancel:active { background: #e8e8e8; }
  .btn-confirm { background: var(--green); color: #fff; }
  .btn-confirm:active { background: var(--green-dark); }
  .btn-confirm:disabled { opacity: 0.5; cursor: not-allowed; }

  /* ===== Success Modal ===== */
  .success-modal {
    text-align: center;
  }
  .success-icon { font-size: 56px; margin-bottom: 12px; display: block; }
  .success-modal .order-no {
    font-size: 13px;
    color: var(--text-secondary);
    margin: 8px 0 4px;
  }
  .success-modal .order-no span {
    color: var(--text);
    font-weight: 600;
    letter-spacing: 1px;
  }
  .success-modal .tips {
    font-size: 12px;
    color: var(--text-secondary);
    margin-bottom: 16px;
  }
  .success-modal .btn-primary {
    width: 100%;
    padding: 12px;
    background: var(--green);
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
  }
  .success-modal .btn-primary:active { background: var(--green-dark); }

  /* ===== Toast ===== */
  .toast {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: rgba(0,0,0,0.78);
    color: #fff;
    padding: 12px 20px;
    border-radius: 8px;
    font-size: 14px;
    z-index: 9999;
    opacity: 0;
    transition: opacity 0.25s;
    pointer-events: none;
    text-align: center;
    max-width: 80%;
  }
  .toast.show { opacity: 1; }

  /* ===== Offline Banner ===== */
  .offline-banner {
    background: #fff3cd;
    color: #856404;
    text-align: center;
    padding: 8px;
    font-size: 13px;
    display: none;
  }
</style>
</head>
<body>

<!-- Header -->
<div class="mall-header">
  <h1>🛍️ 一得书苑 · 线上商城</h1>
  <a href="/cashier/" class="header-admin-btn" title="店长入口">🔑</a>
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
<div class="shopkeeper-bar">🏪 到店取货 · 提交后到柜台报姓名付款取货</div>

<script>
// ============================================================
// 配置 & 状态
// ============================================================
var API_BASE = '';
var CATEGORIES = [
  { id: 'all', name: '全部' },
  { id: 'books', name: '📚 名著书籍' },
  { id: 'pens', name: '🖊️ 书写工具' },
  { id: 'papers', name: '📓 本册纸品' },
  { id: 'stationery', name: '📐 学生文具' },
  { id: 'correction', name: '📦 修正粘合' },
  { id: 'others', name: '📎 其他' }
];
var CATEGORY_COLORS = {
  books: '#667eea', pens: '#f5576c', papers: '#4facfe',
  stationery: '#43e97b', correction: '#fa709a', others: '#a8edea'
};

var state = {
  products: [],
  cart: [],
  activeCat: 'all',
  searchKey: '',
  loading: true,
  cartOpen: false,
  orderOpen: false,
  submitting: false,
  toastTimer: null
};

// ============================================================
// Utility
// ============================================================
function getFromStorage(key, def) {
  try { var v = localStorage.getItem('mall_' + key); return v ? JSON.parse(v) : def; } catch(e) { return def; }
}
function saveCart() {
  try { localStorage.setItem('mall_cart', JSON.stringify(state.cart)); } catch(e) {}
}
function loadCart() {
  try { var v = localStorage.getItem('mall_cart'); state.cart = v ? JSON.parse(v) : []; } catch(e) { state.cart = []; }
  // 防御性清理：确保每个商品都有有效字段
  try {
    state.cart = (state.cart || []).filter(function(item) {
      return item && typeof item.id === 'number' && typeof item.name === 'string' && typeof item.num === 'number' && item.num > 0;
    }).map(function(item) {
      return { id: item.id, name: item.name, price: Number(item.price || 0), num: Math.min(item.num, 999), stock: item.stock || 999, category: item.category || 'others', productEmoji: item.productEmoji || '📦', categoryColor: item.categoryColor || '#c0c0c0' };
    });
    saveCart();
  } catch(e) { state.cart = []; }
}

var EMOJI_MAP = [
  ['字典','📕'], ['词典','📘'], ['成语','📘'],
  ['作文','📗'], ['字帖','🖌️'], ['古诗词','📜'], ['唐诗','📜'], ['诗词','📜'],
  ['绘本','🎨'], ['阅读','📖'],
  ['中性笔','🖊️'], ['圆珠笔','🖊️'], ['签字笔','🖊️'],
  ['铅笔','✏️'], ['自动铅笔','✏️'], ['钢笔','🖋️'],
  ['马克笔','🖍️'], ['荧光笔','🖍️'], ['荧光','🖍️'],
  ['水彩笔','🎨'], ['白板笔','🖍️'], ['记号笔','🖍️'],
  ['笔芯','✒️'], ['替芯','✒️'],
  ['笔记本','📓'], ['作业本','📔'], ['练习本','📔'], ['英语本','📔'],
  ['方格本','📐'], ['便利贴','🏷️'], ['便签','🏷️'],
  ['文件袋','📂'], ['档案袋','📁'], ['复印纸','📄'], ['打印纸','📄'],
  ['A4纸','📄'], ['稿纸','📝'], ['线圈本','📓'],
  ['橡皮','🧽'], ['尺子','📏'], ['直尺','📏'], ['三角尺','📐'],
  ['圆规','📐'], ['剪刀','✂️'], ['订书机','🔧'],
  ['订书钉','📌'], ['订书针','📌'], ['回形针','📎'],
  ['长尾夹','📎'], ['卷笔刀','🌀'], ['削笔','🌀'],
  ['美工刀','🔪'], ['垫板','🖼️'], ['笔袋','👝'],
  ['文具盒','🧰'], ['书包','🎒'], ['打孔','🔴'],
  ['修正带','📦'], ['修正液','🧴'], ['涂改液','🧴'],
  ['改正带','📦'], ['固体胶','🧴'], ['胶棒','🧴'],
  ['胶水','🧴'], ['胶带','📯'], ['双面胶','📯'],
  ['计算器','🔢'], ['台历','📅']
];
function getProductEmoji(name) {
  for (var i = 0; i < EMOJI_MAP.length; i++) {
    if (name.indexOf(EMOJI_MAP[i][0]) !== -1) return EMOJI_MAP[i][1];
  }
  return '📦';
}
function getCategoryColor(cat) { return CATEGORY_COLORS[cat] || '#c0c0c0'; }
function getProductStock(p) { return Number(p.stock || p.remaining_stock || 0); }
function isNewProduct(p) {
  if (!p.create_time) return false;
  var d = new Date(p.create_time);
  return ((Date.now() - d.getTime()) / 86400000) <= 7;
}

// ============================================================
// API
// ============================================================
function apiGet(url) {
  return fetch(API_BASE + url, { signal: AbortSignal.timeout(8000) }).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  });
}
function apiPost(url, data) {
  return fetch(API_BASE + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
    signal: AbortSignal.timeout(8000)
  }).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  });
}

// ============================================================
// Toast
// ============================================================
function showToast(msg, icon) {
  var el = document.getElementById('toast');
  el.textContent = (icon || '') + ' ' + msg;
  el.className = 'toast show';
  if (state.toastTimer) clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(function() { el.className = 'toast'; }, 2000);
}

// ============================================================
// Render Categories
// ============================================================
function renderCategories() {
  var el = document.getElementById('categoryBar');
  el.innerHTML = CATEGORIES.map(function(c) {
    return '<div class="cat-item' + (c.id === state.activeCat ? ' active' : '') + '" data-cat="' + c.id + '">' + c.name + '</div>';
  }).join('');
  el.addEventListener('click', function(e) {
    var item = e.target.closest('.cat-item');
    if (!item) return;
    state.activeCat = item.dataset.cat;
    renderCategories();
    fetchProducts();
  });
}

// ============================================================
// Fetch Products
// ============================================================
var _fetchCount = 0;
function fetchProducts() {
  state.loading = true;
  document.getElementById('loadingTip').style.display = 'block';
  document.getElementById('productGrid').style.display = 'none';
  document.getElementById('emptyTip').style.display = 'none';

  var cat = state.activeCat;
  var search = state.searchKey;
  var reqId = ++_fetchCount;

  apiGet('/api/mall_products/?category=' + encodeURIComponent(cat) + '&search=' + encodeURIComponent(search))
    .then(function(data) {
      if (reqId !== _fetchCount) return; // stale
      state.loading = false;
      document.getElementById('loadingTip').style.display = 'none';
      if (data && data.status === 'success') {
        var list = (data.list || []).map(function(p) {
          return {
            id: p.id,
            name: p.name,
            price: String(p.price),
            stock: getProductStock(p),
            category: p.category,
            create_time: p.create_time,
            productEmoji: getProductEmoji(p.name),
            categoryColor: getCategoryColor(p.category)
          };
        });
        state.products = list;
        if (list.length > 0) {
          document.getElementById('productGrid').style.display = 'grid';
          renderProducts(list);
          syncCartWithProducts();
        } else {
          document.getElementById('emptyTip').style.display = 'block';
        }
      } else {
        showToast((data && data.msg) || '商品加载失败', '⚠️');
        document.getElementById('emptyTip').style.display = 'block';
      }
      document.getElementById('offlineBanner').style.display = 'none';
    })
    .catch(function(err) {
      if (reqId !== _fetchCount) return;
      state.loading = false;
      document.getElementById('loadingTip').style.display = 'none';
      document.getElementById('offlineBanner').style.display = 'block';
      showToast('服务器连接失败', '⚠️');
      // 尝试用缓存的商品展示
      if (state.products.length > 0) {
        document.getElementById('productGrid').style.display = 'grid';
        renderProducts(state.products);
      } else {
        document.getElementById('emptyTip').style.display = 'block';
      }
    });
}

// ============================================================
// Render Products
// ============================================================
function renderProducts(list) {
  var el = document.getElementById('productGrid');
  el.innerHTML = list.map(function(p) {
    var stock = p.stock;
    var badges = '';
    if (isNewProduct(p)) badges += '<div class="card-badge hot">新品</div>';
    else if (stock <= 5) badges += '<div class="card-badge low">仅剩' + stock + '</div>';

    var canBuy = stock > 0;
    var inCart = state.cart.find(function(c) { return c.id === p.id; });
    var btnHtml = canBuy
      ? '<button class="btn-add" data-id="' + p.id + '">加入购物车</button>'
      : '<button class="btn-add sold-out" disabled>已售罄</button>';

    return '<div class="product-card" data-id="' + p.id + '">'
      + '<div class="card-img-wrap" style="background:' + p.categoryColor + ';">'
        + '<span style="font-size:48px">' + p.productEmoji + '</span>'
        + badges
      + '</div>'
      + '<div class="card-info">'
        + '<div class="card-name">' + escHtml(p.name) + '</div>'
        + '<div class="card-meta">'
          + '<span class="card-price">' + p.price + '</span>'
          + '<span class="card-stock' + (stock <= 5 ? ' warn' : '') + '">'
            + (stock > 10 ? '库存充足' : (stock <= 0 ? '无货' : '剩' + stock))
          + '</span>'
        + '</div>'
        + '<div class="btn-add-wrap">' + btnHtml + '</div>'
      + '</div>'
    + '</div>';
  }).join('');

  // Event delegation for add-to-cart
  el.addEventListener('click', function(e) {
    var btn = e.target.closest('.btn-add');
    if (!btn || btn.disabled) return;
    var card = btn.closest('.product-card');
    if (!card) return;
    var id = Number(card.dataset.id);
    var product = state.products.find(function(p) { return p.id === id; });
    if (product) addToCart(product);
  });
}

function escHtml(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ============================================================
// Cart Operations
// ============================================================
function addToCart(product) {
  var idx = state.cart.findIndex(function(c) { return c.id === product.id; });
  if (idx === -1) {
    if (product.stock <= 0) { showToast('该商品已售罄', '😅'); return; }
    state.cart.push({
      id: product.id,
      name: product.name,
      price: Number(product.price),
      num: 1,
      stock: product.stock,
      category: product.category,
      productEmoji: product.productEmoji,
      categoryColor: product.categoryColor
    });
  } else {
    if (state.cart[idx].num >= product.stock) {
      showToast('库存仅剩 ' + product.stock + ' 件', '⚠️');
      return;
    }
    state.cart[idx].num += 1;
  }
  saveCart();
  updateCartBar();
  showToast('已加入 🛒', '✅');
}

function minusItem(id) {
  var idx = state.cart.findIndex(function(c) { return c.id === id; });
  if (idx === -1) return;
  if (state.cart[idx].num > 1) {
    state.cart[idx].num -= 1;
  } else {
    state.cart.splice(idx, 1);
    if (state.cart.length === 0 && state.cartOpen) toggleCart();
  }
  saveCart();
  updateCartBar();
  renderCartList();
}

function plusItem(id) {
  var idx = state.cart.findIndex(function(c) { return c.id === id; });
  if (idx === -1) return;
  var product = state.products.find(function(p) { return p.id === id; });
  var maxStock = product ? product.stock : state.cart[idx].stock;
  if (state.cart[idx].num >= maxStock) {
    showToast('库存仅剩 ' + maxStock + ' 件', '⚠️');
    return;
  }
  state.cart[idx].num += 1;
  saveCart();
  updateCartBar();
  renderCartList();
}

function clearCart() {
  if (state.cart.length === 0) return;
  if (!confirm('确定要清空购物车吗？')) return;
  state.cart = [];
  saveCart();
  updateCartBar();
  renderCartList();
  if (state.cartOpen) toggleCart();
  showToast('已清空', '🗑️');
}

function syncCartWithProducts() {
  var changed = false;
  var productMap = {};
  state.products.forEach(function(p) { productMap[p.id] = p; });

  state.cart = state.cart.filter(function(item) {
    var latest = productMap[item.id];
    if (!latest) { changed = true; return false; }
    var stock = getProductStock(latest);
    if (stock <= 0) { changed = true; return false; }
    var num = Math.min(item.num, stock);
    if (num !== item.num) { changed = true; }
    item.num = num;
    item.stock = stock;
    item.price = Number(latest.price);
    item.name = latest.name;
    // update emoji/color in case product name changed category
    item.productEmoji = getProductEmoji(latest.name);
    item.categoryColor = getCategoryColor(latest.category);
    return true;
  });

  if (changed) {
    saveCart();
    updateCartBar();
    showToast('购物车已按最新库存更新', '🔄');
  }
}

// ============================================================
// Cart Bar & Panel
// ============================================================
function updateCartBar() {
  var totalCount = 0, totalPrice = 0;
  state.cart.forEach(function(v) {
    totalCount += v.num;
    totalPrice += v.num * v.price;
  });

  document.getElementById('cartBadge').textContent = totalCount > 99 ? '99+' : totalCount;
  document.getElementById('cartTotal').textContent = totalPrice.toFixed(2);

  var bar = document.getElementById('cartBar');
  var settleBtn = document.getElementById('settleBtn');
  if (totalCount > 0) {
    bar.className = 'cart-bar';
    settleBtn.className = 'settle-btn';
  } else {
    bar.className = 'cart-bar hidden';
    settleBtn.className = 'settle-btn disabled';
  }
}

function toggleCart() {
  state.cartOpen = !state.cartOpen;
  document.getElementById('cartOverlay').className = 'overlay' + (state.cartOpen ? ' show' : '');
  document.getElementById('cartPanel').className = 'cart-panel' + (state.cartOpen ? ' show' : '');
  document.body.style.overflow = state.cartOpen ? 'hidden' : '';
  if (state.cartOpen) renderCartList();
}

function renderCartList() {
  var el = document.getElementById('cartList');
  if (state.cart.length === 0) {
    el.innerHTML = '<div style="text-align:center;padding:30px 0;color:#999;">购物车为空</div>';
    return;
  }
  el.innerHTML = state.cart.map(function(item) {
    var subtotal = (item.num * item.price).toFixed(2);
    return '<div class="cart-item" data-id="' + item.id + '">'
      + '<span class="cart-item-emoji">' + (item.productEmoji || '📦') + '</span>'
      + '<div class="cart-item-left">'
        + '<span class="cart-item-name">' + escHtml(item.name) + '</span>'
        + '<span class="cart-item-price">¥' + Number(item.price).toFixed(2) + '/件</span>'
      + '</div>'
      + '<div class="qty-ctrl">'
        + '<div class="qty-btn minus-btn" data-id="' + item.id + '">−</div>'
        + '<span class="qty-num">' + item.num + '</span>'
        + '<div class="qty-btn plus-btn" data-id="' + item.id + '">+</div>'
      + '</div>'
      + '<span class="cart-item-subtotal">' + subtotal + '</span>'
    + '</div>';
  }).join('');

  // Event listeners for qty buttons
  el.querySelectorAll('.minus-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      minusItem(Number(e.currentTarget.dataset.id));
    });
  });
  el.querySelectorAll('.plus-btn').forEach(function(btn) {
    btn.addEventListener('click', function(e) {
      plusItem(Number(e.currentTarget.dataset.id));
    });
  });
}

// ============================================================
// Order
// ============================================================
function openOrder() {
  if (state.cart.length === 0) { showToast('购物车为空', '🛒'); return; }
  state.orderOpen = true;
  document.getElementById('orderOverlay').className = 'overlay show';
  document.getElementById('orderPanel').className = 'modal-panel show';

  // Render order summary
  var total = 0;
  var html = state.cart.map(function(item) {
    var sub = (item.num * item.price).toFixed(2);
    total += item.num * item.price;
    return '<div class="order-item">'
      + '<span class="name">' + escHtml(item.name) + ' × ' + item.num + '</span>'
      + '<span class="sub">¥' + sub + '</span>'
    + '</div>';
  }).join('');
  html += '<div class="order-total"><span>合计</span><span class="val">' + total.toFixed(2) + '</span></div>';
  document.getElementById('orderSummary').innerHTML = html;

  document.getElementById('customerName').value = '';
  document.getElementById('orderSubmit').disabled = false;
  document.getElementById('orderSubmit').textContent = '✅ 提交订单';
  state.submitting = false;
  document.body.style.overflow = 'hidden';
}

function closeOrder() {
  state.orderOpen = false;
  document.getElementById('orderOverlay').className = 'overlay';
  document.getElementById('orderPanel').className = 'modal-panel';
  document.body.style.overflow = '';
}

function submitOrder() {
  if (state.submitting) return;
  var name = document.getElementById('customerName').value.trim();
  if (!name) { showToast('请输入取货人姓名', '👤'); return; }

  state.submitting = true;
  var btn = document.getElementById('orderSubmit');
  btn.disabled = true;
  btn.textContent = '⏳ 提交中...';

  var cartData = state.cart.map(function(item) {
    return { id: item.id, name: item.name, price: String(item.price), num: item.num };
  });
  var total = state.cart.reduce(function(sum, item) { return sum + item.num * item.price; }, 0);

  apiPost('/api/submit_order/', {
    name: name,
    cart: cartData,
    total: total.toFixed(2)
  }).then(function(data) {
    state.submitting = false;
    if (data.status === 'success') {
      // Clear cart
      state.cart = [];
      saveCart();
      updateCartBar();

      // Show success
      closeOrder();
      document.getElementById('orderSn').textContent = data.order_sn || '';
      document.getElementById('successOverlay').className = 'overlay show';
      document.getElementById('successPanel').className = 'modal-panel success-modal show';
    } else {
      btn.disabled = false;
      btn.textContent = '✅ 提交订单';
      showToast(data.msg || '提交失败', '⚠️');
    }
  }).catch(function(err) {
    state.submitting = false;
    btn.disabled = false;
    btn.textContent = '✅ 提交订单';
    showToast('网络异常，请重试', '⚠️');
  });
}

function closeSuccess() {
  document.getElementById('successOverlay').className = 'overlay';
  document.getElementById('successPanel').className = 'modal-panel success-modal';
}

// ============================================================
// Init
// ============================================================
function init() {
  loadCart();

  // Search
  document.getElementById('searchBtn').addEventListener('click', function() {
    state.searchKey = document.getElementById('searchInput').value.trim();
    if (state.searchKey) state.activeCat = 'all';
    renderCategories();
    fetchProducts();
  });
  document.getElementById('searchInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      state.searchKey = e.target.value.trim();
      if (state.searchKey) state.activeCat = 'all';
      renderCategories();
      fetchProducts();
    }
  });
  document.getElementById('searchInput').addEventListener('input', function(e) {
    document.getElementById('clearBtn').style.display = e.target.value ? '' : 'none';
  });
  document.getElementById('clearBtn').addEventListener('click', function() {
    document.getElementById('searchInput').value = '';
    state.searchKey = '';
    document.getElementById('clearBtn').style.display = 'none';
    fetchProducts();
  });

  // Cart
  document.getElementById('cartBarInfo').addEventListener('click', toggleCart);
  document.getElementById('cartOverlay').addEventListener('click', toggleCart);
  document.getElementById('clearCartBtn').addEventListener('click', clearCart);

  // Order
  document.getElementById('settleBtn').addEventListener('click', openOrder);
  document.getElementById('orderCancel').addEventListener('click', closeOrder);
  document.getElementById('orderOverlay').addEventListener('click', closeOrder);
  document.getElementById('orderSubmit').addEventListener('click', submitOrder);

  // Success
  document.getElementById('successDone').addEventListener('click', closeSuccess);
  document.getElementById('successOverlay').addEventListener('click', closeSuccess);

  renderCategories();
  updateCartBar();
  fetchProducts();

  // Periodic cart sync
  setInterval(function() {
    if (state.products.length > 0) syncCartWithProducts();
  }, 15000);
}

document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>"""

def mall_home(request):
    from django.http import HttpResponse
    return HttpResponse(MALL_HTML)


def cash_register(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect('cashier_login')
    return HttpResponse(CASHIER_HTML)


# ============================================================
# 店长入口登录（单密码 + 自动登录 Django admin）
# ============================================================
CASHIER_LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>一得书苑 · 店长入口</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }
  .login-card {
    background: #fff;
    border-radius: 20px;
    padding: 40px 32px 32px;
    width: 100%;
    max-width: 380px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.15);
    text-align: center;
  }
  .login-icon { font-size: 56px; margin-bottom: 12px; display: block; }
  .login-title { font-size: 22px; font-weight: 700; color: #333; margin-bottom: 4px; }
  .login-sub { font-size: 14px; color: #999; margin-bottom: 28px; }
  .login-form input {
    width: 100%;
    padding: 14px 16px;
    border: 2px solid #e8e8e8;
    border-radius: 12px;
    font-size: 16px;
    outline: none;
    transition: border-color 0.2s;
    text-align: center;
    letter-spacing: 4px;
  }
  .login-form input:focus { border-color: #667eea; }
  .login-form input::placeholder { letter-spacing: 0; color: #ccc; }
  .login-btn {
    width: 100%;
    padding: 14px;
    margin-top: 16px;
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: #fff;
    border: none;
    border-radius: 12px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.15s, box-shadow 0.15s;
  }
  .login-btn:active { transform: scale(0.97); box-shadow: none; }
  .login-error {
    color: #f5222d;
    font-size: 14px;
    margin-top: 12px;
    display: none;
  }
  .login-error.show { display: block; }
  .back-link {
    margin-top: 20px;
    font-size: 13px;
  }
  .back-link a { color: rgba(255,255,255,0.8); text-decoration: none; }
  .back-link a:hover { color: #fff; }
</style>
</head>
<body>
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

<script>
// 若有错误参数，显示错误提示
var params = new URLSearchParams(window.location.search);
if (params.get('error') === '1') {
  document.getElementById('errorMsg').textContent = '密码错误，请重试';
  document.getElementById('errorMsg').className = 'login-error show';
}
document.getElementById('passwordInput').focus();
</script>
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

        return redirect('/cashier/login/?error=1')

    return HttpResponse(CASHIER_LOGIN_HTML)


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
    条码不在本地库时，尝试从外部开放 API 查询商品信息。
    返回 dict 或 None。
    """
    barcode = barcode.strip()
    price_estimate = None
    full_name = None
    category_hint = 'others'

    # 1) ISBN 类（978/979 开头共 13 位）
    if (barcode.startswith('978') or barcode.startswith('979')) and len(barcode) == 13:
        category_hint = 'books'

        # 1a) Open Library API（免费、无需密钥 → 查书名+作者）
        try:
            url = f'https://openlibrary.org/isbn/{barcode}.json'
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                title = data.get('title', '')
                authors = data.get('authors', [])
                author_names = []
                for a in authors:
                    key = a.get('key', '')
                    if key:
                        try:
                            a_resp = requests.get(f'https://openlibrary.org{key}.json', timeout=5)
                            if a_resp.status_code == 200:
                                a_data = a_resp.json()
                                author_names.append(a_data.get('name', ''))
                        except Exception:
                            pass
                author_str = ' / '.join(author_names) if author_names else ''
                full_name = title
                if author_str:
                    full_name = f'{title}（{author_str}）'
                logger.info("OpenLibrary 查到 ISBN %s → %s", barcode, full_name)
        except requests.Timeout:
            logger.warning("OpenLibrary 查询 %s 超时", barcode)
        except Exception as e:
            logger.warning("OpenLibrary 查询 %s 异常: %s", barcode, e)

        # 1b) Google Books API（公共端点，无 key 可用但有限额）
        try:
            gb_url = f'https://www.googleapis.com/books/v1/volumes?q=isbn:{barcode}'
            gb_resp = requests.get(gb_url, timeout=8)
            if gb_resp.status_code == 200:
                gb_data = gb_resp.json()
                items = gb_data.get('items', [])
                if items:
                    vol = items[0].get('volumeInfo', {})
                    if not full_name:
                        gb_title = vol.get('title', '')
                        gb_authors = vol.get('authors', [])
                        if gb_title:
                            full_name = gb_title
                            if gb_authors:
                                full_name = f'{gb_title}（{" / ".join(gb_authors)}）'
                    # 尝试获取零售价
                    sale_info = items[0].get('saleInfo', {})
                    if sale_info.get('isEbook') or sale_info.get('saleability') != 'NOT_FOR_SALE':
                        list_price = sale_info.get('listPrice', {})
                        if list_price.get('amount'):
                            price_estimate = round(float(list_price['amount']), 2)
                            logger.info("GoogleBooks 查到 %s 定价: %s", barcode, price_estimate)
        except Exception as e:
            logger.warning("GoogleBooks 查询 %s 异常: %s", barcode, e)

        if full_name:
            return {
                'name': full_name,
                'category': category_hint,
                'barcode': barcode,
                'price_estimate': price_estimate,
            }

    # 2) 通用条码 → barcode-list.com 免费 API（无密钥，有频率限制）
    try:
        url = f'https://barcode-list.com/api/v2/barcode/{barcode}'
        resp = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'ok' and data.get('product'):
                p = data['product']
                name = (p.get('name') or '').strip()
                brand = (p.get('brand') or '').strip()
                if name and brand:
                    name = f'{brand} {name}'
                elif brand:
                    name = brand
                logger.info("BarcodeList.com 查到 %s → %s", barcode, name)
                return {
                    'name': name if name else None,
                    'category': 'others',
                    'barcode': barcode,
                    'price_estimate': _estimate_price_from_db(name),
                }
    except Exception as e:
        logger.warning("BarcodeList.com 查询 %s 异常: %s", barcode, e)

    return None


def get_product_by_barcode(request):
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
    CartItem.objects.all().delete()
    return JsonResponse({'status': 'success', 'msg': '账单已重置'})


# 删除购物车中的单个商品（按条码或商品ID）
def remove_cart_item(request):
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
    now = now_local()
    today = now.date()

    # 只统计 SaleHistory 即可。
    # 它核销后会自动把商城订单拆解并存入 SaleHistory。
    line_total = ExpressionWrapper(
        F('price') * F('quantity'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    stats = SaleHistory.objects.filter(
        sale_date__date=today
    ).aggregate(
        total_money=Sum(line_total),
        total_num=Sum('quantity')  # 注意：这里用 Sum(quantity) 比 count() 更准
    )

    total_amount = float(stats['total_money'] or 0)
    # 如果统计的是卖出多少件货，用 Sum('quantity')；
    # 如果统计的是成交了多少笔单，用 .count()
    today_count = stats['total_num'] or 0

    return JsonResponse({
        'status': 'success',
        'total_amount': round(total_amount, 2),
        'today_count': int(today_count)
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
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
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
    barcode = request.GET.get('barcode')
    name = request.GET.get('name')
    price = request.GET.get('price')
    category = request.GET.get('category', 'others')  # 新增：分类参数，默认其他

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
                'category': category
            }
        )

        if not created:
            product.name = name
            product.price = price_value
            product.category = category  # 允许更新分类

        # 增加库存
        product.stock += stock
        product.save(update_fields=['name', 'price', 'stock', 'category'])

    return JsonResponse({
        'status': 'success',
        'is_new': created,
        'current_stock': product.stock
    })


def get_mall_products(request):
    cat = request.GET.get('category', 'all')
    search = request.GET.get('search', '').strip()

    # 基础查询：必须有库存
    query = Product.objects.filter(stock__gt=0)

    # 如果不是“全部”，则增加分类过滤条件
    if cat != 'all':
        query = query.filter(category=cat)

    # 名称搜索
    if search:
        query = query.filter(name__icontains=search)

    products = query.values('id', 'name', 'price', 'category', 'stock', 'create_time')
    # 按录入时间倒序（新品在前）
    products = products.order_by('-create_time')

    return JsonResponse({
        'status': 'success',
        'list': list(products)
    }, json_dumps_params={'ensure_ascii': False})


# 根据商品名称关键词自动分类（供管理员一键整理用）
# 参考文具行业标准分类体系：书写工具/本册纸品/学生文具/修正粘合/书籍/其他
CATEGORY_KEYWORDS = {
    'books': ['名著', '阅读', '作文', '语文', '英语', '数学', '教材', '练习册', '字典', '词典', '字帖', '绘本', '古诗词', '唐诗', '百科', '知识'],
    'pens': ['中性笔', '圆珠笔', '签字笔', '马克笔', '荧光笔', '水彩笔', '蜡笔', '彩笔', '画笔', '白板笔', '铅笔', '钢笔', '笔芯', '替芯', '墨水', '钢笔水'],
    'papers': ['笔记本', '作业本', '本子', '便签', '方格本', '稿纸', '纸', '打印纸', '复印纸', '活页', '线圈本', '胶套本', '文件袋', '档案袋', '资料册'],
    'stationery': ['橡皮', '擦', '尺', '圆规', '剪刀', '订书', '打孔', '笔袋', '文具盒', '书包', '削笔', '卷笔', '垫板', '美工刀', '切纸', '回形针', '长尾夹', '图钉'],
    'correction': ['修正', '涂改', '改正', '修正带', '修正液', '改正带', '固体胶', '胶水', '胶棒', '胶带', '胶擦', '双面胶'],
}

# 排除关键词：商品名称含这些词则跳过该分类（解决"订书机"含"书"误归名著）
CATEGORY_EXCLUDE = {
    'books': ['订', '装订', '封'],
}

@csrf_exempt
def auto_categorize_products(request):
    """一键自动分类：根据商品名称关键词分配分类"""
    from .models import Product

    count = 0
    for product in Product.objects.all():
        old_cat = product.category
        assigned = False
        for cat, keywords in CATEGORY_KEYWORDS.items():
            # 排除检查：如果商品名包含该分类的排除词，跳过
            exclude_words = CATEGORY_EXCLUDE.get(cat, [])
            if any(kw in product.name for kw in exclude_words):
                continue
            # 关键词匹配
            for kw in keywords:
                if kw in product.name:
                    if product.category != cat:
                        product.category = cat
                        product.save(update_fields=['category'])
                        count += 1
                    assigned = True
                    break
            if assigned:
                break

        # 如果所有分类都没匹配上，且原来的分类也不是 others，归入 others
        if not assigned and old_cat != 'others':
            product.category = 'others'
            product.save(update_fields=['category'])
            count += 1

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
    """一键部署示例商品数据到云端数据库（覆盖更新，确保分类正确）"""
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
        cart = data.get('cart') or []

        if not name:
            return JsonResponse({'status': 'fail', 'msg': '请输入取货人姓名'})
        if not cart:
            return JsonResponse({'status': 'fail', 'msg': '购物车不能为空'})

        with transaction.atomic():
            requested_items = {}
            for item in cart:
                product_id = int(item.get('id'))
                count = int(item.get('num', 0))
                if count <= 0:
                    return JsonResponse({'status': 'fail', 'msg': '商品数量必须大于0'})
                requested_items[product_id] = requested_items.get(product_id, 0) + count

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
    # 查询状态为 0 (待取货) 的订单数量
    count = Order.objects.filter(status=0).count()
    low_stock_count = Product.objects.filter(stock__lte=5).count()
    return JsonResponse({'count': count, 'low_stock_count': low_stock_count})


def get_pending_orders(request):
    limit = min(max(get_request_int(request.GET.get('limit'), 10), 1), 50)
    orders = Order.objects.filter(status=0).prefetch_related('items__product').order_by('create_time')[:limit]
    return JsonResponse({
        'status': 'success',
        'list': [serialize_order(order) for order in orders]
    }, json_dumps_params={'ensure_ascii': False})


def get_low_stock_products(request):
    threshold = min(max(get_request_int(request.GET.get('threshold'), 5), 0), 9999)
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


# 2. 确认取货核销接口
@csrf_exempt
def verify_order(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'fail', 'msg': '请使用POST请求'})

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'fail', 'msg': '请求数据格式不正确'})

    order_id = data.get('id')
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(id=order_id, status=0)
            locked_order_items = []
            # 扣库存逻辑（和你 admin.py 里写的一样）
            for item in order.items.select_related('product').all():
                product = Product.objects.select_for_update().get(pk=item.product_id)
                if product.stock < item.count:
                    return JsonResponse({
                        'status': 'fail',
                        'msg': f'{product.name} 库存不足，当前库存 {product.stock}，需要 {item.count}'
                    })
                locked_order_items.append((item, product))

            for item, product in locked_order_items:
                product.stock -= item.count
                product.save(update_fields=['stock'])
                # 存入销售历史
                SaleHistory.objects.create(
                    product_name=product.name,
                    price=product.price,
                    quantity=item.count
                )
            # 修改订单状态
            order.status = 1
            order.save(update_fields=['status'])
        return JsonResponse({'status': 'success'})
    except Order.DoesNotExist:
        return JsonResponse({'status': 'fail', 'msg': '未找到待取货订单'})
    except Exception as e:
        return JsonResponse({'status': 'fail', 'msg': str(e)})


# 仪表盘统计数据（供网页端下方图表使用）
def dashboard_stats(request):
    now = now_local()
    today = now.date()
    week_ago = today - timedelta(days=6)

    # 本日营收
    line_total = ExpressionWrapper(
        F('price') * F('quantity'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    today_stats = SaleHistory.objects.filter(
        sale_date__date=today
    ).aggregate(
        total=Sum(line_total),
        count=Sum('quantity')
    )
    today_revenue = float(today_stats['total'] or 0)
    today_count = int(today_stats['count'] or 0)

    # 最近7天销售趋势
    daily_revenue = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_stats = SaleHistory.objects.filter(
            sale_date__date=day
        ).aggregate(
            total=Sum(line_total)
        )
        daily_revenue.append({
            'date': day.strftime('%m/%d'),
            'total': float(day_stats['total'] or 0)
        })

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
        Product.objects.filter(stock__lte=5)
        .order_by('stock')[:10]
        .values('name', 'stock', 'price')
    )

    # 待处理订单
    pending_orders = Order.objects.filter(status=0).count()

    return JsonResponse({
        'today_revenue': round(today_revenue, 2),
        'today_count': today_count,
        'daily_revenue': daily_revenue,
        'top_products': top_products,
        'category_distribution': cat_counts,
        'low_stock': low_stock,
        'pending_orders': pending_orders,
    })


# 今日销售明细（点卡片弹窗用）
def today_detail(request):
    now = now_local()
    today = now.date()

    # 按商品分组
    line_total = ExpressionWrapper(
        F('price') * F('quantity'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    grouped = (SaleHistory.objects
        .filter(sale_date__date=today)
        .values('product_name')
        .annotate(
            total_qty=Sum('quantity'),
            total_amount=Sum(line_total),
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
    line_total = ExpressionWrapper(
        F('price') * F('quantity'),
        output_field=DecimalField(max_digits=12, decimal_places=2)
    )
    today_stats = SaleHistory.objects.filter(
        sale_date__date=today
    ).aggregate(
        total=Sum(line_total),
        count=Sum('quantity')
    )

    # 3. 待取货订单数 & 低库存数
    pending_count = Order.objects.filter(status=0).count()
    low_stock_count = Product.objects.filter(stock__lte=5).count()

    # 4. 待取货订单列表（前5条）
    orders = Order.objects.filter(status=0).prefetch_related('items__product').order_by('create_time')[:5]

    # 5. 低库存商品列表（前5条）
    low_stock = list(
        Product.objects.filter(stock__lte=5)
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
            'total_amount': round(float(today_stats['total'] or 0), 2),
            'today_count': int(today_stats['count'] or 0),
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


# 健康检查接口（用于部署后快速诊断）
def health_check(request):
    diagnostics = {
        'status': 'ok',
        'debug': settings.DEBUG,
        'database': 'unknown',
        'tables': {},
        'allowed_hosts': settings.ALLOWED_HOSTS,
    }

    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
            tables = [row[0] for row in cursor.fetchall()]
            diagnostics['tables']['all'] = tables

            # Check if auth_user table exists (required for admin login)
            has_auth_user = 'auth_user' in tables
            diagnostics['tables']['has_auth_user'] = has_auth_user
            if has_auth_user:
                cursor.execute("SELECT count(*) FROM auth_user")
                diagnostics['tables']['user_count'] = cursor.fetchone()[0]

        diagnostics['database'] = 'connected'
    except Exception as e:
        diagnostics['database'] = f'error: {e}'

    return JsonResponse(diagnostics)


def wechat_verify(request):
    """微信域名所有权验证（MP 验证文件）"""
    return HttpResponse('c7075ba1e65258ad0c0c1ecb9f9bc774021f57bc', content_type='text/plain; charset=utf-8')
