const api = require('../../utils/api');
const font = require('../../utils/font');
const kbCache = require('../../utils/kb');

const RISK_CLASS = { '高': 'critical', '中高': 'serious', '中': 'warning', '无': 'good', '未知': 'neutral' };
const KIND_ICON = { '虫害': '🐛', '病害': '🍄' };

function decorate(p) {
  return Object.assign({}, p, {
    icon: KIND_ICON[p.kind] || '🌿',
    riskClass: RISK_CLASS[p.risk] || 'neutral',
    hostText: (p.host_parts || []).join('、'),
    peakText: (p.peak_months || []).join('、'),
    hasPeak: !!(p.peak_months && p.peak_months.length),
    peakNow: kbCache.isPeakNow(p)
  });
}

Page({
  data: {
    fontClass: '', loading: true, error: '',
    all: [], list: [], keyword: '', filter: 'all',
    counts: { all: 0, pest: 0, disease: 0, peak: 0 },
    peakNames: '', peakMore: false,
    offline: false, offlineText: ''
  },

  onShow() {
    this.setData({ fontClass: font.fontClass() });
    if (!this.data.all.length) this.load();
  },

  onPullDownRefresh() {
    this.load(() => wx.stopPullDownRefresh());
  },

  load(done) {
    // 先读缓存立即出内容，再去请求网络；断网时页面依然可查
    const cached = kbCache.read();
    if (cached && !this.data.all.length) {
      this.applyRows(cached.rows, { loading: false });
    } else if (!this.data.all.length) {
      this.setData({ loading: true, error: '' });
    }

    api.request('/api/pests')
      .then(rows => {
        const all = this.normalize(rows);
        kbCache.write(all);
        this.applyRows(all, { offline: false, offlineText: '' });
      })
      .catch(err => {
        if (this.data.all.length) {
          const at = cached && cached.at ? kbCache.cacheLabel(cached.at) : '';
          this.setData({
            offline: true,
            offlineText: '当前离线，显示 ' + this.data.all.length + ' 条缓存知识' + (at ? '（' + at + ' 更新）' : '')
          });
        } else {
          this.setData({ error: err.message, loading: false });
        }
      })
      .then(() => { if (typeof done === 'function') done(); });
  },

  normalize(rows) {
    // 知识库只展示病虫害；健康叶片/果实与兜底类不参与浏览
    const all = (rows || [])
      .filter(p => p.kind === '虫害' || p.kind === '病害')
      .map(decorate);
    all.sort((a, b) => (a.kind === b.kind ? 0 : (a.kind === '虫害' ? -1 : 1)));
    return all;
  },

  applyRows(rows, extra) {
    const all = (rows || []).map(decorate);
    const peak = all.filter(p => p.peakNow);
    this.setData(Object.assign({
      all: all,
      loading: false,
      error: '',
      counts: {
        all: all.length,
        pest: all.filter(p => p.kind === '虫害').length,
        disease: all.filter(p => p.kind === '病害').length,
        peak: peak.length
      },
      peakNames: peak.slice(0, 3).map(p => p.name).join('、'),
      peakMore: peak.length > 3
    }, extra || {}));
    this.apply();
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

  showPeak() {
    this.setData({ filter: 'peak' });
    this.apply();
  },

  apply() {
    const kw = String(this.data.keyword || '').trim().toLowerCase();
    const filter = this.data.filter;
    const list = this.data.all.filter(p => {
      if (filter === 'pest' && p.kind !== '虫害') return false;
      if (filter === 'disease' && p.kind !== '病害') return false;
      if (filter === 'peak' && !p.peakNow) return false;
      if (!kw) return true;
      const diff = p.differential || {};
      const hay = [
        p.name, p.latin, p.symptoms, p.timing, p.notes, p.monitoring,
        (p.aliases || []).join(' '),
        (p.host_parts || []).join(' '),
        (p.non_chemical || []).join(' '),
        (p.biological || []).join(' '),
        (diff.confusable || []).join(' '),
        (diff.distinguishing || []).join(' ')
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
