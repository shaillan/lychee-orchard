const api = require('../../utils/api');
const font = require('../../utils/font');
const { extractCode } = require('../../utils/util');

Page({
  data: { items: [], loading: true, error: '', fontClass: '', bigFont: false },

  onShow() {
    this.setData({ fontClass: font.fontClass(), bigFont: font.isLarge() });
    this.load();
  },

  onFontToggle(e) {
    const on = !!e.detail.value;
    font.setLarge(on);
    this.setData({ bigFont: on, fontClass: font.fontClass() });
  },

  onPullDownRefresh() {
    this.load(() => wx.stopPullDownRefresh());
  },

  load(done) {
    this.setData({ loading: true, error: '' });
    api.request('/api/todos')
      .then(items => this.setData({ items: items || [], loading: false }))
      .catch(err => this.setData({ error: err.message, loading: false }))
      .then(() => done && done());
  },

  scan() {
    wx.scanCode({
      success: res => {
        const code = extractCode(res.result) || String(res.result || '').trim();
        if (!code) {
          wx.showToast({ title: '未识别到溯源码', icon: 'none' });
          return;
        }
        wx.navigateTo({ url: '/pages/trace/trace?code=' + encodeURIComponent(code) });
      },
      fail: () => {}
    });
  },

  goScan() {
    // tab 页不能带 query，用 storage 标记让扫码页滚到识别记录区
    wx.setStorageSync('focusHistory', true);
    wx.switchTab({ url: '/pages/scan/scan' });
  },

  goBatches() {
    wx.navigateTo({ url: '/pages/batches/batches' });
  },

  goTrace() {
    wx.navigateTo({ url: '/pages/trace/trace' });
  }
});
