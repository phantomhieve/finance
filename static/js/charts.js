document.addEventListener('DOMContentLoaded', function() {
  var _isMobile = window.innerWidth <= 640;

  var tooltipDefault = {
    backgroundColor: 'oklch(0.2 0 0 / 0.95)',
    borderColor: 'rgba(128,128,128,0.15)',
    borderWidth: 1,
    titleColor: '#ddd',
    bodyColor: '#aaa',
    padding: 12,
    cornerRadius: 8,
    callbacks: { label: function (c) { return ' \u20b9' + Math.round(c.raw).toLocaleString('en-IN'); } }
  };

  var legendDefault = {
    position: _isMobile ? 'bottom' : 'right',
    labels: { color: 'rgba(128,128,128,0.7)', usePointStyle: true, pointStyle: 'circle', boxWidth: 8, boxHeight: 8, padding: 10, font: { size: 12 } }
  };

  var scaleOpts = {
    x: { grid: { display: false }, ticks: { color: 'rgba(128,128,128,0.45)' }, border: { display: false } },
    y: { grid: { color: 'rgba(255,255,255,0.03)' }, ticks: { color: 'rgba(128,128,128,0.45)', callback: function (v) { return v >= 1e7 ? '\u20b9' + (v / 1e7).toFixed(1) + 'Cr' : v >= 1e5 ? '\u20b9' + (v / 1e5).toFixed(1) + 'L' : v >= 1e3 ? '\u20b9' + Math.round(v / 1e3) + 'K' : '\u20b9' + v.toLocaleString('en-IN'); } }, border: { display: false } }
  };

  // 1. Master/Baby Portfolio Doughnut
  var pfDataEl = document.getElementById('pf-chart-data');
  if (pfDataEl) {
    var cd = JSON.parse(pfDataEl.textContent);
    var colors = ['#648cfa','#a78bfa','#34d399','#fbbf24','#f87171','#fb923c','#94a3b8','#60a5fa','#f97316','#2dd4bf','#c084fc'];
    var allocChart = document.getElementById('allocationChart');
    if (allocChart) {
      new Chart(allocChart, {
        type: 'doughnut',
        data: { labels: cd.labels, datasets: [{ data: cd.values, backgroundColor: colors, borderWidth: 0, hoverOffset: 6 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: { legend: legendDefault, tooltip: tooltipDefault } }
      });
    }
    var consChart = document.getElementById('consolidatedChart');
    if (consChart) {
      var consColors = ['#648cfa','#a78bfa','#34d399','#fbbf24','#f97316'];
      new Chart(consChart, {
        type: 'doughnut',
        data: { labels: cd.consolidated_labels, datasets: [{ data: cd.consolidated_values, backgroundColor: consColors, borderWidth: 0, hoverOffset: 6 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: { legend: legendDefault, tooltip: tooltipDefault } }
      });
    }
    var ring = document.querySelector('.ai-score-ring-fg');
    if (ring) {
      var score = parseInt(ring.getAttribute('data-score') || '0', 10);
      var circ = 175.93;
      setTimeout(function() { ring.style.strokeDashoffset = circ * (1 - score / 100); }, 100);
    }
    // Resize trigger for breakdown collapse
    var breakdownCollapse = document.getElementById('breakdownCollapseToggle');
    if (breakdownCollapse) {
      breakdownCollapse.addEventListener('change', function() {
        if (this.checked) {
          setTimeout(function() { window.dispatchEvent(new Event('resize')); }, 250);
        }
      });
    }
  }

  // 2. Zerodha Consolidated Chart
  var equityDataEl = document.getElementById('equity-chart-data');
  if (equityDataEl) {
    var _eqData = JSON.parse(equityDataEl.textContent);
    var eqChart = document.getElementById('equityAllocationChart');
    if (eqChart) {
      new Chart(eqChart, {
        type: 'doughnut',
        data: { labels: _eqData.labels, datasets: [{ data: _eqData.values, backgroundColor: ['#7c9ef8','#b39ddb','#69f0ae'], borderWidth: 0, hoverOffset: 6 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: { legend: legendDefault, tooltip: tooltipDefault } }
      });
    }
  }

  // 3. Growth Charts
  var growthDataEl = document.getElementById('growth-data');
  if (growthDataEl) {
    var gcd = JSON.parse(growthDataEl.textContent);
    var topLegend = { labels: { color: '#8888aa', usePointStyle: true, boxWidth: 6, padding: 16 } };
    
    var gBar = document.getElementById('growthBar');
    if (gBar) {
      new Chart(gBar, {
        type: 'bar',
        data: { labels: gcd.months, datasets: [
          { label: '  Money Added', data: gcd.money_added, backgroundColor: 'rgba(124,158,248,0.5)', borderColor: '#7c9ef8', borderWidth: 1.5, borderRadius: 6, borderSkipped: false },
          { label: '  Returns', data: gcd.returns_gained, backgroundColor: gcd.returns_gained.map(function(v){return v>=0?'rgba(105,240,174,0.5)':'rgba(255,92,138,0.4)';}), borderColor: gcd.returns_gained.map(function(v){return v>=0?'#69f0ae':'#ff5c8a';}), borderWidth: 1.5, borderRadius: 6, borderSkipped: false }
        ]},
        options: { animation: { duration: 900 }, responsive: true, maintainAspectRatio: false, plugins: { legend: topLegend, tooltip: tooltipDefault }, scales: { ...scaleOpts, x: { ...scaleOpts.x, stacked: true }, y: { ...scaleOpts.y, stacked: true } } }
      });
    }
    
    var gVal = document.getElementById('valueChart');
    if (gVal) {
      new Chart(gVal, {
        type: 'line',
        data: { labels: gcd.months, datasets: [{ label: '  Portfolio Value', data: gcd.values, borderColor: '#7c9ef8', backgroundColor: 'rgba(124,158,248,0.07)', borderWidth: 2, pointRadius: 3, pointBackgroundColor: '#7c9ef8', pointBorderColor: '#0a0a14', pointBorderWidth: 2, tension: 0.35, fill: true }] },
        options: { animation: { duration: 1100 }, responsive: true, maintainAspectRatio: false, plugins: { legend: topLegend, tooltip: tooltipDefault }, scales: scaleOpts }
      });
    }

    if (gcd.yearly_labels && gcd.yearly_labels.length) {
      var yBar = document.getElementById('yearlyBar');
      if (yBar) {
        new Chart(yBar, {
          type: 'bar',
          data: { labels: gcd.yearly_labels, datasets: [
            { label: '  Money Added', data: gcd.yearly_added, backgroundColor: 'rgba(124,158,248,0.5)', borderColor: '#7c9ef8', borderWidth: 1.5, borderRadius: 6, borderSkipped: false },
            { label: '  Returns', data: gcd.yearly_returns, backgroundColor: gcd.yearly_returns.map(function(v){return v>=0?'rgba(105,240,174,0.5)':'rgba(255,92,138,0.4)';}), borderColor: gcd.yearly_returns.map(function(v){return v>=0?'#69f0ae':'#ff5c8a';}), borderWidth: 1.5, borderRadius: 6, borderSkipped: false }
          ]},
          options: { animation: { duration: 900 }, responsive: true, maintainAspectRatio: false, plugins: { legend: topLegend, tooltip: tooltipDefault }, scales: { ...scaleOpts, x: { ...scaleOpts.x, stacked: true }, y: { ...scaleOpts.y, stacked: true } } }
        });
      }
      var yVal = document.getElementById('yearlyValueChart');
      if (yVal) {
        new Chart(yVal, {
          type: 'line',
          data: { labels: gcd.yearly_labels, datasets: [{ label: '  Portfolio Value', data: gcd.yearly_values, borderColor: '#7c9ef8', backgroundColor: 'rgba(124,158,248,0.07)', borderWidth: 2, pointRadius: 4, pointBackgroundColor: '#7c9ef8', pointBorderColor: '#0a0a14', pointBorderWidth: 2, tension: 0.35, fill: true }] },
          options: { animation: { duration: 1100 }, responsive: true, maintainAspectRatio: false, plugins: { legend: topLegend, tooltip: tooltipDefault }, scales: scaleOpts }
        });
      }
    }
  }

  // 4. Tracker Dashboard Chart
  var trkDataEl = document.getElementById('chart-data');
  if (trkDataEl) {
    var trkd = JSON.parse(trkDataEl.textContent);
    var bChart = document.getElementById('barChart');
    if (bChart) {
      new Chart(bChart, {
        data: {
          labels: trkd.months,
          datasets: [
            { type: 'bar', label: '  Saved', data: trkd.totals, backgroundColor: trkd.totals.map(function (v, i) { return v >= trkd.goals[i] ? 'rgba(0,200,120,0.45)' : v > 0 ? 'rgba(250,200,50,0.4)' : 'rgba(240,80,80,0.25)'; }), borderColor: trkd.totals.map(function (v, i) { return v >= trkd.goals[i] ? '#00c878' : v > 0 ? '#fab032' : '#f05050'; }), borderWidth: 1.5, borderRadius: 8, borderSkipped: false },
            { type: 'line', label: '  Goal', data: trkd.goals, borderColor: 'rgba(100,140,250,0.5)', borderWidth: 2, borderDash: [5, 4], pointRadius: 0, fill: false, tension: 0.1 }
          ]
        },
        options: { animation: { duration: 900 }, responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: 'rgba(128,128,128,0.45)', usePointStyle: true, boxWidth: 6, padding: 16 } }, tooltip: tooltipDefault }, scales: scaleOpts }
      });
    }
    var lChart = document.getElementById('lineChart');
    if (lChart) {
      new Chart(lChart, {
        type: 'line',
        data: {
          labels: trkd.months,
          datasets: [
            { label: '  Saved', data: trkd.cumulative, borderColor: '#648cfa', backgroundColor: 'rgba(100,140,250,0.06)', borderWidth: 2, pointRadius: 3, pointBackgroundColor: '#648cfa', pointBorderColor: 'transparent', pointBorderWidth: 0, tension: 0.35, fill: true },
            { label: '  Goal', data: trkd.cumulative_goals, borderColor: 'rgba(100,140,250,0.3)', borderWidth: 2, borderDash: [5, 4], pointRadius: 0, fill: false, tension: 0.35 }
          ]
        },
        options: { animation: { duration: 1100 }, responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { color: 'rgba(128,128,128,0.45)', usePointStyle: true, boxWidth: 6, padding: 16 } }, tooltip: tooltipDefault }, scales: scaleOpts }
      });
    }
  }
});
