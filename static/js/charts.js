document.addEventListener('DOMContentLoaded', function() {
  var _reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var _activeCharts = [];

  function isDarkTheme() {
    return document.documentElement.getAttribute('data-theme') !== 'winter';
  }

  function getThemeColors() {
    var dark = isDarkTheme();
    return {
      tooltipBg: dark ? 'rgba(17, 23, 34, 0.96)' : 'rgba(15, 23, 42, 0.95)',
      tooltipBorder: dark ? 'rgba(226, 232, 240, 0.16)' : 'rgba(15, 23, 42, 0.14)',
      tooltipTitle: '#f8fafc',
      tooltipBody: '#cbd5e1',
      legendColor: dark ? '#cbd5e1' : '#334155',
      tickColor: dark ? '#94a3b8' : '#475569',
      gridColor: dark ? 'rgba(226, 232, 240, 0.06)' : 'rgba(15, 23, 42, 0.07)',
      doughnutBorder: dark ? '#111722' : '#ffffff',
      pointBorder: dark ? '#0b0f17' : '#ffffff'
    };
  }

  function formatInrShort(v) {
    var abs = Math.abs(v);
    var sign = v < 0 ? '-' : '';
    if (abs >= 1e7) return sign + '\u20b9' + (abs / 1e7).toFixed(1) + 'Cr';
    if (abs >= 1e5) return sign + '\u20b9' + (abs / 1e5).toFixed(1) + 'L';
    if (abs >= 1e3) return sign + '\u20b9' + Math.round(abs / 1e3) + 'K';
    return sign + '\u20b9' + Math.round(abs).toLocaleString('en-IN');
  }

  function doughnutLegendPos(canvas) {
    var parentW = (canvas && canvas.parentElement && canvas.parentElement.clientWidth) || window.innerWidth;
    if (window.innerWidth < 768 || parentW < 400) return 'bottom';
    return 'right';
  }

  function makeTooltip(isDoughnut) {
    var tc = getThemeColors();
    return {
      backgroundColor: tc.tooltipBg,
      borderColor: tc.tooltipBorder,
      borderWidth: 1,
      titleColor: tc.tooltipTitle,
      bodyColor: tc.tooltipBody,
      padding: 11,
      cornerRadius: 8,
      boxPadding: 5,
      usePointStyle: true,
      titleFont: { family: "'Inter', -apple-system, sans-serif", weight: '600', size: 12 },
      bodyFont: { family: "'Inter', -apple-system, sans-serif", size: 12 },
      callbacks: {
        label: function (c) {
          var val = c.raw != null ? Number(c.raw) : (typeof c.parsed === 'number' ? c.parsed : c.parsed.y);
          if (isNaN(val)) return '';
          var formatted = '\u20b9' + Math.round(val).toLocaleString('en-IN');
          if (isDoughnut && c.dataset && Array.isArray(c.dataset.data)) {
            var total = c.dataset.data.reduce(function(acc, n) { return acc + (Number(n) || 0); }, 0);
            var pct = total > 0 ? ((val / total) * 100).toFixed(1) + '%' : '';
            var lbl = c.label ? c.label + ': ' : '';
            return ' ' + lbl + formatted + (pct ? ' (' + pct + ')' : '');
          }
          return ' ' + (c.dataset.label ? c.dataset.label.trim() + ': ' : '') + formatted;
        }
      }
    };
  }

  function makeDoughnutLegend(canvas) {
    var tc = getThemeColors();
    var pos = doughnutLegendPos(canvas);
    return {
      position: pos,
      labels: {
        color: tc.legendColor,
        usePointStyle: true,
        pointStyle: 'circle',
        boxWidth: 7,
        boxHeight: 7,
        padding: pos === 'bottom' ? 10 : 12,
        font: { family: "'Inter', -apple-system, sans-serif", size: 11, weight: '500' }
      }
    };
  }

  function makeTopLegend() {
    var tc = getThemeColors();
    return {
      labels: {
        color: tc.legendColor,
        usePointStyle: true,
        pointStyle: 'circle',
        boxWidth: 6,
        boxHeight: 6,
        padding: 14,
        font: { family: "'Inter', -apple-system, sans-serif", size: 11, weight: '500' }
      }
    };
  }

  function makeScaleOpts(stacked) {
    var tc = getThemeColors();
    var isNarrow = window.innerWidth < 640;
    return {
      x: {
        stacked: !!stacked,
        grid: { display: false },
        ticks: {
          color: tc.tickColor,
          maxRotation: isNarrow ? 35 : 0,
          autoSkip: true,
          autoSkipPadding: 8,
          font: { family: "'Inter', -apple-system, sans-serif", size: isNarrow ? 10 : 11 }
        },
        border: { display: false }
      },
      y: {
        stacked: !!stacked,
        grid: { color: tc.gridColor },
        ticks: {
          color: tc.tickColor,
          maxTicksLimit: isNarrow ? 5 : 6,
          font: { family: "'Inter', -apple-system, sans-serif", size: isNarrow ? 10 : 11 },
          callback: formatInrShort
        },
        border: { display: false }
      }
    };
  }

  // Cohesive Fiduciary Palette
  var vaultColors = [
    '#6366f1', // Sovereign Indigo
    '#14b8a6', // Debt Teal
    '#eab308', // Bullion Gold
    '#8b5cf6', // Fiduciary Violet
    '#10b981', // Fiduciary Emerald
    '#f97316', // Realty Amber
    '#0ea5e9', // Clearing Sky
    '#94a3b8', // Bullion Silver
    '#f43f5e', // Ledger Rose
    '#06b6d4', // Cyan
    '#a855f7'  // Purple
  ];

  function registerChart(instance, kind) {
    if (instance) _activeCharts.push({ chart: instance, kind: kind });
    return instance;
  }

  function initDoughnut(canvas, labels, values, colors) {
    if (!canvas) return null;
    var tc = getThemeColors();
    return registerChart(new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: colors,
          borderWidth: 1.5,
          borderColor: tc.doughnutBorder,
          hoverOffset: 5
        }]
      },
      options: {
        animation: _reducedMotion ? false : { duration: 550 },
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        layout: { padding: { top: 6, right: 8, bottom: 6, left: 6 } },
        plugins: {
          legend: makeDoughnutLegend(canvas),
          tooltip: makeTooltip(true)
        }
      }
    }), 'doughnut');
  }

  // 1. Master/Baby Portfolio Doughnut
  var pfDataEl = document.getElementById('pf-chart-data');
  if (pfDataEl) {
    try {
      var cd = JSON.parse(pfDataEl.textContent);
      var allocChart = document.getElementById('allocationChart');
      if (allocChart && cd.labels) {
        initDoughnut(allocChart, cd.labels, cd.values, vaultColors.slice(0, cd.labels.length));
      }
      var consChart = document.getElementById('consolidatedChart');
      if (consChart && cd.consolidated_labels) {
        var consColors = ['#6366f1', '#14b8a6', '#10b981', '#eab308', '#f97316'];
        initDoughnut(consChart, cd.consolidated_labels, cd.consolidated_values, consColors);
      }
      var ring = document.querySelector('.ai-score-ring-fg');
      if (ring) {
        var score = parseInt(ring.getAttribute('data-score') || '0', 10);
        var circ = 175.93;
        setTimeout(function() { ring.style.strokeDashoffset = circ * (1 - score / 100); }, _reducedMotion ? 0 : 100);
      }
      var breakdownCollapse = document.getElementById('breakdownCollapseToggle');
      if (breakdownCollapse) {
        breakdownCollapse.addEventListener('change', function() {
          if (this.checked) {
            setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 250);
          }
        });
      }
    } catch (e) {
      console.warn('Portfolio chart init error:', e);
    }
  }

  // 2. Zerodha Consolidated Chart
  var equityDataEl = document.getElementById('equity-chart-data');
  if (equityDataEl) {
    try {
      var _eqData = JSON.parse(equityDataEl.textContent);
      var eqChart = document.getElementById('equityAllocationChart');
      if (eqChart && _eqData.labels) {
        initDoughnut(eqChart, _eqData.labels, _eqData.values, ['#6366f1', '#8b5cf6', '#10b981', '#0ea5e9']);
      }
    } catch (e) {
      console.warn('Equity chart init error:', e);
    }
  }

  // 3. Growth Charts
  var growthDataEl = document.getElementById('growth-data');
  if (growthDataEl && typeof Chart !== 'undefined') {
    try {
      var gcd = JSON.parse(growthDataEl.textContent);
      var tc0 = getThemeColors();

      var gBar = document.getElementById('growthBar');
      if (gBar) {
        registerChart(new Chart(gBar, {
          type: 'bar',
          data: {
            labels: gcd.months,
            datasets: [
              {
                label: '  Capital Added',
                data: gcd.money_added,
                backgroundColor: 'rgba(99, 102, 241, 0.58)',
                borderColor: '#6366f1',
                borderWidth: 1,
                borderRadius: 4,
                borderSkipped: false
              },
              {
                label: '  Market Returns',
                data: gcd.returns_gained,
                backgroundColor: gcd.returns_gained.map(function(v) {
                  return v >= 0 ? 'rgba(16, 185, 129, 0.58)' : 'rgba(244, 63, 94, 0.48)';
                }),
                borderColor: gcd.returns_gained.map(function(v) {
                  return v >= 0 ? '#10b981' : '#f43f5e';
                }),
                borderWidth: 1,
                borderRadius: 4,
                borderSkipped: false
              }
            ]
          },
          options: {
            animation: _reducedMotion ? false : { duration: 550 },
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            layout: { padding: { top: 6, right: 6, bottom: 2, left: 2 } },
            plugins: { legend: makeTopLegend(), tooltip: makeTooltip(false) },
            scales: makeScaleOpts(true)
          }
        }), 'stacked-xy');
      }

      var gVal = document.getElementById('valueChart');
      if (gVal) {
        registerChart(new Chart(gVal, {
          type: 'line',
          data: {
            labels: gcd.months,
            datasets: [{
              label: '  Portfolio Value',
              data: gcd.values,
              borderColor: '#6366f1',
              backgroundColor: 'rgba(99, 102, 241, 0.10)',
              borderWidth: 2,
              pointRadius: 3,
              pointHoverRadius: 5,
              pointBackgroundColor: '#6366f1',
              pointBorderColor: tc0.pointBorder,
              pointBorderWidth: 2,
              tension: 0.3,
              fill: true,
              spanGaps: true
            }]
          },
          options: {
            animation: _reducedMotion ? false : { duration: 600 },
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            layout: { padding: { top: 8, right: 8, bottom: 2, left: 2 } },
            plugins: { legend: makeTopLegend(), tooltip: makeTooltip(false) },
            scales: makeScaleOpts(false)
          }
        }), 'line-xy');
      }

      if (gcd.yearly_labels && gcd.yearly_labels.length) {
        var yBar = document.getElementById('yearlyBar');
        if (yBar) {
          registerChart(new Chart(yBar, {
            type: 'bar',
            data: {
              labels: gcd.yearly_labels,
              datasets: [
                {
                  label: '  Capital Added',
                  data: gcd.yearly_added,
                  backgroundColor: 'rgba(99, 102, 241, 0.58)',
                  borderColor: '#6366f1',
                  borderWidth: 1,
                  borderRadius: 4,
                  borderSkipped: false
                },
                {
                  label: '  Market Returns',
                  data: gcd.yearly_returns,
                  backgroundColor: gcd.yearly_returns.map(function(v) {
                    return v >= 0 ? 'rgba(16, 185, 129, 0.58)' : 'rgba(244, 63, 94, 0.48)';
                  }),
                  borderColor: gcd.yearly_returns.map(function(v) {
                    return v >= 0 ? '#10b981' : '#f43f5e';
                  }),
                  borderWidth: 1,
                  borderRadius: 4,
                  borderSkipped: false
                }
              ]
            },
            options: {
              animation: _reducedMotion ? false : { duration: 550 },
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: 'index', intersect: false },
              layout: { padding: { top: 6, right: 6, bottom: 2, left: 2 } },
              plugins: { legend: makeTopLegend(), tooltip: makeTooltip(false) },
              scales: makeScaleOpts(true)
            }
          }), 'stacked-xy');
        }
        var yVal = document.getElementById('yearlyValueChart');
        if (yVal) {
          registerChart(new Chart(yVal, {
            type: 'line',
            data: {
              labels: gcd.yearly_labels,
              datasets: [{
                label: '  Portfolio Value',
                data: gcd.yearly_values,
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.10)',
                borderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                pointBackgroundColor: '#6366f1',
                pointBorderColor: tc0.pointBorder,
                pointBorderWidth: 2,
                tension: 0.3,
                fill: true,
                spanGaps: true
              }]
            },
            options: {
              animation: _reducedMotion ? false : { duration: 600 },
              responsive: true,
              maintainAspectRatio: false,
              interaction: { mode: 'index', intersect: false },
              layout: { padding: { top: 8, right: 8, bottom: 2, left: 2 } },
              plugins: { legend: makeTopLegend(), tooltip: makeTooltip(false) },
              scales: makeScaleOpts(false)
            }
          }), 'line-xy');
        }
      }
    } catch (e) {
      console.warn('Growth chart init error:', e);
    }
  }

  // 4. Tracker Dashboard Chart
  var trkDataEl = document.getElementById('chart-data');
  if (trkDataEl && typeof Chart !== 'undefined') {
    try {
      var trkd = JSON.parse(trkDataEl.textContent);
      var bChart = document.getElementById('barChart');
      if (bChart) {
        registerChart(new Chart(bChart, {
          data: {
            labels: trkd.months,
            datasets: [
              {
                type: 'bar',
                label: '  Saved',
                data: trkd.totals,
                backgroundColor: trkd.totals.map(function (v, i) {
                  return v >= trkd.goals[i] ? 'rgba(16, 185, 129, 0.58)' : v > 0 ? 'rgba(245, 158, 11, 0.52)' : 'rgba(244, 63, 94, 0.42)';
                }),
                borderColor: trkd.totals.map(function (v, i) {
                  return v >= trkd.goals[i] ? '#10b981' : v > 0 ? '#f59e0b' : '#f43f5e';
                }),
                borderWidth: 1,
                borderRadius: 5,
                borderSkipped: false
              },
              {
                type: 'line',
                label: '  Goal Target',
                data: trkd.goals,
                borderColor: 'rgba(99, 102, 241, 0.72)',
                borderWidth: 2,
                borderDash: [5, 4],
                pointRadius: 0,
                pointHoverRadius: 4,
                fill: false,
                tension: 0.1
              }
            ]
          },
          options: {
            animation: _reducedMotion ? false : { duration: 550 },
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            layout: { padding: { top: 6, right: 6, bottom: 2, left: 2 } },
            plugins: {
              legend: makeTopLegend(),
              tooltip: makeTooltip(false)
            },
            scales: makeScaleOpts(false)
          }
        }), 'bar-xy');
      }
      var lChart = document.getElementById('lineChart');
      if (lChart) {
        registerChart(new Chart(lChart, {
          type: 'line',
          data: {
            labels: trkd.months,
            datasets: [
              {
                label: '  Cumulative Saved',
                data: trkd.cumulative,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.10)',
                borderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5,
                pointBackgroundColor: '#10b981',
                pointBorderColor: 'transparent',
                pointBorderWidth: 0,
                tension: 0.3,
                fill: true
              },
              {
                label: '  Cumulative Goal',
                data: trkd.cumulative_goals,
                borderColor: 'rgba(99, 102, 241, 0.55)',
                borderWidth: 2,
                borderDash: [5, 4],
                pointRadius: 0,
                pointHoverRadius: 4,
                fill: false,
                tension: 0.3
              }
            ]
          },
          options: {
            animation: _reducedMotion ? false : { duration: 600 },
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            layout: { padding: { top: 8, right: 8, bottom: 2, left: 2 } },
            plugins: {
              legend: makeTopLegend(),
              tooltip: makeTooltip(false)
            },
            scales: makeScaleOpts(false)
          }
        }), 'line-xy');
      }
    } catch (e) {
      console.warn('Tracker chart init error:', e);
    }
  }

  // Live theme + viewport adaptation across all initialized charts
  function refreshChartStyles() {
    if (!_activeCharts.length) return;
    var tc = getThemeColors();
    _activeCharts.forEach(function(entry) {
      var ch = entry.chart;
      if (!ch || !ch.options) return;
      if (ch.options.plugins && ch.options.plugins.legend && ch.options.plugins.legend.labels) {
        ch.options.plugins.legend.labels.color = tc.legendColor;
        if (entry.kind === 'doughnut') {
          var nextPos = doughnutLegendPos(ch.canvas);
          ch.options.plugins.legend.position = nextPos;
          ch.options.plugins.legend.labels.padding = nextPos === 'bottom' ? 10 : 12;
        }
      }
      if (ch.options.plugins && ch.options.plugins.tooltip) {
        ch.options.plugins.tooltip.backgroundColor = tc.tooltipBg;
        ch.options.plugins.tooltip.borderColor = tc.tooltipBorder;
      }
      if (entry.kind === 'doughnut' && ch.data && ch.data.datasets && ch.data.datasets[0]) {
        ch.data.datasets[0].borderColor = tc.doughnutBorder;
      }
      if (entry.kind === 'line-xy' && ch.data && ch.data.datasets && ch.data.datasets[0] && ch.data.datasets[0].pointBorderWidth > 0) {
        ch.data.datasets[0].pointBorderColor = tc.pointBorder;
      }
      if (ch.options.scales) {
        if (ch.options.scales.x && ch.options.scales.x.ticks) {
          ch.options.scales.x.ticks.color = tc.tickColor;
          ch.options.scales.x.ticks.maxRotation = window.innerWidth < 640 ? 35 : 0;
        }
        if (ch.options.scales.y) {
          if (ch.options.scales.y.ticks) ch.options.scales.y.ticks.color = tc.tickColor;
          if (ch.options.scales.y.grid) ch.options.scales.y.grid.color = tc.gridColor;
        }
      }
      ch.update('none');
    });
  }

  window.addEventListener('vault:themechange', refreshChartStyles);
  var _resizeTimer;
  window.addEventListener('resize', function() {
    clearTimeout(_resizeTimer);
    _resizeTimer = setTimeout(refreshChartStyles, 160);
  });
});
