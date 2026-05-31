// pages/index/index.js
const api = require('../../utils/api.js');

Page({
  data: {
    cart: [],
    total_amount: '0.00',
    today_count: 0,
    total: '0.00',
    lastOrderCount: 0, // 用于记录上次订单数，防止重复弹窗
    searchKey: '',
    pendingOrder: null
  },

  onLoad: function () {
    this.refreshDashboard();
  },

  onShow: function () {
    this.refreshDashboard();
    this.startPolling();
  },

  onHide: function () {
    this.stopPolling();
  },

  // 退出页面清理
  onUnload: function () {
    this.stopPolling();
  },

  startPolling: function () {
    this.stopPolling();
    this.timer = setInterval(() => {
      this.refreshDashboard();
    }, 2000);
  },

  stopPolling: function () {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  },

  refreshDashboard: function () {
    this.fetchCart();
    this.fetchTodayStats();
    this.checkMallOrders();
  },

  // 获取扫码收银台的数据
  fetchCart: function () {
    api.request({ url: '/get_cart_status/' })
      .then((data) => {
        this.setData({
          cart: data.items || [],
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

  // 检查商城新订单（待取货订单）
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
        this.setData({ lastOrderCount: count });
      })
      .catch((err) => {
        console.error('检查商城订单失败', err);
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

  // 点击“收款完成”按钮（扫码结账）
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
              wx.showToast({ title: data.message || '结账失败', icon: 'none' });
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
