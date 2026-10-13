// 生产环境请改为 false
const DEV_MODE = false;

// 生产环境域名
// 旧：https://yide-hy.vercel.app（Vercel）
// 新：https://yideshuyuan-pehlausf.edgeone.cool（EdgeOne Pages）
const BASE_URL = DEV_MODE
  ? 'http://192.168.1.138:8000'
  : 'https://yide.dpdns.org';

// 店长敏感接口 Token：需与后端（EdgeOne 环境变量）SHOPKEEPER_API_TOKEN 一致。
//
// ⚠️ 本文件是被 git 跟踪的，而仓库是公开的（github.com/HYiung/yide），
//    所以真实 Token 绝不能写在这里，否则会永久留在公开的 git 历史里。
//    真实值放在同目录的 config.local.js（已加入 .gitignore）：
//
//        // yide_xcx/utils/config.local.js
//        module.exports = { TOKEN: '真实值' };
//
//    微信开发者工具上传时会把该文件编译进小程序包，但它不进 git。
//    换机器/重新 clone 后需要手动补建这个文件，否则敏感接口会返回 403。
let localConfig = {};
try {
  localConfig = require('./config.local.js');
} catch (e) {
  // config.local.js 不存在（新克隆的仓库）→ 静默降级为无 Token
  console.warn('[api.js] 未找到 config.local.js，店长敏感接口将无法访问');
}
const SHOPKEEPER_API_TOKEN = localConfig.TOKEN || '';

// 供 wx.uploadFile 等绕过 request() 的调用复用
function authHeader() {
  return SHOPKEEPER_API_TOKEN ? { 'X-Shopkeeper-Token': SHOPKEEPER_API_TOKEN } : {};
}

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
  const mergedHeader = { ...header, ...authHeader() };
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
  authHeader,
  request
};
