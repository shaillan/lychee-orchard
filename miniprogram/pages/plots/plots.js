const api = require('../../utils/api');
const font = require('../../utils/font');

// 只保留列表里展示所需的字段，避免把整条地块数据塞进 data
function slimDetail(p) {
  return {
    id: p.id,
    safe: !!(p.safety && p.safety.safe),
    safetyMessage: (p.safety && p.safety.message) || '',
    ops: (p.operations || []).slice(0, 8),
    psts: (p.pesticides || []).slice(0, 5)
  };
}

Page({
  data: {
    plots: [], loading: true, error: '', fontClass: '',
    // 当前展开的地块 id（0 表示全部收起）及其农事 / 用药记录
    expandedId: 0, detail: null, detailLoading: false, detailError: ''
  },

  onShow() {
    this.setData({ fontClass: font.fontClass() });
    this.load();
  },

  onPullDownRefresh() {
    this.load(() => wx.stopPullDownRefresh());
  },

  load(done) {
    this.setData({ loading: true, error: '' });
    api.request('/api/plots')
      .then(list => {
        const plots = (list || []).map(p => {
          const s = p.safety || {};
          const safe = !!s.safe;
          const days = s.remaining_days;
          const m = p.maturity || {};
          return Object.assign({}, p, {
            safe: safe,
            safeText: safe ? '可采收' : ('还需 ' + (days === null || days === undefined ? '—' : days) + ' 天'),
            safeClass: safe ? 'good' : 'critical',
            maturityStatus: m.status || '',
            maturityClass: m.status === '最佳' ? 'good'
              : (m.status === '已过' ? 'critical' : (m.status === '临近' ? 'warning' : 'neutral'))
          });
        });
        this.setData({ plots, loading: false });
      })
      .catch(err => this.setData({ error: err.message, loading: false }))
      .then(() => done && done());
  },

  retry() {
    this.load();
  },

  // 点地块：直接在本页展开农事记录 / 用药台账（与 H5 一致），再点一次收起。
  // 之前这里只做 navigateTo，一旦跳转失败页面上看不到任何记录，所以改成页内展开。
  open(e) {
    const ds = e.currentTarget.dataset;
    const id = Number(ds.id);
    if (!id) return;

    if (this.data.expandedId === id) {
      // 从分区图再点同一个地块：只滚回档案卡，不收起
      if (ds.scroll) {
        this.scrollToPlot(id);
        return;
      }
      this.setData({ expandedId: 0, detail: null, detailLoading: false, detailError: '' });
      return;
    }

    this.setData({ expandedId: id, detail: null, detailLoading: true, detailError: '' });
    if (ds.scroll) this.scrollToPlot(id);

    api.request('/api/plots/' + id)
      .then(p => {
        if (this.data.expandedId !== id) return;  // 期间已切到别的地块，丢弃旧响应
        this.setData({ detail: slimDetail(p), detailLoading: false });
      })
      .catch(err => {
        if (this.data.expandedId !== id) return;
        this.setData({ detailError: err.message || '记录加载失败', detailLoading: false });
      });
  },

  // 从分区图点进来时，把对应档案卡滚到可见位置
  scrollToPlot(id) {
    setTimeout(() => {
      wx.pageScrollTo({ selector: '#plot-' + id, duration: 200, fail: () => {} });
    }, 60);
  },

  // 展开后仍可进入完整档案页（含产量趋势）
  openFull(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;
    wx.navigateTo({ url: '/pages/plot/plot?id=' + id });
  },

  // 展开区内点击不应触发外层的收起
  noop() {}
});
