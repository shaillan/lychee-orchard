const api = require('../../utils/api');
const font = require('../../utils/font');
const { today } = require('../../utils/util');

const COLD_TEXT = {
  pending: '待预冷', overdue: '预冷超时', cooling: '已预冷',
  transit: '运输中', arrived: '已到货', legacy: '历史批次'
};
const COLD_CLASS = {
  pending: 'warning', overdue: 'critical', cooling: 'good',
  transit: 'good', arrived: 'good', legacy: 'neutral'
};
// 当前阶段 → 下一个可登记的冷链节点
const NEXT_EVENT = {
  harvested: { event: 'precool', label: '预冷完成' },
  precooled: { event: 'ship', label: '装车发运' },
  shipped: { event: 'arrive', label: '确认到货' }
};
const CONCLUSIONS = ['合格', '不合格', '待复检'];

function decorateBatch(b) {
  const chain = b.cold_chain || {};
  const next = NEXT_EVENT[chain.stage] || null;
  const hours = chain.hours_since_harvest;
  const conclusion = b.residue_conclusion || '待检测';
  return Object.assign({}, b, {
    statusText: b.status === 'released' ? '已放行' : '已拦截',
    statusClass: b.status === 'released' ? 'good' : 'critical',
    qr: api.BASE_URL + b.qrcode_url,
    coldText: COLD_TEXT[chain.status] || '—',
    coldClass: COLD_CLASS[chain.status] || 'neutral',
    coldHours: hours === null || hours === undefined ? '—' : Math.round(hours),
    nextEvent: next ? next.event : '',
    nextLabel: next ? next.label : '',
    residueText: conclusion,
    residueClass: conclusion === '合格' ? 'good' : (conclusion === '不合格' ? 'critical' : 'warning')
  });
}

Page({
  data: {
    fontClass: '',
    batches: [], loading: true, error: '',
    plots: [], plotNames: [], plotIndex: 0,
    harvestDate: today(), seq: '1',
    creating: false, createMsg: '', createOk: false,
    coldBusy: false,
    // 农残快检录入
    conclusions: CONCLUSIONS,
    residueFor: '', resConclusionIndex: 0,
    resLab: '', resTested: today(), resOperator: '陈伯',
    resItemName: '', resItemValue: '', resItemLimit: '',
    resReportUrl: '', resUploading: false, resSubmitting: false, resMsg: ''
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
      .then(list => this.setData({
        batches: (list || []).map(decorateBatch),
        loading: false
      }))
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
  },

  // 登记冷链节点：预冷 → 发运 → 到货
  coldEvent(e) {
    const ds = e.currentTarget.dataset || {};
    if (!ds.batch || !ds.event || this.data.coldBusy) return;
    this.setData({ coldBusy: true });
    wx.showLoading({ title: '登记中' });
    api.request('/api/batches/' + encodeURIComponent(ds.batch) + '/cold-chain', 'POST', {
      event: ds.event
    })
      .then(() => {
        wx.hideLoading();
        this.setData({ coldBusy: false });
        wx.showToast({ title: '已登记', icon: 'success' });
        this.load();
      })
      .catch(err => {
        wx.hideLoading();
        this.setData({ coldBusy: false });
        wx.showToast({ title: err.message || '登记失败', icon: 'none' });
      });
  },

  // ---- 农残快检录入 ----
  openResidue(e) {
    const batchNo = (e.currentTarget.dataset || {}).batch || '';
    this.setData({
      residueFor: this.data.residueFor === batchNo ? '' : batchNo,
      resConclusionIndex: 0, resLab: '', resTested: today(), resOperator: '陈伯',
      resItemName: '', resItemValue: '', resItemLimit: '',
      resReportUrl: '', resMsg: '', resUploading: false, resSubmitting: false
    });
  },

  onResLabInput(e) { this.setData({ resLab: e.detail.value }); },
  onResTestedChange(e) { this.setData({ resTested: e.detail.value }); },
  onResOperatorInput(e) { this.setData({ resOperator: e.detail.value }); },
  onResConclusionChange(e) { this.setData({ resConclusionIndex: Number(e.detail.value) }); },
  onResItemName(e) { this.setData({ resItemName: e.detail.value }); },
  onResItemValue(e) { this.setData({ resItemValue: e.detail.value }); },
  onResItemLimit(e) { this.setData({ resItemLimit: e.detail.value }); },

  chooseReport() {
    if (this.data.resUploading) return;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      sizeType: ['compressed'],
      success: res => {
        const path = res.tempFiles[0].tempFilePath;
        this.setData({ resUploading: true });
        wx.showLoading({ title: '上传中' });
        api.upload('/api/uploads', path)
          .then(r => {
            wx.hideLoading();
            this.setData({ resReportUrl: r.url || '', resUploading: false });
          })
          .catch(err => {
            wx.hideLoading();
            this.setData({ resUploading: false });
            wx.showToast({ title: err.message || '上传失败', icon: 'none' });
          });
      },
      fail: () => {}
    });
  },

  submitResidue() {
    const batchNo = this.data.residueFor;
    if (!batchNo || this.data.resSubmitting) return;
    const items = [];
    if (this.data.resItemName) {
      items.push({
        name: this.data.resItemName,
        value: this.data.resItemValue,
        unit: 'mg/kg',
        limit: this.data.resItemLimit
      });
    }
    this.setData({ resSubmitting: true, resMsg: '' });
    api.request('/api/batches/' + encodeURIComponent(batchNo) + '/residue-tests', 'POST', {
      tested_at: this.data.resTested,
      lab: this.data.resLab,
      conclusion: this.data.conclusions[this.data.resConclusionIndex],
      items: items,
      report_url: this.data.resReportUrl || null,
      operator: this.data.resOperator || '果农'
    })
      .then(r => {
        this.setData({
          resSubmitting: false,
          residueFor: '',
          resMsg: r.blocked ? '检测不合格，批次已拦截' : '检测已记录'
        });
        wx.showToast({
          title: r.blocked ? '已拦截该批次' : '已记录',
          icon: r.blocked ? 'none' : 'success'
        });
        this.load();
      })
      .catch(err => this.setData({ resSubmitting: false, resMsg: err.message }));
  }
});
