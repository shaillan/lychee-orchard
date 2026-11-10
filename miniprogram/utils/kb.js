// 知识库本地缓存与「当季高发」判断。
// /api/pests 的条目几乎不变，果园信号差时用缓存兜底；缓存里存原始行，展示前再装饰。
const CACHE_KEY = 'kb_cache_v1';
const PESTICIDE_KEY = 'kb_pesticides_v1';
const MAX_AGE = 30 * 24 * 60 * 60 * 1000; // 30 天，仅用于提示缓存新旧，过期仍可读

function read() {
  try {
    const cached = wx.getStorageSync(CACHE_KEY);
    if (cached && Array.isArray(cached.rows) && cached.rows.length) {
      return { at: cached.at || 0, rows: cached.rows };
    }
  } catch (e) {
    // 存储不可用时不阻塞页面
  }
  return null;
}

function write(rows) {
  if (!Array.isArray(rows) || !rows.length) return;
  try {
    wx.setStorageSync(CACHE_KEY, { at: Date.now(), rows: rows });
  } catch (e) {
    // 忽略写入失败
  }
}

function readPesticides() {
  try {
    const cached = wx.getStorageSync(PESTICIDE_KEY);
    if (cached && Array.isArray(cached.rows) && cached.rows.length) return cached.rows;
  } catch (e) {
    // 忽略
  }
  return null;
}

function writePesticides(rows) {
  if (!Array.isArray(rows) || !rows.length) return;
  try {
    wx.setStorageSync(PESTICIDE_KEY, { at: Date.now(), rows: rows });
  } catch (e) {
    // 忽略写入失败
  }
}

function cacheLabel(at) {
  if (!at) return '';
  const d = new Date(at);
  const pad = n => (n < 10 ? '0' + n : '' + n);
  return (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

function isStale(at) {
  return !at || Date.now() - at > MAX_AGE;
}

function currentMonth() {
  return new Date().getMonth() + 1;
}

// peak_months 形如 ["5月", "6月", "7月"]
function isPeakNow(item) {
  const months = (item && item.peak_months) || [];
  const now = currentMonth();
  return months.some(m => parseInt(m, 10) === now);
}

module.exports = {
  read, write, readPesticides, writePesticides,
  cacheLabel, isStale, currentMonth, isPeakNow
};
