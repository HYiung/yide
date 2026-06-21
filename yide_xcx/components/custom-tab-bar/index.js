Component({
  properties: {
    activeIndex: {
      type: Number,
      value: 0
    }
  },

  data: {
    tabs: [
      { icon: '💳', label: '收银台', path: '/pages/index/index' },
      { icon: '📦', label: '进货录入', path: '/pages/product/product' }
    ],
    showSafeArea: false
  },

  lifetimes: {
    attached() {
      // 判断是否需要安全区域适配
      try {
        const sys = wx.getSystemInfoSync();
        const showSafeArea = sys.safeArea && (sys.screenHeight - sys.safeArea.bottom > 0);
        this.setData({ showSafeArea });
      } catch (e) {}
    }
  },

  methods: {
    onTabTap(e) {
      const path = e.currentTarget.dataset.path;
      wx.reLaunch({ url: path });
    }
  }
});
