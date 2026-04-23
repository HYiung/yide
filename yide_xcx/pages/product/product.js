Page({
  data: {
    barcode: '',
    name: '',
    price: '',
    stock: 1
  },

  scanBarcode: function() {
    wx.scanCode({
      scanType: ['barCode', 'qrCode'], // 👈 明确指定扫描条码和二维码
      success: (res) => {
        // 这里的 res.result 就是扫出来的原始字符串
        console.log("扫码原始数据：", res.result);
        this.setData({ barcode: res.result });
        this.checkOldProduct(res.result);
      },
      fail: (err) => {
        console.error("扫码失败", err);
      }
    });
  },

  // 检查是否是库里已有的商品
  checkOldProduct: function(code) {
    wx.request({
      url: 'http://192.168.1.138:8000/get_product_by_barcode/', // 换成你的服务器IP
      data: { barcode: code },
      success: (res) => {
        if (res.data.status === 'success') {
          this.setData({
            name: res.data.name,
            price: res.data.price
          });
          wx.showToast({ title: '匹配到旧商品', icon: 'none' });
        }
      }
    });
  },

  submitData: function() {
    if (!this.data.name || !this.data.price) {
      wx.showToast({ title: '请填写完整', icon: 'error' });
      return;
    }
    wx.request({
      url: 'http://192.168.1.138:8000/quick_add_product/',
      data: {
        barcode: this.data.barcode,
        name: this.data.name,
        price: this.data.price,
        stock: this.data.stock
      },
      success: (res) => {
        if (res.data.status === 'success') {
          wx.showModal({
            title: '入库成功',
            content: `当前总库存：${res.data.current_stock}`,
            showCancel: false,
            success: () => {
              this.setData({ barcode: '', name: '', price: '', stock: 1 });
            }
          });
        }
      }
    });
  }
});