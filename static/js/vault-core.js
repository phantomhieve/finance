var Vault = (function(){
  var el = document.getElementById('pageOverlay');
  function hide() { if (el) el.style.display = 'none'; }
  function show() { if (el) el.style.display = 'flex'; }
  function afterPaint(fn) { requestAnimationFrame(function(){ requestAnimationFrame(fn); }); }

  hide();

  var skip = /^(javascript|mailto|tel|#)/i;
  var cur = window.location.href;

  // Keep the reader's place when a form or action link comes back to the same page
  // (POST → redirect, filters, tabs). Only restored when we land on the path we left.
  var SCROLL_KEY = 'vault-scroll';
  var SCROLL_MAX_AGE = 60000;

  function rememberScroll() {
    try {
      sessionStorage.setItem(SCROLL_KEY, JSON.stringify({ path: location.pathname, y: window.scrollY, t: Date.now() }));
    } catch(x) {}
  }

  function restoreScroll() {
    var saved;
    try {
      saved = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || 'null');
      sessionStorage.removeItem(SCROLL_KEY);
    } catch(x) { return; }
    if (!saved || saved.path !== location.pathname || location.hash) return;
    if (Date.now() - saved.t > SCROLL_MAX_AGE || !saved.y) return;
    var started = Date.now();
    var cancelled = false;
    function cancel() { cancelled = true; }
    ['wheel', 'touchstart', 'keydown'].forEach(function(ev) { window.addEventListener(ev, cancel, { once: true, passive: true }); });
    // Charts and fonts can grow the page after load; keep trying until the target fits.
    (function attempt() {
      if (cancelled) return;
      var maxY = document.documentElement.scrollHeight - window.innerHeight;
      window.scrollTo({ top: Math.min(saved.y, maxY), behavior: 'instant' });
      if (maxY < saved.y && Date.now() - started < 1500) requestAnimationFrame(attempt);
    })();
  }

  var nativeSubmit = HTMLFormElement.prototype.submit;
  HTMLFormElement.prototype.submit = function() {
    if (this.method !== 'dialog') rememberScroll();
    return nativeSubmit.call(this);
  };

  document.addEventListener('click', function(e) {
    var a = e.target.closest('a[href]');
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    var h = a.getAttribute('href') || '';
    if (!h || skip.test(h) || a.getAttribute('target') === '_blank') return;
    if (a.closest('.dropdown-content')) return;
    var dest;
    try { dest = new URL(h, cur); if (dest.href === cur) return; } catch(x) {}
    e.preventDefault();
    // Action links (refresh, sync…) redirect back here; plain navigation lands elsewhere and is ignored.
    if (!dest || !dest.hash) rememberScroll();
    show();
    var href = a.href;
    afterPaint(function(){ window.location.href = href; });
  });

  document.addEventListener('submit', function(e) {
    if (e.target.method === 'dialog') return;
    e.preventDefault();
    var dialog = e.target.closest('dialog');
    if (dialog) dialog.close();
    show();
    var form = e.target;
    afterPaint(function(){ form.submit(); });
  });

  window.addEventListener('pageshow', function(e) {
    hide();
    if (!e.persisted) restoreScroll();
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
