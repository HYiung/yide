Component({
  properties: {
    activeIndex: {
      type: Number,
      value: 0
    }
  },

  data: {
    tabs: [],
    showSafeArea: false
  },

  lifetimes: {
    attached() {
      const isAdmin = wx.getStorageSync('is_admin');
      const isAdminValue = isAdmin === true || isAdmin === 'true';

      const tabs = isAdminValue
        ? [
            { icon: '💳', label: '收银台', path: '/pages/index/index' },
            { icon: '📦', label: '进货录入', path: '/pages/product/product' },
            { icon: '🛍️', label: '商城', path: '/pages/mall/mall' }
          ]
        : [
            { icon: '🛍️', label: '商城', path: '/pages/mall/mall' }
          ];

      // 判断是否需要安全区域适配
      try {
        const sys = wx.getSystemInfoSync();
        const showSafeArea = sys.safeArea && (sys.screenHeight - sys.safeArea.bottom > 0);
        this.setData({ tabs, showSafeArea });
      } catch (e) {
        this.setData({ tabs });
      }
    }
  },

  methods: {
    onTabTap(e) {
      const path = e.currentTarget.dataset.path;
      wx.reLaunch({ url: path });
    }
  }
});
