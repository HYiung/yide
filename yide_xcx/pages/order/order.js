Page({
  data: {
    cart: [],
    totalPrice: 0,
    customerName: ''
  },

  onLoad: function () {
    // 获取从商城页存入缓存的数据
    const cart = wx.getStorageSync('cart') || [];
    const totalPrice = wx.getStorageSync('totalPrice') || 0;
    this.setData({ cart, totalPrice });
  },

  onNameInput: function (e) {
    this.setData({ customerName: e.detail.value });
  },

  submitOrder: function () {
    const { cart, customerName, totalPrice } = this.data;

    if (!customerName.trim()) {
      wx.showToast({ title: '请输入取货人姓名', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '提交中...' });

    wx.request({
      url: 'http://192.168.1.138:8000/api/submit_order/', // 对应你 Django 的接口
      method: 'POST',
      data: {
        name: customerName,
        cart: cart,
        total: totalPrice
      },
      success: (res) => {
        wx.hideLoading();
        if (res.data.status === 'success') {
          wx.showModal({
            title: '下单成功',
            content: '请凭姓名到柜台核对并付款',
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
          wx.showToast({ title: res.data.msg || '提交失败', icon: 'none' });
        }
      },
      fail: () => {
        wx.hideLoading();
        wx.showToast({ title: '网络异常', icon: 'none' });
      }
    });
  }
})