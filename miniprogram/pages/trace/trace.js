const api = require('../../utils/api');
const font = require('../../utils/font');
const { extractCode } = require('../../utils/util');

Page({
  data: { code: '', trace: null, qrcodeUrl: '', loading: false, error: '', fontClass: '' },

  onLoad(options) {
    this.setData({ fontClass: font.fontClass() });
    if (options && options.code) {
      this.setData({ code: decodeURIComponent(options.code) });
      this.load();
    }
  },

  onShow() {
    this.setData({ fontClass: font.fontClass() });
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
        const cv = t.chain_verify || {};
        const badIds = (cv.tampered || []).concat(cv.broken || []);
        const sales = t.sales || {};
        const chain = sales.cold_chain || {};
        const COLD_TEXT = {
          pending: '待预冷', overdue: '预冷超时', cooling: '已预冷',
          transit: '运输中', arrived: '已到货', legacy: '无采后记录'
        };
        const COLD_CLASS = {
          pending: 'warning', overdue: 'critical', cooling: 'good',
          transit: 'good', arrived: 'good', legacy: 'neutral'
        };
        const residueTests = (sales.residue_tests || []).map(r => Object.assign({}, r, {
          conclusionClass: r.conclusion === '合格' ? 'good' : (r.conclusion === '不合格' ? 'critical' : 'warning'),
          itemText: (r.items || []).map(i => i.name + ' ' + i.value + (i.unit ? ' ' + i.unit : '') +
            (i.limit ? '（限量 ' + i.limit + '）' : '')).join('；')
        }));
        const trace = Object.assign({}, t, {
          statusText: t.status === 'released' ? '已放行' : '已拦截',
          statusClass: t.status === 'released' ? 'good' : 'critical',
          cold: Object.assign({}, chain, {
            statusText: COLD_TEXT[chain.status] || '—',
            statusClass: COLD_CLASS[chain.status] || 'neutral',
            hours: chain.hours_since_harvest === null || chain.hours_since_harvest === undefined
              ? '—' : Math.round(chain.hours_since_harvest)
          }),
          residueTests: residueTests,
          residueConclusion: sales.residue_conclusion || '待检测',
          residueClass: sales.residue_conclusion === '合格' ? 'good'
            : (sales.residue_conclusion === '不合格' ? 'critical' : 'warning'),
          chainBadgeText: cv.valid
            ? '链校验通过 · ' + (cv.total || 0) + ' 条'
            : '链校验失败 · 第 ' + badIds.join('、') + ' 条',
          chainBadgeClass: cv.valid ? 'good' : 'critical',
          legacyNote: (cv.legacy || []).length
            ? cv.legacy.length + ' 条历史记录未存原文，未参与重算' : '',
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
