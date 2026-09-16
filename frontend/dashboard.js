// Renders the report returned by POST /api/report. Nothing here computes risk,
// the page only draws what the backend sends. RiskDashboard.render(report) can
// be called with any report object, RiskDashboard.load(request) fetches one.
var RiskDashboard = (function () {
  var C = {
    red: '#ae1f19', grey: '#9ca3af', greyDark: '#6b7280', ink: '#111827', line: '#eef0f2',
    green: '#16a34a', amber: '#f59e0b', orange: '#ea580c', danger: '#dc2626', blue: '#2a78d6',
    neutral: '#f0efec'
  }
  var LEVELS = { Low: C.green, Moderate: C.amber, High: C.orange, 'Very High': C.danger }
  var LEVEL_PILL = { Low: 'green', Moderate: 'amber', High: 'orange', 'Very High': 'red' }
  var charts = {}
  var state = { apiBase: '', report: null }

  function pct(x, d) {
    if (x === null || x === undefined || isNaN(x)) return '—'
    return (x * 100).toFixed(d === undefined ? 1 : d) + '%'
  }
  function signedPct(x, d) {
    if (x === null || x === undefined || isNaN(x)) return '—'
    return (x >= 0 ? '+' : '') + pct(x, d)
  }
  function num(x, d) {
    if (x === null || x === undefined || isNaN(x)) return '—'
    return Number(x).toFixed(d === undefined ? 2 : d)
  }
  function money(x, cur) {
    if (x === null || x === undefined || isNaN(x)) return '—'
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: cur || 'USD', maximumFractionDigits: 0 }).format(x)
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    })
  }
  function el(id) { return document.getElementById(id) }
  function levelColor(level) { return LEVELS[level] || C.grey }

  // Chart.js defaults shared by every chart: hairline grid, no dashes, thin bars.
  function baseOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      plugins: { legend: { display: false }, tooltip: { backgroundColor: C.ink, titleFont: { weight: '700' }, padding: 10, cornerRadius: 8 } },
      scales: {
        x: { grid: { color: C.line, lineWidth: 1, drawTicks: false }, border: { display: false }, ticks: { color: C.greyDark, font: { size: 11 } } },
        y: { grid: { color: C.line, lineWidth: 1, drawTicks: false }, border: { display: false }, ticks: { color: C.greyDark, font: { size: 11 } } }
      }
    }
  }

  // Writes the value at the end of each bar for the datasets that ask for it.
  var endLabels = {
    id: 'endLabels',
    afterDatasetsDraw: function (chart) {
      var ctx = chart.ctx
      chart.data.datasets.forEach(function (ds, di) {
        if (!ds.endLabel) return
        var meta = chart.getDatasetMeta(di)
        ctx.save()
        ctx.font = '700 11px ' + getComputedStyle(document.body).fontFamily
        ctx.fillStyle = C.ink
        ctx.textBaseline = 'middle'
        meta.data.forEach(function (bar, i) {
          var v = ds.data[i]
          if (v === null || v === undefined) return
          // Positive bars are labeled past their end, negative bars just right
          // of the zero line so the text never runs into the axis labels.
          ctx.textAlign = 'left'
          ctx.fillText(ds.endLabel(v), (v >= 0 ? bar.x : bar.base) + 6, bar.y)
        })
        ctx.restore()
      })
    }
  }

  function destroy(key) {
    if (!charts[key]) return
    charts[key].destroy()
    delete charts[key]
  }

  function renderHeader(r) {
    el('rd-asof').textContent = r.as_of
    el('rd-window').textContent = r.window.trading_days + ' trading days, ' + r.window.start + ' to ' + r.window.end
    el('rd-bench-label').textContent = r.window.benchmark
  }

  function arcPath(cx, cy, rOuter, rInner, a0, a1) {
    var s0 = Math.PI * (1 - a0), s1 = Math.PI * (1 - a1)
    var x0 = cx + rOuter * Math.cos(s0), y0 = cy - rOuter * Math.sin(s0)
    var x1 = cx + rOuter * Math.cos(s1), y1 = cy - rOuter * Math.sin(s1)
    var x2 = cx + rInner * Math.cos(s1), y2 = cy - rInner * Math.sin(s1)
    var x3 = cx + rInner * Math.cos(s0), y3 = cy - rInner * Math.sin(s0)
    return 'M' + x0 + ' ' + y0 + ' A' + rOuter + ' ' + rOuter + ' 0 0 1 ' + x1 + ' ' + y1 +
      ' L' + x2 + ' ' + y2 + ' A' + rInner + ' ' + rInner + ' 0 0 0 ' + x3 + ' ' + y3 + ' Z'
  }

  function renderMeter(r) {
    var m = r.risk_meter
    var color = levelColor(m.level)
    var cx = 125, cy = 135, ro = 110, ri = 84
    var bands = [[0, 0.25, C.green], [0.25, 0.5, C.amber], [0.5, 0.75, C.orange], [0.75, 1, C.danger]]
    var gap = 0.008
    var svg = '<svg viewBox="0 0 250 150" role="img" aria-label="Risk meter ' + esc(m.level) + '">'
    bands.forEach(function (b) {
      svg += '<path d="' + arcPath(cx, cy, ro, ri, b[0] + (b[0] ? gap : 0), b[1] - (b[1] < 1 ? gap : 0)) + '" fill="' + b[2] + '" opacity="0.28"/>'
    })
    var frac = Math.max(0, Math.min(1, m.score / 100))
    svg += '<path d="' + arcPath(cx, cy, ro, ri, 0, Math.max(frac, 0.01)) + '" fill="' + color + '"/>'
    svg += '</svg>'
    svg += '<div class="rd-gauge__level"><div class="rd-gauge__score" style="color:' + color + '">' + Math.round(m.score) + '</div><div class="rd-gauge__name" style="color:' + color + '">' + esc(m.level) + '</div></div>'
    el('rd-gauge').innerHTML = svg

    var pill = el('rd-level-pill')
    pill.className = 'rd-pill rd-pill--' + (LEVEL_PILL[m.level] || 'grey')
    pill.textContent = m.level + ' risk'

    var fmt = { volatility: pct, max_drawdown: pct, cvar: pct, concentration: function (v) { return num(v, 3) }, correlation: function (v) { return num(v, 2) } }
    el('rd-components').innerHTML = m.components.map(function (c) {
      var cc = c.score < 25 ? C.green : c.score < 50 ? C.amber : c.score < 75 ? C.orange : C.danger
      return '<div class="rd-comp"><div><span class="rd-comp__n">' + esc(c.name) + '</span><span class="rd-comp__v">' + (fmt[c.key] || num)(c.value) + '</span></div>' +
        '<div class="rd-bar" title="Score ' + c.score + ' of 100, weight ' + pct(c.weight, 0) + '"><span style="width:' + c.score + '%; background:' + cc + '"></span></div>' +
        '<div class="rd-comp__s">' + Math.round(c.score) + '</div></div>'
    }).join('')
  }

  function tile(label, value, cls, note) {
    return '<div class="rd-stat"><div class="rd-stat__l">' + esc(label) + '</div><div class="rd-stat__v ' + (cls || '') + '">' + value + '</div>' + (note ? '<div class="rd-stat__n">' + note + '</div>' : '') + '</div>'
  }

  function renderStats(r) {
    var s = r.summary, d = r.downside, cur = r.portfolio.base_currency, v = r.portfolio.value
    var conf = Math.round(d.confidence * 100)
    var cls = function (x) { return x > 0 ? 'pos' : x < 0 ? 'neg' : '' }
    el('rd-stats').innerHTML = [
      tile('Return (annualized)', signedPct(s.annualized_return), cls(s.annualized_return), s.benchmark + ' ' + signedPct(s.benchmark_annualized_return)),
      tile('Volatility (annualized)', pct(s.annualized_volatility), '', s.benchmark + ' ' + pct(s.benchmark_annualized_volatility)),
      tile('Max drawdown', pct(s.max_drawdown), 'neg', esc(s.drawdown_peak_date) + ' to ' + esc(s.drawdown_trough_date) + (s.drawdown_recovery_date ? ', recovered' : ', not recovered')),
      tile('Sharpe', num(s.sharpe), '', 'Current drawdown ' + pct(s.current_drawdown)),
      tile('Beta to ' + s.benchmark, num(s.beta), '', 'Correlation ' + num(s.correlation_to_benchmark)),
      tile('VaR ' + conf + ' (1 day)', pct(d.var_historical, 2), 'neg', v ? money(d.var_historical_value, cur) + ' historical' : 'historical'),
      tile('CVaR ' + conf + ' (1 day)', pct(d.cvar_historical, 2), 'neg', v ? money(d.cvar_historical_value, cur) + ' historical' : 'historical'),
      tile('Worst day', pct(d.worst_windows[0].return, 2), 'neg', esc(d.worst_windows[0].end) + (d.worst_windows[2] ? ', worst 20 days ' + pct(d.worst_windows[2].return) : ''))
    ].join('')
  }

  function renderWarnings(r) {
    var box = el('rd-warnings')
    if (!r.warnings.length) {
      box.innerHTML = '<div class="rd-ok">No thresholds crossed. Concentration, downside and market dependence are inside the limits.</div>'
      return
    }
    var pill = { critical: 'red', warning: 'amber', info: 'info' }
    box.innerHTML = r.warnings.map(function (w) {
      return '<div class="rd-warn rd-warn--' + w.level + '"><span class="rd-pill rd-pill--' + pill[w.level] + '">' + w.level + '</span>' +
        '<div><div class="rd-warn__t">' + esc(w.title) + '</div><div class="rd-warn__m">' + esc(w.message) + '</div></div></div>'
    }).join('')
  }

  function renderContribution(r) {
    var rows = r.risk_contribution.positions
    el('rd-contrib-wrap').style.height = Math.max(180, rows.length * 44 + 40) + 'px'
    destroy('contrib')
    var opts = baseOptions()
    opts.indexAxis = 'y'
    opts.layout = { padding: { right: 48 } }
    opts.scales.x.ticks.callback = function (v) { return pct(v, 0) }
    opts.scales.x.beginAtZero = true
    opts.scales.y.grid.display = false
    opts.scales.y.ticks.font = { size: 12, weight: '700' }
    opts.plugins.tooltip.callbacks = { label: function (c) { return c.dataset.label + ': ' + pct(c.raw) } }
    charts.contrib = new Chart(el('rd-contrib'), {
      type: 'bar',
      data: {
        labels: rows.map(function (p) { return p.ticker }),
        datasets: [
          { label: 'Risk share', data: rows.map(function (p) { return p.share }), backgroundColor: C.red, borderRadius: 4, maxBarThickness: 16, endLabel: function (v) { return pct(v, 0) } },
          { label: 'Weight', data: rows.map(function (p) { return Math.abs(p.weight) }), backgroundColor: C.grey, borderRadius: 4, maxBarThickness: 16 }
        ]
      },
      options: opts,
      plugins: [endLabels]
    })
  }

  function mix(a, b, t) {
    var pa = [parseInt(a.slice(1, 3), 16), parseInt(a.slice(3, 5), 16), parseInt(a.slice(5, 7), 16)]
    var pb = [parseInt(b.slice(1, 3), 16), parseInt(b.slice(3, 5), 16), parseInt(b.slice(5, 7), 16)]
    var c = pa.map(function (x, i) { return Math.round(x + (pb[i] - x) * t) })
    return 'rgb(' + c.join(',') + ')'
  }
  function corrColor(v) {
    return v >= 0 ? mix(C.neutral, C.red, Math.min(1, v)) : mix(C.neutral, C.blue, Math.min(1, -v))
  }

  function renderHeatmap(r) {
    var t = r.correlation.tickers, m = r.correlation.matrix
    var n = t.length
    var html = '<div class="rd-heat" style="grid-template-columns: 64px repeat(' + n + ', 1fr)">'
    html += '<div></div>' + t.map(function (x) { return '<div class="rd-heat__h">' + esc(x) + '</div>' }).join('')
    t.forEach(function (row, i) {
      html += '<div class="rd-heat__r">' + esc(row) + '</div>'
      t.forEach(function (col, j) {
        var v = m[i][j]
        var fg = Math.abs(v) > 0.55 ? '#fff' : C.ink
        var label = i === j ? '' : num(v, 2)
        html += '<div class="rd-heat__c" style="background:' + corrColor(v) + '; color:' + fg + '" title="' + esc(row) + ' vs ' + esc(col) + ': ' + num(v, 2) + '">' + label + '</div>'
      })
    })
    html += '</div>'
    el('rd-heatmap').innerHTML = html
    var c = r.correlation
    el('rd-corr-note').textContent = 'Average ' + num(c.average_pairwise) + (c.highest_pair ? ', highest ' + c.highest_pair.a + ' / ' + c.highest_pair.b + ' ' + num(c.highest_pair.value) : '')
  }

  function renderGrowth(r) {
    var s = r.series
    var labels = s.dates
    var tickEvery = Math.max(1, Math.round(labels.length / 6))
    destroy('growth')
    destroy('drawdown')
    var opts = baseOptions()
    opts.interaction = { mode: 'index', intersect: false }
    opts.scales.x.grid.display = false
    opts.scales.x.ticks.maxRotation = 0
    opts.scales.x.ticks.autoSkip = false
    opts.scales.x.ticks.callback = function (v, i) { return i % tickEvery === 0 ? labels[i] : '' }
    opts.scales.y.ticks.callback = function (v) { return num(v, 2) }
    opts.plugins.tooltip.callbacks = { label: function (c) { return c.dataset.label + ': ' + num(c.raw, 3) } }
    charts.growth = new Chart(el('rd-growth'), {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          { label: 'Portfolio', data: s.portfolio, borderColor: C.red, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.1 },
          { label: r.window.benchmark, data: s.benchmark, borderColor: C.grey, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.1 }
        ]
      },
      options: opts
    })
    var dopts = baseOptions()
    dopts.interaction = { mode: 'index', intersect: false }
    dopts.scales.x.grid.display = false
    dopts.scales.x.ticks.display = false
    dopts.scales.y.ticks.callback = function (v) { return pct(v, 0) }
    dopts.scales.y.max = 0
    dopts.plugins.tooltip.callbacks = { label: function (c) { return 'Drawdown ' + pct(c.raw, 2) } }
    charts.drawdown = new Chart(el('rd-drawdown'), {
      type: 'line',
      data: { labels: labels, datasets: [{ label: 'Drawdown', data: s.drawdown, borderColor: C.red, backgroundColor: 'rgba(174,31,25,0.10)', fill: true, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.1 }] },
      options: dopts
    })
  }

  function weightRow(name, sub, weight, color) {
    return '<div class="rd-wrow"><div class="rd-wrow__t">' + esc(name) + (sub ? '<span class="rd-wrow__n">' + esc(sub) + '</span>' : '') + '</div>' +
      '<div class="rd-bar"><span style="width:' + Math.min(100, weight * 100) + '%; background:' + color + '"></span></div>' +
      '<div class="rd-wrow__p">' + pct(weight, 1) + '</div></div>'
  }

  function renderConcentration(r) {
    var c = r.concentration
    el('rd-conc-stats').innerHTML = [
      tile('Effective positions', num(c.effective_positions, 1), '', 'HHI ' + num(c.hhi, 3)),
      tile('Top 3 weight', pct(c.top3_weight, 0), '', 'Largest ' + esc(c.top_position.ticker) + ' ' + pct(c.top_position.weight, 0))
    ].join('')
    var byTicker = {}
    r.positions.forEach(function (p) { byTicker[p.ticker] = p })
    var sorted = r.positions.slice().sort(function (a, b) { return Math.abs(b.weight) - Math.abs(a.weight) })
    el('rd-weights').innerHTML = sorted.map(function (p) {
      return weightRow(p.ticker, p.name !== p.ticker ? p.name : '', Math.abs(p.weight), C.red)
    }).join('')
    el('rd-sectors').innerHTML = c.sectors.map(function (s) {
      return weightRow(s.sector, s.positions.join(', '), s.weight, C.greyDark)
    }).join('')
  }

  function renderStress(r) {
    var tests = r.stress_tests
    var cur = r.portfolio.base_currency, v = r.portfolio.value
    el('rd-stress-wrap').style.height = (tests.length * 40 + 40) + 'px'
    destroy('stress')
    var opts = baseOptions()
    opts.indexAxis = 'y'
    opts.layout = { padding: { right: 56 } }
    opts.scales.x.grace = '8%'
    opts.scales.x.ticks.callback = function (x) { return pct(x, 0) }
    opts.scales.y.grid.display = false
    opts.scales.y.ticks.font = { size: 12, weight: '700' }
    opts.plugins.tooltip.callbacks = { label: function (c) { return 'Portfolio move ' + signedPct(c.raw) } }
    charts.stress = new Chart(el('rd-stress'), {
      type: 'bar',
      data: {
        labels: tests.map(function (t) { return t.name }),
        datasets: [{
          data: tests.map(function (t) { return t.portfolio_loss_pct }),
          backgroundColor: tests.map(function (t) { return t.portfolio_loss_pct < 0 ? C.red : C.green }),
          borderRadius: 4, maxBarThickness: 18,
          endLabel: function (x) { return signedPct(x) }
        }]
      },
      options: opts,
      plugins: [endLabels]
    })

    el('rd-scenarios').innerHTML = tests.map(function (t) {
      var loss = t.portfolio_loss_pct
      var color = loss === null ? C.grey : loss < 0 ? C.danger : C.green
      var top = t.positions.filter(function (p) { return p.loss_pct < 0 }).slice(0, 3)
      var maxShare = top.length ? Math.max.apply(null, top.map(function (p) { return p.share_of_loss })) : 1
      var rows = top.map(function (p) {
        return '<div class="rd-scen__row"><b>' + esc(p.ticker) + '</b><div class="rd-bar"><span style="width:' + (p.share_of_loss / maxShare * 100) + '%; background:' + C.red + '"></span></div><span>' + pct(p.share_of_loss, 0) + '</span></div>'
      }).join('')
      var extra = ''
      if (t.details) extra = '<div class="rd-scen__v">Volatility ' + pct(t.details.volatility_before) + ' to ' + pct(t.details.volatility_after) + ', average correlation ' + num(t.details.average_correlation_before) + ' to ' + num(t.details.average_correlation_after) + '</div>'
      if (t.sector) extra = '<div class="rd-scen__v">Sector: ' + esc(t.sector) + (t.note ? '. ' + esc(t.note) : '') + '</div>'
      return '<div class="rd-scen__c"><div class="rd-scen__n">' + esc(t.name) + '</div><div class="rd-scen__d">' + esc(t.description) + '</div>' +
        '<div class="rd-scen__l" style="color:' + color + '">' + (loss === null ? '—' : signedPct(loss)) + '</div>' +
        '<div class="rd-scen__v">' + (v && t.portfolio_loss_value !== null ? money(t.portfolio_loss_value, cur) : '') + '</div>' + extra +
        (top.length ? '<div class="rd-scen__v" style="margin-top:6px;">Share of the loss</div>' + rows : '') + '</div>'
    }).join('')
  }

  function renderPositions(r) {
    var cur = r.portfolio.base_currency
    el('rd-positions-body').innerHTML = r.positions.map(function (p) {
      var ratio = p.weight ? p.risk_share / Math.abs(p.weight) : 0
      return '<tr><td class="sym">' + esc(p.ticker) + '<small>' + esc(p.name) + '</small></td><td>' + esc(p.sector) + '</td><td>' + pct(p.weight) + '</td><td>' + (p.value === null ? '—' : money(p.value, cur)) + '</td>' +
        '<td class="' + (p.period_return >= 0 ? 'pos' : 'neg') + '">' + signedPct(p.period_return) + '</td><td>' + pct(p.annualized_volatility) + '</td><td>' + pct(p.max_drawdown) + '</td><td>' + num(p.beta) + '</td><td>' + pct(p.var_historical, 2) + '</td>' +
        '<td>' + pct(p.risk_share) + '</td><td class="' + (ratio > 1.2 ? 'flag' : '') + '">' + num(ratio, 2) + 'x</td></tr>'
    }).join('')
  }

  function render(report) {
    state.report = report
    renderHeader(report)
    renderMeter(report)
    renderStats(report)
    renderWarnings(report)
    renderContribution(report)
    renderHeatmap(report)
    renderGrowth(report)
    renderConcentration(report)
    renderStress(report)
    renderPositions(report)
    el('rd-body').classList.remove('rd-loading')
  }

  // "AAPL 25, MSFT 20" or "AAPL:25" or "AAPL, MSFT" for equal weights.
  function parsePositions(text) {
    var out = []
    text.split(/[,\n]+/).forEach(function (chunk) {
      var parts = chunk.trim().split(/[\s:=]+/).filter(Boolean)
      if (!parts.length) return
      var pos = { ticker: parts[0].toUpperCase() }
      if (parts[1] !== undefined) pos.weight = parseFloat(parts[1])
      out.push(pos)
    })
    var withWeight = out.filter(function (p) { return p.weight !== undefined && !isNaN(p.weight) })
    if (withWeight.length && withWeight.length !== out.length) throw new Error('Give every ticker a weight, or none of them')
    return out
  }

  function showError(msg) {
    var box = el('rd-error')
    box.textContent = msg
    box.classList.toggle('show', !!msg)
  }

  function load(request) {
    el('rd-body').classList.add('rd-loading')
    el('rd-run').disabled = true
    showError('')
    return fetch(state.apiBase + '/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request)
    }).then(function (res) {
      return res.json().then(function (body) {
        if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail))
        return body
      })
    }).then(function (report) {
      render(report)
      return report
    }).catch(function (err) {
      showError(err.message)
      el('rd-body').classList.remove('rd-loading')
      throw err
    }).finally(function () {
      el('rd-run').disabled = false
    })
  }

  function requestFromForm() {
    var value = parseFloat(String(el('rd-value').value).replace(/[^0-9.]/g, ''))
    return {
      positions: parsePositions(el('rd-positions').value),
      benchmark: el('rd-benchmark').value.trim().toUpperCase() || 'SPY',
      lookback_days: parseInt(el('rd-lookback').value, 10),
      portfolio_value: isNaN(value) || value <= 0 ? null : value,
      base_currency: el('rd-currency').value
    }
  }

  function init(opts) {
    state.apiBase = (opts && opts.apiBase) || ''
    el('rd-form').addEventListener('submit', function (e) {
      e.preventDefault()
      try {
        load(requestFromForm()).catch(function () {})
      } catch (err) {
        showError(err.message)
      }
    })
    load(requestFromForm()).catch(function () {})
  }

  return { init: init, load: load, render: render, parsePositions: parsePositions, state: state }
})()
