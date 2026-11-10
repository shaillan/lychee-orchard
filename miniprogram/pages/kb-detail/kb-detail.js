const api = require('../../utils/api');
const font = require('../../utils/font');
const kbCache = require('../../utils/kb');

const RISK_CLASS = { '高': 'critical', '中高': 'serious', '中': 'warning', '无': 'good', '未知': 'neutral' };
const KIND_ICON = { '虫害': '🐛', '病害': '🍄' };

Page({
  data: {
    fontClass: '', name: '',
    pest: null, pesticides: [],
    loading: true, error: '', offline: false, drugsUnknown: false
  },

  onLoad(options) {
    const name = decodeURIComponent((options && options.name) || '');
    this.setData({ name: name });
    this.load();
  },

  onShow() {
    this.setData({ fontClass: font.fontClass() });
  },

  load() {
    this.setData({ loading: true, error: '', offline: false });
    Promise.all([api.request('/api/pests'), api.request('/api/pesticides')])
      .then(res => {
        kbCache.write(res[0] || []);
        kbCache.writePesticides(res[1] || []);
        this.render(res[0] || [], res[1] || [], false);
      })
      .catch(err => {
        // 断网时用缓存兜底，知识库在果园里照样能查
        const cached = kbCache.read();
        if (cached) {
          this.render(cached.rows, kbCache.readPesticides() || [], true);
          return;
        }
        this.setData({ error: err.message, loading: false });
      });
  },

  render(pests, pesticides, offline) {
    const raw = (pests || []).filter(p => p.name === this.data.name)[0];
    if (!raw) {
      this.setData({ error: '知识库中没有找到「' + (this.data.name || '该条目') + '」', loading: false });
      return;
    }

    const diff = raw.differential || {};
    const pest = Object.assign({}, raw, {
      icon: KIND_ICON[raw.kind] || '🌿',
      riskClass: RISK_CLASS[raw.risk] || 'neutral',
      hostText: (raw.host_parts || []).join('、'),
      peakText: (raw.peak_months || []).join('、'),
      peakNow: kbCache.isPeakNow(raw),
      confusableText: (diff.confusable || []).join('、'),
      distinguishing: diff.distinguishing || [],
      nonChemical: raw.non_chemical || [],
      biological: raw.biological || [],
      monitoring: raw.monitoring || ''
    });
    const drugs = (pesticides || [])
      .filter(p => (p.targets || []).indexOf(raw.name) >= 0)
      .sort((a, b) => (a.safe_interval_days || 0) - (b.safe_interval_days || 0));

    this.setData({
      pest: pest, pesticides: drugs, loading: false,
      offline: !!offline,
      drugsUnknown: !!offline && !(pesticides || []).length
    });
    wx.setNavigationBarTitle({ title: raw.name });
  },

  onRetry() { this.load(); }
});
