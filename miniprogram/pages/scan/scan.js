const api = require('../../utils/api');

function decorate(r) {
  const s = r.suggestion || {};
  let riskClass = 'neutral';
  if (s.kind === '无异常') riskClass = 'good';
  else if (s.risk === '高') riskClass = 'critical';
  else if (s.risk === '中高') riskClass = 'serious';
  else if (s.risk === '中') riskClass = 'warning';

  let sourceLabel = '本地模拟（未配置 AI Key）';
  if (r.source === 'demo') sourceLabel = '演示模式';
  else if (!r.is_mock) sourceLabel = '云端 AI · ' + (r.source || '');

  return Object.assign({}, r, {
    confidencePct: Math.round((Number(r.confidence) || 0) * 100),
    riskClass: riskClass,
    sourceLabel: sourceLabel,
    pesticides: s.pesticides || [],
    warnings: s.warnings || []
  });
}

Page({
  data: {
    plots: [], plotNames: [], plotIndex: 0,
    pests: [], pestNames: [], pestIndex: 0,
    days: '', preview: '', loading: false, error: '', result: null
  },

  onShow() {
    if (!this.data.plots.length) this.loadMeta();
  },

  loadMeta() {
    Promise.all([api.request('/api/plots'), api.request('/api/pests')])
      .then(res => {
        const plots = res[0] || [];
        const pests = res[1] || [];
        this.setData({
          plots: plots,
          plotNames: plots.map(p => p.name + '（' + p.variety + '）'),
          pests: pests,
          pestNames: pests.map(p => p.name)
        });
      })
      .catch(err => this.setData({ error: err.message }));
  },

  onPlotChange(e) { this.setData({ plotIndex: Number(e.detail.value) }); },
  onPestChange(e) { this.setData({ pestIndex: Number(e.detail.value) }); },
  onDaysInput(e) { this.setData({ days: e.detail.value }); },

  choosePhoto() {
    if (this.data.loading) return;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      sizeType: ['compressed'],
      success: res => {
        const path = res.tempFiles[0].tempFilePath;
        this.setData({ preview: path, result: null, error: '' });
        wx.compressImage({
          src: path,
          quality: 70,
          compressedWidth: 1080,
          success: c => this.uploadPhoto(c.tempFilePath),
          fail: () => this.uploadPhoto(path)
        });
      },
      fail: () => {}
    });
  },

  uploadPhoto(path) {
    const plot = this.data.plots[this.data.plotIndex];
    const formData = {};
    if (plot) formData.plot_id = String(plot.id);
    if (this.data.days !== '') formData.days_to_harvest = String(this.data.days);

    this.setData({ loading: true, error: '' });
    api.upload('/api/recognitions', path, formData)
      .then(r => this.setData({ result: decorate(r), loading: false }))
      .catch(err => this.setData({ error: err.message, loading: false }));
  },

  runDemo() {
    const pest = this.data.pests[this.data.pestIndex];
    if (!pest) return;
    const body = { pest_class: pest.name };
    const plot = this.data.plots[this.data.plotIndex];
    if (plot) body.plot_id = plot.id;
    if (this.data.days !== '') body.days_to_harvest = parseInt(this.data.days, 10);

    this.setData({ loading: true, error: '', result: null, preview: '' });
    api.request('/api/recognitions/demo', 'POST', body)
      .then(r => this.setData({ result: decorate(r), loading: false }))
      .catch(err => this.setData({ error: err.message, loading: false }));
  }
});
