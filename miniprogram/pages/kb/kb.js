const api = require('../../utils/api');
const font = require('../../utils/font');

const RISK_CLASS = { '高': 'critical', '中高': 'serious', '中': 'warning', '无': 'good', '未知': 'neutral' };
const KIND_ICON = { '虫害': '🐛', '病害': '🍄' };

function decorate(p) {
  return Object.assign({}, p, {
    icon: KIND_ICON[p.kind] || '🌿',
    riskClass: RISK_CLASS[p.risk] || 'neutral',
    hostText: (p.host_parts || []).join('、'),
    peakText: (p.peak_months || []).join('、'),
    hasPeak: !!(p.peak_months && p.peak_months.length)
  });
}

Page({
  data: {
    fontClass: '', loading: true, error: '',
    all: [], list: [], keyword: '', filter: 'all',
    counts: { all: 0, pest: 0, disease: 0 }
  },

  onShow() {
    this.setData({ fontClass: font.fontClass() });
    if (!this.data.all.length) this.load();
  },

  onPullDownRefresh() {
    this.load(() => wx.stopPullDownRefresh());
  },

  load(done) {
    this.setData({ loading: !this.data.all.length, error: '' });
    api.request('/api/pests')
      .then(rows => {
        // 知识库只展示病虫害；健康叶片/果实与兜底类不参与浏览
        const all = (rows || [])
          .filter(p => p.kind === '虫害' || p.kind === '病害')
          .map(decorate);
        all.sort((a, b) => (a.kind === b.kind ? 0 : (a.kind === '虫害' ? -1 : 1)));
        this.setData({
          all: all,
          loading: false,
          counts: {
            all: all.length,
            pest: all.filter(p => p.kind === '虫害').length,
            disease: all.filter(p => p.kind === '病害').length
          }
        });
        this.apply();
      })
      .catch(err => this.setData({ error: err.message, loading: false }))
      .then(() => { if (typeof done === 'function') done(); });
  },

  onSearch(e) {
    this.setData({ keyword: e.detail.value });
    this.apply();
  },

  setFilter(e) {
    const filter = e.currentTarget.dataset.filter || 'all';
    this.setData({ filter: filter });
    this.apply();
  },

  apply() {
    const kw = String(this.data.keyword || '').trim().toLowerCase();
    const filter = this.data.filter;
    const list = this.data.all.filter(p => {
      if (filter === 'pest' && p.kind !== '虫害') return false;
      if (filter === 'disease' && p.kind !== '病害') return false;
      if (!kw) return true;
      const hay = [
        p.name, p.latin, p.symptoms,
        (p.aliases || []).join(' '),
        (p.host_parts || []).join(' ')
      ].join(' ').toLowerCase();
      return hay.indexOf(kw) >= 0;
    });
    this.setData({ list: list });
  },

  openDetail(e) {
    const name = e.currentTarget.dataset.name;
    if (!name) return;
    wx.navigateTo({ url: '/pages/kb-detail/kb-detail?name=' + encodeURIComponent(name) });
  }
});
