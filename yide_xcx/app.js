// app.js
const api = require('./utils/api.js');

App({
  onLaunch() {
    // 展示本地存储能力
    const logs = wx.getStorageSync('logs') || [];
    logs.unshift(Date.now());
    wx.setStorageSync('logs', logs);

    // 登录并缓存身份。页面会根据 is_admin 做二次兜底跳转。
    this.checkRole();
  },

  checkRole() {
    wx.login({
      success: (res) => {
        if (!res.code) {
          wx.setStorageSync('is_admin', false);
          wx.reLaunch({ url: '/pages/mall/mall' });
          return;
        }

        api.request({
          url: '/api/check_role/',
          data: { code: res.code }
        }).then((data) => {
          const isAdmin = data.role === 'admin';
          wx.setStorageSync('is_admin', isAdmin);
          console.log(`身份确认：${isAdmin ? '店主' : '顾客'}`);

          // 店主 → 跳转收银台，顾客 → 跳转商城
          if (isAdmin) {
            wx.reLaunch({ url: '/pages/index/index' });
          } else {
            wx.reLaunch({ url: '/pages/mall/mall' });
          }
        }).catch((err) => {
          console.error('角色检查请求失败', err);
          wx.setStorageSync('is_admin', false);
          wx.reLaunch({ url: '/pages/mall/mall' });
        });
      },
      fail: (err) => {
        console.error('微信登录失败', err);
        wx.setStorageSync('is_admin', false);
        wx.reLaunch({ url: '/pages/mall/mall' });
      }
    });
  },

  globalData: {
    userInfo: null
  }
});
