// 生产环境请改为 false
const DEV_MODE = false;

// 生产环境域名
// 旧：https://yide-hy.vercel.app（Vercel）
// 新：https://yideshuyuan-pehlausf.edgeone.cool（EdgeOne Pages）
const BASE_URL = DEV_MODE
  ? 'http://192.168.1.138:8000'
  : 'https://yide.dpdns.org';

function buildUrl(path) {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  const base = BASE_URL.endsWith('/') ? BASE_URL.slice(0, -1) : BASE_URL;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}

function request(options) {
  const { url, timeout = 10000, ...rest } = options;  // 默认10秒超时
  return new Promise((resolve, reject) => {
    wx.request({
      ...rest,
      url: buildUrl(url),
      timeout: timeout,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data || {});
        } else {
          reject(new Error(`服务器返回异常：${res.statusCode}`));
        }
      },
      fail: (err) => {
        console.error(`请求失败 [${url}]:`, err);
        reject(err);
      }
    });
  });
}

module.exports = {
  BASE_URL,
  request
};
