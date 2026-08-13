// 生产环境请改为 false
const DEV_MODE = false;

// 生产环境域名
// 旧：https://yide-hy.vercel.app（Vercel）
// 新：https://yideshuyuan-pehlausf.edgeone.cool（EdgeOne Pages）
const BASE_URL = DEV_MODE
  ? 'http://192.168.1.138:8000'
  : 'https://yide.dpdns.org';

// 店长敏感接口 Token：需与后端 SHOPKEEPER_API_TOKEN 环境变量一致。
// 建议只在店长专用小程序版本中配置，不要放入公开顾客端。
const SHOPKEEPER_API_TOKEN = '';

function buildUrl(path) {
  if (/^https?:\/\//.test(path)) {
    return path;
  }
  const base = BASE_URL.endsWith('/') ? BASE_URL.slice(0, -1) : BASE_URL;
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}

function request(options) {
  const { url, timeout = 10000, header = {}, ...rest } = options;  // 默认10秒超时
  const mergedHeader = { ...header };
  if (SHOPKEEPER_API_TOKEN) {
    mergedHeader['X-Shopkeeper-Token'] = SHOPKEEPER_API_TOKEN;
  }
  return new Promise((resolve, reject) => {
    wx.request({
      ...rest,
      url: buildUrl(url),
      timeout: timeout,
      header: mergedHeader,
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
  SHOPKEEPER_API_TOKEN,
  request
};
