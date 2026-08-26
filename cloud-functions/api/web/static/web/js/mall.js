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
function fetchWithTimeout(url, options, timeoutMs) {
  options = options || {};
  timeoutMs = timeoutMs || 8000;
  if (window.AbortController) {
    var controller = new AbortController();
    var timer = setTimeout(function() { controller.abort(); }, timeoutMs);
    options.signal = controller.signal;
    return fetch(url, options).finally(function() { clearTimeout(timer); });
  }
  return fetch(url, options);
}
function apiGet(url) {
  return fetchWithTimeout(API_BASE + url, {}, 8000).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  });
}
function apiPost(url, data) {
  return fetchWithTimeout(API_BASE + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  }, 8000).then(function(r) {
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

// 商品图片加载失败时：隐藏图片，显示 emoji 占位
function onProductImgError(img) {
  img.style.display = 'none';
  var wrap = img.parentNode;
  if (img.dataset.bg) wrap.style.background = img.dataset.bg;
  var fb = wrap.querySelector('.emoji-fallback');
  if (fb) fb.style.display = 'flex';
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
            image_url: p.image_url || '',
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
      + '<div class="card-img-wrap" style="background:' + p.categoryColor + ';position:relative;overflow:hidden;">'
        + (p.image_url
          ? '<img src="' + escAttr(p.image_url) + '" alt="' + escAttr(p.name) + '" style="width:100%;height:100%;object-fit:cover;position:absolute;top:0;left:0;" onerror="onProductImgError(this)" data-bg="' + p.categoryColor + '">'
          : '')
        + '<span class="emoji-fallback" style="font-size:48px' + (p.image_url ? ';display:none' : '') + '">' + p.productEmoji + '</span>'
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

}

function escHtml(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
function escAttr(s) {
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
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
      image_url: product.image_url || '',
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
    item.image_url = latest.image_url || '';
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
// Order Query
// ============================================================
var queryOpen = false;
function openQuery() {
  queryOpen = true;
  document.getElementById('queryOverlay').className = 'overlay show';
  document.getElementById('queryPanel').className = 'modal-panel show';
  document.getElementById('queryNameInput').value = '';
  document.getElementById('queryResult').innerHTML = '';
  document.body.style.overflow = 'hidden';
  setTimeout(function() { document.getElementById('queryNameInput').focus(); }, 300);
}
function closeQuery() {
  queryOpen = false;
  document.getElementById('queryOverlay').className = 'overlay';
  document.getElementById('queryPanel').className = 'modal-panel';
  document.body.style.overflow = '';
}
function doQueryOrders() {
  var name = document.getElementById('queryNameInput').value.trim();
  if (!name) { showToast('请输入姓名', '👤'); return; }
  var el = document.getElementById('queryResult');
  el.innerHTML = '<div style="text-align:center;padding:20px 0;color:var(--text-secondary);"><div class="loading-spinner"></div><div style="margin-top:6px">查询中...</div></div>';
  apiGet('/api/query_orders/?name=' + encodeURIComponent(name))
    .then(function(data) {
      if (data.status === 'success' && data.list.length > 0) {
        var html = '<div style="font-size:13px;color:var(--text-secondary);margin-bottom:8px;">共 ' + data.list.length + ' 个待取货订单</div>';
        data.list.forEach(function(o) {
          html += '<div style="margin-bottom:12px;padding:12px;background:var(--bg);border-radius:8px;font-size:13px;">'
            + '<div style="display:flex;justify-content:space-between;font-weight:600;margin-bottom:4px;">'
            + '<span>#' + o.order_sn.slice(-8) + '</span>'
            + '<span style="color:#fa8c16">待取货</span></div>'
            + '<div style="color:var(--text-secondary);font-size:12px;">' + o.create_time + ' · ' + o.customer_name + '</div>';
          o.items.forEach(function(item) {
            html += '<div style="display:flex;justify-content:space-between;padding:2px 0;font-size:12px;">'
              + '<span>' + escHtml(item.name) + ' ×' + item.count + '</span>'
              + '<span style="color:#f5222d">¥' + (parseFloat(item.price) * item.count).toFixed(2) + '</span></div>';
          });
          html += '<div style="text-align:right;font-weight:700;font-size:14px;margin-top:4px;padding-top:4px;border-top:1px solid #eee;">合计: ¥' + o.total_price + '</div>';
          html += '</div>';
        });
        el.innerHTML = html;
      } else {
        el.innerHTML = '<div style="text-align:center;padding:20px 0;color:var(--text-secondary);">📭 未找到待取货订单<br><span style="font-size:12px;">请确认姓名与下单时填写的一致</span></div>';
      }
    })
    .catch(function() {
      el.innerHTML = '<div style="text-align:center;padding:20px 0;color:#f5222d;">⚠️ 查询失败，请检查网络后重试</div>';
    });
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
    if (searchTimer) clearTimeout(searchTimer); // 取消等待中的防抖
  });
  document.getElementById('searchInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      if (searchTimer) clearTimeout(searchTimer);
      state.searchKey = e.target.value.trim();
      if (state.searchKey) state.activeCat = 'all';
      renderCategories();
      fetchProducts();
    }
  });
  document.getElementById('searchInput').addEventListener('input', function(e) {
    document.getElementById('clearBtn').style.display = e.target.value ? '' : 'none';
  });
  // 搜索防抖：输入后 300ms 自动搜索（合并快速输入）
  var searchTimer = null;
  document.getElementById('searchInput').addEventListener('keyup', function(e) {
    if (e.key === 'Enter') return; // Enter 由 keydown 处理
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(function() {
      state.searchKey = document.getElementById('searchInput').value.trim();
      if (state.searchKey) state.activeCat = 'all';
      renderCategories();
      fetchProducts();
    }, 300);
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

  // Order Query
  // Share QR
  document.getElementById('shareBtn').addEventListener('click', function() {
    document.getElementById('shareOverlay').className = 'overlay show';
    document.getElementById('sharePanel').className = 'modal-panel success-modal show';
  });
  document.getElementById('shareOverlay').addEventListener('click', function() {
    document.getElementById('shareOverlay').className = 'overlay';
    document.getElementById('sharePanel').className = 'modal-panel success-modal';
  });
  document.getElementById('shareDoneBtn').addEventListener('click', function() {
    document.getElementById('shareOverlay').className = 'overlay';
    document.getElementById('sharePanel').className = 'modal-panel success-modal';
  });

  document.getElementById('orderQueryBtn').addEventListener('click', openQuery);
  document.getElementById('queryOverlay').addEventListener('click', closeQuery);
  document.getElementById('queryCloseBtn').addEventListener('click', closeQuery);
  document.getElementById('querySubmitBtn').addEventListener('click', doQueryOrders);
  document.getElementById('queryNameInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') doQueryOrders();
  });

  // Success
  document.getElementById('successDone').addEventListener('click', closeSuccess);
  document.getElementById('successOverlay').addEventListener('click', closeSuccess);

  // Event delegation for add-to-cart (只绑定一次, 不在 renderProducts 中重复绑定)
  document.getElementById('productGrid').addEventListener('click', function(e) {
    var btn = e.target.closest('.btn-add');
    if (!btn || btn.disabled) return;
    var card = btn.closest('.product-card');
    if (!card) return;
    var id = Number(card.dataset.id);
    var product = state.products.find(function(p) { return p.id === id; });
    if (product) addToCart(product);
  });

  renderCategories();
  updateCartBar();
  fetchProducts();

  // Periodic cart sync + 商品数据热刷新（图片/库存热插拔）
  setInterval(function() {
    if (state.products.length > 0) {
      syncCartWithProducts();
      refreshProductsSilent();
    }
  }, 15000);
}

// ============================================================
// 热插拔：静默刷新商品数据（图片/库存有变化时自动更新 UI）
// ============================================================
var _lastSilentRefresh = 0;
function refreshProductsSilent() {
  var now = Date.now();
  if (now - _lastSilentRefresh < 20000) return; // 至少间隔 20s
  _lastSilentRefresh = now;

  var cat = state.activeCat;
  var search = state.searchKey;
  apiGet('/api/mall_products/?category=' + encodeURIComponent(cat) + '&search=' + encodeURIComponent(search))
    .then(function(data) {
      if (!data || data.status !== 'success') return;
      var updated = (data.list || []).map(function(p) {
        return {
          id: p.id, name: p.name, price: String(p.price),
          stock: getProductStock(p), category: p.category,
          create_time: p.create_time, image_url: p.image_url || '',
          productEmoji: getProductEmoji(p.name),
          categoryColor: getCategoryColor(p.category)
        };
      });
      // 对比是否有变化（图片/库存/数量）
      var changed = updated.length !== state.products.length;
      if (!changed) {
        for (var i = 0; i < updated.length; i++) {
          var o = state.products[i];
          var n = updated[i];
          if (o.image_url !== n.image_url || o.stock !== n.stock || o.price !== n.price) {
            changed = true; break;
          }
        }
      }
      if (changed) {
        state.products = updated;
        renderProducts(updated);
        syncCartWithProducts();
      }
    })
    .catch(function() {}); // 静默失败，不干扰用户
}

document.addEventListener('DOMContentLoaded', init);

window.addEventListener('pageshow', function (e) {
  // ⚠️ 修复手机浏览器 bfcache 恢复时 body overflow 残留导致页面卡死
  document.body.style.overflow = '';
  if (e.persisted) {
    loadCart();
    updateCartBar();
    fetchProducts();
  }
});
