const api = require('../../utils/api');

Page({
  data: { plots: [], loading: true, error: '' },

  onShow() {
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
          const safe = p.safety && p.safety.safe;
          return Object.assign({}, p, {
            safe: !!safe,
            safeText: safe ? '可采收' : ('还需 ' + p.safety.remaining_days + ' 天'),
            safeClass: safe ? 'good' : 'critical'
          });
        });
        this.setData({ plots, loading: false });
      })
      .catch(err => this.setData({ error: err.message, loading: false }))
      .then(() => done && done());
  },

  open(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: '/pages/plot/plot?id=' + id });
  }
});
