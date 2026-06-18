// 生产环境请改为 false
const DEV_MODE = false;

// 生产环境域名
// 旧：https://yide-hy.vercel.app（Vercel，已迁移）
// 新：部署到 EdgeOne Pages 后替换下方的域名
const BASE_URL = DEV_MODE
  ? 'http://192.168.1.138:8000'
  : 'https://yide-hy.vercel.app';

function buildUrl(path) {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${BASE_URL}${normalizedPath}`;
}

function request(options) {
  const { url, ...rest } = options;
  return new Promise((resolve, reject) => {
    wx.request({
      ...rest,
      url: buildUrl(url),
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data || {});
        } else {
          reject(new Error(`服务器返回异常：${res.statusCode}`));
        }
      },
      fail: reject
    });
  });
}

module.exports = {
  BASE_URL,
  request
};
