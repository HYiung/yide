const api = require('../../utils/api.js');

Page({
  data: {
    barcode: '',
    name: '',
    price: '',
    stock: 1,
    currentStock: null,
    submitting: false
  },

  scanBarcode: function() {
    wx.scanCode({
      scanType: ['barCode', 'qrCode'], // 明确指定扫描条码和二维码
      success: (res) => {
        const code = (res.result || '').trim();
        console.log('扫码原始数据：', code);
        this.setData({
          barcode: code,
          name: '',
          price: '',
          stock: 1,
          currentStock: null
        });
        if (code) {
          this.checkOldProduct(code);
        }
      },
      fail: (err) => {
        console.error('扫码失败', err);
        wx.showToast({ title: '扫码失败', icon: 'none' });
      }
    });
  },

  // 检查是否是库里已有的商品
  checkOldProduct: function(code) {
    api.request({
      url: '/get_product_by_barcode/',
      data: { barcode: code }
    }).then((data) => {
      if (data.status === 'success') {
        this.setData({
          name: data.name,
          price: data.price,
          currentStock: data.stock
        });
        wx.showToast({ title: '匹配到旧商品', icon: 'none' });
      } else {
        wx.showToast({ title: '新商品，请录入信息', icon: 'none' });
      }
    }).catch((err) => {
      console.error('查找商品失败', err);
      wx.showToast({ title: '查找失败，请检查网络', icon: 'none' });
    });
  },

  submitData: function() {
    if (this.data.submitting) return;

    const barcode = (this.data.barcode || '').trim();
    const name = (this.data.name || '').trim();
    const price = Number(this.data.price);
    const stock = Number(this.data.stock);

    if (!barcode) {
      wx.showToast({ title: '请先扫码', icon: 'none' });
      return;
    }
    if (!name || !Number.isFinite(price)) {
      wx.showToast({ title: '请填写商品名称和单价', icon: 'none' });
      return;
    }
    if (price < 0) {
      wx.showToast({ title: '单价不能为负数', icon: 'none' });
      return;
    }
    if (!Number.isInteger(stock) || stock <= 0) {
      wx.showToast({ title: '入库数量必须为正整数', icon: 'none' });
      return;
    }

    this.setData({ submitting: true });
    wx.showLoading({ title: '入库中...' });
    api.request({
      url: '/quick_add_product/',
      data: {
        barcode: barcode,
        name: name,
        price: price.toFixed(2),
        stock: stock
      }
    }).then((data) => {
      wx.hideLoading();
      this.setData({ submitting: false });
      if (data.status === 'success') {
        wx.showModal({
          title: '入库成功',
          content: `当前总库存：${data.current_stock}`,
          showCancel: false,
          success: () => {
            this.setData({ barcode: '', name: '', price: '', stock: 1, currentStock: null });
          }
        });
      } else {
        wx.showToast({ title: data.msg || '入库失败', icon: 'none' });
      }
    }).catch((err) => {
      wx.hideLoading();
      this.setData({ submitting: false });
      console.error('入库失败', err);
      wx.showToast({ title: '入库失败，请检查网络', icon: 'none' });
    });
  }
});
