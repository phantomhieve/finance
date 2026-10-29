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
    if (!changed && $('expRemember')) $('expRemember').checked = false;
  }

  function open(id) {
    var form = $('expenseForm');
    if (!form) return;
    current = id ? data[String(id)] : null;
    form.reset();
    if ($('expRemember')) $('expRemember').checked = false;

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

      if (current.is_refunded || current.direction === 'CREDIT') {
        if (current.is_refunded) {
          setText('expRefundDetail', 'Refunded on ' + (current.refund_date || 'card') + ' · ₹' + current.refunded_amount + ' refunded (Net: ₹' + current.net_amount + ')');
        } else {
          setText('expRefundDetail', 'Refund / reversal received on ' + (current.txn_date || 'card') + ' · ₹' + current.amount + ' credited back to your account');
        }
        toggle('expRefundBox', true, 'flex');
      } else {
        toggle('expRefundBox', false);
      }

      if (current.is_emi) {
        var emiTxt = 'Active EMI transaction';
        if (current.emi_installment_num && current.emi_total_installments) {
          var pending = Math.max(0, current.emi_total_installments - current.emi_installment_num);
          emiTxt = 'Installment #' + current.emi_installment_num + ' of ' + current.emi_total_installments + ' · ' + (pending === 0 ? 'Final installment' : (pending + ' pending'));
        } else if (current.emi_installment_num) {
          emiTxt = 'Installment #' + current.emi_installment_num + ' · Tenure unknown';
        }
        if (current.emi_reference) emiTxt += ' (Loan ••' + current.emi_reference + ')';
        setText('expEmiDetail', emiTxt);
        toggle('expEmiBox', true, 'flex');
      } else {
        toggle('expEmiBox', false);
      }
      if ($('expIsEmi')) $('expIsEmi').checked = !!current.is_emi;
      if ($('expEmiInstallmentNum')) $('expEmiInstallmentNum').value = current.emi_installment_num || '';
      if ($('expEmiTotalInstallments')) $('expEmiTotalInstallments').value = current.emi_total_installments || '';
      toggle('expEmiFields', !!current.is_emi, 'flex');
      syncEmiPending();

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
      if ($('expIsEmi')) $('expIsEmi').checked = false;
      if ($('expEmiInstallmentNum')) $('expEmiInstallmentNum').value = '';
      if ($('expEmiTotalInstallments')) $('expEmiTotalInstallments').value = '';
      toggle('expEmiFields', false);
      setText('expEmiPendingNote', '');
      toggle('expFlagBox', false, 'flex');
      toggle('expRefundBox', false);
      toggle('expEmiBox', false);
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
  var _yearChartInstance = null;
  var _yearChartData = null;
  var _yearChartCanvas = null;
  var _yearChartMode = 'stacked';

  var yearTopValues = {
    id: 'expYearTopValues',
    afterDatasetsDraw: function (chart) {
      var d = _yearChartData;
      if (!d || !d.totals) return;
      var ctx = chart.ctx;
      var barDatasetIndices = [];
      chart.data.datasets.forEach(function (ds, idx) {
        if (ds.type === 'bar' && chart.isDatasetVisible(idx)) barDatasetIndices.push(idx);
      });
      if (!barDatasetIndices.length) return;
      ctx.save();
      ctx.font = '600 9.5px Inter, ui-sans-serif, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillStyle = palette().label;
      d.labels.forEach(function (_, i) {
        var topY = Infinity;
        var barX = null;
        var sum = 0;
        barDatasetIndices.forEach(function (dsIdx) {
          var val = chart.data.datasets[dsIdx].data[i] || 0;
          if (val > 0) {
            sum += val;
            var meta = chart.getDatasetMeta(dsIdx);
            var el = meta && meta.data && meta.data[i];
            if (el) {
              barX = el.x;
              if (el.y < topY) topY = el.y;
            }
          }
        });
        if (sum > 0 && barX != null && topY < Infinity) {
          ctx.fillText(inrShort(sum), barX, Math.max(10, topY - 5));
        }
      });
      ctx.restore();
    },
  };

  function buildYearDatasets(d, mode, c) {
    var datasets = [];
    if (mode === 'total' && d.totals) {
      var peak = Math.max.apply(null, d.totals);
      datasets.push({
        type: 'bar',
        label: 'Monthly spend',
        data: d.totals,
        stack: 'spend',
        backgroundColor: d.totals.map(function (v, i) {
          if (d.partial && d.partial[i]) return 'rgba(251, 146, 60, 0.65)';
          if (peak > 0 && v === peak) return '#f87171';
          return ORANGE;
        }),
        hoverBackgroundColor: ORANGE,
        borderRadius: { topLeft: 6, topRight: 6 },
        borderSkipped: false,
        maxBarThickness: 32,
      });
    } else {
      datasets = d.stack.map(function (s, i) {
        var color = s.hue == null ? 'rgba(148,163,184,0.55)' : STACK_COLORS[i % STACK_COLORS.length];
        return {
          type: 'bar', label: s.label, data: s.values, stack: 'spend',
          backgroundColor: color, hoverBackgroundColor: color,
          borderRadius: i === d.stack.length - 1 ? { topLeft: 5, topRight: 5 } : 0, borderSkipped: false,
          maxBarThickness: 30,
        };
      });
    }
    if (d.avg) {
      datasets.push({
        type: 'line', label: 'Monthly average', data: d.labels.map(function () { return d.avg; }),
        borderColor: c.muted, borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, pointHoverRadius: 0, stack: 'avg',
      });
    }
    return datasets;
  }

  function yearChart(canvas, d) {
    _yearChartCanvas = canvas;
    _yearChartData = d;
    var c = palette();
    if (_yearChartInstance) {
      _yearChartInstance.destroy();
    }
    var datasets = buildYearDatasets(d, _yearChartMode, c);
    _yearChartInstance = new Chart(canvas, {
      data: { labels: d.labels, datasets: datasets },
      plugins: [yearTopValues],
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 650 },
        layout: { padding: { top: 18 } },
        interaction: { mode: 'index', intersect: false },
        onClick: function (_, els) {
          if (els.length) window.location.href = canvas.dataset.monthUrl + '?m=' + d.params[els[0].index];
        },
        onHover: function (evt, els) {
          if (evt && evt.native && evt.native.target) {
            evt.native.target.style.cursor = els.length ? 'pointer' : 'default';
          }
        },
        plugins: {
          legend: {
            display: _yearChartMode === 'stacked',
            position: 'bottom',
            labels: { color: c.tick, usePointStyle: true, pointStyle: 'circle', boxWidth: 7, boxHeight: 7, padding: 12, font: { size: 11 },
                      filter: function (item) { return item.text !== 'Monthly average'; } },
          },
          tooltip: Object.assign({}, tooltip, {
            displayColors: true, usePointStyle: true, itemSort: function (a, b) { return b.raw - a.raw; },
            filter: function (item) { return item.raw > 0 && item.dataset.type === 'bar'; },
            callbacks: {
              label: function (item) {
                var suffix = (_yearChartMode === 'total' && d.partial && d.partial[item.dataIndex]) ? ' (in progress)' : '';
                return ' ' + item.dataset.label + '  ' + inr(item.raw) + suffix;
              },
              footer: function (items) {
                if (_yearChartMode === 'total') {
                  return d.avg ? 'Monthly avg  ' + inr(d.avg) : '';
                }
                var t = items.reduce(function (s, i) { return s + (i.dataset.type === 'bar' ? i.raw : 0); }, 0);
                return 'Total  ' + inr(t);
              },
            },
          }),
        },
        scales: {
          x: { stacked: true, grid: { display: false }, border: { display: false },
               ticks: { color: c.tick, font: { size: 10, weight: '600' }, maxRotation: 0, autoSkip: false } },
          y: {
            stacked: true, beginAtZero: true, grid: { color: c.grid }, border: { display: false },
            ticks: { color: c.tick, font: { size: 10 }, maxTicksLimit: 5, callback: inrShort },
          },
        },
      },
    });
  }

  function setYearChartMode(mode) {
    if (!_yearChartCanvas || !_yearChartData) return;
    _yearChartMode = mode === 'total' ? 'total' : 'stacked';
    yearChart(_yearChartCanvas, _yearChartData);
    var btnStacked = $('yearChartBtnStacked');
    var btnTotal = $('yearChartBtnTotal');
    if (btnStacked && btnTotal) {
      var isStacked = _yearChartMode === 'stacked';
      btnStacked.classList.toggle('bg-primary', isStacked);
      btnStacked.classList.toggle('text-primary-content', isStacked);
      btnStacked.classList.toggle('opacity-60', !isStacked);
      btnTotal.classList.toggle('bg-primary', !isStacked);
      btnTotal.classList.toggle('text-primary-content', !isStacked);
      btnTotal.classList.toggle('opacity-60', isStacked);
    }
  }

  function toggleEmi(enable) {
    var cb = $('expIsEmi');
    if (cb) cb.checked = !!enable;
    toggle('expEmiBox', !!enable, 'flex');
    toggle('expEmiFields', !!enable, 'flex');
    if (enable) {
      syncEmiPending();
    } else {
      var cat = $('expCategory');
      if (cat && cat.selectedOptions && cat.selectedOptions[0] && cat.selectedOptions[0].text.indexOf('EMI') !== -1) {
        cat.value = '';
      }
    }
  }

  function syncEmiPending() {
    var numEl = $('expEmiInstallmentNum');
    var totEl = $('expEmiTotalInstallments');
    var noteEl = $('expEmiPendingNote');
    if (!numEl || !totEl || !noteEl) return;
    var num = parseInt(numEl.value, 10);
    var tot = parseInt(totEl.value, 10);
    if (!isNaN(tot) && tot > 0) {
      if (!isNaN(num) && num > 0) {
        var pending = Math.max(0, tot - num);
        noteEl.textContent = pending === 0 ? '✓ Final installment' : (pending + ' installment' + (pending === 1 ? '' : 's') + ' pending');
        noteEl.className = 'text-[11px] font-semibold ' + (pending === 0 ? 'text-emerald-400' : 'text-purple-300');
      } else {
        noteEl.textContent = tot + ' total installments';
        noteEl.className = 'text-[11px] font-semibold text-purple-300';
      }
    } else {
      noteEl.textContent = '';
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var merchant = $('expMerchant');
    var category = $('expCategory');
    if (merchant) merchant.addEventListener('input', syncRemember);
    if (category) category.addEventListener('change', syncRemember);

    var isEmi = $('expIsEmi');
    if (isEmi) {
      isEmi.addEventListener('change', function () {
        toggleEmi(this.checked);
      });
    }

    if (typeof Chart !== 'undefined') {
      var pace = readJson('expense-chart');
      if (pace && $('paceChart')) paceChart($('paceChart'), pace);
      var trend = readJson('expense-trend-chart');
      if (trend && $('trendChart')) trendChart($('trendChart'), trend);
      var year = readJson('expense-year-chart');
      if (year && $('yearChart')) {
        yearChart($('yearChart'), year);
        if (typeof MutationObserver !== 'undefined') {
          new MutationObserver(function () {
            if (_yearChartCanvas && _yearChartData) yearChart(_yearChartCanvas, _yearChartData);
          }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
        }
      }
    }

    var params = new URLSearchParams(window.location.search);
    if (params.get('add') === '1') open();
  });

  return {
    open: open,
    remove: remove,
    toggleEmi: toggleEmi,
    syncEmiPending: syncEmiPending,
    setYearChartMode: setYearChartMode,
  };
})();
