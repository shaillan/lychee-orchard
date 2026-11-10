const api = require('../../utils/api');
const font = require('../../utils/font');

// 微信同声传译插件：需先在 mp 后台为该 AppID 添加插件并在 app.json 声明，
// 否则开发者工具会报「插件未授权使用」导致模拟器启动失败，因此这里必须容错降级
let voiceManager = null;
try {
  if (typeof requirePlugin === 'function') {
    voiceManager = requirePlugin('WechatSI').getRecordRecognitionManager();
  }
} catch (e) {
  voiceManager = null;
}

Page({
  data: {
    fontClass: '',
    plots: [], plotNames: [], plotIndex: 0,
    opTypes: ['施肥', '灌溉', '修剪', '疏花疏果', '巡检', '清园'],
    opIndex: 0,
    operator: '陈伯',
    remark: '',
    voiceAvailable: !!voiceManager, recording: false,
    pesticides: [], pesticideNames: [], pestiIndex: 0,
    pestiName: '', pestiCas: '', pestiSafe: '',
    pestiDays: '',
    opMsg: '', opOk: false,
    pstMsg: '', pstOk: false,
    submitting: false
  },

  onLoad() {
    if (!voiceManager) return;
    voiceManager.onStop = res => {
      const text = String((res && res.result) || '').trim();
      this.setData({ recording: false });
      if (!text) {
        wx.showToast({ title: '没听清，请再说一次', icon: 'none' });
        return;
      }
      const merged = (this.data.remark ? this.data.remark + ' ' : '') + text;
      this.setData({ remark: merged });
    };
    voiceManager.onError = () => {
      this.setData({ recording: false });
      wx.showToast({ title: '语音识别失败，请手动输入', icon: 'none' });
    };
    this.setData({ voiceAvailable: true });
  },

  startVoice() {
    if (!voiceManager || this.data.recording) return;
    this.setData({ recording: true });
    voiceManager.start({ duration: 60000, lang: 'zh_CN' });
  },

  stopVoice() {
    if (!voiceManager || !this.data.recording) return;
    voiceManager.stop();
  },

  onShow() {
    this.setData({ fontClass: font.fontClass() });
    if (!this.data.plots.length) this.loadMeta();
    else this.applyPendingPlot();
  },

  // 从待办「去填报」进来时，自动选中对应地块
  applyPendingPlot() {
    const id = Number(wx.getStorageSync('formPlotId') || 0);
    if (!id) return;
    wx.removeStorageSync('formPlotId');
    const plots = this.data.plots || [];
    for (let i = 0; i < plots.length; i++) {
      if (Number(plots[i].id) === id) {
        this.setData({ plotIndex: i });
        return;
      }
    }
  },

  loadMeta() {
    Promise.all([api.request('/api/plots'), api.request('/api/pesticides')])
      .then(res => {
        const plots = res[0] || [];
        const pesticides = res[1] || [];
        const first = pesticides[0] || {};
        this.setData({
          plots: plots,
          plotNames: plots.map(p => p.name + '（' + p.variety + '）'),
          pesticides: pesticides,
          pesticideNames: pesticides.map(p => p.name + '（' + p.category + '）'),
          pestiName: first.name || '',
          pestiCas: first.cas_no || '',
          pestiSafe: first.safe_interval_days || ''
        });
        this.applyPendingPlot();
      })
      .catch(err => this.setData({ opMsg: err.message, opOk: false }));
  },

  onPlotChange(e) { this.setData({ plotIndex: Number(e.detail.value) }); },
  onOpTypeChange(e) { this.setData({ opIndex: Number(e.detail.value) }); },
  onOperatorInput(e) { this.setData({ operator: e.detail.value }); },
  onRemarkInput(e) { this.setData({ remark: e.detail.value }); },
  onPestiChange(e) {
    const idx = Number(e.detail.value);
    const p = this.data.pesticides[idx] || {};
    this.setData({
      pestiIndex: idx,
      pestiName: p.name || '',
      pestiCas: p.cas_no || '',
      pestiSafe: p.safe_interval_days || ''
    });
  },
  onPestiDaysInput(e) { this.setData({ pestiDays: e.detail.value }); },

  submitOperation() {
    const plot = this.data.plots[this.data.plotIndex];
    if (!plot) return;
    this.setData({ submitting: true, opMsg: '' });
    api.request('/api/operations', 'POST', {
      plot_id: plot.id,
      operation_type: this.data.opTypes[this.data.opIndex],
      operator: this.data.operator || '果农',
      detail: { remark: this.data.remark }
    })
      .then(() => this.setData({
        submitting: false, opOk: true,
        opMsg: '农事记录已提交 ✅', remark: ''
      }))
      .catch(err => this.setData({ submitting: false, opOk: false, opMsg: err.message }));
  },

  submitPesticide() {
    const plot = this.data.plots[this.data.plotIndex];
    const pesti = this.data.pesticides[this.data.pestiIndex];
    if (!plot || !pesti) return;
    const body = {
      plot_id: plot.id,
      pesticide_name: pesti.name,
      cas_no: pesti.cas_no
    };
    if (this.data.pestiDays !== '') body.days_to_harvest = parseInt(this.data.pestiDays, 10);

    this.setData({ submitting: true, pstMsg: '' });
    api.request('/api/pesticide-records', 'POST', body)
      .then(r => this.setData({
        submitting: false,
        pstOk: !r.warning,
        pstMsg: (r.warning || '用药记录已提交') + '（最早可采收：' + r.earliest_harvest_date + '）',
        pestiDays: ''
      }))
      .catch(err => this.setData({ submitting: false, pstOk: false, pstMsg: err.message }));
  }
});
