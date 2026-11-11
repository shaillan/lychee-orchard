/* ---------------------------------------------------------------------------
   果农端 H5 —— 与小程序功能、布局、文案一一对应。
   设计目标：评委在浏览器里打开 H5 时，看到的是同一套产品，而不是另一套界面。
   只依赖原生浏览器能力 + 后端 REST API，无构建链。
   --------------------------------------------------------------------------- */
(function () {
  'use strict';

  /* =========================================================================
     一、基础设施
     ========================================================================= */
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'
  }[c]));

  const TAB_VIEWS = ['todo', 'plots', 'scan', 'form'];
  const TITLES = {
    todo: '智慧果园管家', plots: '智慧果园管家', scan: '智慧果园管家', form: '智慧果园管家',
    plot: '地块档案', trace: '品质溯源', batches: '批次二维码', kb: '病虫害知识库', kbDetail: '知识库'
  };

  function today() {
    const d = new Date();
    const pad = n => (n < 10 ? '0' + n : '' + n);
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  }
  const pct = v => Math.round((Number(v) || 0) * 100);

  function toast(msg) {
    const el = $('#toast');
    el.textContent = msg || '';
    el.classList.add('show');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove('show'), 1800);
  }

  // 可输入原因的模态框：作废台账时用，替代 window.prompt
  function askModal(title, placeholder) {
    return new Promise(resolve => {
      $('#modalTitle').textContent = title;
      const input = $('#modalInput');
      input.placeholder = placeholder || '';
      input.value = '';
      $('#modalMask').classList.remove('hidden');
      setTimeout(() => input.focus(), 50);
      const done = value => {
        $('#modalMask').classList.add('hidden');
        $('#modalOk').onclick = null;
        $('#modalCancel').onclick = null;
        input.onkeydown = null;
        resolve(value);
      };
      $('#modalOk').onclick = () => done(input.value.trim());
      $('#modalCancel').onclick = () => done(null);
      input.onkeydown = e => { if (e.key === 'Enter') done(input.value.trim()); };
    });
  }

  // 统一超时：普通接口 10 秒，图片识别要等云端 AI + 二次确认，单独放宽到 120 秒。
  // 自己建 AbortController 而不是 AbortSignal.timeout，便于把超时翻译成人话。
  function fetchT(url, opts, timeoutMs) {
    const ms = timeoutMs || 10000;
    let signal;
    let timer = null;
    if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
      signal = AbortSignal.timeout(ms);
    } else {
      const c = new AbortController();
      timer = setTimeout(() => c.abort(), ms);
      signal = c.signal;
    }
    return fetch(url, Object.assign({}, opts || {}, { signal }))
      .catch(err => {
        if (err && (err.name === 'AbortError' || err.name === 'TimeoutError')) {
          throw new Error('请求超时（超过 ' + Math.round(ms / 1000) + ' 秒），请检查网络后重试');
        }
        if (err && err.name === 'TypeError' && /fetch/i.test(err.message || '')) {
          throw new Error('无法连接服务器，请确认后端已启动（run.py）');
        }
        throw err;
      })
      .finally(() => { if (timer) clearTimeout(timer); });
  }

  async function readError(r) {
    try {
      const data = await r.json();
      const detail = data && data.detail;
      if (typeof detail === 'string') return detail;
      if (Array.isArray(detail)) return detail.map(d => d.msg || JSON.stringify(d)).join('；');
    } catch (e) { /* 非 JSON 响应 */ }
    return 'HTTP ' + r.status;
  }

  const api = {
    async get(url) {
      const r = await fetchT(url);
      if (!r.ok) throw new Error(await readError(r));
      return r.json();
    },
    async send(url, method, body, timeoutMs) {
      const r = await fetchT(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body)
      }, timeoutMs);
      if (!r.ok) throw new Error(await readError(r));
      return r.json();
    },
    post(url, body, timeoutMs) { return this.send(url, 'POST', body || {}, timeoutMs); },
    put(url, body, timeoutMs) { return this.send(url, 'PUT', body || {}, timeoutMs); },
    // 识别图片：单张也要 5~40 秒（云端多模态 + 二次确认），给足 120 秒
    async upload(url, blob, fields, timeoutMs) {
      const fd = new FormData();
      fd.append('file', blob, 'photo.jpg');
      Object.keys(fields || {}).forEach(k => {
        const v = fields[k];
        if (v !== '' && v != null) fd.append(k, v);
      });
      const r = await fetchT(url, { method: 'POST', body: fd }, timeoutMs || 120000);
      if (!r.ok) throw new Error(await readError(r));
      return r.json();
    }
  };

  function errorCard(message, retry) {
    const btn = retry ? `<button class="btn ghost small mt" onclick="${retry}">重试</button>` : '';
    return `<div class="card"><div class="error">${esc(message)}</div>${btn}</div>`;
  }

  function kv(k, v, cls) {
    return `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${cls ? `<span class="pill ${cls}">${esc(v)}</span>` : esc(v)}</span></div>`;
  }

  /* =========================================================================
     二、路由：hash 驱动，浏览器返回键可用
     ========================================================================= */
  let currentView = 'todo';

  function route() {
    const raw = decodeURIComponent((location.hash || '').replace(/^#\/?/, ''));
    const parts = raw.split('/');
    const view = parts[0] || 'todo';
    const param = parts.slice(1).join('/');
    showView(view, param);
  }

  function go(view, param) {
    const hash = '#/' + view + (param != null && param !== '' ? '/' + encodeURIComponent(param) : '');
    if (location.hash === hash) { showView(view, String(param == null ? '' : param)); return; }
    location.hash = hash;
  }

  function showView(view, param) {
    const known = ['todo', 'plots', 'scan', 'form', 'plot', 'trace', 'batches', 'kb', 'kbDetail'];
    if (known.indexOf(view) < 0) { go('todo'); return; }
    currentView = view;

    $$('.view').forEach(v => v.classList.add('hidden'));
    const el = $('#view-' + view);
    if (el) el.classList.remove('hidden');

    const isTab = TAB_VIEWS.indexOf(view) >= 0;
    $('#tabbar').classList.toggle('hidden', !isTab);
    $('#content').classList.toggle('no-tab', !isTab);
    $('#navBack').classList.toggle('hidden', isTab);
    $('#navTitle').textContent = TITLES[view] || '智慧果园管家';
    $('#navbar').classList.toggle('home', view === 'todo');
    $('#navSubtitle').classList.toggle('hidden', view !== 'todo');
    $$('.tabbar button').forEach(b => b.classList.toggle('active', b.dataset.tab === view));

    stopVoice();
    const renderers = {
      todo: renderTodo,
      plots: renderPlots,
      plot: () => renderPlot(param),
      scan: renderScan,
      form: renderForm,
      trace: () => renderTrace(param),
      batches: renderBatches,
      kb: renderKb,
      kbDetail: () => renderKbDetail(param)
    };
    const fn = renderers[view];
    if (fn) Promise.resolve(fn()).catch(err => {
      if (el) el.innerHTML = errorCard(err.message || '页面加载失败');
    });
  }

  /* =========================================================================
     三、公共数据（地块 / 病虫害 / 农药库）
     ========================================================================= */
  let plotsCache = null;
  let pestsCache = null;
  let pesticidesCache = null;

  async function loadPlots(force) {
    if (!plotsCache || force) plotsCache = await api.get('/api/plots');
    return plotsCache;
  }
  async function loadPests(force) {
    if (!pestsCache || force) pestsCache = await api.get('/api/pests');
    return pestsCache;
  }
  async function loadPesticides(force) {
    if (!pesticidesCache || force) pesticidesCache = await api.get('/api/pesticides');
    return pesticidesCache;
  }

  /* =========================================================================
     四、今日待办
     ========================================================================= */
  let pendingFormPlot = 0;

  async function renderTodo() {
    const el = $('#view-todo');
    const bigFont = localStorage.getItem('fontLarge') === '1';
    el.innerHTML = `
      <div class="quick">
        <a class="quick-item" href="/dashboard"><span class="qi">📊</span><span>数据看板</span></a>
        <div class="quick-item" onclick="go('batches')"><span class="qi">▣</span><span>批次二维码</span></div>
        <a class="quick-item" href="/trace"><span class="qi">⌕</span><span>品质溯源</span></a>
        <div class="quick-item" onclick="go('kb')"><span class="qi">📚</span><span>知识库</span></div>
      </div>

      <div class="h2">今日待办</div>
      <div id="todoList" class="muted small">加载中…</div>

      <div class="card">
        <div class="kv" style="align-items:center;border-bottom:none;padding:0">
          <div>
            <div class="h2" style="margin:0">大字模式</div>
            <div class="small muted">放大字号，方便田间查看</div>
          </div>
          <label class="switch">
            <input type="checkbox" id="fontSwitch" ${bigFont ? 'checked' : ''}>
            <span class="slider"></span>
          </label>
        </div>
      </div>

      <div class="card">
        <div class="h2" style="margin:0">天气地区</div>
        <div class="small muted">天气预警按此地区生成，H5 与小程序共用</div>
        <div class="kv mt"><span class="k">当前地区</span><span class="v" id="regionLabel">加载中…</span></div>
        <div class="field mt">
          <span class="label">地区名（如 广州）</span>
          <input id="regionInput" placeholder="输入城市名">
        </div>
        <div class="btn block" id="regionBtn" onclick="saveRegion()">保存地区</div>
        <div id="regionMsg" class="mt"></div>
      </div>`;

    $('#fontSwitch').onchange = e => {
      const on = e.target.checked;
      localStorage.setItem('fontLarge', on ? '1' : '0');
      applyFont();
    };

    loadRegion();
    try {
      const items = await api.get('/api/todos');
      const box = $('#todoList');
      if (!items || !items.length) {
        box.innerHTML = '<div class="card empty">今日暂无待办，果园状态正常</div>';
        return;
      }
      box.innerHTML = items.map(i => {
        let btn = '';
        if (i.type === 'recognition') {
          btn = '<div class="btn ghost small mt" style="display:inline-flex" onclick="goRecognition()">去处置</div>';
        } else if (i.type === 'weather') {
          btn = '<div class="btn ghost small mt" style="display:inline-flex" onclick="go(\'scan\')">去拍照识别</div>';
        } else if (i.action) {
          btn = `<div class="btn ghost small mt" style="display:inline-flex" onclick="todoAction('${esc(i.type || '')}', ${Number(i.plot_id) || 0})">${esc(i.action)}</div>`;
        }
        return `<div class="alert ${esc(i.level || '')}">
          <div class="al-title">${esc(i.title)}</div>
          <div class="al-detail">${esc(i.detail)}</div>
          ${btn}
        </div>`;
      }).join('');
    } catch (e) {
      $('#todoList').innerHTML = `<div class="card error">${esc(e.message)}</div>`;
    }
  }

  async function loadRegion() {
    const now = $('#regionLabel');
    if (!now) return;
    try {
      const info = await api.get('/api/weather/region');
      const r = info.region || {};
      now.textContent = (r.label || r.name || '未设置') + (r.source === 'db' ? '（自定义）' : '（默认）');
    } catch (e) {
      now.textContent = '地区信息加载失败';
    }
  }

  async function saveRegion() {
    const name = ($('#regionInput').value || '').trim();
    const msg = $('#regionMsg');
    if (!name) { msg.innerHTML = '<div class="alert critical"><div class="al-detail">请输入地区名</div></div>'; return; }
    const btn = $('#regionBtn');
    btn.disabled = true;
    msg.innerHTML = '<div class="small muted">解析并保存中…</div>';
    try {
      const res = await api.put('/api/weather/region', { name });
      const r = res.region || {};
      $('#regionInput').value = '';
      msg.innerHTML = `<div class="alert good"><div class="al-detail">已设置：${esc(r.label || r.name)}</div></div>`;
      await loadRegion();
    } catch (e) {
      msg.innerHTML = `<div class="alert critical"><div class="al-detail">${esc(e.message)}</div></div>`;
    } finally { btn.disabled = false; }
  }

  function quickScan() {
    if (navigator.mediaDevices && window.BarcodeDetector) {
      toast('请在下方输入溯源码，或使用手机相机扫码打开');
    } else {
      toast('当前浏览器不支持扫码，请手动输入溯源码');
    }
    go('trace');
  }

  function goRecognition() {
    sessionStorage.setItem('focusHistory', '1');
    go('scan');
  }

  function todoAction(type, plotId) {
    if (type === 'safety' || type === 'harvest' || type === 'crack') {
      plotId ? go('plot', plotId) : go('plots');
      return;
    }
    if (type === 'operation') {
      pendingFormPlot = plotId;
      go('form');
      return;
    }
    if (type === 'batch' || type === 'coldchain' || type === 'residue') {
      go('batches');
      return;
    }
    toast('暂不支持该操作');
  }

  /* =========================================================================
     五、我的果园（分区图 + 卡片就地展开）
     ========================================================================= */
  const plotsState = { expandedId: 0, detail: null, loading: false, error: '' };

  async function renderPlots() {
    const el = $('#view-plots');
    el.innerHTML = '<div class="card muted">加载中…</div>';
    try { await loadPlots(true); }
    catch (e) { el.innerHTML = errorCard(e.message, 'renderPlots()'); return; }
    plotsState.expandedId = 0;
    plotsState.detail = null;
    paintPlots();
  }

  function paintPlots() {
    const el = $('#view-plots');
    const rows = plotsCache || [];
    if (!rows.length) {
      el.innerHTML = '<div class="card empty">还没有地块档案</div>';
      return;
    }
    const zones = rows.map(p => `
      <div class="zone ${p.safety && p.safety.safe ? 'z-good' : 'z-warn'}" data-zone="${p.id}">
        <div class="z-code">${esc(p.code || p.name)}</div>
        <div class="z-name">${esc(p.variety || '')}</div>
        <div class="z-tree">${p.tree_count || 0} 株</div>
      </div>`).join('');

    const cards = rows.map(p => {
      const s = p.safety || {};
      const safe = !!s.safe;
      const m = p.maturity || {};
      const safeText = safe ? '可采收' : ('还需 ' + (s.remaining_days == null ? '—' : s.remaining_days) + ' 天');
      const safeCls = safe ? 'good' : 'critical';
      const mCls = m.status === '最佳' ? 'good' : (m.status === '已过' ? 'critical' : (m.status === '临近' ? 'warning' : 'neutral'));
      const expanded = plotsState.expandedId === p.id;
      return `<div class="card" id="plot-${p.id}" data-plot="${p.id}">
        <div class="card-head">
          <span class="title">${esc(p.name)}</span>
          <span class="pill ${safeCls}"><span class="pdot"></span>${esc(safeText)}</span>
        </div>
        ${m.status ? `<div class="mt"><span class="pill ${mCls}"><span class="pdot"></span>采收期：${esc(m.status)}</span></div>` : ''}
        ${kv('品种', p.variety)}
        ${kv('面积 / 株数', `${p.area_mu} 亩 · ${p.tree_count} 株`)}
        ${kv('定植年份', p.planting_year)}
        ${kv('位置', p.location)}
        ${expanded ? plotDetailHtml(p) : '<div class="pd-hint">点击查看农事 / 用药记录</div>'}
        ${expanded ? `<div class="pd-more" data-id="${p.id}">查看完整档案（产量趋势）›</div>` : ''}
      </div>`;
    }).join('');

    el.innerHTML = `<div class="h2">果树分区</div><div class="zone-map">${zones}</div>
      <div class="h2 mt">地块档案</div>${cards}`;

    el.onclick = e => {
      const more = e.target.closest('.pd-more');
      if (more) { go('plot', more.dataset.id); return; }
      if (e.target.closest('.pd')) return;
      const zone = e.target.closest('[data-zone]');
      if (zone) { togglePlot(Number(zone.dataset.zone), true); return; }
      const card = e.target.closest('[data-plot]');
      if (card) togglePlot(Number(card.dataset.plot), false);
    };
  }

  function plotDetailHtml() {
    if (plotsState.loading) return '<div class="pd"><div class="pd-tip">记录加载中…</div></div>';
    if (plotsState.error) return `<div class="pd"><div class="pd-tip err">${esc(plotsState.error)}</div></div>`;
    const d = plotsState.detail;
    if (!d) return '';
    const ops = (d.ops || []).length
      ? d.ops.map(o => `<div class="list-item"><div class="li-main">
          <div class="li-title">${esc(o.operation_type)}</div>
          <div class="li-desc">${esc(o.operator)} · ${esc(o.operation_date)}</div>
        </div></div>`).join('')
      : '<div class="pd-tip">暂无农事记录</div>';
    const psts = (d.psts || []).length
      ? d.psts.map(r => `<div class="list-item"><div class="li-main">
          <div class="li-title">${esc(r.pesticide_name)}</div>
          <div class="li-desc">${esc(r.apply_time)} · 安全间隔期 ${r.safe_interval_days} 天</div>
        </div></div>`).join('')
      : '<div class="pd-tip">暂无用药记录</div>';
    return `<div class="pd">
      ${d.safe ? '' : `<div class="alert critical mt"><div class="al-title">用药安全间隔期内</div><div class="al-detail">${esc(d.safetyMessage || '')}</div></div>`}
      <div class="pd-sec">最近农事记录</div>${ops}
      <div class="pd-sec">最近用药台账</div>${psts}
    </div>`;
  }

  async function togglePlot(id, scrollOnly) {
    if (plotsState.expandedId === id) {
      if (scrollOnly) { scrollToPlot(id); return; }
      plotsState.expandedId = 0;
      plotsState.detail = null;
      paintPlots();
      return;
    }
    plotsState.expandedId = id;
    plotsState.detail = null;
    plotsState.loading = true;
    plotsState.error = '';
    paintPlots();
    if (scrollOnly) scrollToPlot(id);
    try {
      const p = await api.get('/api/plots/' + id);
      if (plotsState.expandedId !== id) return;
      plotsState.detail = {
        id: p.id,
        safe: !!(p.safety && p.safety.safe),
        safetyMessage: (p.safety && p.safety.message) || '',
        ops: (p.operations || []).slice(0, 8),
        psts: (p.pesticides || []).slice(0, 5)
      };
    } catch (e) {
      if (plotsState.expandedId !== id) return;
      plotsState.error = e.message || '记录加载失败';
    }
    plotsState.loading = false;
    paintPlots();
  }

  function scrollToPlot(id) {
    setTimeout(() => {
      const card = document.getElementById('plot-' + id);
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 60);
  }

  /* =========================================================================
     六、地块完整档案（产量趋势 / 采收窗口 / 台账留痕）
     ========================================================================= */
  async function renderPlot(id) {
    const el = $('#view-plot');
    if (!id) { el.innerHTML = errorCard('缺少地块参数，请从「我的果园」重新进入'); return; }
    el.innerHTML = '<div class="card muted">加载中…</div>';
    const p = await api.get('/api/plots/' + id);
    $('#navTitle').textContent = p.name || '地块档案';

    const s = p.safety || {};
    const m = p.maturity || {};
    const mCls = m.status === '最佳' ? 'good' : (m.status === '已过' ? 'critical' : (m.status === '临近' ? 'warning' : 'neutral'));

    // 产量趋势：没填的年份高度给 0（不画柱），避免误导
    const raw = p.yields || [];
    let max = 1;
    raw.forEach(y => { max = Math.max(max, Number(y.actual_yield) || 0, Number(y.estimated_yield) || 0); });
    const bars = raw.map(y => {
      const actual = Number(y.actual_yield) || 0;
      const est = Number(y.estimated_yield) || 0;
      const actH = actual ? Math.max(4, Math.round(actual / max * 100)) : 0;
      const estH = est ? Math.max(4, Math.round(est / max * 100)) : 0;
      return `<div class="bar-col">
        <div class="bar-stack">
          ${estH ? `<div class="bar bar-est" style="height:${estH}%"></div>` : ''}
          ${actH ? `<div class="bar bar-act" style="height:${actH}%"></div>` : ''}
        </div>
        <div class="bar-season">${esc(y.season)}</div>
      </div>`;
    }).join('');

    let lastCheck = null;
    (p.operations || []).some(o => {
      if (o.operation_type !== '成熟度观察') return false;
      let d = {};
      try { d = JSON.parse(o.detail || '{}') || {}; } catch (e) { d = {}; }
      lastCheck = { ripeness: d.ripeness, note: d.note || '', date: o.operation_date, operator: o.operator || '' };
      return true;
    });

    const voidTag = o => o.voided_at ? '<span class="pill neutral void-pill">已作废</span>' : '';
    const voidNote = o => o.voided_at ? `<div class="li-desc">作废原因：${esc(o.void_reason || '')}</div>` : '';
    const ops = (p.operations || []).slice(0, 12).map(o => `
      <div class="list-item">
        <div class="li-main">
          <div class="li-title">${esc(o.operation_type)}${voidTag(o)}</div>
          <div class="li-desc">${esc(o.operator)} · ${esc(o.operation_date)}</div>
          ${voidNote(o)}
        </div>
        ${o.voided_at ? '' : `<div class="void-btn" onclick="voidRecord('op', ${o.id})">作废</div>`}
      </div>`).join('');
    const psts = (p.pesticides || []).slice(0, 8).map(r => `
      <div class="list-item">
        <div class="li-main">
          <div class="li-title">${esc(r.pesticide_name)}${voidTag(r)}</div>
          <div class="li-desc">${esc(r.apply_time)} · 安全间隔期 ${r.safe_interval_days} 天</div>
          ${voidNote(r)}
        </div>
        ${r.voided_at ? '' : `<div class="void-btn" onclick="voidRecord('pest', ${r.id})">作废</div>`}
      </div>`).join('');

    el.innerHTML = `
      <div class="card">
        <div class="card-head">
          <span class="title">${esc(p.name)}</span>
          <span class="pill ${s.safe ? 'good' : 'critical'}"><span class="pdot"></span>${s.safe ? '可采收' : '间隔期内'}</span>
        </div>
        ${kv('品种', p.variety)}
        ${kv('面积 / 株数', `${p.area_mu} 亩 · ${p.tree_count} 株`)}
        ${kv('位置', p.location)}
        ${s.safe ? '' : `<div class="alert critical mt"><div class="al-title">用药安全间隔期内</div><div class="al-detail">${esc(s.message || '')}</div></div>`}
      </div>

      ${m.window_start ? `<div class="card">
        <div class="card-head"><span class="title">采收窗口</span><span class="pill ${mCls}"><span class="pdot"></span>${esc(m.status)}</span></div>
        ${kv('最佳采收期', `${m.window_start} ~ ${m.window_end}`)}
        ${kv('当前物候期', m.phenology || '')}
        ${m.status === '临近' ? kv('距窗口开始', m.days_to_start + ' 天') : ''}
        ${m.status === '最佳' ? kv('窗口剩余', m.days_remaining + ' 天') : ''}
        ${m.status === '已过' ? kv('已过窗口', m.days_overdue + ' 天') : ''}
        ${m.label ? `<div class="small muted mt">${esc(m.label)}</div>` : ''}
      </div>` : ''}

      <div class="card">
        <div class="card-head">
          <span class="title">产量趋势（kg）</span>
          <span class="legend"><span class="lg-dot lg-act"></span>实际<span class="lg-dot lg-est"></span>预估</span>
        </div>
        ${raw.length ? `<div class="chart">${bars}</div>` : '<div class="empty">暂无产量记录</div>'}
      </div>

      ${lastCheck ? `<div class="card">
        <div class="card-head"><span class="title">最近成熟度观察</span></div>
        <div class="small muted">成熟度 ${lastCheck.ripeness == null ? '—' : esc(lastCheck.ripeness)}% · ${esc(lastCheck.date)} · ${esc(lastCheck.operator)}</div>
        ${lastCheck.note ? `<div class="small mt">${esc(lastCheck.note)}</div>` : ''}
      </div>` : ''}

      <div class="card"><div class="h2">最近农事记录</div>${ops || '<div class="muted small">暂无记录</div>'}</div>
      <div class="card"><div class="h2">最近用药台账</div>${psts || '<div class="muted small">暂无记录</div>'}</div>`;

    // 台账留痕：记录不能改也不能删，只能作废并留原因
    window.voidRecord = async (kind, recordId) => {
      const reason = await askModal('作废记录', '填写作废原因（如录入错误、重复记录）');
      if (reason === null) return;
      const url = kind === 'pest' ? '/api/pesticide-records/' + recordId + '/void'
        : '/api/operations/' + recordId + '/void';
      try {
        await api.post(url, { reason: reason || '未填写原因', operator: '果农' });
        toast('已作废');
        renderPlot(id);
      } catch (e) { toast(e.message || '作废失败'); }
    };
  }

  /* =========================================================================
     七、拍照识别
     ========================================================================= */
  const scanState = {
    plotId: '', days: '', preview: '', result: null, patrol: null,
    patrolProgress: '', error: '', busy: false, correcting: false,
    correctOptions: [], correctValue: '', history: []
  };
  const STATUS_TEXT = { pending: '待处置', handled: '已处置', ignored: '已忽略', false_positive: '误判' };
  const STATUS_CLASS = { pending: 'critical', handled: 'good', ignored: 'neutral', false_positive: 'neutral' };
  const HEALTHY = ['健康叶片', '健康果实'];

  async function renderScan() {
    const el = $('#view-scan');
    el.innerHTML = '<div class="card muted">加载中…</div>';
    try {
      await Promise.all([loadPlots(), loadPests()]);
    } catch (e) { el.innerHTML = errorCard(e.message, 'renderScan()'); return; }
    if (!scanState.correctOptions.length) {
      scanState.correctOptions = ['不确定（仅标记误判）'].concat((pestsCache || []).map(p => p.name));
    }
    paintScan();
    loadHistory();
  }

  function paintScan() {
    const el = $('#view-scan');
    const plots = plotsCache || [];
    const pestOpts = (pestsCache || []).map(p => `<option value="${esc(p.name)}" ${scanState.demoPest === p.name ? 'selected' : ''}>${esc(p.name)}（${esc(p.kind)}）</option>`).join('');
    const plotOpts = plots.map(p => `<option value="${p.id}" ${String(scanState.plotId) === String(p.id) ? 'selected' : ''}>${esc(p.name)}（${esc(p.variety)}）</option>`).join('');

    el.innerHTML = `
      <div class="card kb-entry" onclick="go('kb')">
        <div class="kb-entry-main">
          <div class="h2" style="margin:0">📚 病虫害知识库</div>
          <div class="small muted">18 种常见病虫害 · 症状、鉴别与防治要点</div>
        </div>
        <span class="picker-arrow">›</span>
      </div>

      <div class="card">
        <div class="h2">拍照识别病虫害</div>
        <div class="photo-box" id="photoBox" onclick="pickPhoto()">
          ${scanState.preview
            ? `<img class="photo" id="scanPreview" src="${scanState.preview}" alt="待识别照片">`
            : `<div class="photo-empty"><span class="cam">📷</span><span>点击拍照 / 从相册选择</span><span class="small muted">选多张自动巡园（最多 9 张），上传前压缩至 1080p</span></div>`}
        </div>
        <input type="file" id="scanFile" accept="image/*" multiple class="hidden">

        <div class="field mt">
          <span class="label">地块</span>
          <select id="scanPlot"><option value="">请选择地块</option>${plotOpts}</select>
        </div>
        <div class="field">
          <span class="label">距预计采收天数（可选，用于安全间隔期校验）</span>
          <input type="number" id="scanDays" value="${esc(scanState.days)}" placeholder="如 5 表示 5 天后采收">
        </div>

        ${scanState.busy
          ? '<div class="btn block" aria-disabled="true">识别中…</div><div class="small muted mt">云端识别通常 5–20 秒，请勿关闭页面</div>'
          : '<div class="btn block" onclick="pickPhoto()">拍照 / 选图识别</div>'}
        ${scanState.error ? `<div class="alert critical mt"><div class="al-detail">${esc(scanState.error)}</div></div>` : ''}
      </div>

      <div class="card">
        <div class="h2">演示模式（无需图片）</div>
        <div class="field">
          <span class="label">选择病虫害类别</span>
          <select id="demoPest">${pestOpts}</select>
        </div>
        <div class="btn ghost block" onclick="runDemo()">生成识别结果与防治建议</div>
      </div>

      <div id="resultBox">${scanState.result ? recognitionHtml(scanState.result) : ''}</div>

      ${scanState.patrolProgress ? `<div class="card muted">${esc(scanState.patrolProgress)}</div>` : ''}
      <div id="patrolBox">${scanState.patrol ? patrolHtml(scanState.patrol) : ''}</div>

      <div class="card" id="historyCard">
        <div class="head"><span class="title">识别记录</span><span class="pill neutral">${scanState.history.length} 条</span></div>
        <div id="historyList">${historyHtml()}</div>
      </div>`;

    const plotSel = $('#scanPlot');
    if (plotSel) plotSel.onchange = e => { scanState.plotId = e.target.value; };
    const daysInput = $('#scanDays');
    if (daysInput) daysInput.oninput = e => { scanState.days = e.target.value; };
    const demo = $('#demoPest');
    if (demo) demo.onchange = e => { scanState.demoPest = e.target.value; };
    const file = $('#scanFile');
    if (file) file.onchange = e => {
      const files = Array.from(e.target.files || []);
      if (files.length) onFilesPicked(files);
    };
    bindHistory();

    if (sessionStorage.getItem('focusHistory') === '1') {
      sessionStorage.removeItem('focusHistory');
      setTimeout(() => {
        const card = $('#historyCard');
        if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 80);
    }
  }

  function historyHtml() {
    if (!scanState.history.length) return '<div class="empty">暂无识别记录，先拍一张或试试演示模式</div>';
    return scanState.history.map((r, i) => `
      <div class="hist-item" data-hist="${i}">
        <div class="hist-main">
          <div class="hist-title">${esc(r.pestName)}</div>
          <div class="hist-meta">${esc(r.plotName)} · ${esc(r.timeText)} · 置信度 ${r.confidencePct}%</div>
        </div>
        <span class="pill ${r.statusClass}">${esc(r.statusText)}</span>
      </div>`).join('');
  }

  function bindHistory() {
    const list = $('#historyList');
    if (!list) return;
    list.onclick = e => {
      const item = e.target.closest('[data-hist]');
      if (!item) return;
      const row = scanState.history[Number(item.dataset.hist)];
      if (!row) return;
      if (!row.pending) { toast('该记录' + row.statusText); return; }
      scanState.result = decorateRecognition(row.raw);
      scanState.correcting = false;
      paintScan();
      const card = $('#resultCard');
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
  }

  async function loadHistory() {
    try {
      const rows = await api.get('/api/recognitions?limit=20');
      const list = (rows || []).map(decorateHistory);
      list.sort((a, b) => (a.pending ? 0 : 1) - (b.pending ? 0 : 1));
      scanState.history = list;
      const box = $('#historyList');
      if (box) { box.innerHTML = historyHtml(); bindHistory(); }
    } catch (e) { /* 识别记录加载失败不阻塞主流程 */ }
  }

  function parseSuggestion(r) {
    if (r && r.suggestion && typeof r.suggestion === 'object') return r.suggestion;
    try { return JSON.parse((r && r.suggestion_json) || '{}') || {}; } catch (e) { return {}; }
  }

  function decorateHistory(r) {
    const s = parseSuggestion(r);
    return {
      raw: r,
      pestName: r.detected_class || s.pest_class || '未知',
      plotName: r.plot_name || '未指定地块',
      confidencePct: pct(r.confidence),
      statusText: STATUS_TEXT[r.status] || r.status || '待处置',
      statusClass: STATUS_CLASS[r.status] || 'neutral',
      pending: !r.status || r.status === 'pending',
      timeText: String(r.created_at || '').replace('T', ' ').slice(0, 16)
    };
  }

  function decorateRecognition(r) {
    const s = parseSuggestion(r);
    if (!s.pest_class) s.pest_class = r.detected_class || '未知';
    let riskClass = 'neutral';
    if (s.kind === '无异常') riskClass = 'good';
    else if (s.risk === '高') riskClass = 'critical';
    else if (s.risk === '中高') riskClass = 'serious';
    else if (s.risk === '中') riskClass = 'warning';

    const rawSource = String(r.source || '').split('#')[0];
    let sourceLabel = '本地模拟（未配置 AI Key）';
    if (rawSource === 'demo') sourceLabel = '演示模式';
    else if (rawSource.indexOf('mock_fallback') === 0) sourceLabel = '云端调用失败，已降级本地模拟';
    else if (!r.is_mock) sourceLabel = '云端 AI · ' + rawSource;

    const diff = s.differential || {};
    const verifyStatus = (s.verification || {}).status || '';
    const VERIFY_TEXT = { confirmed: '已通过', rejected: '未通过，已降级', unavailable: '复核不可用（保留首轮）' };
    const ra = s.recommended_action || 'none';

    return {
      raw: r,
      suggestion: s,
      id: r.id,
      pestClass: s.pest_class || r.detected_class || '未知',
      confidencePct: pct(r.confidence),
      riskClass,
      sourceLabel,
      hostPartsText: (s.host_parts || []).join('、'),
      peakText: (s.peak_months || []).join('、'),
      monitoringText: s.monitoring || '',
      biological: s.biological || [],
      kbName: (s.kind === '虫害' || s.kind === '病害') ? (s.pest_class || '') : '',
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
      actionLabel: { pesticide: '按建议用药', operation: '人工清除', ignore: '观察（暂不处理）', none: '无需处置' }[ra] || '',
      actionReason: s.action_reason || '',
      showActions: ra !== 'none'
    };
  }

  function recognitionHtml(r) {
    const btnCls = a => (r.recommendedAction === a ? 'btn block mt' : 'btn ghost block mt');
    const pesticides = r.pesticides.map(p => `<span class="pill neutral">${esc(p.name)} · ${p.safe_interval_days}天</span>`).join(' ');
    const warns = r.warnings.map(w => `<div class="alert serious mt"><div class="al-detail">${esc(w)}</div></div>`).join('');

    let actions = '';
    if (r.pending && r.showActions) {
      actions = `<div class="small muted mt">识别后处置（形成闭环，处置记录回链本次识别）</div>
        ${r.pesticides.length ? `<div class="${btnCls('pesticide')}" onclick="handleRecognition('pesticide')">按建议用药${r.recommendedAction === 'pesticide' ? ' · 推荐' : ''}</div>` : ''}
        <div class="${btnCls('operation')}" onclick="handleRecognition('operation')">人工清除${r.recommendedAction === 'operation' ? ' · 推荐' : ''}</div>
        <div class="row mt">
          <div class="btn ghost" onclick="handleRecognition('false_positive')">误判</div>
          <div class="${r.recommendedAction === 'ignore' ? 'btn' : 'btn ghost'}" onclick="handleRecognition('ignore')">忽略${r.recommendedAction === 'ignore' ? ' · 推荐' : ''}</div>
        </div>`;
    } else if (r.pending) {
      actions = `<div class="row mt">
        <div class="btn ghost" onclick="handleRecognition('false_positive')">误判</div>
        <div class="btn ghost" onclick="handleRecognition('ignore')">忽略</div>
      </div>`;
    } else {
      actions = `<div class="mt"><span class="pill good">已处置</span></div>`;
    }

    const correction = (r.pending && scanState.correcting) ? `
      <div class="correct-box mt">
        <div class="small muted">实际类别（可选，选了才计入纠错样本，用于后续微调与评测）</div>
        <select class="picker-value" id="correctSelect">
          ${scanState.correctOptions.map((n, i) => `<option value="${i}">${esc(n)}</option>`).join('')}
        </select>
        <div class="row mt">
          <div class="btn ghost" onclick="cancelCorrect()">取消</div>
          <div class="btn" onclick="submitCorrect()">提交误判</div>
        </div>
      </div>` : '';

    return `<div class="card mt" id="resultCard">
      <div class="head">
        <span class="title">识别结果</span>
        <span class="pill ${r.riskClass}">${esc(r.pestClass)}</span>
      </div>
      ${kv('置信度', r.confidencePct + '%')}
      ${kv('风险等级', (r.suggestion.risk || '未知') + '（' + (r.suggestion.kind || '未知') + '）')}
      ${r.hostPartsText ? kv('危害部位', r.hostPartsText) : ''}
      ${r.peakText ? kv('高发期', r.peakText) : ''}
      ${kv('识别来源', r.sourceLabel)}
      ${r.verificationText ? `<div class="mt"><span class="pill ${r.verificationClass}">二次确认：${esc(r.verificationText)}</span></div>` : ''}

      <div class="pre mt">${esc(r.suggestion.text || '')}</div>

      ${r.confusableText ? `<div class="alert warning mt"><div class="al-title">易混淆：${esc(r.confusableText)}</div><div class="al-detail">${esc(r.distinguishingText)}</div></div>` : ''}
      ${r.nonChemical.length ? `<div class="alert good mt"><div class="al-title">非化学措施</div><div class="al-detail">${r.nonChemical.map(m => '· ' + esc(m)).join('<br>')}</div></div>` : ''}
      ${r.monitoringText ? `<div class="alert warning mt"><div class="al-title">监测要点</div><div class="al-detail">${esc(r.monitoringText)}</div></div>` : ''}
      ${r.biological.length ? `<div class="alert good mt"><div class="al-title">生物防治</div><div class="al-detail">${r.biological.map(m => '· ' + esc(m)).join('<br>')}</div></div>` : ''}
      ${pesticides ? `<div class="pills mt">${pesticides}</div>` : ''}
      ${warns}
      ${r.handleTip ? `<div class="alert good mt"><div class="al-title">已写入台账</div><div class="al-detail">${esc(r.handleTip)}</div></div>` : ''}
      ${r.pending && r.showActions ? `<div class="alert good mt"><div class="al-title">系统建议：${esc(r.actionLabel)}</div><div class="al-detail">${esc(r.actionReason)}</div></div>` : ''}
      ${actions}
      ${correction}
      ${r.kbName ? `<div class="btn ghost block mt" data-kbname="${esc(r.kbName)}" onclick="openKbDetail(this.dataset.kbname)">查看「${esc(r.kbName)}」知识库详情</div>` : ''}
    </div>`;
  }

  function patrolHtml(p) {
    const byClass = (p.byClass || []).map(i => `
      <div class="list-item">
        <div class="li-main"><div class="li-title">${esc(i.name)} · ${i.count} 处</div></div>
        ${i.risk ? `<span class="pill ${i.riskClass}">风险 ${esc(i.risk)}</span>` : ''}
      </div>`).join('');
    return `<div class="card">
      <div class="head"><span class="title">巡园报告</span><span class="pill ${p.total ? 'serious' : 'good'}">${p.total} 处异常</span></div>
      <div class="pre">${esc(p.summary)}</div>
      ${byClass ? `<div class="mt">${byClass}</div>` : ''}
      ${p.focusText ? `<div class="small mt">建议重点巡查：${esc(p.focusText)}</div>` : ''}
      ${p.byPlot && p.byPlot.length ? `<div class="small muted mt">${p.byPlot.map(i => esc(i.plot_name) + ' ' + i.count + ' 处').join(' · ')}</div>` : ''}
      ${(p.advice || []).slice(0, 3).map(a => `<div class="alert warning mt"><div class="al-title">${esc(a.class)} · 监测要点</div><div class="al-detail">${esc(a.monitoring)}</div></div>`).join('')}
      ${p.failureText ? `<div class="alert serious mt"><div class="al-detail">${esc(p.failureText)}，可重新拍这几张补识别</div></div>` : ''}
    </div>`;
  }

  function pickPhoto() {
    const input = $('#scanFile');
    if (input) input.click();
  }

  // H5 端压缩：长边 1080、JPEG 0.7，与小程序 wx.compressImage 对齐
  function compressImage(file, maxSide, quality) {
    return new Promise(resolve => {
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = () => {
        URL.revokeObjectURL(url);
        const scale = Math.min(1, (maxSide || 1080) / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement('canvas');
        canvas.width = w; canvas.height = h;
        canvas.getContext('2d').drawImage(img, 0, 0, w, h);
        canvas.toBlob(b => resolve(b || file), 'image/jpeg', quality || 0.7);
      };
      img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
      img.src = url;
    });
  }

  async function onFilesPicked(files) {
    if (scanState.busy) return;
    if (files.length > 1) { runPatrol(files); return; }
    const file = files[0];
    scanState.preview = URL.createObjectURL(file);
    scanState.result = null;
    scanState.patrol = null;
    scanState.error = '';
    scanState.busy = true;
    paintScan();
    try {
      const blob = await compressImage(file);
      const body = await api.upload('/api/recognitions', blob, {
        plot_id: scanState.plotId,
        days_to_harvest: scanState.days
      });
      scanState.result = decorateRecognition(body);
      scanState.busy = false;
      paintScan();
      const card = $('#resultCard');
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
      loadHistory();
    } catch (e) {
      scanState.busy = false;
      scanState.error = e.message || '识别失败';
      paintScan();
    }
  }

  async function runPatrol(files) {
    const patrolId = 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    scanState.busy = true;
    scanState.result = null;
    scanState.patrol = null;
    scanState.error = '';
    scanState.preview = '';
    scanState.patrolProgress = '正在识别 0/' + files.length;
    paintScan();

    const results = [];
    const failures = [];
    for (let i = 0; i < files.length; i++) {
      try {
        const blob = await compressImage(files[i]);
        const r = await api.upload('/api/recognitions', blob, {
          patrol_id: patrolId,
          plot_id: scanState.plotId,
          days_to_harvest: scanState.days
        });
        results.push(r);
      } catch (e) {
        failures.push({ index: i + 1, message: e.message });
      }
      scanState.patrolProgress = '正在识别 ' + (i + 1) + '/' + files.length;
      paintScan();
    }
    scanState.patrolProgress = '';
    scanState.busy = false;

    let report = null;
    try {
      report = await api.get('/api/patrols/' + encodeURIComponent(patrolId));
    } catch (e) {
      report = localPatrol(patrolId, results);
    }
    scanState.patrol = decoratePatrol(report, failures);
    paintScan();
    loadHistory();
  }

  // 巡园接口不可用时的本地兜底，结构与后端 patrol.build_patrol_report 对齐
  function localPatrol(patrolId, results) {
    const names = {};
    (plotsCache || []).forEach(p => { names[p.id] = p.name; });
    const counts = {};
    const byPlot = {};
    (results || []).forEach(r => {
      const cls = r.pest_class || r.detected_class || '无法判断';
      if (HEALTHY.indexOf(cls) >= 0) return;
      counts[cls] = (counts[cls] || 0) + 1;
      if (r.plot_id) byPlot[r.plot_id] = (byPlot[r.plot_id] || 0) + 1;
    });
    const by_class = Object.keys(counts).map(k => ({ class: k, count: counts[k] }))
      .sort((a, b) => b.count - a.count);
    const by_plot = Object.keys(byPlot).map(k => ({
      plot_id: Number(k), plot_name: names[k] || ('地块 ' + k), count: byPlot[k]
    })).sort((a, b) => b.count - a.count);
    const total = by_class.reduce((s, e) => s + e.count, 0);
    const parts = by_class.slice(0, 3).map(e => e.class + ' ' + e.count + ' 处').join('、');
    return {
      patrol_id: patrolId,
      total,
      by_class,
      by_plot,
      focus_plot: by_plot[0] || null,
      summary: total ? '本次巡园 ' + total + ' 处异常：' + parts : '本次巡园未发现异常',
      advice: []
    };
  }

  function decoratePatrol(report, failures) {
    return {
      summary: report.summary || '',
      total: report.total || 0,
      byClass: (report.by_class || []).map(e => ({
        name: e.class,
        count: e.count,
        risk: e.risk || '',
        riskClass: e.risk === '高' ? 'critical' : (e.risk === '中高' ? 'serious' : (e.risk === '中' ? 'warning' : 'neutral'))
      })),
      byPlot: report.by_plot || [],
      focusText: report.focus_plot ? report.focus_plot.plot_name + '（' + report.focus_plot.count + ' 处）' : '',
      advice: (report.advice || []).slice(0, 3),
      failureText: failures && failures.length
        ? failures.length + ' 张识别失败（第 ' + failures.map(f => f.index).join('、') + ' 张）'
        : ''
    };
  }

  async function runDemo() {
    const sel = $('#demoPest');
    if (!sel) return;
    const body = { pest_class: sel.value };
    if (scanState.plotId) body.plot_id = parseInt(scanState.plotId, 10);
    if (scanState.days !== '') body.days_to_harvest = parseInt(scanState.days, 10);
    scanState.busy = true;
    scanState.error = '';
    scanState.result = null;
    scanState.patrol = null;
    scanState.preview = '';
    paintScan();
    try {
      const r = await api.post('/api/recognitions/demo', body);
      scanState.result = decorateRecognition(r);
      scanState.busy = false;
      paintScan();
      const card = $('#resultCard');
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
      loadHistory();
    } catch (e) {
      scanState.busy = false;
      scanState.error = e.message;
      paintScan();
    }
  }

  function handleRecognition(method) {
    const r = scanState.result;
    if (!r || scanState.busy) return;
    if (method === 'false_positive') {
      scanState.correcting = true;
      paintScan();
      return;
    }
    const body = { method };
    if (method === 'pesticide') {
      const p = (r.pesticides || [])[0];
      if (!p) { toast('没有可用的推荐药剂'); return; }
      body.pesticide_name = p.name;
      body.cas_no = p.cas_no;
      body.dosage = p.dosage_hint || '';
    } else if (method === 'operation') {
      body.operation_type = '人工清除';
      body.detail = { method: '人工清除', detected_class: r.pestClass };
    } else {
      body.note = '暂不处理';
    }
    submitHandle(r, body);
  }

  function cancelCorrect() {
    scanState.correcting = false;
    paintScan();
  }

  function submitCorrect() {
    const r = scanState.result;
    if (!r) return;
    const sel = $('#correctSelect');
    const idx = sel ? Number(sel.value) : 0;
    const body = { method: 'false_positive', note: '人工判定为误判' };
    if (idx > 0) body.actual_class = scanState.correctOptions[idx];
    submitHandle(r, body);
  }

  async function submitHandle(r, body) {
    scanState.busy = true;
    try {
      const res = await api.post('/api/recognitions/' + r.id + '/handle', body);
      let tip = '';
      if (res.summary && res.summary.safe_interval_days) {
        tip = res.summary.pesticide_name + ' · 安全间隔期 ' + res.summary.safe_interval_days +
          ' 天，' + res.summary.earliest_harvest_date + ' 之后方可采收';
      } else if (res.summary && res.summary.operation_type) {
        tip = res.summary.operation_type + ' · ' + res.summary.operation_date;
      } else if (res.actual_class) {
        tip = '已记录纠错：' + (res.detected_class || r.pestClass) + ' → ' + res.actual_class;
      }
      const merged = Object.assign({}, r.raw, { status: res.status });
      scanState.result = decorateRecognition(merged);
      scanState.result.handleTip = tip;
      scanState.correcting = false;
      scanState.busy = false;
      paintScan();
      toast(body.method === 'false_positive' ? '已记录' : '已处置');
      loadHistory();
    } catch (e) {
      scanState.busy = false;
      toast(e.message || '处置失败');
      paintScan();
    }
  }

  /* =========================================================================
     八、快速填报（含语音）
     ========================================================================= */
  let voiceRec = null;
  let voiceRecording = false;

  function stopVoice() {
    if (voiceRec && voiceRecording) {
      try { voiceRec.stop(); } catch (e) { /* 已停止 */ }
    }
    voiceRecording = false;
  }

  async function renderForm() {
    const el = $('#view-form');
    el.innerHTML = '<div class="card muted">加载中…</div>';
    try {
      await Promise.all([loadPlots(), loadPesticides()]);
    } catch (e) { el.innerHTML = errorCard(e.message, 'renderForm()'); return; }

    const plots = plotsCache || [];
    const drugs = pesticidesCache || [];
    const plotOpts = plots.map(p => `<option value="${p.id}" ${Number(p.id) === Number(pendingFormPlot) ? 'selected' : ''}>${esc(p.name)}（${esc(p.variety)}）</option>`).join('');
    const drugOpts = drugs.map((p, i) => `<option value="${i}">${esc(p.name)}（${esc(p.category)}）</option>`).join('');
    pendingFormPlot = 0;

    el.innerHTML = `
      <div class="card">
        <div class="h2">农事记录填报</div>
        <div class="field">
          <span class="label">地块</span>
          <select id="opPlot">${plotOpts}</select>
        </div>
        <div class="field">
          <span class="label">农事类型</span>
          <select id="opType">
            <option>施肥</option><option>灌溉</option><option>修剪</option>
            <option>疏花疏果</option><option>巡检</option><option>清园</option>
          </select>
        </div>
        <div class="field">
          <span class="label">操作人</span>
          <input id="opOperator" value="陈伯">
        </div>
        <div class="field">
          <span class="label">备注（可语音输入）</span>
          <div class="voice-row">
            <input class="voice-input" id="opRemark" placeholder="如：复合肥 40kg 环状沟施">
            <div class="voice-btn" id="voiceBtn">🎤</div>
          </div>
          <div class="small voice-tip mt" id="voiceTip"></div>
        </div>
        <div class="btn block" onclick="submitOperation()">提交农事记录</div>
        <div id="opMsg" class="mt"></div>
      </div>

      <div class="card">
        <div class="h2">用药台账录入</div>
        <div class="field">
          <span class="label">地块</span>
          <select id="pstPlot">${plotOpts}</select>
        </div>
        <div class="field">
          <span class="label">农药名称</span>
          <select id="pstSelect">${drugOpts}</select>
        </div>
        <div class="small muted" id="pstInfo"></div>
        <div class="field mt">
          <span class="label">距预计采收天数（可选）</span>
          <input id="pstDays" type="number" placeholder="如 5">
        </div>
        <div class="btn block" onclick="submitPesticide()">提交用药记录</div>
        <div id="pstMsg" class="mt"></div>
      </div>`;

    const sel = $('#pstSelect');
    const info = $('#pstInfo');
    const syncDrug = () => {
      const p = drugs[Number(sel.value)] || {};
      info.textContent = p.cas_no ? `CAS ${p.cas_no} · 安全间隔期 ${p.safe_interval_days} 天` : '';
    };
    if (sel) { sel.onchange = syncDrug; syncDrug(); }
    setupVoice();
  }

  function setupVoice() {
    const btn = $('#voiceBtn');
    const tip = $('#voiceTip');
    const input = $('#opRemark');
    if (!btn || !input) return;

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      btn.classList.add('hidden');
      if (tip) tip.textContent = '当前浏览器不支持语音输入，请手动输入';
      return;
    }
    const rec = new SR();
    rec.lang = 'zh-CN';
    rec.interimResults = false;
    rec.continuous = false;
    voiceRec = rec;

    rec.onresult = e => {
      const text = String((e.results[0] && e.results[0][0] && e.results[0][0].transcript) || '').trim();
      if (!text) { toast('没听清，请再说一次'); return; }
      input.value = (input.value ? input.value + ' ' : '') + text;
    };
    rec.onend = () => {
      voiceRecording = false;
      btn.classList.remove('on');
      btn.textContent = '🎤';
    };
    rec.onerror = () => {
      voiceRecording = false;
      btn.classList.remove('on');
      btn.textContent = '🎤';
      toast('语音识别失败，请手动输入');
    };
    btn.onclick = () => {
      if (voiceRecording) { try { rec.stop(); } catch (e) { /* 已停止 */ } return; }
      try {
        rec.start();
        voiceRecording = true;
        btn.classList.add('on');
        btn.textContent = '停止';
        if (tip) tip.textContent = '正在录音，请说出农事内容，说完点「停止」';
      } catch (e) {
        toast('无法启动录音，请检查麦克风权限');
      }
    };
  }

  async function submitOperation() {
    const plotId = Number($('#opPlot').value);
    const msg = $('#opMsg');
    if (!plotId) { msg.innerHTML = '<div class="alert critical">请先选择地块</div>'; return; }
    try {
      await api.post('/api/operations', {
        plot_id: plotId,
        operation_type: $('#opType').value,
        operator: $('#opOperator').value || '果农',
        detail: { remark: $('#opRemark').value }
      });
      msg.innerHTML = '<div class="alert good">农事记录已提交 ✅</div>';
      $('#opRemark').value = '';
      plotsCache = null;
    } catch (e) {
      msg.innerHTML = `<div class="alert critical">${esc(e.message)}</div>`;
    }
  }

  async function submitPesticide() {
    const plotId = Number($('#pstPlot').value);
    const idx = Number($('#pstSelect').value);
    const p = (pesticidesCache || [])[idx];
    const msg = $('#pstMsg');
    if (!plotId || !p) { msg.innerHTML = '<div class="alert critical">请先选择地块与药剂</div>'; return; }
    const body = { plot_id: plotId, pesticide_name: p.name, cas_no: p.cas_no };
    const days = $('#pstDays').value;
    if (days !== '') body.days_to_harvest = parseInt(days, 10);
    try {
      const r = await api.post('/api/pesticide-records', body);
      msg.innerHTML = `<div class="alert ${r.warning ? 'warning' : 'good'}">${esc(r.warning || '用药记录已提交')} ✅
        <br><span class="small">最早可采收：${esc(r.earliest_harvest_date)}</span></div>`;
      $('#pstDays').value = '';
      plotsCache = null;
    } catch (e) {
      msg.innerHTML = `<div class="alert critical">${esc(e.message)}</div>`;
    }
  }

  /* =========================================================================
     九、一物一码溯源
     ========================================================================= */
  async function renderTrace(code) {
    const el = $('#view-trace');
    const value = code || '';
    el.innerHTML = `
      <div class="card">
        <div class="h2">一物一码 · 查询溯源</div>
        <div class="field">
          <span class="label">溯源码</span>
          <input id="traceCode" value="${esc(value)}" placeholder="如 LZ-P03-20260702-0001">
        </div>
        <div class="row">
          <div class="btn ghost" onclick="quickScan()">扫一扫</div>
          <div class="btn" onclick="doTrace()">查询</div>
        </div>
        <div class="mt small muted">演示码：LZ-P03-20260702-0001（已放行）· LZ-P01-20260708-0002（已拦截）</div>
      </div>
      <div id="traceResult">${value ? '<div class="card muted">查询中…</div>' : ''}</div>`;

    const input = $('#traceCode');
    if (input) input.onkeydown = e => { if (e.key === 'Enter') doTrace(); };
    if (value) await loadTrace(value);
  }

  function doTrace() {
    const input = $('#traceCode');
    const code = (input ? input.value : '').trim();
    if (!code) { toast('请输入溯源码'); return; }
    go('trace', code);
  }

  async function loadTrace(code) {
    const box = $('#traceResult');
    if (!box) return;
    box.innerHTML = '<div class="card muted">查询中…</div>';
    try {
      const t = await api.get('/api/trace/' + encodeURIComponent(code));
      box.innerHTML = traceHtml(t);
    } catch (e) {
      box.innerHTML = `<div class="alert critical"><div class="al-detail">${esc(e.message)}</div></div>`;
    }
  }

  function traceHtml(t) {
    const cv = t.chain_verify || {};
    const badIds = (cv.tampered || []).concat(cv.broken || []);
    const sales = t.sales || {};
    const chain = sales.cold_chain || {};
    const COLD_TEXT = { pending: '待预冷', overdue: '预冷超时', cooling: '已预冷', transit: '运输中', arrived: '已到货', legacy: '无采后记录' };
    const COLD_CLASS = { pending: 'warning', overdue: 'critical', cooling: 'good', transit: 'good', arrived: 'good', legacy: 'neutral' };
    const planting = t.planting || {};
    const care = t.care || {};
    const residueTests = sales.residue_tests || [];
    const residueCls = sales.residue_conclusion === '合格' ? 'good' : (sales.residue_conclusion === '不合格' ? 'critical' : 'warning');
    const statusCls = t.status === 'released' ? 'good' : 'critical';
    const chainText = cv.valid ? ('链校验通过 · ' + (cv.total || 0) + ' 条') : ('链校验失败 · 第 ' + badIds.join('、') + ' 条');
    const qr = '/api/batches/' + encodeURIComponent(t.batch_no) + '/qrcode';

    const ops = (care.operations || []).map(o => kv(o.operation_type, o.operation_date + ' · ' + (o.operator || ''))).join('');
    const residues = residueTests.length ? residueTests.map(r => `
      <div class="residue-item">
        <div class="residue-head">
          <span>${esc(r.lab || '检测机构未填')} · ${esc(r.tested_at)}</span>
          <span class="pill ${r.conclusion === '合格' ? 'good' : (r.conclusion === '不合格' ? 'critical' : 'warning')}">${esc(r.conclusion)}</span>
        </div>
        ${(r.items || []).length ? `<div class="small muted">${(r.items || []).map(i => esc(i.name) + ' ' + esc(i.value) + (i.unit ? ' ' + esc(i.unit) : '') + (i.limit ? '（限量 ' + esc(i.limit) + '）' : '')).join('；')}</div>` : ''}
        ${r.note ? `<div class="small muted">${esc(r.note)}</div>` : ''}
      </div>`).join('') : '<div class="small muted">暂无检测记录</div>';

    const chainRows = (t.hash_chain || []).map((h, i) => `
      <div class="kv">
        <span class="k">#${i + 1} ${esc(h.payload_summary || '')}</span>
        <span class="v small muted">${esc(String(h.record_hash || '').slice(0, 16))}…</span>
      </div>`).join('');

    return `
      <div class="card hero-card">
        <div class="t-code">${esc(t.code)}</div>
        <div class="mt">
          <span class="pill ${statusCls}">${t.status === 'released' ? '已放行' : '已拦截'}</span>
          <span class="pill neutral">${esc(t.variety || '')}</span>
        </div>
        ${t.status !== 'released' ? `<div class="alert critical mt"><div class="al-title">批次已拦截</div><div class="al-detail">${esc(t.block_reason || '')}</div></div>` : ''}
        <div class="qr-wrap mt">
          <img class="qr" src="${qr}" alt="批次二维码">
          <div class="small muted">长按二维码可保存 / 识别<br>扫码即可查看全过程</div>
        </div>
      </div>

      <div class="card">
        <div class="seg-head"><span class="seg-no">1</span>种植 · 谁种的</div>
        ${kv('果园', planting.orchard || '')}
        ${kv('地块', planting.plot_name || '')}
        ${kv('位置', planting.location || '')}
        ${kv('品种', planting.variety || '')}
        ${kv('定植年份', planting.planting_year || '')}
      </div>

      <div class="card">
        <div class="seg-head"><span class="seg-no">2</span>管护 · 怎么管的</div>
        ${kv('关键农事记录', (care.operations || []).length + ' 条')}
        ${ops}
        ${kv('用药次数', (care.pesticide_count || 0) + ' 次')}
        ${care.last_pesticide ? kv('最后一次用药', care.last_pesticide.pesticide_name + ' · ' + care.last_pesticide.apply_time) : ''}
        ${kv('安全间隔期状态', care.safety_state || '')}
      </div>

      <div class="card">
        <div class="seg-head"><span class="seg-no">3</span>销售 · 检测是否合格</div>
        ${kv('采收日期', t.harvest_date || '')}
        ${kv('农残检测', sales.detection_report || '')}
        ${kv('包装', sales.packaging || '')}
        ${kv('物流', sales.logistics || '—')}

        <div class="seg-sub">采后冷链</div>
        ${kv('状态', COLD_TEXT[chain.status] || '—', COLD_CLASS[chain.status] || 'neutral')}
        ${kv('离树', (chain.harvest_at || '未记录') + (chain.harvest_at_estimated ? '（估算）' : ''))}
        ${kv('离树时长', (chain.hours_since_harvest == null ? '—' : Math.round(chain.hours_since_harvest)) + ' 小时')}
        ${kv('预冷完成', chain.precooled_at || '未记录')}
        ${kv('装车发运', chain.shipped_at || '未记录')}
        ${kv('到货', chain.arrived_at || '未记录')}

        <div class="seg-sub">农残快检<span class="pill ${residueCls}">${esc(sales.residue_conclusion || '待检测')}</span></div>
        ${residues}
      </div>

      ${(t.hash_chain || []).length ? `<div class="card">
        <div class="seg-head"><span class="seg-no">🔗</span>哈希存证链
          <span class="pill ${cv.valid ? 'good' : 'critical'}">${esc(chainText)}</span>
        </div>
        ${chainRows}
        ${(cv.legacy || []).length ? `<div class="small muted mt">${cv.legacy.length} 条历史记录未存原文，未参与重算</div>` : ''}
      </div>` : ''}

      <div class="small muted tip">溯源数据来自地块档案与用药台账，哈希链保证不可篡改</div>`;
  }

  /* =========================================================================
     十、批次二维码（含冷链与农残快检）
     ========================================================================= */
  const batchState = { msg: '', ok: true, residueFor: '' };
  const COLD_TEXT = { pending: '待预冷', overdue: '预冷超时', cooling: '已预冷', transit: '运输中', arrived: '已到货', legacy: '历史批次' };
  const COLD_CLASS = { pending: 'warning', overdue: 'critical', cooling: 'good', transit: 'good', arrived: 'good', legacy: 'neutral' };
  const NEXT_EVENT = {
    harvested: { event: 'precool', label: '预冷完成' },
    precooled: { event: 'ship', label: '装车发运' },
    shipped: { event: 'arrive', label: '确认到货' }
  };
  const CONCLUSIONS = ['合格', '不合格', '待复检'];

  async function renderBatches() {
    const el = $('#view-batches');
    el.innerHTML = '<div class="card muted">加载中…</div>';
    let rows = [];
    try {
      const res = await Promise.all([api.get('/api/batches'), loadPlots()]);
      rows = res[0] || [];
    } catch (e) { el.innerHTML = errorCard(e.message, 'renderBatches()'); return; }

    const plots = plotsCache || [];
    const plotOpts = plots.map(p => `<option value="${p.id}">${esc(p.name)}（${esc(p.variety)}）</option>`).join('');

    const cards = rows.map(b => {
      const chain = b.cold_chain || {};
      const next = NEXT_EVENT[chain.stage] || null;
      const hours = chain.hours_since_harvest;
      const conclusion = b.residue_conclusion || '待检测';
      const residueCls = conclusion === '合格' ? 'good' : (conclusion === '不合格' ? 'critical' : 'warning');
      const blocked = b.status !== 'released';
      return `<div class="card">
        <div class="batch-head">
          <div class="b-main">
            <div class="b-code">${esc(b.batch_no)}</div>
            <div class="small muted">${esc(b.plot_name)} · ${esc(b.variety)} · ${esc(b.harvest_date)}</div>
          </div>
          <span class="pill ${blocked ? 'critical' : 'good'}">${blocked ? '已拦截' : '已放行'}</span>
        </div>

        ${blocked
          ? `<div class="alert critical mt"><div class="al-title">未生成销售溯源码</div><div class="al-detail">${esc(b.block_reason || '安全间隔期未满')}</div></div>`
          : `<div class="batch-body">
              <img class="qr" src="/api/batches/${encodeURIComponent(b.batch_no)}/qrcode" alt="批次二维码">
              <div class="small muted">一物一码 · 长按可保存<br>扫码查看「种植—管护—销售」全过程</div>
            </div>`}

        <div class="kv mt">
          <span class="k">采后冷链</span>
          <span class="v">离树 ${hours == null ? '—' : Math.round(hours)} 小时 · <span class="pill ${COLD_CLASS[chain.status] || 'neutral'}">${esc(COLD_TEXT[chain.status] || '—')}</span></span>
        </div>
        <div class="kv">
          <span class="k">农残快检</span>
          <span class="v"><span class="pill ${residueCls}">${esc(conclusion)}</span></span>
        </div>

        <div class="row mt">
          ${!blocked && next ? `<div class="btn ghost small" onclick="coldEvent('${esc(b.batch_no)}', '${next.event}')">${esc(next.label)}</div>` : ''}
          <div class="btn ghost small" onclick="toggleResidue('${esc(b.batch_no)}')">${batchState.residueFor === b.batch_no ? '收起录入' : '录入检测'}</div>
        </div>

        ${batchState.residueFor === b.batch_no ? residueFormHtml() : ''}
      </div>`;
    }).join('');

    el.innerHTML = `
      <div class="card">
        <div class="h2">生成采收批次</div>
        <div class="field">
          <span class="label">地块</span>
          <select id="batchPlot">${plotOpts}</select>
        </div>
        <div class="row align-start">
          <div class="field half">
            <span class="label">采收日期</span>
            <input type="date" id="batchDate" value="${today()}">
          </div>
          <div class="field half">
            <span class="label">包装序号</span>
            <input type="number" id="batchSeq" value="1">
          </div>
        </div>
        <div class="btn block" onclick="createBatch()">生成批次并锁定档案</div>
        ${batchState.msg ? `<div class="alert ${batchState.ok ? 'good' : 'warning'} mt"><div class="al-detail">${esc(batchState.msg)}</div></div>` : ''}
        <div class="small muted mt">安全间隔期未满的批次会被拦截，不生成销售溯源码。</div>
      </div>

      <div class="h2">批次列表</div>
      ${cards || '<div class="card empty">还没有批次，先生成一个</div>'}`;

    batchState.msg = '';
  }

  function residueFormHtml() {
    return `<div class="residue-form mt">
      <div class="field">
        <span class="label">检测机构</span>
        <input id="resLab" placeholder="如 从化区农产品检测站">
      </div>
      <div class="field">
        <span class="label">检测日期</span>
        <input type="date" id="resTested" value="${today()}">
      </div>
      <div class="field">
        <span class="label">结论</span>
        <select id="resConclusion">${CONCLUSIONS.map(c => `<option>${c}</option>`).join('')}</select>
      </div>
      <div class="row align-start">
        <div class="field half">
          <span class="label">检测项</span>
          <input id="resItemName" placeholder="如 毒死蜱">
        </div>
        <div class="field half">
          <span class="label">实测值</span>
          <input id="resItemValue" placeholder="如 0.008">
        </div>
      </div>
      <div class="field">
        <span class="label">限量（mg/kg）</span>
        <input id="resItemLimit" placeholder="如 0.01">
      </div>
      <div class="field">
        <span class="label">检测报告照片（可选）</span>
        <input type="file" id="resReport" accept="image/*">
      </div>
      <div class="btn block mt" onclick="submitResidue()">提交检测记录</div>
    </div>`;
  }

  async function createBatch() {
    const plotId = Number($('#batchPlot').value);
    if (!plotId) { toast('请先选择地块'); return; }
    try {
      const r = await api.post('/api/batches', {
        plot_id: plotId,
        harvest_date: $('#batchDate').value || today(),
        packaging_seq: parseInt($('#batchSeq').value, 10) || 1
      });
      const blocked = r.status !== 'released';
      batchState.ok = !blocked;
      batchState.msg = blocked
        ? '批次已生成但被拦截：' + (r.block_reason || '安全间隔期未满')
        : '批次已生成，溯源码：' + r.trace_code + '，二维码已入库';
      plotsCache = null;
      renderBatches();
    } catch (e) { batchState.ok = false; batchState.msg = e.message; renderBatches(); }
  }

  async function coldEvent(batchNo, event) {
    try {
      await api.post('/api/batches/' + encodeURIComponent(batchNo) + '/cold-chain', { event });
      toast('已登记');
      renderBatches();
    } catch (e) { toast(e.message || '登记失败'); }
  }

  function toggleResidue(batchNo) {
    batchState.residueFor = batchState.residueFor === batchNo ? '' : batchNo;
    renderBatches();
  }

  async function submitResidue() {
    const batchNo = batchState.residueFor;
    if (!batchNo) return;
    const items = [];
    const itemName = $('#resItemName').value.trim();
    if (itemName) {
      items.push({
        name: itemName,
        value: $('#resItemValue').value.trim(),
        unit: 'mg/kg',
        limit: $('#resItemLimit').value.trim()
      });
    }
    let reportUrl = null;
    const reportInput = $('#resReport');
    if (reportInput && reportInput.files && reportInput.files[0]) {
      try {
        const up = await api.upload('/api/uploads', reportInput.files[0]);
        reportUrl = up.url || null;
      } catch (e) { toast('报告上传失败：' + e.message); return; }
    }
    try {
      const r = await api.post('/api/batches/' + encodeURIComponent(batchNo) + '/residue-tests', {
        tested_at: $('#resTested').value || today(),
        lab: $('#resLab').value.trim(),
        conclusion: $('#resConclusion').value,
        items,
        report_url: reportUrl,
        operator: '果农'
      });
      batchState.residueFor = '';
      batchState.ok = !r.blocked;
      batchState.msg = r.blocked ? '检测不合格，批次已拦截' : '检测已记录';
      toast(r.blocked ? '已拦截该批次' : '已记录');
      renderBatches();
    } catch (e) { toast(e.message || '提交失败'); }
  }

  /* =========================================================================
     十一、病虫害知识库
     ========================================================================= */
  const KB_CACHE = 'kb_cache_v1';
  const KB_PESTICIDE_CACHE = 'kb_pesticides_v1';
  const kbState = { rows: [], keyword: '', filter: 'all', loaded: false, offline: false, offlineText: '' };

  const RISK_CLASS = { '高': 'critical', '中高': 'serious', '中': 'warning', '无': 'good', '未知': 'neutral' };
  const KIND_ICON = { '虫害': '🐛', '病害': '🍄' };

  function kbReadCache() {
    try {
      const raw = localStorage.getItem(KB_CACHE);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (data && Array.isArray(data.rows) && data.rows.length) return data;
    } catch (e) { /* 忽略损坏缓存 */ }
    return null;
  }
  function kbWriteCache(rows) {
    try { localStorage.setItem(KB_CACHE, JSON.stringify({ at: Date.now(), rows })); } catch (e) { /* 忽略 */ }
  }
  function kbReadPesticides() {
    try {
      const raw = localStorage.getItem(KB_PESTICIDE_CACHE);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (data && Array.isArray(data.rows)) return data.rows;
    } catch (e) { /* 忽略 */ }
    return null;
  }
  function kbWritePesticides(rows) {
    try { localStorage.setItem(KB_PESTICIDE_CACHE, JSON.stringify({ at: Date.now(), rows })); } catch (e) { /* 忽略 */ }
  }
  function isPeakNow(item) {
    const months = (item && item.peak_months) || [];
    const now = new Date().getMonth() + 1;
    return months.some(m => parseInt(m, 10) === now);
  }
  function cacheLabel(at) {
    if (!at) return '';
    const d = new Date(at);
    const pad = n => (n < 10 ? '0' + n : '' + n);
    return (d.getMonth() + 1) + '月' + d.getDate() + '日 ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function decoratePest(p) {
    return Object.assign({}, p, {
      icon: KIND_ICON[p.kind] || '🌿',
      riskClass: RISK_CLASS[p.risk] || 'neutral',
      hostText: (p.host_parts || []).join('、'),
      peakText: (p.peak_months || []).join('、'),
      hasPeak: !!(p.peak_months && p.peak_months.length),
      peakNow: isPeakNow(p)
    });
  }

  async function renderKb() {
    const el = $('#view-kb');
    if (!kbState.loaded) {
      el.innerHTML = '<div class="card muted">加载中…</div>';
      const cached = kbReadCache();
      if (cached) {
        kbState.rows = cached.rows.filter(p => p.kind === '虫害' || p.kind === '病害').map(decoratePest);
        kbState.loaded = true;
      }
      try {
        const rows = await api.get('/api/pests');
        const all = (rows || []).filter(p => p.kind === '虫害' || p.kind === '病害').map(decoratePest);
        all.sort((a, b) => (a.kind === b.kind ? 0 : (a.kind === '虫害' ? -1 : 1)));
        kbState.rows = all;
        kbState.loaded = true;
        kbState.offline = false;
        kbWriteCache(all);
      } catch (e) {
        if (!kbState.rows.length) { el.innerHTML = errorCard(e.message, 'renderKb()'); return; }
        kbState.offline = true;
        kbState.offlineText = '当前离线，显示 ' + kbState.rows.length + ' 条缓存知识（' + cacheLabel(cached && cached.at) + ' 更新）';
      }
    }
    paintKb();
  }

  function paintKb() {
    const el = $('#view-kb');
    const all = kbState.rows;
    const peak = all.filter(p => p.peakNow);
    const counts = {
      all: all.length,
      pest: all.filter(p => p.kind === '虫害').length,
      disease: all.filter(p => p.kind === '病害').length,
      peak: peak.length
    };

    el.innerHTML = `
      <div class="hero kb-hero">
        <div class="glow glow-a"></div><div class="glow glow-b"></div>
        <div class="hero-kicker">知识与防治 · 东风荔枝</div>
        <div class="hero-title">病虫害知识库</div>
        <div class="hero-sub">症状识别 · 易混淆鉴别 · 非化学措施 · 推荐药剂</div>
        <div class="hero-chips">
          <div class="hero-chip">🐛 虫害 ${counts.pest} 种</div>
          <div class="hero-chip">🍄 病害 ${counts.disease} 种</div>
        </div>
      </div>

      <div class="card kb-search">
        <div class="field">
          <input id="kbSearch" placeholder="搜索名称、症状、防治或监测要点" value="${esc(kbState.keyword)}">
        </div>
        <div class="kb-filters">
          <button class="kb-filter ${kbState.filter === 'all' ? 'on' : ''}" data-filter="all">全部 ${counts.all}</button>
          <button class="kb-filter ${kbState.filter === 'pest' ? 'on' : ''}" data-filter="pest">虫害 ${counts.pest}</button>
          <button class="kb-filter ${kbState.filter === 'disease' ? 'on' : ''}" data-filter="disease">病害 ${counts.disease}</button>
          ${counts.peak ? `<button class="kb-filter ${kbState.filter === 'peak' ? 'on' : ''}" data-filter="peak">本月 ${counts.peak}</button>` : ''}
        </div>
        ${kbState.offline ? `<div class="kb-offline">${esc(kbState.offlineText)}</div>` : ''}
      </div>

      ${counts.peak
        ? `<div class="kb-peak" data-filter="peak">
            <div class="kb-peak-main">
              <div class="kb-peak-title">本月高发 ${counts.peak} 种</div>
              <div class="kb-peak-sub">${esc(peak.slice(0, 3).map(p => p.name).join('、'))}${peak.length > 3 ? ' 等' : ''}正在高发期，建议加强巡园</div>
            </div>
            <span class="kb-peak-go">查看 ›</span>
          </div>`
        : '<div class="kb-quiet">🌤 本月不在主要病虫害高发期，按常规频次巡园即可</div>'}

      <div id="kbList"></div>
      <div class="tip">资料整理自公开农技资料，仅供辅助判断；用药请以农药标签登记为准。</div>`;

    const input = $('#kbSearch');
    let timer = null;
    input.oninput = e => {
      clearTimeout(timer);
      const v = e.target.value;
      timer = setTimeout(() => { kbState.keyword = v; paintKbList(); }, 120);
    };
    el.querySelectorAll('[data-filter]').forEach(b => {
      b.onclick = () => { kbState.filter = b.dataset.filter; paintKb(); };
    });
    paintKbList();
  }

  function paintKbList() {
    const box = $('#kbList');
    if (!box) return;
    const kw = String(kbState.keyword || '').trim().toLowerCase();
    const list = kbState.rows.filter(p => {
      if (kbState.filter === 'pest' && p.kind !== '虫害') return false;
      if (kbState.filter === 'disease' && p.kind !== '病害') return false;
      if (kbState.filter === 'peak' && !p.peakNow) return false;
      if (!kw) return true;
      const diff = p.differential || {};
      const hay = [
        p.name, p.latin, p.symptoms, p.timing, p.notes, p.monitoring,
        (p.aliases || []).join(' '), (p.host_parts || []).join(' '),
        (p.non_chemical || []).join(' '), (p.biological || []).join(' '),
        (diff.confusable || []).join(' '), (diff.distinguishing || []).join(' ')
      ].join(' ').toLowerCase();
      return hay.indexOf(kw) >= 0;
    });

    if (!list.length) {
      box.innerHTML = `<div class="card"><div class="empty">
        <span class="empty-icon">🔎</span><span class="empty-title">没有匹配的条目</span>
        <span class="empty-sub">换个关键词，或切换到「全部」</span></div></div>`;
      return;
    }

    box.innerHTML = list.map(p => `
      <div class="kb-card" data-kb="${esc(p.name)}">
        <div class="kb-icon ${p.kind === '虫害' ? 'kb-icon-pest' : 'kb-icon-disease'}">${p.icon}</div>
        <div class="kb-main">
          <div class="kb-head">
            <span class="kb-name">${esc(p.name)}</span>
            <span class="pill ${p.riskClass}"><span class="pdot"></span>${esc(p.risk || '')}</span>
          </div>
          <div class="kb-latin mono">${esc(p.latin || '')}</div>
          <div class="kb-symptom">${esc(p.symptoms || '')}</div>
          <div class="kb-meta">
            ${p.hostText ? '危害 ' + esc(p.hostText) : ''}${p.hostText && p.hasPeak ? ' · ' : ''}${p.hasPeak ? '高发 ' + esc(p.peakText) : ''}
          </div>
        </div>
        <span class="kb-arrow">›</span>
      </div>`).join('');

    box.querySelectorAll('[data-kb]').forEach(card => {
      card.onclick = () => openKbDetail(card.dataset.kb);
    });
  }

  function openKbDetail(name) {
    if (!name) return;
    go('kbDetail', name);
  }

  let kbDetailName = '';

  async function renderKbDetail(name) {
    const el = $('#view-kbDetail');
    kbDetailName = name;
    el.innerHTML = '<div class="card muted">加载中…</div>';
    let pests = [];
    let drugs = [];
    let offline = false;
    try {
      const res = await Promise.all([api.get('/api/pests'), api.get('/api/pesticides')]);
      pests = res[0] || [];
      drugs = res[1] || [];
      kbWriteCache(pests.filter(p => p.kind === '虫害' || p.kind === '病害'));
      kbWritePesticides(drugs);
    } catch (e) {
      const cached = kbReadCache();
      if (!cached) { el.innerHTML = errorCard(e.message, "renderKbDetail('" + String(name || '').replace(/'/g, "\\'") + "')"); return; }
      pests = cached.rows;
      drugs = kbReadPesticides() || [];
      offline = true;
    }

    const raw = (pests || []).filter(p => p.name === name)[0];
    if (!raw) {
      el.innerHTML = errorCard('知识库中没有找到「' + (name || '该条目') + '」');
      return;
    }
    $('#navTitle').textContent = raw.name;
    const diff = raw.differential || {};
    const pest = Object.assign({}, raw, {
      icon: KIND_ICON[raw.kind] || '🌿',
      riskClass: RISK_CLASS[raw.risk] || 'neutral',
      hostText: (raw.host_parts || []).join('、'),
      peakText: (raw.peak_months || []).join('、'),
      peakNow: isPeakNow(raw),
      confusableText: (diff.confusable || []).join('、'),
      distinguishing: diff.distinguishing || [],
      nonChemical: raw.non_chemical || [],
      biological: raw.biological || []
    });
    const matchedDrugs = (drugs || [])
      .filter(p => (p.targets || []).indexOf(raw.name) >= 0)
      .sort((a, b) => (a.safe_interval_days || 0) - (b.safe_interval_days || 0));

    el.innerHTML = `
      <div class="hero kb-hero">
        <div class="glow glow-a"></div><div class="glow glow-b"></div>
        <div class="hero-top">
          <span class="hero-kicker">${esc(raw.kind)} · ${esc(raw.latin || '')}</span>
          <span class="kb-hero-icon">${pest.icon}</span>
        </div>
        <div class="hero-title">${esc(raw.name)}</div>
        <div class="hero-chips">
          <div class="hero-chip">风险 ${esc(raw.risk || '未知')}</div>
          ${pest.peakText ? `<div class="hero-chip">高发 ${esc(pest.peakText)}</div>` : ''}
          ${pest.peakNow ? '<div class="hero-chip kb-peak-chip">本月高发</div>' : ''}
          <div class="hero-chip">✓ 已收录</div>
        </div>
      </div>

      ${offline ? '<div class="kb-offline-banner">当前离线，显示本地缓存内容</div>' : ''}

      <div class="card">
        <div class="card-head">
          <span class="card-title" style="font-weight:600">典型症状</span>
          <span class="pill ${pest.riskClass}"><span class="pdot"></span>${esc(raw.risk || '未知')}</span>
        </div>
        <div class="kb-text">${esc(raw.symptoms || '')}</div>
        <div class="kv mt"><span class="k">危害部位</span><span class="v">${esc(pest.hostText || '—')}</span></div>
        ${pest.peakText ? kv('高发期', pest.peakText) : ''}
        ${raw.timing ? kv('防治时机', raw.timing) : ''}
      </div>

      ${raw.monitoring ? `<div class="card">
        <div class="card-head"><span class="card-title" style="font-weight:600">🔍 监测要点</span></div>
        <div class="kb-text">${esc(raw.monitoring)}</div>
      </div>` : ''}

      <div class="card">
        <div class="card-head"><span class="card-title" style="font-weight:600">🆚 易混淆与鉴别</span></div>
        ${pest.confusableText ? `<div class="kb-sub">易混淆：${esc(pest.confusableText)}</div>` : ''}
        ${pest.distinguishing.length ? pest.distinguishing.map(d => `<div class="kb-li">· ${esc(d)}</div>`).join('') : '<div class="hint">暂未收录鉴别要点。</div>'}
      </div>

      ${pest.nonChemical.length ? `<div class="card">
        <div class="card-head"><span class="card-title" style="font-weight:600">🌱 非化学措施</span></div>
        ${pest.nonChemical.map(m => `<div class="kb-li">· ${esc(m)}</div>`).join('')}
      </div>` : ''}

      ${pest.biological.length ? `<div class="card">
        <div class="card-head"><span class="card-title" style="font-weight:600">🐞 生物防治</span></div>
        ${pest.biological.map(m => `<div class="kb-li">· ${esc(m)}</div>`).join('')}
      </div>` : ''}

      ${raw.notes ? `<div class="card">
        <div class="card-head"><span class="card-title" style="font-weight:600">🧑‍🌾 田间管理</span></div>
        <div class="kb-text">${esc(raw.notes)}</div>
      </div>` : ''}

      <div class="sec"><div class="sec-bar"></div><span class="sec-title">推荐药剂</span><span class="sec-count">${matchedDrugs.length} 种</span></div>

      ${offline && !drugs.length
        ? `<div class="card"><div class="empty"><span class="empty-icon">📶</span>
            <span class="empty-title">离线状态，药剂清单暂不可用</span>
            <span class="empty-sub">联网后重新打开即可查看；非化学措施可正常参考</span></div></div>`
        : (!matchedDrugs.length
          ? `<div class="card"><div class="empty"><span class="empty-icon">🧪</span>
              <span class="empty-title">暂无登记药剂</span>
              <span class="empty-sub">优先采用上方非化学措施，必要时咨询当地农技人员</span></div></div>`
          : `<div class="card">${matchedDrugs.map(d => `
              <div class="kb-drug">
                <div class="kb-drug-main">
                  <div class="kb-drug-name">
                    <span class="kb-drug-title">${esc(d.name)}</span>
                    <span class="pill neutral">${esc(d.category)}</span>
                  </div>
                  <div class="kb-drug-meta">${esc(d.dosage_hint || '')}</div>
                  <div class="kb-drug-cas mono">CAS ${esc(d.cas_no || '—')}</div>
                </div>
                <div class="kb-drug-days">
                  <span class="num">${d.safe_interval_days}</span>
                  <span class="lbl">天间隔期</span>
                </div>
              </div>`).join('')}</div>`)}

      <div class="tip">资料整理自公开农药登记信息与荔枝栽培农技资料，仅供辅助判断；具体用药请核对农药标签登记作物与剂量，并严格执行安全间隔期。</div>`;
  }

  /* =========================================================================
     十二、启动
     ========================================================================= */
  function applyFont() {
    const on = localStorage.getItem('fontLarge') === '1';
    $('#content').classList.toggle('font-lg', on);
    const sw = $('#fontSwitch');
    if (sw) sw.checked = on;
  }

  // 供内联 onclick 调用的入口
  window.go = go;
  window.toast = toast;
  window.quickScan = quickScan;
  window.goRecognition = goRecognition;
  window.todoAction = todoAction;
  window.renderPlots = renderPlots;
  window.renderScan = renderScan;
  window.renderForm = renderForm;
  window.renderBatches = renderBatches;
  window.renderKb = renderKb;
  window.renderKbDetail = renderKbDetail;
  window.pickPhoto = pickPhoto;
  window.runDemo = runDemo;
  window.handleRecognition = handleRecognition;
  window.cancelCorrect = cancelCorrect;
  window.submitCorrect = submitCorrect;
  window.submitOperation = submitOperation;
  window.submitPesticide = submitPesticide;
  window.doTrace = doTrace;
  window.createBatch = createBatch;
  window.coldEvent = coldEvent;
  window.toggleResidue = toggleResidue;
  window.submitResidue = submitResidue;
  window.openKbDetail = openKbDetail;
  window.saveRegion = saveRegion;

  $$('.tabbar button').forEach(b => {
    b.onclick = () => go(b.dataset.tab);
  });

  window.addEventListener('hashchange', route);
  applyFont();
  if (!location.hash) {
    history.replaceState(null, '', '#/todo');
  }
  route();
})();
