// pages/index/index.js
Page({
  data: {
    cart: [],
    todayTotal: "0.00",
    todayCount: 0,
    total: 0,
    lastOrderCount: 0, // 用于记录上次订单数，防止重复弹窗
    searchKey: '',
    pendingOrder: null
  },

  // 1. 页面加载：启动定时器
  onLoad: function () {
    this.fetchTodayStats(); // 初始化今日数据

    // 启动 2 秒轮询：同时拉取收银台购物车和商城新订单
    this.timer = setInterval(() => {
      this.fetchCart();
      this.checkMallOrders();
    }, 2000);
  },

  // 2. 获取扫码收银台的数据
  fetchCart: function () {
    wx.request({
      url: 'http://192.168.1.138:8000/get_cart_status/',
      success: (res) => {
        this.setData({
          cart: res.data.items || [],
          total: res.data.total || 0
        });
      },
      fail: () => { console.error("收银台连接失败"); }
    });
  },
  onSearchInput: function(e) {
    this.setData({ searchKey: e.detail.value });
  },
  
  // 搜索待取货订单
  searchOrder: function() {
    if (!this.data.searchKey) return;
    wx.request({
      url: 'http://192.168.1.138:8000/api/search_order/', 
      data: { key: this.data.searchKey },
      success: (res) => {
        if (res.data.status === 'success') {
          this.setData({ pendingOrder: res.data.order });
        } else {
          wx.showToast({ title: '未找到匹配订单', icon: 'none' });
          this.setData({ pendingOrder: null });
        }
      }
    });
  },
  
  // 一键核销（确认取货）
  verifyOrder: function(e) {
    const orderId = e.currentTarget.dataset.id;
    wx.showModal({
      title: '确认取货',
      content: '确认学生已付款并取走货品吗？',
      success: (sm) => {
        if (sm.confirm) {
          wx.request({
            url: 'http://192.168.1.138:8000/api/verify_order/',
            method: 'POST',
            data: { id: orderId },
            success: (res) => {
              if (res.data.status === 'success') {
                wx.showToast({ title: '核销成功', icon: 'success' });
                this.setData({ pendingOrder: null, searchKey: '' });
                this.fetchTodayStats(); // 刷新今日营收，因为这笔钱现在算进来了
              }
            }
          });
        }
      }
    });
  },

  // 3. 核心：检查商城新订单（待取货订单）
  checkMallOrders: function () {
    wx.request({
      url: 'http://192.168.1.138:8000/api/get_new_order_count/', // 需在后端写这个简单接口
      success: (res) => {
        // 如果后端返回的待处理订单数增加了
        if (res.data.count > this.data.lastOrderCount) {
          wx.vibrateLong(); // 震动提醒
          wx.showModal({
            title: '🎁 商城新订单',
            content: `收到 ${res.data.count} 个新订单，请注意准备货品！`,
            confirmText: '我知道了',
            showCancel: false
          });
          // 更新统计数据，让长辈看到最新的总额
          this.fetchTodayStats();
        }
        this.setData({ lastOrderCount: res.data.count });
      }
    });
  },

  // 4. 获取今日营收统计
  fetchTodayStats: function () {
    wx.request({
      url: 'http://192.168.1.138:8000/get_today_stats/',
      success: (res) => {
        if (res.data.status === 'success') {
          this.setData({
            total_amount: (res.data.total_amount || 0).toFixed(2),
            today_count: res.data.today_count || 0
          });
        }
      }
    });
  },

  // 5. 点击“收款完成”按钮（扫码结账）
  onFinish: function () {
    if (this.data.cart.length === 0) return;
    wx.showModal({
      title: '确认收款',
      content: '是否已收到款项？点击后将正式扣除库存。',
      success: (res) => {
        if (res.confirm) {
          wx.request({
            url: 'http://192.168.1.138:8000/checkout_cart/',
            success: (response) => {
              if (response.data.status === 'success') {
                this.setData({ cart: [], total: 0 });
                wx.showToast({ title: '已结账', icon: 'success' });
                this.fetchTodayStats();
              }
            }
          });
        }
      }
    });
  },

  // 6. 退出页面清理
  onUnload: function () {
    clearInterval(this.timer);
  },

  // 补充：下拉手动刷新
  onPullDownRefresh: function () {
    this.fetchTodayStats();
    wx.stopPullDownRefresh();
  }
});