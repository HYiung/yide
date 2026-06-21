const api = require('../../utils/api.js');

Page({
  data: {
    barcode: '',
    name: '',
    price: '',
    stock: 1,
    category: 'others',
    currentStock: null,
    submitting: false,
    // AI 识别状态
    aiLoading: false,
    imagePreview: '',
    aiStatus: ''       // 持久状态文本（AI识别结果/错误信息）
  },

  selectCategory: function(e) {
    this.setData({ category: e.currentTarget.dataset.cat });
  },

  onShow: function () {
    // 顾客请使用线上商城 H5，进货录入是店主用的
    const isAdmin = wx.getStorageSync('is_admin');
    if (isAdmin === false) {
      wx.showModal({
        title: '📱 线上商城已升级',
        content: '请在浏览器中打开 yide.dpdns.org 浏览商品并下单。',
        confirmText: '知道了',
        showCancel: false
      });
      return;
    }
  },

  /* ─── 扫码识别（已有） ─── */
  scanBarcode: function() {
    wx.scanCode({
      scanType: ['barCode', 'qrCode'],
      success: (res) => {
        const code = (res.result || '').trim();
        console.log('扫码原始数据：', code);
        this.setData({
          barcode: code,
          name: '',
          price: '',
          stock: 1,
          category: 'others',
          currentStock: null,
          imagePreview: '',
          aiStatus: ''
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

  // 检查是否是库里已有的商品（或外部 API 查到）
  checkOldProduct: function(code) {
    api.request({
      url: '/get_product_by_barcode/',
      data: { barcode: code }
    }).then((data) => {
      if (data.status === 'success') {
        const category = data.category || 'others';
        const setData = {
          name: data.name,
          price: data.price || data.price_estimate || '',
          category: category,
          currentStock: data.stock ?? null
        };
        this.setData(setData);
        if (data.from_db) {
          wx.showToast({ title: '已匹配到库内商品', icon: 'none' });
        } else {
          wx.showToast({ title: '已从外部查询到商品信息，确认后入库', icon: 'none', duration: 3000 });
        }
      } else {
        wx.showToast({ title: '新商品，请录入信息', icon: 'none' });
      }
    }).catch((err) => {
      console.error('查找商品失败', err);
      wx.showToast({ title: '查找失败，请检查网络', icon: 'none' });
    });
  },

  /* ─── AI 拍照识别（新功能） ─── */
  aiRecognize: function() {
    const that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      sizeType: ['compressed'], // 压缩，减少上传大小
      success(res) {
        const tempFile = res.tempFiles[0];
        const tempPath = tempFile.tempFilePath;
        console.log('拍照/选图成功：', tempPath, '大小:', tempFile.size);

        // 显示预览
        that.setData({
          imagePreview: tempPath,
          aiLoading: true,
          aiStatus: ''
        });

        // 上传到后端识别
        that._uploadForAI(tempPath);
      },
      fail(err) {
        console.error('拍照/选图失败', err);
        if (err.errMsg.indexOf('cancel') === -1) {
          wx.showToast({ title: '获取图片失败', icon: 'none' });
        }
      }
    });
  },

  _uploadForAI: function(filePath, retryCount) {
    const that = this;
    retryCount = retryCount || 0;
    this.setData({ aiStatus: '🤖 AI 正在识别商品...' });
    wx.showLoading({ title: 'AI 识别中...' });

    // 构建上传地址
    const uploadUrl = api.BASE_URL + '/api/ai_recognize/';

    wx.uploadFile({
      url: uploadUrl,
      filePath: filePath,
      name: 'image',
      timeout: 60000, // 60 秒超时（AI 视觉识别可能较慢）
      success(res) {
        console.log('AI 识别响应：', res.statusCode, (res.data || '').slice(0, 200));
        if (res.statusCode === 413) {
          that.setData({ aiStatus: '❌ 图片太大，请压缩后重试' });
          wx.showToast({ title: '图片太大', icon: 'none', duration: 3000 });
          that._resetAIState();
          return;
        }
        try {
          const data = JSON.parse(res.data);
          if (data.status === 'success') {
            that._fillAIResult(data);
          } else {
            const errMsg = data.msg || '识别失败';
            that.setData({ aiStatus: '❌ ' + errMsg });
            wx.showToast({ title: errMsg, icon: 'none', duration: 3000 });
            that._resetAIState();
          }
        } catch (e) {
          console.error('解析响应失败', e, '原始数据:', (res.data || '').slice(0, 300));
          that.setData({ aiStatus: '❌ 识别结果解析失败，请手动录入' });
          wx.showToast({ title: '识别结果解析失败', icon: 'none', duration: 3000 });
          that._resetAIState();
        }
      },
      fail(err) {
        console.error('上传识别失败', err, '重试次数:', retryCount);
        // 自动重试一次（网络波动）
        if (retryCount < 1 && err.errMsg && err.errMsg.indexOf('timeout') === -1) {
          console.log('正在重试上传...');
          that.setData({ aiStatus: '🤖 上传失败，正在重试...' });
          setTimeout(function() {
            that._uploadForAI(filePath, retryCount + 1);
          }, 1000);
          return;
        }
        var errMsg = '上传失败，请检查网络后重试';
        if (err.errMsg && err.errMsg.indexOf('timeout') > -1) {
          errMsg = '上传超时，请稍后重试';
        }
        that.setData({ aiStatus: '❌ ' + errMsg });
        wx.showToast({ title: errMsg, icon: 'none', duration: 3000 });
        that._resetAIState();
      },
      complete() {
        wx.hideLoading();
        that.setData({ aiLoading: false });
      }
    });
  },

  // 填充 AI 识别结果到表单
  _fillAIResult: function(data) {
    const name = data.name || '';
    const category = data.category || 'others';
    const barcode = data.barcode || '';
    const priceEstimate = data.price_estimate;

    let setData = {
      name: name,
      category: category,
      barcode: barcode,
    };

    // 如果有预估价格，填入
    if (priceEstimate !== null && priceEstimate !== undefined) {
      setData.price = String(priceEstimate);
    }

    // 如果已存在该商品，显示当前库存和价格
    if (data.exists) {
      setData.currentStock = data.current_stock;
      setData.price = data.existing_price || setData.price;
      // 用数据库名称覆盖 AI 识别（更准确）
      if (data.existing_name) {
        setData.name = data.existing_name;
      }
    }

    this.setData(setData);

    // 弹窗告知识别结果
    const msg = data.exists
      ? `已匹配到现有商品「${data.existing_name || name}」，确认后入库`
      : `AI 识别为「${name || '未知商品'}」，请确认信息后入库`;

    this.setData({ aiStatus: '✅ ' + (data.exists ? '已匹配 ' : 'AI 识别到 ') + (name || '商品') });

    wx.showModal({
      title: '✅ AI 识别完成',
      content: msg,
      showCancel: false
    });
  },

  _resetAIState: function() {
    this.setData({
      aiLoading: false
      // 保留 imagePreview 不清除，让用户看到之前拍的是哪张照片
    });
  },

  /* ─── 入库提交 ─── */
  submitData: function() {
    if (this.data.submitting) return;

    const barcode = (this.data.barcode || '').trim();
    const name = (this.data.name || '').trim();
    const price = Number(this.data.price);
    const stock = Number(this.data.stock);

    if (!barcode) {
      wx.showToast({ title: '请先扫码或拍照识别', icon: 'none' });
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
        stock: stock,
        category: this.data.category
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
            this.setData({ barcode: '', name: '', price: '', stock: 1, category: 'others', currentStock: null, imagePreview: '', aiStatus: '' });
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
