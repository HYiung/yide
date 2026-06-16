const api = require('../../utils/api.js');

Page({
  data: {
    cart: [],
    totalPrice: '0.00',
    customerName: '',
    submitting: false
  },

  onLoad: function () {
    // 获取从商城页存入缓存的数据
    const cart = wx.getStorageSync('cart') || [];
    const totalPrice = wx.getStorageSync('totalPrice') || '0.00';
    this.setData({ cart, totalPrice });
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
    wx.showLoading({ title: '提交中...' });

    api.request({
      url: '/api/submit_order/',
      method: 'POST',
      data: {
        name: customerName.trim(),
        cart: cart,
        total: totalPrice
      }
    }).then((data) => {
      wx.hideLoading();
      this.setData({ submitting: false });
      if (data.status === 'success') {
        wx.showModal({
          title: '下单成功',
          content: `订单号：${data.order_sn || ''}\n请凭姓名到柜台核对并付款`,
          showCancel: false,
          success: () => {
            // 提交成功后，彻底清理购物车缓存
            wx.removeStorageSync('cart');
            wx.removeStorageSync('totalPrice');
            // 跳转回商城或首页
            wx.reLaunch({ url: '/pages/mall/mall' });
          }
        });
      } else {
        wx.showToast({ title: data.msg || '提交失败', icon: 'none' });
      }
    }).catch((err) => {
      wx.hideLoading();
      this.setData({ submitting: false });
      console.error('提交订单失败', err);
      wx.showToast({ title: '网络异常', icon: 'none' });
    });
  }
});
