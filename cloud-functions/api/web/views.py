import json
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Max, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import AdminUser, CartItem, Order, OrderItem, Product, SaleHistory

logger = logging.getLogger(__name__)


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
var scanCart = [];
var revenueChart = null, categoryChart = null;

var input = document.getElementById('barcode-input');
var pName = document.getElementById('p-name');
var pPrice = document.getElementById('p-price');
var logArea = document.getElementById('logArea');
var emptyLog = document.getElementById('emptyLog');

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

function fetchJSON(url) {
  return fetch(url).then(function (r) { return r.json(); });
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
  fetchJSON('/api/dashboard_stats/').then(function (d) {
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
  var url = (isCheckOnly ? '/get_product_by_barcode/?barcode=' : '/add_item/?barcode=') + encodeURIComponent(code);
  fetch(url).then(function (r) { return r.json(); }).then(function (d) {
    if (d.status === 'success') {
      var tag = isCheckOnly ? '<span class="tag">仅查价</span>' : '<span class="tag">已录入</span>';
      pName.innerHTML = d.name + ' ' + tag;
      pPrice.textContent = '￥' + d.price;
      speakText(d.name + '，' + d.price + '元');
      if (!isCheckOnly) {
        var el = emptyLog; if (el && el.parentNode) el.parentNode.removeChild(el);
        var t = new Date();
        var ts = t.getHours().toString().padStart(2,'0') + ':' + t.getMinutes().toString().padStart(2,'0') + ':' + t.getSeconds().toString().padStart(2,'0');
        var e = document.createElement('div'); e.className = 'log-entry';
        e.innerHTML = '<span class="log-time">' + ts + '</span><span class="log-name">' + d.name + '</span><span class="log-price">￥' + d.price + '</span>';
        logArea.insertBefore(e, logArea.firstChild);
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
    if (d.status === 'success') { pName.textContent = '等待扫码...'; pPrice.textContent = '-'; location.reload(); }
  });
}

function doCheckout() {
  speakText('正在处理结账');
  fetchJSON('/checkout_cart/').then(function (d) {
    if (d.status === 'success') {
      speakText('收款成功');
      pName.textContent = '✅ 结账完成'; pPrice.textContent = '-';
      updateStats(); loadDashboard();
      setTimeout(function () {
        pName.textContent = '等待扫码...';
        logArea.innerHTML = '<div class="empty-state">账单已结清，扫码开始新订单</div>';
        emptyLog = document.querySelector('.empty-state');
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

updateStats();
loadDashboard();
setInterval(updateStats, 5000);
setInterval(loadDashboard, 30000);
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

</body>
</html>"""

def cash_register(request):
    from django.http import HttpResponse
    return HttpResponse(CASHIER_HTML)


# API 接口：根据条码查商品
def get_product_by_barcode(request):
    barcode = request.GET.get('barcode')
    if not barcode:
        return JsonResponse({'status': 'fail', 'msg': '条码不能为空'})

    product = Product.objects.filter(barcode=barcode).first()
    if not product:
        return JsonResponse({'status': 'fail', 'msg': '未找到商品'})

    return JsonResponse({
        'status': 'success',
        'name': product.name,
        'price': str(product.price),  # Decimal 需要转字符串
        'stock': product.stock,
        'category': product.category  # 返回分类，让前端能回显
    })


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
            'category': i.product.category
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
    # 使用 Django 提供的 timezone.now()，它会自动处理 settings.py 里的时区
    now = timezone.now()
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
    now = timezone.now()
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
    now = timezone.now()
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
