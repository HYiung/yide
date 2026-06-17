const api = require('../../utils/api.js');

Page({
  data: {
    cart: [],
    totalPrice: '0.00',
    customerName: '',
    submitting: false
  },

  onLoad: function () {
    const cart = wx.getStorageSync('cart') || [];
    const totalPrice = wx.getStorageSync('totalPrice') || '0.00';

    if (!cart.length) {
      wx.showToast({ title: '购物车为空', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1000);
      return;
    }

    // 预计算小计（WXML不支持.toFixed()）
    const cartWithSubtotal = cart.map(item => ({
      ...item,
      subtotal: (Number(item.num) * Number(item.price)).toFixed(2)
    }));

    this.setData({ cart: cartWithSubtotal, totalPrice });
  },

  onNameInput: function (e) {
    this.setData({ customerName: e.detail.value });
  },

  submitOrder: function () {
    const { cart, customerName, totalPrice, submitting } = this.data;

    if (submitting) return;
    if (!cart.length) {
      wx.showToast({ title: '购物车为空', icon: 'none' });
      return;
    }
    if (!customerName.trim()) {
      wx.showToast({ title: '请输入取货人姓名', icon: 'none' });
      return;
    }

    this.setData({ submitting: true });

    api.request({
      url: '/api/submit_order/',
      method: 'POST',
      data: {
        name: customerName.trim(),
        cart: cart,
        total: totalPrice
      }
    }).then((data) => {
      this.setData({ submitting: false });
      if (data.status === 'success') {
        wx.showModal({
          title: '🎉 下单成功',
          content: `订单号：${data.order_sn || ''}\n请凭姓名到柜台核对并付款取货`,
          confirmText: '好的',
          confirmColor: '#07c160',
          showCancel: false,
          success: () => {
            wx.removeStorageSync('cart');
            wx.removeStorageSync('totalPrice');
            wx.reLaunch({ url: '/pages/mall/mall' });
          }
        });
      } else {
        wx.showToast({ title: data.msg || '提交失败', icon: 'none' });
      }
    }).catch((err) => {
      this.setData({ submitting: false });
      console.error('提交订单失败', err);
      wx.showToast({ title: '网络异常', icon: 'none' });
    });
  }
});