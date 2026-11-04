const api = require('../../utils/api');
const { extractCode } = require('../../utils/util');

Page({
  data: { code: '', trace: null, qrcodeUrl: '', loading: false, error: '' },

  onLoad(options) {
    if (options && options.code) {
      this.setData({ code: decodeURIComponent(options.code) });
      this.load();
    }
  },

  onInput(e) {
    this.setData({ code: e.detail.value });
  },

  scan() {
    wx.scanCode({
      success: res => {
        const code = extractCode(res.result) || String(res.result || '').trim();
        if (!code) {
          wx.showToast({ title: '未识别到溯源码', icon: 'none' });
          return;
        }
        this.setData({ code: code });
        this.load();
      },
      fail: () => {}
    });
  },

  load() {
    const code = (this.data.code || '').trim();
    if (!code) {
      wx.showToast({ title: '请输入溯源码', icon: 'none' });
      return;
    }
    this.setData({ loading: true, error: '', trace: null });
    api.request('/api/trace/' + encodeURIComponent(code))
      .then(t => {
        const trace = Object.assign({}, t, {
          statusText: t.status === 'released' ? '已放行' : '已拦截',
          statusClass: t.status === 'released' ? 'good' : 'critical',
          hash_chain: (t.hash_chain || []).map(h => Object.assign({}, h, {
            short: (h.record_hash || '').slice(0, 16)
          }))
        });
        this.setData({
          trace: trace,
          qrcodeUrl: api.BASE_URL + '/api/batches/' + encodeURIComponent(t.batch_no) + '/qrcode',
          loading: false
        });
      })
      .catch(err => this.setData({ error: err.message, loading: false }));
  }
});
