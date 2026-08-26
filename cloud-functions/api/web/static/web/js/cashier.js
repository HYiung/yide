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
      var price = d.price || d.price_estimate || '';
      pName.innerHTML = d.name + ' ' + tag;
      pPrice.textContent = price ? ('￥' + price) : ('（无定价）');
      speakText(d.name + '，' + (price || '待定价') + '元');
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
  if (/^\\d{18}$/.test(code) && (code.startsWith('13') || code.startsWith('28'))) {
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
  e.innerHTML = '<span class="log-time">' + ts + '</span><span class="log-name">' + (item.name || '').replace(/</g,'&lt;').replace(/>/g,'&gt;') + qty + '</span><span class="log-price">￥' + item.price + sub + '</span>';
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

window.addEventListener('pageshow', function (e) {
  // ⚠️ 修复手机浏览器 bfcache 恢复时 body overflow 残留导致页面卡死
  document.body.style.overflow = '';
  if (e.persisted) { updateStats(); loadDashboard(); initCartSummary(); }
});
