/* Expense tracker: add/edit sheet + charts. Data comes from json_script blocks. */
var Expenses = (function () {
  function readJson(id) {
    var el = document.getElementById(id);
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }

  var data = readJson('expense-data') || {};
  var current = null;
  var addUrl = (document.getElementById('expenseForm') || {}).action;

  function $(id) { return document.getElementById(id); }

  function setText(id, text) {
    var el = $(id);
    if (el) el.textContent = text || '';
  }

  function toggle(id, show, display) {
    var el = $(id);
    if (!el) return;
    el.classList.toggle('hidden', !show);
    if (display) el.classList.toggle(display, !!show);
  }

  function syncRemember() {
    var merchant = $('expMerchant').value.trim();
    var category = $('expCategory').value;
    var changed = !current || String(current.category) !== category;
    toggle('expRememberRow', !!(merchant && category && changed), 'flex');
    setText('expRememberName', merchant || 'this merchant');
  }

  function open(id) {
    var form = $('expenseForm');
    if (!form) return;
    current = id ? data[String(id)] : null;
    form.reset();

    if (current) {
      form.action = current.edit_url;
      setText('expModalTitle', 'Edit expense');
      $('expAmount').value = String(current.amount).replace(/\.00$/, '');
      $('expMerchant').value = current.merchant;
      $('expDate').value = current.txn_date;
      $('expCategory').value = current.category;
      $('expSource').value = current.payment_source;
      $('expMember').value = current.member;
      $('expNotes').value = current.notes || '';
      (current.direction === 'CREDIT' ? $('expDirCredit') : $('expDirDebit')).checked = true;

      var reasons = $('expFlagReasons');
      reasons.innerHTML = '';
      (current.flag_reasons || []).forEach(function (r) {
        var li = document.createElement('li');
        li.textContent = r;
        reasons.appendChild(li);
      });
      toggle('expFlagBox', current.flagged, 'flex');
      $('expReviewForm').action = current.review_url;

      setText('expMetaSource', current.source);
      setText('expMetaCat', current.category_source);
      setText('expMetaRaw', current.raw);
      setText('expMetaSubject', current.subject);
      toggle('expMetaRawLbl', !!current.raw);
      toggle('expMetaRaw', !!current.raw);
      toggle('expMetaSubjLbl', !!current.subject);
      toggle('expMetaSubject', !!current.subject);
      toggle('expMeta', true);
      toggle('expDeleteBtn', true, 'inline-flex');
      $('expDeleteForm').action = current.delete_url;
    } else {
      form.action = addUrl;
      setText('expModalTitle', 'Add expense');
      $('expDate').value = new Date().toLocaleDateString('en-CA');
      var self = document.querySelector('#expMember option[data-self]');
      if (self) $('expMember').value = self.value;
      toggle('expFlagBox', false, 'flex');
      toggle('expMeta', false);
      toggle('expDeleteBtn', false, 'inline-flex');
    }
    syncRemember();
    openModal('expenseModal');
    if (!current) setTimeout(function () { $('expAmount').focus(); }, 60);
  }

  function remove() {
    if (!current) return;
    var msg = current.source === 'Manual'
      ? 'Delete this expense? This cannot be undone.'
      : 'Remove this ' + current.source.toLowerCase() + ' transaction? It will not be re-imported on the next sync.';
    confirmDelete('expDeleteForm', msg);
  }

  /* ── Charts ─────────────────────────────────────────────────────── */

  var ORANGE = '#fb923c';

  function palette() {
    var dark = document.documentElement.getAttribute('data-theme') !== 'winter';
    return {
      grid: dark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.06)',
      tick: 'rgba(128,128,128,0.6)',
      muted: dark ? 'rgba(255,255,255,0.28)' : 'rgba(0,0,0,0.28)',
      soft: dark ? 'rgba(148,163,184,0.22)' : 'rgba(100,116,139,0.22)',
      label: dark ? 'rgba(255,255,255,0.7)' : 'rgba(0,0,0,0.65)',
    };
  }

  // Draws a short ₹ value above each bar of the first dataset (readable on phones without tapping).
  var barValues = {
    id: 'expBarValues',
    afterDatasetsDraw: function (chart) {
      var meta = chart.getDatasetMeta(0);
      var ctx = chart.ctx;
      ctx.save();
      ctx.font = '600 10px ui-sans-serif, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = palette().label;
      meta.data.forEach(function (bar, i) {
        var v = chart.data.datasets[0].data[i];
        if (v) ctx.fillText(inrShort(v), bar.x, bar.y - 5);
      });
      ctx.restore();
    },
  };

  function inr(v) {
    return '₹' + Math.round(v).toLocaleString('en-IN');
  }

  function inrShort(v) {
    if (v >= 1e7) return '₹' + (v / 1e7).toFixed(1) + 'Cr';
    if (v >= 1e5) return '₹' + (v / 1e5).toFixed(1) + 'L';
    if (v >= 1e3) return '₹' + Math.round(v / 1e3) + 'K';
    return '₹' + Math.round(v);
  }

  var tooltip = {
    backgroundColor: 'oklch(0.2 0 0 / 0.95)',
    borderColor: 'rgba(128,128,128,0.15)',
    borderWidth: 1,
    titleColor: '#ddd',
    bodyColor: '#aaa',
    padding: 10,
    cornerRadius: 8,
    displayColors: false,
  };

  function cumulative(values, upto) {
    var out = [], run = 0;
    for (var i = 0; i < values.length; i++) {
      run += values[i];
      out.push(upto != null && i >= upto ? null : run);
    }
    return out;
  }

  // This month's running total against last month's, so a big day-1 rent payment doesn't hide the rest.
  function paceChart(canvas, d) {
    var c = palette();
    var days = Math.max(d.daily.length, d.prev_daily.length);
    var labels = [];
    for (var i = 1; i <= days; i++) labels.push(i);
    var current = cumulative(d.daily, d.upto);
    var previous = cumulative(d.prev_daily);
    var last = d.upto - 1;
    new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: d.label, data: current, borderColor: ORANGE, borderWidth: 2.5, tension: 0.25,
            backgroundColor: function (ctx) {
              var area = ctx.chart.chartArea;
              if (!area) return 'transparent';
              var g = ctx.chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
              g.addColorStop(0, 'rgba(251,146,60,0.28)');
              g.addColorStop(1, 'rgba(251,146,60,0)');
              return g;
            },
            fill: true,
            pointRadius: function (ctx) { return ctx.dataIndex === last ? 4 : 0; },
            pointBackgroundColor: ORANGE, pointBorderColor: '#0a0a14', pointBorderWidth: 2, pointHoverRadius: 4,
          },
          {
            label: d.prev_label, data: previous, borderColor: c.muted, borderWidth: 1.5, borderDash: [4, 4],
            tension: 0.25, pointRadius: 0, pointHoverRadius: 3, fill: false,
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 700 },
        interaction: { mode: 'index', intersect: false },
        layout: { padding: { top: 6, right: 4 } },
        plugins: {
          legend: { display: false },
          tooltip: Object.assign({}, tooltip, {
            displayColors: true, usePointStyle: true,
            callbacks: {
              title: function (items) { return 'By day ' + items[0].label; },
              label: function (item) { return item.raw == null ? null : ' ' + item.dataset.label + '  ' + inr(item.raw); },
            },
          }),
        },
        scales: {
          x: {
            grid: { display: false }, border: { display: false },
            ticks: { color: c.tick, font: { size: 9 }, maxRotation: 0, autoSkip: false,
                     callback: function (v, i) { var n = i + 1; return n === 1 || n % 7 === 0 || n === days ? n : ''; } },
          },
          y: { display: false, beginAtZero: true },
        },
      },
    });
  }

  function trendChart(canvas, d) {
    var c = palette();
    var datasets = [{
      type: 'bar', data: d.values, borderRadius: 6, borderSkipped: false, maxBarThickness: 34,
      backgroundColor: d.values.map(function (_, i) { return i === d.selected ? ORANGE : c.soft; }),
    }];
    if (d.avg) {
      datasets.push({
        type: 'line', data: d.values.map(function () { return d.avg; }), borderColor: c.muted,
        borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, pointHoverRadius: 0,
      });
    }
    new Chart(canvas, {
      data: { labels: d.labels, datasets: datasets },
      plugins: [barValues],
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 600 },
        layout: { padding: { top: 16 } },
        onClick: function (_, els) {
          if (els.length) window.location.search = '?m=' + d.params[els[0].index];
        },
        onHover: function (evt, els) { evt.native.target.style.cursor = els.length ? 'pointer' : 'default'; },
        plugins: {
          legend: { display: false },
          tooltip: Object.assign({}, tooltip, {
            filter: function (item) { return item.datasetIndex === 0; },
            callbacks: {
              label: function (item) { return inr(item.raw) + (d.partial[item.dataIndex] ? ' so far' : ''); },
              afterLabel: function () { return d.avg ? 'Average ' + inr(d.avg) : ''; },
            },
          }),
        },
        scales: {
          x: { grid: { display: false }, border: { display: false }, ticks: { color: c.tick, font: { size: 10 } } },
          y: { display: false, beginAtZero: true },
        },
      },
    });
  }

  // Vault's chart palette: category hues sit too close together (food vs fuel) to tell apart when stacked.
  var STACK_COLORS = ['#648cfa', '#a78bfa', '#34d399', '#fbbf24', '#f87171'];

  function yearChart(canvas, d) {
    var c = palette();
    var datasets = d.stack.map(function (s, i) {
      var color = s.hue == null ? 'rgba(148,163,184,0.55)' : STACK_COLORS[i % STACK_COLORS.length];
      return {
        type: 'bar', label: s.label, data: s.values, stack: 'spend',
        backgroundColor: color, hoverBackgroundColor: color,
        borderRadius: i === d.stack.length - 1 ? { topLeft: 5, topRight: 5 } : 0, borderSkipped: false,
        maxBarThickness: 30,
      };
    });
    if (d.avg) {
      datasets.push({
        type: 'line', label: 'Monthly average', data: d.labels.map(function () { return d.avg; }),
        borderColor: c.muted, borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, pointHoverRadius: 0, stack: 'avg',
      });
    }
    new Chart(canvas, {
      data: { labels: d.labels, datasets: datasets },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 700 },
        interaction: { mode: 'index', intersect: false },
        onClick: function (_, els) {
          if (els.length) window.location.href = canvas.dataset.monthUrl + '?m=' + d.params[els[0].index];
        },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: c.tick, usePointStyle: true, pointStyle: 'circle', boxWidth: 7, boxHeight: 7, padding: 12, font: { size: 11 },
                      filter: function (item) { return item.text !== 'Monthly average'; } },
          },
          tooltip: Object.assign({}, tooltip, {
            displayColors: true, usePointStyle: true, itemSort: function (a, b) { return b.raw - a.raw; },
            filter: function (item) { return item.raw > 0 && item.dataset.type === 'bar'; },
            callbacks: {
              label: function (item) { return ' ' + item.dataset.label + '  ' + inr(item.raw); },
              footer: function (items) {
                var t = items.reduce(function (s, i) { return s + (i.dataset.type === 'bar' ? i.raw : 0); }, 0);
                return 'Total  ' + inr(t);
              },
            },
          }),
        },
        scales: {
          x: { stacked: true, grid: { display: false }, border: { display: false },
               ticks: { color: c.tick, font: { size: 10 }, maxRotation: 0, autoSkip: false } },
          y: {
            stacked: true, beginAtZero: true, grid: { color: c.grid }, border: { display: false },
            ticks: { color: c.tick, font: { size: 10 }, maxTicksLimit: 5, callback: inrShort },
          },
        },
      },
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var merchant = $('expMerchant');
    var category = $('expCategory');
    if (merchant) merchant.addEventListener('input', syncRemember);
    if (category) category.addEventListener('change', syncRemember);

    if (typeof Chart !== 'undefined') {
      var pace = readJson('expense-chart');
      if (pace && $('paceChart')) paceChart($('paceChart'), pace);
      var trend = readJson('expense-trend-chart');
      if (trend && $('trendChart')) trendChart($('trendChart'), trend);
      var year = readJson('expense-year-chart');
      if (year && $('yearChart')) yearChart($('yearChart'), year);
    }

    var params = new URLSearchParams(window.location.search);
    if (params.get('add') === '1') open();
  });

  return { open: open, remove: remove };
})();
