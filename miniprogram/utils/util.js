const CODE_RE = /LZ-[A-Za-z0-9]+-\d{8}-\d{4}/;

function extractCode(text) {
  const m = String(text || '').match(CODE_RE);
  return m ? m[0] : '';
}

function pct(value) {
  return Math.round((Number(value) || 0) * 100);
}

function today() {
  const d = new Date();
  const pad = n => (n < 10 ? '0' + n : '' + n);
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}

module.exports = { extractCode, pct, today };
