document.addEventListener('DOMContentLoaded', function() {
  var _isMobile = window.innerWidth <= 640;

  var tooltipDefault = {
    backgroundColor: 'rgba(17, 23, 34, 0.94)',
    borderColor: 'rgba(226, 232, 240, 0.14)',
    borderWidth: 1,
    titleColor: '#f1f5f9',
    bodyColor: '#94a3b8',
    padding: 12,
    cornerRadius: 8,
    titleFont: { family: "'Inter', -apple-system, sans-serif", weight: '600', size: 13 },
    bodyFont: { family: "'Inter', -apple-system, sans-serif", size: 12 },
    callbacks: {
      label: function (c) {
        var val = c.raw != null ? c.raw : c.parsed.y;
        return ' ' + (c.dataset.label ? c.dataset.label.trim() + ': ' : '') + '\u20b9' + Math.round(val).toLocaleString('en-IN');
      }
    }
  };

  var legendDefault = {
    position: _isMobile ? 'bottom' : 'right',
    labels: {
      color: 'rgba(226, 232, 240, 0.75)',
      usePointStyle: true,
      pointStyle: 'circle',
      boxWidth: 7,
      boxHeight: 7,
      padding: 14,
      font: { family: "'Inter', -apple-system, sans-serif", size: 11, weight: '500' }
    }
  };

  var scaleOpts = {
    x: {
      grid: { display: false },
      ticks: {
        color: 'rgba(226, 232, 240, 0.5)',
        maxRotation: 0,
        autoSkipPadding: 6,
        font: { family: "'Inter', -apple-system, sans-serif", size: 11 }
      },
      border: { display: false }
    },
    y: {
      grid: { color: 'rgba(226, 232, 240, 0.06)' },
      ticks: {
        color: 'rgba(226, 232, 240, 0.5)',
        font: { family: "'Inter', -apple-system, sans-serif", size: 11 },
        callback: function (v) {
          if (Math.abs(v) >= 1e7) return '\u20b9' + (v / 1e7).toFixed(1) + 'Cr';
          if (Math.abs(v) >= 1e5) return '\u20b9' + (v / 1e5).toFixed(1) + 'L';
          if (Math.abs(v) >= 1e3) return '\u20b9' + Math.round(v / 1e3) + 'K';
          return '\u20b9' + v.toLocaleString('en-IN');
        }
      },
      border: { display: false }
    }
  };

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

  // 1. Master/Baby Portfolio Doughnut
  var pfDataEl = document.getElementById('pf-chart-data');
  if (pfDataEl) {
    try {
      var cd = JSON.parse(pfDataEl.textContent);
      var allocChart = document.getElementById('allocationChart');
      if (allocChart) {
        new Chart(allocChart, {
          type: 'doughnut',
          data: {
            labels: cd.labels,
            datasets: [{
              data: cd.values,
              backgroundColor: vaultColors.slice(0, cd.labels.length),
              borderWidth: 1,
              borderColor: 'rgba(17, 23, 34, 0.8)',
              hoverOffset: 6
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: { legend: legendDefault, tooltip: tooltipDefault }
          }
        });
      }
      var consChart = document.getElementById('consolidatedChart');
      if (consChart) {
        var consColors = ['#6366f1', '#14b8a6', '#10b981', '#eab308', '#f97316'];
        new Chart(consChart, {
          type: 'doughnut',
          data: {
            labels: cd.consolidated_labels,
            datasets: [{
              data: cd.consolidated_values,
              backgroundColor: consColors,
              borderWidth: 1,
              borderColor: 'rgba(17, 23, 34, 0.8)',
              hoverOffset: 6
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: { legend: legendDefault, tooltip: tooltipDefault }
          }
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
      if (eqChart) {
        new Chart(eqChart, {
          type: 'doughnut',
          data: {
            labels: _eqData.labels,
            datasets: [{
              data: _eqData.values,
              backgroundColor: ['#6366f1', '#8b5cf6', '#10b981', '#0ea5e9'],
              borderWidth: 1,
              borderColor: 'rgba(17, 23, 34, 0.8)',
              hoverOffset: 6
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: { legend: legendDefault, tooltip: tooltipDefault }
          }
        });
      }
    } catch (e) {
      console.warn('Equity chart init error:', e);
    }
  }

  // 3. Growth Charts
  var growthDataEl = document.getElementById('growth-data');
  if (growthDataEl) {
    try {
      var gcd = JSON.parse(growthDataEl.textContent);
      var topLegend = {
        labels: {
          color: 'rgba(226, 232, 240, 0.7)',
          usePointStyle: true,
          boxWidth: 6,
          padding: 16,
          font: { family: "'Inter', -apple-system, sans-serif", size: 11 }
        }
      };

      var gBar = document.getElementById('growthBar');
      if (gBar) {
        new Chart(gBar, {
          type: 'bar',
          data: {
            labels: gcd.months,
            datasets: [
              {
                label: '  Capital Added',
                data: gcd.money_added,
                backgroundColor: 'rgba(99, 102, 241, 0.55)',
                borderColor: '#6366f1',
                borderWidth: 1,
                borderRadius: 4,
                borderSkipped: false
              },
              {
                label: '  Market Returns',
                data: gcd.returns_gained,
                backgroundColor: gcd.returns_gained.map(function(v) {
                  return v >= 0 ? 'rgba(16, 185, 129, 0.55)' : 'rgba(244, 63, 94, 0.45)';
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
            animation: { duration: 600 },
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: topLegend, tooltip: tooltipDefault },
            scales: {
              ...scaleOpts,
              x: { ...scaleOpts.x, stacked: true },
              y: { ...scaleOpts.y, stacked: true }
            }
          }
        });
      }

      var gVal = document.getElementById('valueChart');
      if (gVal) {
        new Chart(gVal, {
          type: 'line',
          data: {
            labels: gcd.months,
            datasets: [{
              label: '  Portfolio Value',
              data: gcd.values,
              borderColor: '#6366f1',
              backgroundColor: 'rgba(99, 102, 241, 0.08)',
              borderWidth: 2,
              pointRadius: 3,
              pointBackgroundColor: '#6366f1',
              pointBorderColor: '#0b0f17',
              pointBorderWidth: 2,
              tension: 0.3,
              fill: true,
              spanGaps: true
            }]
          },
          options: {
            animation: { duration: 700 },
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: topLegend, tooltip: tooltipDefault },
            scales: scaleOpts
          }
        });
      }

      if (gcd.yearly_labels && gcd.yearly_labels.length) {
        var yBar = document.getElementById('yearlyBar');
        if (yBar) {
          new Chart(yBar, {
            type: 'bar',
            data: {
              labels: gcd.yearly_labels,
              datasets: [
                {
                  label: '  Capital Added',
                  data: gcd.yearly_added,
                  backgroundColor: 'rgba(99, 102, 241, 0.55)',
                  borderColor: '#6366f1',
                  borderWidth: 1,
                  borderRadius: 4,
                  borderSkipped: false
                },
                {
                  label: '  Market Returns',
                  data: gcd.yearly_returns,
                  backgroundColor: gcd.yearly_returns.map(function(v) {
                    return v >= 0 ? 'rgba(16, 185, 129, 0.55)' : 'rgba(244, 63, 94, 0.45)';
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
              animation: { duration: 600 },
              responsive: true,
              maintainAspectRatio: false,
              plugins: { legend: topLegend, tooltip: tooltipDefault },
              scales: {
                ...scaleOpts,
                x: { ...scaleOpts.x, stacked: true },
                y: { ...scaleOpts.y, stacked: true }
              }
            }
          });
        }
        var yVal = document.getElementById('yearlyValueChart');
        if (yVal) {
          new Chart(yVal, {
            type: 'line',
            data: {
              labels: gcd.yearly_labels,
              datasets: [{
                label: '  Portfolio Value',
                data: gcd.yearly_values,
                borderColor: '#6366f1',
                backgroundColor: 'rgba(99, 102, 241, 0.08)',
                borderWidth: 2,
                pointRadius: 4,
                pointBackgroundColor: '#6366f1',
                pointBorderColor: '#0b0f17',
                pointBorderWidth: 2,
                tension: 0.3,
                fill: true,
                spanGaps: true
              }]
            },
            options: {
              animation: { duration: 700 },
              responsive: true,
              maintainAspectRatio: false,
              plugins: { legend: topLegend, tooltip: tooltipDefault },
              scales: scaleOpts
            }
          });
        }
      }
    } catch (e) {
      console.warn('Growth chart init error:', e);
    }
  }

  // 4. Tracker Dashboard Chart
  var trkDataEl = document.getElementById('chart-data');
  if (trkDataEl) {
    try {
      var trkd = JSON.parse(trkDataEl.textContent);
      var bChart = document.getElementById('barChart');
      if (bChart) {
        new Chart(bChart, {
          data: {
            labels: trkd.months,
            datasets: [
              {
                type: 'bar',
                label: '  Saved',
                data: trkd.totals,
                backgroundColor: trkd.totals.map(function (v, i) {
                  return v >= trkd.goals[i] ? 'rgba(16, 185, 129, 0.55)' : v > 0 ? 'rgba(245, 158, 11, 0.50)' : 'rgba(244, 63, 94, 0.40)';
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
                borderColor: 'rgba(99, 102, 241, 0.65)',
                borderWidth: 2,
                borderDash: [5, 4],
                pointRadius: 0,
                fill: false,
                tension: 0.1
              }
            ]
          },
          options: {
            animation: { duration: 600 },
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                labels: {
                  color: 'rgba(226, 232, 240, 0.65)',
                  usePointStyle: true,
                  boxWidth: 6,
                  padding: 16,
                  font: { family: "'Inter', -apple-system, sans-serif", size: 11 }
                }
              },
              tooltip: tooltipDefault
            },
            scales: scaleOpts
          }
        });
      }
      var lChart = document.getElementById('lineChart');
      if (lChart) {
        new Chart(lChart, {
          type: 'line',
          data: {
            labels: trkd.months,
            datasets: [
              {
                label: '  Cumulative Saved',
                data: trkd.cumulative,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.08)',
                borderWidth: 2,
                pointRadius: 3,
                pointBackgroundColor: '#10b981',
                pointBorderColor: 'transparent',
                pointBorderWidth: 0,
                tension: 0.3,
                fill: true
              },
              {
                label: '  Cumulative Goal',
                data: trkd.cumulative_goals,
                borderColor: 'rgba(99, 102, 241, 0.45)',
                borderWidth: 2,
                borderDash: [5, 4],
                pointRadius: 0,
                fill: false,
                tension: 0.3
              }
            ]
          },
          options: {
            animation: { duration: 700 },
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                labels: {
                  color: 'rgba(226, 232, 240, 0.65)',
                  usePointStyle: true,
                  boxWidth: 6,
                  padding: 16,
                  font: { family: "'Inter', -apple-system, sans-serif", size: 11 }
                }
              },
              tooltip: tooltipDefault
            },
            scales: scaleOpts
          }
        });
      }
    } catch (e) {
      console.warn('Tracker chart init error:', e);
    }
  }
});
