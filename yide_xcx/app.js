// app.js
App({
  onLaunch() {
    // 展示本地存储能力
    const logs = wx.getStorageSync('logs') || []
    logs.unshift(Date.now())
    wx.setStorageSync('logs', logs)

    // 登录
    wx.login({
      success: res => {
        // 发送 res.code 到后台换取 openId
        wx.request({
          url: 'http://192.168.1.138:8000/api/check_role/', // 确保后端有这个接口
          data: { code: res.code },
          success: (response) => {
            if (response.data.role === 'admin') {
              console.log("身份确认：店主");
              wx.setStorageSync('is_admin', true);
              // 如果默认首页是收银台，店主无需跳转
            } else {
              console.log("身份确认：顾客");
              wx.setStorageSync('is_admin', false);
              // 跳转到商城页
              wx.reLaunch({
                url: '/pages/mall/mall' 
              });
            }
          },
          fail: (err) => {
            console.error("角色检查请求失败", err);
          }
        }); // 👈 这里分号结束请求
      }
    })
  }, // 👈 这里逗号分隔生命周期函数和全局数据

  globalData: {
    userInfo: null
  }
})