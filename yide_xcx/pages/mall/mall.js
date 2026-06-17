// pages/mall/mall.js
const api = require('../../utils/api.js');

Page({
  data: {
    showCartDetail: false, // 控制清单弹窗显示
    products: [],
    loading: true,
    activeCat: 'all',
    searchKey: '',
    categories: [
      { id: 'all', name: '全部' },
      { id: 'books', name: '📚 名著' },
      { id: 'pens', name: '🖊️ 笔类' },
      { id: 'erasers', name: '🧽 橡皮' },
      { id: 'correction', name: '📦 修正' },
      { id: 'others', name: '📎 其他' }
    ],
    cart: [],
    totalPrice: '0.00',
    totalCount: 0,
    isAdmin: false
  },

  onLoad: function () {
    this.setData({ isAdmin: !!wx.getStorageSync('is_admin') });
    this.quietCheckIdentity();
    if (this.data.isAdmin) {
      wx.setStorageSync('cart', []);
    }
    this.fetchData(this.data.activeCat, this.data.searchKey);
  },

  onShow: function() {
    this.setData({ isAdmin: !!wx.getStorageSync('is_admin') });
    this.fetchData(this.data.activeCat, this.data.searchKey);
    const cart = wx.getStorageSync('cart') || [];
    this.calculateTotal(cart);
  },

  // ---------- 数据处理 ----------

  fetchData: function (category, search) {
    this.setData({ loading: true });
    api.request({
      url: '/api/mall_products/',
      data: {
        category: category,
        search: search || ''
      }
    }).then((data) => {
      if (data && data.status === 'success') {
        const products = (data.list || []).map(p => ({
          ...p,
          iconUrl: this.getCategoryIcon(p.category),
          _createTime: p.create_time
        }));
        this.setData({
          products: products,
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

  // 判断是否为新品（7天内录入）
  isNewProduct: function(product) {
    if (!product.create_time) return false;
    const created = new Date(product.create_time);
    const now = new Date();
    const diffDays = (now - created) / (1000 * 60 * 60 * 24);
    return diffDays <= 7;
  },

  // ---------- 搜索 & 分类 ----------

  onSearchInput: function(e) {
    this.setData({ searchKey: e.detail.value });
  },

  doSearch: function() {
    this.setData({ activeCat: 'all' });
    this.fetchData('all', this.data.searchKey);
  },

  clearSearch: function() {
    this.setData({ searchKey: '' });
    this.fetchData(this.data.activeCat, '');
  },

  switchCat: function (e) {
    const catId = e.currentTarget.dataset.id;
    this.setData({ activeCat: catId, showCartDetail: false });

    // 如果有搜索关键词，搜全部再按分类过滤
    if (this.data.searchKey) {
      this.fetchData('all', this.data.searchKey);
    } else {
      this.fetchData(catId, '');
    }
  },

  // 触底加载更多（预留，目前一次加载全部）
  onLoadMore: function() {
    // 分页功能可在此扩展
  },

  // ---------- 购物车操作 ----------

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
    const icons = {
      'books': 'https://cdn-icons-png.flaticon.com/512/2232/2232688.png',
      'pens': 'https://cdn-icons-png.flaticon.com/512/3361/3361993.png',
      'erasers': 'https://cdn-icons-png.flaticon.com/512/4781/4781902.png',
      'correction': 'https://cdn-icons-png.flaticon.com/512/5603/5603981.png',
      'others': 'https://cdn-icons-png.flaticon.com/512/2462/2462630.png'
    };
    return icons[category] || 'https://cdn-icons-png.flaticon.com/512/2541/2541991.png';
  },

  addToCart: function (e) {
    if (this.data.isAdmin) {
      wx.showToast({ title: '店主仅可浏览，顾客才能购买', icon: 'none', duration: 1500 });
      return;
    }
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
    wx.showToast({ title: '已加入 🛒', icon: 'success', duration: 600 });
  },

  plusItem: function(e) {
    if (this.data.isAdmin) return;
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

  minusItem: function(e) {
    if (this.data.isAdmin) return;
    const id = e.currentTarget.dataset.id;
    let cart = this.data.cart.slice();
    const index = cart.findIndex(v => v.id === id);
    if (index > -1) {
      if (cart[index].num > 1) {
        cart[index].num -= 1;
      } else {
        cart.splice(index, 1);
      }
      this.calculateTotal(cart);
      if (cart.length === 0) {
        this.setData({ showCartDetail: false });
      }
    }
  },

  clearCart: function() {
    if (this.data.isAdmin) return;
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
    if (this.data.isAdmin) {
      wx.showToast({ title: '店主仅可浏览，顾客才能购买', icon: 'none' });
      return;
    }
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
