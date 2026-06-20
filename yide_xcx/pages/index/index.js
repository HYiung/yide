// pages/index/index.js
const api = require('../../utils/api.js');

// 分类对应的 emoji
const CATEGORY_EMOJI = {
  books: '📚',
  pens: '🖊️',
  papers: '📓',
  stationery: '📐',
  correction: '📦',
  others: '📎'
};
const DEFAULT_EMOJI = '📎';

Page({
  data: {
    cart: [],
    total_amount: '0.00',
    today_count: 0,
    total: '0.00',
    lastOrderCount: 0,
    searchKey: '',
    pendingOrder: null,
    pendingOrders: [],
    lowStockProducts: [],
    lowStockCount: 0,
    activeTab: 'orders',   // 'orders' | 'lowstock'
    _autoSwitched: false,
    _roleReady: false       // 身份确认后才渲染页面
  },

  onLoad: function () {
    // 立即检查身份，顾客跳转到线上商城 H5
    const isAdmin = wx.getStorageSync('is_admin');
    if (isAdmin === false) {
      this._showCustomerPrompt();
      return;
    }
    // 身份还未确认时（undefined），显示 loading 不渲染内容
    if (isAdmin === undefined || isAdmin === '') {
      return;
    }
    // 身份确认是店主，继续加载
    this._initPage();
  },

  onShow: function () {
    const isAdmin = wx.getStorageSync('is_admin');
    if (isAdmin === false) {
      this._showCustomerPrompt();
      return;
    }
    if (isAdmin === undefined || isAdmin === '') {
      return; // 等 checkRole 完成
    }
    if (!this.data._roleReady) {
      this._initPage();
    }
    this.refreshDashboard();
    this.startPolling();
  },

  _showCustomerPrompt: function () {
    // 顾客请使用线上商城 H5
    if (this._promptShown) return;
    this._promptShown = true;
    wx.showModal({
      title: '📱 线上商城已升级',
      content: '请在浏览器中打开 yide.dpdns.org 浏览商品并下单，无需使用小程序。',
      confirmText: '知道了',
      showCancel: false,
      success: () => {
        // 提示后留在空白页（小程序无可用页面）
      }
    });
  },

  _initPage: function () {
    this.setData({ _roleReady: true });
    this.refreshDashboard();
    // 等数据加载完再决定默认切到哪个tab（仅首次）
    setTimeout(() => this.autoSwitchOnce(), 500);
  },

  onHide: function () {
    this.stopPolling();
  },

  onUnload: function () {
    this.stopPolling();
  },

  startPolling: function () {
    this.stopPolling();
    this.timer = setInterval(() => {
      this.refreshDashboard();
    }, 5000);  // 从 2s 改为 5s，减少请求频率
  },

  stopPolling: function () {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  },

  refreshDashboard: function () {
    // 使用合并接口，1 个请求替代原来的 5 个，大幅降低延迟
    api.request({ url: '/api/dashboard_all/' })
      .then((data) => {
        if (data.status !== 'success') {
          // 降级：逐个请求
          this._fallbackRefresh();
          return;
        }

        // 1. 购物车
        const cart = (data.cart?.items || []).map(item => ({
          ...item,
          emoji: this.getEmoji(item.category),
          subtotal: (parseFloat(item.price) * item.quantity).toFixed(2)
        }));
        this.setData({
          cart: cart,
          total: data.cart?.total || '0.00'
        });

        // 2. 今日营收
        if (data.today_stats) {
          this.setData({
            total_amount: (Number(data.today_stats.total_amount) || 0).toFixed(2),
            today_count: data.today_stats.today_count || 0
          });
        }

        // 3. 商城新订单提醒
        const count = Number(data.new_order?.count || 0);
        if (count > this.data.lastOrderCount) {
          wx.vibrateLong();
          wx.showModal({
            title: '🎁 商城新订单',
            content: `收到 ${count} 个新订单，请注意准备货品！`,
            confirmText: '我知道了',
            showCancel: false
          });
        }
        this.setData({
          lastOrderCount: count,
          lowStockCount: Number(data.new_order?.low_stock_count || 0)
        });

        // 4. 待取货订单
        if (data.pending_orders) {
          this.setData({ pendingOrders: data.pending_orders.list || [] });
        }

        // 5. 低库存商品
        if (data.low_stock) {
          const lowList = (data.low_stock.list || []).map(item => ({
            ...item,
            emoji: this.getEmoji(item.category)
          }));
          this.setData({
            lowStockProducts: lowList,
            lowStockCount: Number(data.low_stock.total_count || 0)
          });
        }
      })
      .catch((err) => {
        console.error('综合看板加载失败，降级为逐个请求', err);
        this._fallbackRefresh();
      });
  },

  // 降级方案：分别请求各接口（原 refreshDashboard 逻辑）
  _fallbackRefresh: function () {
    this.fetchCart();
    this.fetchTodayStats();
    this.checkMallOrders();
    this.fetchPendingOrders();
    this.fetchLowStockProducts();
  },

  // 首次加载完成后，自动切到有内容tab（仅执行一次）
  autoSwitchOnce: function () {
    if (this.data._autoSwitched) return;
    const { pendingOrders, lowStockProducts } = this.data;
    if (pendingOrders.length === 0 && lowStockProducts.length > 0) {
      this.setData({ activeTab: 'lowstock' });
    }
    this.data._autoSwitched = true;
  },

  // 标签切换
  switchTab: function (e) {
    const tab = e.currentTarget.dataset.tab;
    this.setData({ activeTab: tab });
  },

  // 分类 → emoji
  getEmoji: function (category) {
    return CATEGORY_EMOJI[category] || DEFAULT_EMOJI;
  },

  // 获取购物车
  fetchCart: function () {
    api.request({ url: '/get_cart_status/' })
      .then((data) => {
        const items = (data.items || []).map(item => ({
          ...item,
          emoji: this.getEmoji(item.category),
          subtotal: (parseFloat(item.price) * item.quantity).toFixed(2)
        }));
        this.setData({
          cart: items,
          total: data.total || '0.00'
        });
      })
      .catch((err) => {
        console.error('收银台连接失败', err);
      });
  },

  onSearchInput: function(e) {
    this.setData({ searchKey: e.detail.value });
  },

  // 搜索待取货订单
  searchOrder: function() {
    const key = (this.data.searchKey || '').trim();
    if (!key) {
      wx.showToast({ title: '请输入姓名或单号', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '搜索中...' });
    api.request({
      url: '/api/search_order/',
      data: { key }
    }).then((data) => {
      wx.hideLoading();
      if (data.status === 'success') {
        this.setData({ pendingOrder: data.order });
      } else {
        wx.showToast({ title: data.msg || '未找到匹配订单', icon: 'none' });
        this.setData({ pendingOrder: null });
      }
    }).catch((err) => {
      wx.hideLoading();
      console.error('搜索订单失败', err);
      wx.showToast({ title: '搜索失败，请检查网络', icon: 'none' });
    });
  },

  // 一键核销（确认取货）
  verifyOrder: function(e) {
    const orderId = e.currentTarget.dataset.id;
    wx.showModal({
      title: '确认取货',
      content: '确认学生已付款并取走货品吗？',
      success: (sm) => {
        if (!sm.confirm) return;

        wx.showLoading({ title: '核销中...' });
        api.request({
          url: '/api/verify_order/',
          method: 'POST',
          data: { id: orderId }
        }).then((data) => {
          wx.hideLoading();
          if (data.status === 'success') {
            wx.showToast({ title: '核销成功', icon: 'success' });
            this.setData({ pendingOrder: null, searchKey: '' });
            this.refreshDashboard();
          } else {
            wx.showToast({ title: data.msg || '核销失败', icon: 'none' });
          }
        }).catch((err) => {
          wx.hideLoading();
          console.error('核销失败', err);
          wx.showToast({ title: '核销失败，请检查网络', icon: 'none' });
        });
      }
    });
  },

  // 检查商城新订单
  checkMallOrders: function () {
    api.request({ url: '/api/get_new_order_count/' })
      .then((data) => {
        const count = Number(data.count || 0);
        if (count > this.data.lastOrderCount) {
          wx.vibrateLong();
          wx.showModal({
            title: '🎁 商城新订单',
            content: `收到 ${count} 个新订单，请注意准备货品！`,
            confirmText: '我知道了',
            showCancel: false
          });
        }
        this.setData({
          lastOrderCount: count,
          lowStockCount: Number(data.low_stock_count || 0)
        });
      })
      .catch((err) => {
        console.error('检查商城订单失败', err);
      });
  },

  // 获取待取货订单列表
  fetchPendingOrders: function () {
    api.request({
      url: '/api/pending_orders/',
      data: { limit: 5 }
    }).then((data) => {
      if (data.status === 'success') {
        this.setData({ pendingOrders: data.list || [] });
      }
    }).catch((err) => {
      console.error('获取待取货订单失败', err);
    });
  },

  // 获取低库存商品
  fetchLowStockProducts: function () {
    api.request({
      url: '/api/low_stock_products/',
      data: { threshold: 5, limit: 5 }
    }).then((data) => {
      if (data.status === 'success') {
        const list = (data.list || []).map(item => ({
          ...item,
          emoji: this.getEmoji(item.category)
        }));
        this.setData({
          lowStockProducts: list,
          lowStockCount: Number(data.total_count || 0)
        });
      }
    }).catch((err) => {
      console.error('获取低库存商品失败', err);
    });
  },

  // 获取今日营收统计
  fetchTodayStats: function () {
    api.request({ url: '/get_today_stats/' })
      .then((data) => {
        if (data.status === 'success') {
          this.setData({
            total_amount: (Number(data.total_amount) || 0).toFixed(2),
            today_count: data.today_count || 0
          });
        }
      })
      .catch((err) => {
        console.error('获取今日营收失败', err);
      });
  },

  // 增加数量
  onIncrement: function (e) {
    const productId = e.currentTarget.dataset.id;
    const item = this.data.cart.find(v => v.id === productId);
    if (!item) return;

    if (item.quantity >= item.remaining_stock) {
      wx.showToast({ title: `库存仅剩 ${item.remaining_stock} 件`, icon: 'none' });
      return;
    }

    wx.showLoading({ title: '更新中...' });
    api.request({
      url: '/update_cart_item/',
      data: { product_id: productId, quantity: item.quantity + 1 }
    }).then((data) => {
      wx.hideLoading();
      if (data.status === 'success') {
        this.refreshDashboard();
      } else {
        wx.showToast({ title: data.msg || '操作失败', icon: 'none' });
      }
    }).catch(() => {
      wx.hideLoading();
      wx.showToast({ title: '网络异常', icon: 'none' });
    });
  },

  // 减少数量
  onDecrement: function (e) {
    const productId = e.currentTarget.dataset.id;
    const item = this.data.cart.find(v => v.id === productId);
    if (!item) return;

    if (item.quantity <= 1) {
      this.removeSingleItem(productId);
      return;
    }

    wx.showLoading({ title: '更新中...' });
    api.request({
      url: '/update_cart_item/',
      data: { product_id: productId, quantity: item.quantity - 1 }
    }).then((data) => {
      wx.hideLoading();
      if (data.status === 'success') {
        this.refreshDashboard();
      } else {
        wx.showToast({ title: data.msg || '操作失败', icon: 'none' });
      }
    }).catch(() => {
      wx.hideLoading();
      wx.showToast({ title: '网络异常', icon: 'none' });
    });
  },

  // 删除单个商品
  onRemoveItem: function (e) {
    const productId = e.currentTarget.dataset.id;
    wx.showModal({
      title: '移除商品',
      content: '确定移除此商品吗？',
      success: (res) => {
        if (res.confirm) {
          this.removeSingleItem(productId);
        }
      }
    });
  },

  removeSingleItem: function (productId) {
    wx.showLoading({ title: '移除中...' });
    api.request({
      url: '/remove_cart_item/',
      data: { product_id: productId }
    }).then((data) => {
      wx.hideLoading();
      if (data.status === 'success') {
        wx.showToast({ title: '已移除', icon: 'success' });
        this.refreshDashboard();
      } else {
        wx.showToast({ title: data.msg || '移除失败', icon: 'none' });
      }
    }).catch(() => {
      wx.hideLoading();
      wx.showToast({ title: '网络异常', icon: 'none' });
    });
  },

  // 清空购物车（不扣库存）
  onResetCart: function () {
    if (this.data.cart.length === 0) {
      wx.showToast({ title: '当前账单为空', icon: 'none' });
      return;
    }

    wx.showModal({
      title: '确认清空',
      content: '确定要清空当前账单吗？（此操作不会扣除库存）',
      success: (res) => {
        if (!res.confirm) return;

        wx.showLoading({ title: '清空中...' });
        api.request({ url: '/reset_cart/' })
          .then((data) => {
            wx.hideLoading();
            if (data.status === 'success') {
              this.setData({ cart: [], total: '0.00' });
              wx.showToast({ title: '已清空', icon: 'success' });
              this.refreshDashboard();
            } else {
              wx.showToast({ title: data.msg || '清空失败', icon: 'none' });
            }
          })
          .catch(() => {
            wx.hideLoading();
            wx.showToast({ title: '清空失败，请检查网络', icon: 'none' });
          });
      }
    });
  },

  // 收款完成
  onFinish: function () {
    if (this.data.cart.length === 0) {
      wx.showToast({ title: '当前账单为空', icon: 'none' });
      return;
    }

    wx.showModal({
      title: '确认收款',
      content: '是否已收到款项？点击后将正式扣除库存。',
      success: (res) => {
        if (!res.confirm) return;

        wx.showLoading({ title: '结账中...' });
        api.request({ url: '/checkout_cart/' })
          .then((data) => {
            wx.hideLoading();
            if (data.status === 'success') {
              this.setData({ cart: [], total: '0.00' });
              wx.showToast({ title: '已结账', icon: 'success' });
              this.refreshDashboard();
            } else {
              wx.showToast({ title: data.msg || '结账失败', icon: 'none' });
            }
          })
          .catch((err) => {
            wx.hideLoading();
            console.error('结账失败', err);
            wx.showToast({ title: '结账失败，请检查网络', icon: 'none' });
          });
      }
    });
  },

  // 下拉手动刷新
  onPullDownRefresh: function () {
    this.refreshDashboard();
    wx.stopPullDownRefresh();
  }
});
