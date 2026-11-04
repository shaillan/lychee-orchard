const api = require('../../utils/api');

Page({
  data: { plot: null, yields: [], loading: true, error: '' },

  onLoad(options) {
    this.id = options.id;
    this.load();
  },

  load() {
    api.request('/api/plots/' + this.id)
      .then(p => {
        const raw = p.yields || [];
        let max = 1;
        raw.forEach(y => {
          max = Math.max(max, Number(y.actual_yield) || 0, Number(y.estimated_yield) || 0);
        });
        const yields = raw.map(y => {
          const actual = Number(y.actual_yield) || 0;
          const estimated = Number(y.estimated_yield) || 0;
          return {
            season: y.season,
            actual: actual,
            estimated: estimated,
            actH: Math.max(4, Math.round((actual / max) * 100)),
            estH: Math.max(4, Math.round((estimated / max) * 100))
          };
        });
        this.setData({
          plot: Object.assign({}, p, { safe: !!(p.safety && p.safety.safe) }),
          yields: yields,
          loading: false
        });
      })
      .catch(err => this.setData({ error: err.message, loading: false }));
  }
});
