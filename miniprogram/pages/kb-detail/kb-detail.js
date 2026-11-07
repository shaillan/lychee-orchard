const api = require('../../utils/api');
const font = require('../../utils/font');

const RISK_CLASS = { '高': 'critical', '中高': 'serious', '中': 'warning', '无': 'good', '未知': 'neutral' };
const KIND_ICON = { '虫害': '🐛', '病害': '🍄' };

Page({
  data: {
    fontClass: '', name: '',
    pest: null, pesticides: [],
    loading: true, error: ''
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
    this.setData({ loading: true, error: '' });
    Promise.all([api.request('/api/pests'), api.request('/api/pesticides')])
      .then(res => {
        const pests = res[0] || [];
        const raw = pests.filter(p => p.name === this.data.name)[0];
        if (!raw) throw new Error('知识库中没有找到「' + (this.data.name || '该条目') + '」');

        const diff = raw.differential || {};
        const pest = Object.assign({}, raw, {
          icon: KIND_ICON[raw.kind] || '🌿',
          riskClass: RISK_CLASS[raw.risk] || 'neutral',
          hostText: (raw.host_parts || []).join('、'),
          peakText: (raw.peak_months || []).join('、'),
          confusableText: (diff.confusable || []).join('、'),
          distinguishing: diff.distinguishing || [],
          nonChemical: raw.non_chemical || [],
          biological: raw.biological || [],
          monitoring: raw.monitoring || ''
        });
        const pesticides = (res[1] || [])
          .filter(p => (p.targets || []).indexOf(raw.name) >= 0)
          .sort((a, b) => (a.safe_interval_days || 0) - (b.safe_interval_days || 0));

        this.setData({ pest: pest, pesticides: pesticides, loading: false });
        wx.setNavigationBarTitle({ title: raw.name });
      })
      .catch(err => this.setData({ error: err.message, loading: false }));
  },

  onRetry() { this.load(); }
});
