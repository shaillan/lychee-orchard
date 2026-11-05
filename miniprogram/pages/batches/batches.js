const api = require('../../utils/api');
const font = require('../../utils/font');
const { today } = require('../../utils/util');

Page({
  data: {
    fontClass: '',
    batches: [], loading: true, error: '',
    plots: [], plotNames: [], plotIndex: 0,
    harvestDate: today(), seq: '1',
    creating: false, createMsg: '', createOk: false
  },

  onShow() {
    this.setData({ fontClass: font.fontClass() });
    this.load();
    if (!this.data.plots.length) this.loadMeta();
  },

  onPullDownRefresh() {
    this.load(() => wx.stopPullDownRefresh());
  },

  load(done) {
    api.request('/api/batches')
      .then(list => {
        const batches = (list || []).map(b => Object.assign({}, b, {
          statusText: b.status === 'released' ? '已放行' : '已拦截',
          statusClass: b.status === 'released' ? 'good' : 'critical',
          qr: api.BASE_URL + b.qrcode_url
        }));
        this.setData({ batches: batches, loading: false });
      })
      .catch(err => this.setData({ error: err.message, loading: false }))
      .then(() => done && done());
  },

  loadMeta() {
    api.request('/api/plots')
      .then(plots => this.setData({
        plots: plots || [],
        plotNames: (plots || []).map(p => p.name + '（' + p.variety + '）')
      }))
      .catch(() => {});
  },

  onPlotChange(e) { this.setData({ plotIndex: Number(e.detail.value) }); },
  onDateChange(e) { this.setData({ harvestDate: e.detail.value }); },
  onSeqInput(e) { this.setData({ seq: e.detail.value }); },

  create() {
    const plot = this.data.plots[this.data.plotIndex];
    if (!plot) {
      wx.showToast({ title: '请先选择地块', icon: 'none' });
      return;
    }
    this.setData({ creating: true, createMsg: '' });
    api.request('/api/batches', 'POST', {
      plot_id: plot.id,
      harvest_date: this.data.harvestDate,
      packaging_seq: parseInt(this.data.seq, 10) || 1
    })
      .then(r => {
        const blocked = r.status !== 'released';
        this.setData({
          creating: false,
          createOk: !blocked,
          createMsg: blocked
            ? '批次已生成但被拦截：' + (r.block_reason || '安全间隔期未满')
            : '批次已生成，溯源码：' + r.trace_code + '，二维码已入库'
        });
        this.load();
      })
      .catch(err => this.setData({ creating: false, createOk: false, createMsg: err.message }));
  }
});
