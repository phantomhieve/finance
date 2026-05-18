var Vault = (function(){
  var el = document.getElementById('pageOverlay');
  function hide() { if (el) el.style.display = 'none'; }
  function show() { if (el) el.style.display = 'flex'; }
  function afterPaint(fn) { requestAnimationFrame(function(){ requestAnimationFrame(fn); }); }

  hide();

  var skip = /^(javascript|mailto|tel|#)/i;
  var cur = window.location.href;

  document.addEventListener('click', function(e) {
    var a = e.target.closest('a[href]');
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    var h = a.getAttribute('href') || '';
    if (!h || skip.test(h) || a.getAttribute('target') === '_blank') return;
    if (a.closest('.dropdown-content')) return;
    try { if (new URL(h, cur).href === cur) return; } catch(x) {}
    e.preventDefault();
    show();
    var href = a.href;
    afterPaint(function(){ window.location.href = href; });
  });

  document.addEventListener('submit', function(e) {
    if (e.target.method === 'dialog') return;
    e.preventDefault();
    var dialog = e.target.closest('dialog');
    if (dialog) dialog.close();
    try { sessionStorage.setItem('vault-scroll', window.scrollY); } catch(x) {}
    show();
    var form = e.target;
    afterPaint(function(){ form.submit(); });
  });

  window.addEventListener('pageshow', function() {
    hide();
    try {
      var sy = sessionStorage.getItem('vault-scroll');
      if (sy !== null) {
        sessionStorage.removeItem('vault-scroll');
        requestAnimationFrame(function() { window.scrollTo(0, parseInt(sy, 10)); });
      }
    } catch(x) {}
  });

  var sw = document.getElementById('fySwitcher');
  if (sw) {
    var tabs = Array.prototype.slice.call(sw.querySelectorAll('.fy-tab'));
    var activeIdx = -1;
    tabs.forEach(function(b, i){ if (b.classList.contains('fy-tab-active')) activeIdx = i; });
    if (activeIdx === -1) activeIdx = tabs.length - 1;

    function markVisible() {
      tabs.forEach(function(b, i){
        b.classList.toggle('fy-visible', Math.abs(i - activeIdx) <= 1);
      });
    }
    markVisible();
    var resizeTimer;
    window.addEventListener('resize', function(){ clearTimeout(resizeTimer); resizeTimer = setTimeout(markVisible, 150); });

    sw.addEventListener('click', function(e) {
      var tab = e.target.closest('.fy-tab');
      if (!tab || tab.classList.contains('fy-tab-active')) return;
      e.preventDefault();
      tabs.forEach(function(b){ b.classList.remove('fy-tab-active'); });
      tab.classList.add('fy-tab-active');
      show();
      var href = tab.href;
      afterPaint(function(){ window.location.href = href; });
    });
  }

  var _pfExpMeta = document.querySelector('meta[name="portfolio-expires"]');
  if (_pfExpMeta) {
    var _pfExpAt = parseInt(_pfExpMeta.content, 10) * 1000;
    document.addEventListener('visibilitychange', function() {
      if (document.visibilityState === 'visible' && Date.now() > _pfExpAt) {
        window.location.href = '/portfolio/unlock/?next=' + encodeURIComponent(window.location.pathname + window.location.search);
      }
    });
  }

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(function(){});
  }

  return { showLoader: show, hideLoader: hide, afterPaint: afterPaint };
})();
