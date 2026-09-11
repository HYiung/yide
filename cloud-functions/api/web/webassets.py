"""网页端 CSS / JS 资源（内嵌在 Python 模块里）。

⚠️ 为什么不像常规项目那样放在 static/ 目录？
EdgeOne Pages 打包函数代码时只带上 `.py` 文件，`web/static/` 下的 css/js 会被剥离
（线上执行 finders.find('web/css/mall.css') 得到 None），于是商城首页和店长登录页
拿不到样式和脚本，页面直接白屏。把资源内容内嵌进 Python 模块随代码一起部署，再由
Django 视图负责输出，就能绕开这个限制 —— 和 views.py 里把 HTML 内联是同一个原因。

⚠️ 修改样式 / 脚本请直接编辑本文件下方的常量，本文件就是唯一来源。
原来的 static/web/{css,js}/* 已删除，以免出现「改了文件线上却不生效」的错觉。
"""
import hashlib

MALL_CSS = """* { margin: 0; padding: 0; box-sizing: border-box; }
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
  .header-btn-group {
    position: absolute;
    right: 14px;
    top: 50%;
    transform: translateY(-50%);
    display: flex;
    gap: 4px;
  }
  .header-btn {
    font-size: 16px;
    text-decoration: none;
    opacity: 0.55;
    color: #fff;
    padding: 6px;
    border-radius: 8px;
    transition: opacity 0.2s;
    cursor: pointer;
    background: none;
    border: none;
    line-height: 1;
  }
  .header-btn:hover { opacity: 1; }

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
"""

CASHIER_CSS = """* { margin: 0; padding: 0; box-sizing: border-box; }
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
"""

CASHIER_LOGIN_CSS = """* { margin: 0; padding: 0; box-sizing: border-box; }
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
"""

MALL_JS = """// ============================================================
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
"""

CASHIER_JS = """var isCheckOnly = false;
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
  if (/^\\\\d{18}$/.test(code) && (code.startsWith('13') || code.startsWith('28'))) {
    doCheckout(); input.value = ''; return;
  }
  processBarcode(code);
});

/* ===== Modal Functions ===== */
function openModal(title) {
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalBody').innerHTML = '<div class="modal-loading">\\u52a0\\u8f7d\\u4e2d...</div>';
  document.getElementById('modalOverlay').classList.add('show');
}
function closeModal(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('modalOverlay').classList.remove('show');
}
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeModal(); });

/* Today Revenue Detail */
function showTodayDetail() {
  openModal('\\U0001F4B0 \\u4eca\\u65e5\\u9500\\u552e\\u660e\\u7ec6');
  fetchJSON('/api/today_detail/').then(function (d) {
    if (!d.grouped || !d.grouped.length) {
      document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\\u4eca\\u65e5\\u6682\\u65e0\\u9500\\u552e\\u8bb0\\u5f55</div>';
      return;
    }
    var html = '<table class="modal-table"><tr><th>\\u5546\\u54c1</th><th style="text-align:center">\\u6570\\u91cf</th><th style="text-align:right">\\u5c0f\\u8ba1</th><th style="text-align:right">\\u65f6\\u95f4</th></tr>';
    d.grouped.forEach(function (g) {
      html += '<tr><td>' + g.name + '</td><td class="num" style="text-align:center">\\u00d7' + g.qty + '</td><td class="money" style="text-align:right">\\uffe5' + g.amount.toFixed(2) + '</td><td class="time" style="text-align:right">' + g.last_time + '</td></tr>';
    });
    html += '</table>';
    html += '<div class="modal-footer"><span>\\u5408\\u8ba1 ' + d.total_count + ' \\u4ef6</span><span style="color:#f5222d">\\uffe5' + d.total_revenue.toFixed(2) + '</span></div>';
    document.getElementById('modalBody').innerHTML = html;
  }).catch(function () {
    document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\\u52a0\\u8f7d\\u5931\\u8d25</div>';
  });
}

/* Pending Orders Detail */
function showPendingOrders() {
  openModal('\\U0001F4CB \\u5f85\\u53d6\\u8d27\\u8ba2\\u5355');
  fetchJSON('/api/pending_orders/').then(function (d) {
    if (!d.list || !d.list.length) {
      document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\\u2705 \\u6682\\u65e0\\u5f85\\u53d6\\u8d27\\u8ba2\\u5355</div>';
      return;
    }
    var html = '';
    d.list.forEach(function (o) {
      html += '<div style="margin-bottom:16px;padding:12px;background:#fafafa;border-radius:8px;">';
      html += '<div style="display:flex;justify-content:space-between;font-weight:700;font-size:13px;"><span>#' + o.order_sn.slice(-8) + '</span><span style="color:#fa8c16">\\u5f85\\u53d6\\u8d27</span></div>';
      html += '<div style="margin:4px 0;font-size:13px;color:#666;">\\u53d6\\u8d27\\u4eba: ' + o.customer_name + '</div>';
      html += '<div style="font-size:12px;color:#999;margin-bottom:4px;">\\u5546\\u54c1:</div>';
      o.items.forEach(function (item) {
        html += '<div style="display:flex;justify-content:space-between;font-size:12px;padding:2px 0;"><span>' + item.name + ' \\u00d7' + item.count + '</span><span style="color:#f5222d">\\uffe5' + (parseFloat(item.price) * item.count).toFixed(2) + '</span></div>';
      });
      html += '<div style="text-align:right;font-weight:700;font-size:13px;margin-top:4px;padding-top:4px;border-top:1px solid #eee;">\\u5408\\u8ba1: \\uffe5' + o.total_price + '</div>';
      html += '</div>';
    });
    document.getElementById('modalBody').innerHTML = html;
  }).catch(function () {
    document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\\u52a0\\u8f7d\\u5931\\u8d25</div>';
  });
}

/* Low Stock Detail */
function showLowStock() {
  openModal('\\u26a0\\ufe0f \\u4f4e\\u5e93\\u5b58\\u5546\\u54c1');
  fetchJSON('/api/low_stock_products/?threshold=5&limit=100').then(function (d) {
    if (!d.list || !d.list.length) {
      document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\\u2705 \\u5e93\\u5b58\\u5145\\u8db3</div>';
      return;
    }
    var html = '<table class="modal-table"><tr><th>\\u5546\\u54c1</th><th style="text-align:right">\\u5e93\\u5b58</th><th style="text-align:right">\\u4ef7\\u683c</th></tr>';
    d.list.forEach(function (p) {
      var color = p.stock <= 0 ? '#f5222d' : p.stock <= 3 ? '#fa8c16' : '#52c41a';
      html += '<tr><td>' + p.name + '</td><td style="text-align:right;color:' + color + ';font-weight:700;">' + p.stock + '</td><td class="money" style="text-align:right">\\uffe5' + p.price + '</td></tr>';
    });
    html += '</table>';
    html += '<div class="modal-footer"><span>\\u5171 ' + d.total_count + ' \\u4e2a\\u5546\\u54c1\\u4f4e\\u5e93\\u5b58</span></div>';
    document.getElementById('modalBody').innerHTML = html;
  }).catch(function () {
    document.getElementById('modalBody').innerHTML = '<div class="modal-empty">\\u52a0\\u8f7d\\u5931\\u8d25</div>';
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
"""

CASHIER_LOGIN_JS = """if (document.body.dataset.loginError === 'true') {
  document.getElementById('errorMsg').textContent = '密码错误，请重试';
  document.getElementById('errorMsg').className = 'login-error show';
}
document.getElementById('passwordInput').focus();
"""


# 所有资源按内容算一个版本号，页面引用时带上 ?v= ，
# 内容一变 URL 就变，浏览器可以放心长期缓存。
def _compute_version():
    digest = hashlib.sha256()
    for _content, _ctype in ASSETS.values():
        digest.update(_content.encode('utf-8'))
        digest.update(_ctype.encode('utf-8'))
    return digest.hexdigest()[:12]


# 相对 /assets/ 的路径 -> (内容, Content-Type)
ASSETS = {
    'web/css/mall.css': (MALL_CSS, 'text/css; charset=utf-8'),
    'web/css/cashier.css': (CASHIER_CSS, 'text/css; charset=utf-8'),
    'web/css/cashier-login.css': (CASHIER_LOGIN_CSS, 'text/css; charset=utf-8'),
    'web/js/mall.js': (MALL_JS, 'application/javascript; charset=utf-8'),
    'web/js/cashier.js': (CASHIER_JS, 'application/javascript; charset=utf-8'),
    'web/js/cashier-login.js': (CASHIER_LOGIN_JS, 'application/javascript; charset=utf-8'),
}

VERSION = _compute_version()


def url(path):
    """返回带版本号的资源 URL，例如 /assets/web/css/mall.css?v=ab12cd34ef56"""
    return '/assets/%s?v=%s' % (path, VERSION)
