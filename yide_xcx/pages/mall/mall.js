// pages/mall/mall.js
Page({
  data: {
    showCartDetail: false, // 控制清单弹窗显示
    products: [],
    loading: true,
    activeCat: 'all',
    categories: [
      { id: 'all', name: '全部' },
      { id: 'books', name: '名著' },
      { id: 'pens', name: '笔类' },
      { id: 'erasers', name: '橡皮' }
    ],
    cart: [],         // 购物车列表
    totalPrice: "0.00",
    totalCount: 0
  },

  onLoad: function () {
    const isAdmin = wx.getStorageSync('is_admin');
    if (isAdmin === true) {
      wx.reLaunch({ url: '/pages/index/index' });
      return;
    }
    this.fetchData(this.data.activeCat);
    this.quietCheckIdentity();
  },

  onShow: function() {
    const cart = wx.getStorageSync('cart') || [];
    this.calculateTotal(cart);
  },

  fetchData: function (category) {
    this.setData({ loading: true });
    wx.request({
      url: 'http://192.168.1.138:8000/api/mall_products/',
      data: { category: category },
      success: (res) => {
        if (res.data && res.data.status === 'success') {
          this.setData({
            products: res.data.list,
            loading: false
          });
        } else {
          this.setData({ loading: false });
        }
      },
      fail: (err) => {
        this.setData({ loading: false });
        wx.showToast({ title: '服务器连接失败', icon: 'none' });
      }
    });
  },

  switchCat: function (e) {
    const catId = e.currentTarget.dataset.id;
    this.setData({ activeCat: catId });
    this.fetchData(catId);
  },

  // 1. 切换清单弹窗显示/隐藏
  toggleCartDetail: function() {
    if (this.data.totalCount > 0) {
      this.setData({ showCartDetail: !this.data.showCartDetail });
    }
  },

  // 2. 加入购物车 (主列表按钮)
  addToCart: function (e) {
    const product = e.currentTarget.dataset.item;
    let cart = this.data.cart;
    const index = cart.findIndex(v => v.id === product.id);
    
    if (index === -1) {
      cart.push({ ...product, num: 1 });
    } else {
      cart[index].num++;
    }
    this.calculateTotal(cart);
    wx.showToast({ title: '已加入', icon: 'success', duration: 800 });
  },

  // 3. 清单内加数量
  plusItem: function(e) {
    const id = e.currentTarget.dataset.id;
    let cart = this.data.cart;
    const index = cart.findIndex(v => v.id === id);
    if (index > -1) {
      cart[index].num++;
      this.calculateTotal(cart);
    }
  },

  // 4. 清单内减数量
  minusItem: function(e) {
    const id = e.currentTarget.dataset.id;
    let cart = this.data.cart;
    const index = cart.findIndex(v => v.id === id);
    if (index > -1) {
      if (cart[index].num > 1) {
        cart[index].num--;
      } else {
        cart.splice(index, 1); // 减到0则移除
      }
      this.calculateTotal(cart);
      // 如果减完了，自动收起清单
      if (cart.length === 0) {
        this.setData({ showCartDetail: false });
      }
    }
  },

  // 5. 清空购物车
  clearCart: function() {
    wx.showModal({
      title: '提示',
      content: '确定要清空购物车吗？',
      success: (res) => {
        if (res.confirm) {
          this.calculateTotal([]);
          this.setData({ showCartDetail: false });
          wx.showToast({ title: '已清空', icon: 'none' });
        }
      }
    });
  },

  calculateTotal: function (cart) {
    let totalPrice = 0;
    let totalCount = 0;
    cart.forEach(v => {
      totalPrice += v.num * v.price;
      totalCount += v.num;
    });
    this.setData({
      cart: cart,
      totalPrice: totalPrice.toFixed(2),
      totalCount: totalCount
    });
    wx.setStorageSync('cart', cart);
  },

  goToOrder: function() {
    wx.setStorageSync('cart', this.data.cart);
    wx.setStorageSync('totalPrice', this.data.totalPrice);
    wx.navigateTo({ url: '/pages/order/order' });
  },

  quietCheckIdentity: function () {
    wx.login({
      success: res => {
        wx.request({
          url: 'http://192.168.1.138:8000/api/check_role/',
          data: { code: res.code },
          success: (response) => {
            if (response.data.role === 'admin') {
              wx.setStorageSync('is_admin', true);
              wx.reLaunch({ url: '/pages/index/index' });
            } else {
              wx.setStorageSync('is_admin', false);
            }
          }
        });
      }
    });
  }
})