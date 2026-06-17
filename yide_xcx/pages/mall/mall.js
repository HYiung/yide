// pages/mall/mall.js
const api = require('../../utils/api.js');

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
      { id: 'erasers', name: '橡皮' },
      { id: 'others', name: '其他' }
    ],
    cart: [],         // 购物车列表
    totalPrice: '0.00',
    totalCount: 0
  },

  onLoad: function () {
    this.quietCheckIdentity();
    this.fetchData(this.data.activeCat);
  },

  onShow: function() {
    // 每次页面显示时重新加载数据（tab 切换、navigateBack 等场景）
    this.fetchData(this.data.activeCat);
    const cart = wx.getStorageSync('cart') || [];
    this.calculateTotal(cart);
  },

  fetchData: function (category) {
    this.setData({ loading: true });
    api.request({
      url: '/api/mall_products/',
      data: { category: category }
    }).then((data) => {
      if (data && data.status === 'success') {
        this.setData({
          products: data.list || [],
          loading: false
        });
        this.syncCartWithProducts(data.list || []);
      } else {
        this.setData({ loading: false });
        wx.showToast({ title: data.msg || '商品加载失败', icon: 'none' });
      }
    }).catch((err) => {
      console.error('商品加载失败', err);
      this.setData({ loading: false });
      wx.showToast({ title: '服务器连接失败', icon: 'none' });
    });
  },

  switchCat: function (e) {
    const catId = e.currentTarget.dataset.id;
    this.setData({ activeCat: catId, showCartDetail: false });
    this.fetchData(catId);
  },

  // 切换清单弹窗显示/隐藏
  toggleCartDetail: function() {
    if (this.data.totalCount > 0) {
      this.setData({ showCartDetail: !this.data.showCartDetail });
    }
  },

  getProductStock: function(product) {
    return Number(product.stock || product.remaining_stock || 0);
  },

  normalizeProduct: function(product, num) {
    return {
      id: product.id,
      name: product.name,
      price: Number(product.price),
      category: product.category,
      stock: this.getProductStock(product),
      num: num,
      iconUrl: this.getCategoryIcon(product.category)
    };
  },

  getCategoryIcon: function(category) {
    // 各类文具对应不同图标（Flaticon CDN，与项目原有用法一致）
    const icons = {
      'books': 'https://cdn-icons-png.flaticon.com/512/2232/2232688.png',
      'pens': 'https://cdn-icons-png.flaticon.com/512/3361/3361993.png',
      'erasers': 'https://cdn-icons-png.flaticon.com/512/4781/4781902.png',
      'others': 'https://cdn-icons-png.flaticon.com/512/2462/2462630.png'
    };
    return icons[category] || 'https://cdn-icons-png.flaticon.com/512/2541/2541991.png';
  },

  // 加入购物车 (主列表按钮)
  addToCart: function (e) {
    const product = e.currentTarget.dataset.item;
    const stock = this.getProductStock(product);
    let cart = this.data.cart.slice();
    const index = cart.findIndex(v => v.id === product.id);

    if (index === -1) {
      if (stock <= 0) {
        wx.showToast({ title: '该商品已售罄', icon: 'none' });
        return;
      }
      cart.push(this.normalizeProduct(product, 1));
    } else {
      if (cart[index].num >= stock) {
        wx.showToast({ title: `库存仅剩 ${stock} 件`, icon: 'none' });
        return;
      }
      cart[index].num += 1;
      cart[index].stock = stock;
      cart[index].price = Number(product.price);
    }

    this.calculateTotal(cart);
    wx.showToast({ title: '已加入', icon: 'success', duration: 800 });
  },

  // 清单内加数量
  plusItem: function(e) {
    const id = e.currentTarget.dataset.id;
    let cart = this.data.cart.slice();
    const index = cart.findIndex(v => v.id === id);
    if (index > -1) {
      const stock = this.getProductStock(cart[index]);
      if (cart[index].num >= stock) {
        wx.showToast({ title: `库存仅剩 ${stock} 件`, icon: 'none' });
        return;
      }
      cart[index].num += 1;
      this.calculateTotal(cart);
    }
  },

  // 清单内减数量
  minusItem: function(e) {
    const id = e.currentTarget.dataset.id;
    let cart = this.data.cart.slice();
    const index = cart.findIndex(v => v.id === id);
    if (index > -1) {
      if (cart[index].num > 1) {
        cart[index].num -= 1;
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

  // 清空购物车
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
      const price = Number(v.price) || 0;
      const num = Number(v.num) || 0;
      totalPrice += num * price;
      totalCount += num;
    });

    const formattedTotal = totalPrice.toFixed(2);
    this.setData({
      cart: cart,
      totalPrice: formattedTotal,
      totalCount: totalCount
    });
    wx.setStorageSync('cart', cart);
    wx.setStorageSync('totalPrice', formattedTotal);
  },

  syncCartWithProducts: function(products) {
    if (!this.data.cart.length) return;

    const productMap = {};
    products.forEach((product) => {
      productMap[product.id] = product;
    });

    let changed = false;
    const cart = this.data.cart.reduce((result, item) => {
      const latest = productMap[item.id];
      if (!latest && this.data.activeCat !== 'all') {
        result.push(item);
        return result;
      }
      if (!latest) {
        changed = true;
        return result;
      }

      const stock = this.getProductStock(latest);
      if (stock <= 0) {
        changed = true;
        return result;
      }

      const num = Math.min(item.num, stock);
      if (num !== item.num || Number(item.price) !== Number(latest.price)) {
        changed = true;
      }
      result.push(this.normalizeProduct(latest, num));
      return result;
    }, []);

    if (changed) {
      this.calculateTotal(cart);
      wx.showToast({ title: '购物车已按最新库存更新', icon: 'none' });
    }
  },

  goToOrder: function() {
    if (this.data.totalCount <= 0) {
      wx.showToast({ title: '购物车为空', icon: 'none' });
      return;
    }
    wx.setStorageSync('cart', this.data.cart);
    wx.setStorageSync('totalPrice', this.data.totalPrice);
    wx.navigateTo({ url: '/pages/order/order' });
  },

  quietCheckIdentity: function () {
    wx.login({
      success: res => {
        api.request({
          url: '/api/check_role/',
          data: { code: res.code }
        }).then((data) => {
          wx.setStorageSync('is_admin', data.role === 'admin');
        }).catch((err) => {
          console.error('身份检查失败', err);
        });
      }
    });
  }
});
