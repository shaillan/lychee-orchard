const api = require('../../utils/api');
const font = require('../../utils/font');

const STATUS_TEXT = { pending: '待处置', handled: '已处置', ignored: '已忽略', false_positive: '误判' };
const STATUS_CLASS = { pending: 'critical', handled: 'good', ignored: 'neutral', false_positive: 'neutral' };

// suggestion_json 是字符串，老记录可能为空，解析失败要兜底成 {}
function parseSuggestion(r) {
  if (r && r.suggestion && typeof r.suggestion === 'object') return r.suggestion;
  try { return JSON.parse((r && r.suggestion_json) || '{}') || {}; } catch (e) { return {}; }
}

function decorateHistory(r) {
  const s = parseSuggestion(r);
  return Object.assign({}, r, {
    suggestion: s,
    pestName: r.detected_class || s.pest_class || '未知',
    plotName: r.plot_name || '未指定地块',
    confidencePct: Math.round((Number(r.confidence) || 0) * 100),
    statusText: STATUS_TEXT[r.status] || r.status,
    statusClass: STATUS_CLASS[r.status] || 'neutral',
    pending: !r.status || r.status === 'pending',
    timeText: String(r.created_at || '').replace('T', ' ').slice(0, 16)
  });
}

const HEALTHY = ['健康叶片', '健康果实'];

// 巡园接口不可用时的本地兜底：结构与后端 patrol.build_patrol_report 对齐
function localPatrol(patrolId, results, plots) {
  const names = {};
  (plots || []).forEach(p => { names[p.id] = p.name; });
  const counts = {};
  const byPlot = {};
  (results || []).forEach(r => {
    const cls = r.pest_class || r.detected_class || '无法判断';
    if (HEALTHY.indexOf(cls) >= 0) return;
    counts[cls] = (counts[cls] || 0) + 1;
    const pid = r.plot_id;
    if (pid) byPlot[pid] = (byPlot[pid] || 0) + 1;
  });
  const by_class = Object.keys(counts)
    .map(k => ({ class: k, count: counts[k] }))
    .sort((a, b) => b.count - a.count);
  const by_plot = Object.keys(byPlot)
    .map(k => ({ plot_id: Number(k), plot_name: names[k] || ('地块 ' + k), count: byPlot[k] }))
    .sort((a, b) => b.count - a.count);
  const total = by_class.reduce((sum, e) => sum + e.count, 0);
  const parts = by_class.slice(0, 3).map(e => e.class + ' ' + e.count + ' 处').join('、');
  return {
    patrol_id: patrolId,
    total: total,
    by_class: by_class,
    by_plot: by_plot,
    focus_plot: by_plot[0] || null,
    summary: total ? '本次巡园 ' + total + ' 处异常：' + parts : '本次巡园未发现异常',
    advice: []
  };
}

function decorate(r) {
  const s = r.suggestion || {};
  let riskClass = 'neutral';
  if (s.kind === '无异常') riskClass = 'good';
  else if (s.risk === '高') riskClass = 'critical';
  else if (s.risk === '中高') riskClass = 'serious';
  else if (s.risk === '中') riskClass = 'warning';

  const rawSource = String(r.source || '').split('#')[0];  // 丢掉 #confirm_false 内部后缀
  let sourceLabel = '本地模拟（未配置 AI Key）';
  if (rawSource === 'demo') sourceLabel = '演示模式';
  else if (rawSource.indexOf('mock_fallback') === 0) sourceLabel = '云端调用失败，已降级本地模拟';
  else if (!r.is_mock) sourceLabel = '云端 AI · ' + rawSource;

  const ra = s.recommended_action || 'none';
  const actionLabels = { pesticide: '按建议用药', operation: '人工清除', ignore: '观察（暂不处理）', none: '无需处置' };
  const btnCls = a => (a === ra ? 'btn' : 'btn ghost');
  const diff = s.differential || {};
  const verifyStatus = (s.verification || {}).status || '';
  const VERIFY_TEXT = { confirmed: '已通过', rejected: '未通过，已降级', unavailable: '复核不可用（保留首轮）' };

  return Object.assign({}, r, {
    confidencePct: Math.round((Number(r.confidence) || 0) * 100),
    riskClass: riskClass,
    sourceLabel: sourceLabel,
    hostPartsText: (s.host_parts || []).join('、'),
    peakText: (s.peak_months || []).join('、'),
    monitoringText: s.monitoring || '',
    biological: s.biological || [],
    kbName: (s.kind === '虫害' || s.kind === '病害') ? (s.pest_class || r.pest_class || '') : '',
    confusableText: (diff.confusable || []).join('、'),
    distinguishingText: (diff.distinguishing || []).join('；'),
    nonChemical: s.non_chemical || [],
    verificationText: VERIFY_TEXT[verifyStatus] || '',
    verificationClass: verifyStatus === 'confirmed' ? 'good' : (verifyStatus === 'rejected' ? 'serious' : 'neutral'),
    pesticides: s.pesticides || [],
    warnings: s.warnings || [],
    pending: !r.status || r.status === 'pending',
    handleTip: '',
    recommendedAction: ra,
    actionLabel: actionLabels[ra] || '',
    actionReason: s.action_reason || '',
    showActions: ra !== 'none',
    pesticideBtnClass: btnCls('pesticide'),
    operationBtnClass: btnCls('operation'),
    ignoreBtnClass: btnCls('ignore')
  });
}

Page({
  data: {
    fontClass: '',
    plots: [], plotNames: [], plotIndex: 0,
    pests: [], pestNames: [], pestIndex: 0,
    days: '', preview: '', loading: false, handling: false, error: '', result: null,
    patrol: null, patrolProgress: '',
    correcting: false, correctOptions: [], correctIndex: 0,
    history: []
  },

  onShow() {
    this.setData({ fontClass: font.fontClass() });
    if (!this.data.plots.length) this.loadMeta();
    this.loadHistory();
  },

  loadHistory() {
    api.request('/api/recognitions?limit=20')
      .then(rows => {
        const list = (rows || []).map(decorateHistory);
        list.sort((a, b) => (a.pending ? 0 : 1) - (b.pending ? 0 : 1));
        this.setData({ history: list });
        if (wx.getStorageSync('focusHistory')) {
          wx.removeStorageSync('focusHistory');
          setTimeout(() => wx.pageScrollTo({
            selector: '#historyCard', duration: 200, fail: () => {}
          }), 80);
        }
      })
      .catch(() => {});
  },

  openHistory(e) {
    const row = this.data.history[e.currentTarget.dataset.index];
    if (!row) return;
    if (!row.pending) {
      wx.showToast({ title: '该记录' + row.statusText, icon: 'none' });
      return;
    }
    const s = row.suggestion && row.suggestion.pest_class
      ? row.suggestion
      : Object.assign({}, row.suggestion, { pest_class: row.pestName });
    const result = decorate(Object.assign({}, row, {
      pest_class: row.detected_class || s.pest_class,
      suggestion: s
    }));
    this.setData({ result: result, handling: false, error: '' });
    wx.pageScrollTo({ selector: '#resultCard', duration: 200, fail: () => {} });
  },

  loadMeta() {
    Promise.all([api.request('/api/plots'), api.request('/api/pests')])
      .then(res => {
        const plots = res[0] || [];
        const pests = res[1] || [];
        const pestNames = pests.map(p => p.name);
        this.setData({
          plots: plots,
          plotNames: plots.map(p => p.name + '（' + p.variety + '）'),
          pests: pests,
          pestNames: pestNames,
          // 纠错选项：第 0 项表示只标记误判、不提供正确类别
          correctOptions: ['不确定（仅标记误判）'].concat(pestNames)
        });
      })
      .catch(err => this.setData({ error: err.message }));
  },

  openKb() {
    wx.navigateTo({ url: '/pages/kb/kb' });
  },

  openKbDetail(e) {
    const name = e.currentTarget.dataset.name;
    if (!name) return;
    wx.navigateTo({ url: '/pages/kb-detail/kb-detail?name=' + encodeURIComponent(name) });
  },

  onPlotChange(e) { this.setData({ plotIndex: Number(e.detail.value) }); },
  onPestChange(e) { this.setData({ pestIndex: Number(e.detail.value) }); },
  onDaysInput(e) { this.setData({ days: e.detail.value }); },

  choosePhoto() {
    if (this.data.loading) return;
    wx.chooseMedia({
      count: 9,   // 选 1 张走单张识别，多张自动进入巡园模式
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      sizeType: ['compressed'],
      success: res => {
        const files = (res.tempFiles || []).map(f => f.tempFilePath).filter(Boolean);
        if (!files.length) return;
        if (files.length > 1) {
          this.runPatrol(files);
          return;
        }
        const path = files[0];
        this.setData({ preview: path, result: null, patrol: null, error: '' });
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

    this.setData({ loading: true, error: '', patrol: null });
    api.upload('/api/recognitions', path, formData)
      .then(r => {
        this.setData({ result: decorate(r), loading: false });
        this.loadHistory();
      })
      .catch(err => this.setData({ error: err.message, loading: false }));
  },

  // 连拍巡园：串行上传（每张独立请求），单张失败不中断，结束后聚合一份现场报告
  runPatrol(paths) {
    const patrolId = 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    const plot = this.data.plots[this.data.plotIndex];
    const base = { patrol_id: patrolId };
    if (plot) base.plot_id = String(plot.id);
    if (this.data.days !== '') base.days_to_harvest = String(this.data.days);

    const results = [];
    const failures = [];
    let done = 0;
    this.setData({
      loading: true, error: '', result: null, preview: '', patrol: null,
      patrolProgress: '正在识别 0/' + paths.length
    });

    const step = index => {
      if (index >= paths.length) {
        this.finishPatrol(patrolId, results, failures);
        return;
      }
      const onReady = file => {
        api.upload('/api/recognitions', file, base)
          .then(r => results.push(r))
          .catch(err => failures.push({ index: index + 1, message: err.message }))
          .then(() => {
            done += 1;
            this.setData({ patrolProgress: '正在识别 ' + done + '/' + paths.length });
            step(index + 1);
          });
      };
      wx.compressImage({
        src: paths[index],
        quality: 70,
        compressedWidth: 1080,
        success: c => onReady(c.tempFilePath),
        fail: () => onReady(paths[index])
      });
    };
    step(0);
  },

  finishPatrol(patrolId, results, failures) {
    const local = localPatrol(patrolId, results, this.data.plots);
    api.request('/api/patrols/' + encodeURIComponent(patrolId))
      .then(report => this.applyPatrol(report, failures))
      .catch(() => this.applyPatrol(local, failures))
      .then(() => this.loadHistory());
  },

  applyPatrol(report, failures) {
    const byClass = (report.by_class || []).map(e => ({
      name: e.class,
      count: e.count,
      risk: e.risk || '',
      riskClass: e.risk === '高' ? 'critical'
        : (e.risk === '中高' ? 'serious' : (e.risk === '中' ? 'warning' : 'neutral'))
    }));
    const byPlot = report.by_plot || [];
    this.setData({
      loading: false,
      patrolProgress: '',
      patrol: {
        summary: report.summary || '',
        total: report.total || 0,
        byClass: byClass,
        byPlot: byPlot,
        focusText: report.focus_plot
          ? report.focus_plot.plot_name + '（' + report.focus_plot.count + ' 处）' : '',
        advice: (report.advice || []).slice(0, 3),
        failures: failures || [],
        failureText: failures && failures.length
          ? failures.length + ' 张识别失败（第 ' + failures.map(f => f.index).join('、') + ' 张）'
          : ''
      }
    });
  },

  runDemo() {
    const pest = this.data.pests[this.data.pestIndex];
    if (!pest) return;
    const body = { pest_class: pest.name };
    const plot = this.data.plots[this.data.plotIndex];
    if (plot) body.plot_id = plot.id;
    if (this.data.days !== '') body.days_to_harvest = parseInt(this.data.days, 10);

    this.setData({ loading: true, error: '', result: null, preview: '', patrol: null });
    api.request('/api/recognitions/demo', 'POST', body)
      .then(r => {
        this.setData({ result: decorate(r), loading: false });
        this.loadHistory();
      })
      .catch(err => this.setData({ error: err.message, loading: false }));
  },

  handleRecognition(e) {
    const r = this.data.result;
    if (!r || this.data.handling) return;
    const method = e.currentTarget.dataset.method;
    // 误判先展开纠错面板：选了实际类别才形成可回流的纠错样本
    if (method === 'false_positive') {
      const options = (this.data.correctOptions || []).length
        ? this.data.correctOptions
        : ['不确定（仅标记误判）', '无法判断'];
      this.setData({ correcting: true, correctIndex: 0, correctOptions: options });
      return;
    }
    const body = { method };
    if (method === 'pesticide') {
      const p = (r.suggestion && r.suggestion.pesticides || [])[0];
      if (!p) {
        wx.showToast({ title: '没有可用的推荐药剂', icon: 'none' });
        return;
      }
      body.pesticide_name = p.name;
      body.cas_no = p.cas_no;
      body.dosage = p.dosage_hint || '';
    } else if (method === 'operation') {
      body.operation_type = '人工清除';
      body.detail = { method: '人工清除', detected_class: r.pest_class };
    } else {
      body.note = '暂不处理';
    }
    this.submitHandle(body);
  },

  onCorrectChange(e) {
    this.setData({ correctIndex: Number(e.detail.value) });
  },

  cancelCorrect() {
    this.setData({ correcting: false });
  },

  submitCorrect() {
    const r = this.data.result;
    if (!r || this.data.handling) return;
    const idx = Number(this.data.correctIndex) || 0;
    const body = { method: 'false_positive', note: '人工判定为误判' };
    // idx=0 只标记误判；其余把人工判定的真实类别一并回传
    if (idx > 0) body.actual_class = this.data.correctOptions[idx];
    this.submitHandle(body);
  },

  submitHandle(body) {
    const r = this.data.result;
    if (!r || this.data.handling) return;
    this.setData({ handling: true });
    wx.showLoading({ title: body.method === 'false_positive' ? '提交纠错' : '提交处置' });
    api.request('/api/recognitions/' + r.id + '/handle', 'POST', body)
      .then(res => {
        wx.hideLoading();
        let tip = '';
        if (res.summary && res.summary.safe_interval_days) {
          tip = res.summary.pesticide_name + ' · 安全间隔期 ' + res.summary.safe_interval_days +
            ' 天，' + res.summary.earliest_harvest_date + ' 之后方可采收';
        } else if (res.summary && res.summary.operation_type) {
          tip = res.summary.operation_type + ' · ' + res.summary.operation_date;
        } else if (res.actual_class) {
          tip = '已记录纠错：' + (res.detected_class || r.pest_class) + ' → ' + res.actual_class;
        }
        this.setData({
          handling: false,
          correcting: false,
          result: Object.assign({}, r, { status: res.status, pending: false, handleTip: tip })
        });
        wx.showToast({ title: body.method === 'false_positive' ? '已记录' : '已处置', icon: 'success' });
        this.loadHistory();
      })
      .catch(err => {
        wx.hideLoading();
        this.setData({ handling: false });
        wx.showToast({ title: err.message || '处置失败', icon: 'none' });
      });
  }
});
