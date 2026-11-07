const api = require('../../utils/api');
const font = require('../../utils/font');

Page({
  data: { plot: null, yields: [], loading: true, error: '', fontClass: '' },

  onLoad(options) {
    this.setData({ fontClass: font.fontClass() });
    const id = options && options.id;
    if (!id) {
      this.setData({ loading: false, error: '缺少地块参数，请从「我的果园」重新进入' });
      return;
    }
    this.id = id;
    this.load();
  },

  onShow() {
    this.setData({ fontClass: font.fontClass() });
  },

  retry() {
    this.load();
  },

  load() {
    this.setData({ loading: true, error: '' });
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
            // 没填的年份高度给 0（模板里 wx:if 掉），否则会画出一根误导的小柱子
            actH: actual ? Math.max(4, Math.round((actual / max) * 100)) : 0,
            estH: estimated ? Math.max(4, Math.round((estimated / max) * 100)) : 0
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
