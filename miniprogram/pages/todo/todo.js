const api = require('../../utils/api');
const { extractCode } = require('../../utils/util');

Page({
  data: { items: [], loading: true, error: '' },

  onShow() {
    this.load();
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

  goBatches() {
    wx.navigateTo({ url: '/pages/batches/batches' });
  },

  goTrace() {
    wx.navigateTo({ url: '/pages/trace/trace' });
  }
});
