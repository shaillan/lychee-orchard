const api = require('../../utils/api');
const font = require('../../utils/font');

Page({
  data: { plot: null, yields: [], maturity: null, lastCheck: null, loading: true, error: '', fontClass: '' },

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

  // 台账留痕：记录不能改也不能删，只能作废；原记录保留并可查
  voidRecord(e) {
    const ds = e.currentTarget.dataset;
    const id = ds.id;
    if (!id) return;
    wx.showModal({
      title: '作废记录',
      editable: true,
      placeholderText: '填写作废原因（如录入错误、重复记录）',
      cancelText: '取消',
      confirmText: '确认作废',
      success: res => {
        if (!res.confirm) return;
        const url = ds.kind === 'pest'
          ? '/api/pesticide-records/' + id + '/void'
          : '/api/operations/' + id + '/void';
        api.request(url, 'POST', {
          reason: (res.content || '').trim(),
          operator: '果农'
        })
          .then(() => {
            wx.showToast({ title: '已作废', icon: 'success' });
            this.load();
          })
          .catch(err => wx.showToast({ title: err.message || '作废失败', icon: 'none' }));
      }
    });
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
        const m = p.maturity || {};
        let lastCheck = null;
        (p.operations || []).some(o => {
          if (o.operation_type !== '成熟度观察') return false;
          let detail = {};
          try { detail = JSON.parse(o.detail || '{}') || {}; } catch (e) { detail = {}; }
          lastCheck = {
            ripeness: detail.ripeness,
            note: detail.note || '',
            image_url: detail.image_url || '',
            date: o.operation_date || '',
            operator: o.operator || ''
          };
          return true;
        });
        this.setData({
          plot: Object.assign({}, p, { safe: !!(p.safety && p.safety.safe) }),
          yields: yields,
          maturity: Object.assign({}, m, {
            statusClass: m.status === '最佳' ? 'good'
              : (m.status === '已过' ? 'critical' : (m.status === '临近' ? 'warning' : 'neutral'))
          }),
          lastCheck: lastCheck,
          loading: false
        });
      })
      .catch(err => this.setData({ error: err.message, loading: false }));
  }
});
