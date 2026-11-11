function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
  });
}

function openModal(id) {
  var el = document.getElementById(id);
  if (!el || el.tagName !== 'DIALOG') return;
  if (id !== 'mobileNavDrawer') {
    var navDrawer = document.getElementById('mobileNavDrawer');
    if (navDrawer && navDrawer.open) navDrawer.close();
  }
  if (!el.open) el.showModal();
}

function closeModal(id) {
  var el = document.getElementById(id);
  if (el && el.tagName === 'DIALOG' && el.open) el.close();
}

var _pendingDeleteFormId = null;
function confirmDelete(formId, msg) {
  _pendingDeleteFormId = formId;
  var el = document.getElementById('confirmDeleteMsg');
  if (el) {
    el.textContent = msg || 'Are you sure you want to delete this entry? This action cannot be undone.';
  }
  var modal = document.getElementById('confirmDeleteModal');
  if (modal && !modal.open) modal.showModal();
}

function confirmDeleteProceed() {
  document.querySelectorAll('dialog[open]').forEach(function(d) { d.close(); });
  if (!_pendingDeleteFormId) return;
  if (typeof Vault !== 'undefined' && Vault.showLoader) Vault.showLoader();
  var form = document.getElementById(_pendingDeleteFormId);
  if (!form) return;
  if (typeof Vault !== 'undefined' && Vault.afterPaint) {
    Vault.afterPaint(function() { form.submit(); });
  } else {
    form.submit();
  }
}

function toggleVaultTheme() {
  var current = document.documentElement.getAttribute('data-theme') || 'night';
  var theme = current === 'night' ? 'winter' : 'night';
  document.documentElement.setAttribute('data-theme', theme);
  try { localStorage.setItem('vault-theme', theme); } catch (e) {}

  var tc = theme === 'night' ? '#0b0f17' : '#f8fafc';
  var m = document.getElementById('metaThemeColor');
  if (m) m.setAttribute('content', tc);
  var bg = document.getElementById('bodyBgHint');
  if (bg) bg.textContent = 'body{background-color:' + tc + '}';

  var isLight = theme === 'winter';
  document.querySelectorAll('[data-theme-toggle]').forEach(function(b) {
    b.setAttribute('aria-pressed', isLight ? 'true' : 'false');
  });
  var labelEl = document.getElementById('mobileThemeLabel');
  if (labelEl) labelEl.textContent = isLight ? 'Daylight Folio (Winter)' : 'Obsidian Folio (Night)';

  var btn = document.getElementById('themeToggleBtn');
  if (btn) {
    btn.classList.add('theme-toggle-spin');
    setTimeout(function() { btn.classList.remove('theme-toggle-spin'); }, 420);
  }

  try {
    window.dispatchEvent(new CustomEvent('vault:themechange', { detail: { theme: theme } }));
  } catch (e) {}
}

function toggleSidebar() {
  var sb = document.getElementById('desktopSidebar');
  var mc = document.getElementById('mainContent');
  if (!sb) return;
  var collapsed = sb.classList.toggle('sidebar-collapsed');
  if (mc) mc.classList.toggle('main-content-collapsed', collapsed);
  sb.querySelectorAll('.sidebar-toggle-btn').forEach(function(btn) {
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  });
  try { localStorage.setItem('vault-sidebar', collapsed ? 'collapsed' : 'expanded'); } catch (e) {}
}

(function() {
  try {
    if (localStorage.getItem('vault-sidebar') === 'collapsed') {
      var sb = document.getElementById('desktopSidebar');
      var mc = document.getElementById('mainContent');
      if (sb) {
        sb.classList.add('sidebar-collapsed');
        sb.querySelectorAll('.sidebar-toggle-btn').forEach(function(btn) {
          btn.setAttribute('aria-expanded', 'false');
        });
      }
      if (mc) mc.classList.add('main-content-collapsed');
    }
    var curTheme = document.documentElement.getAttribute('data-theme') || 'night';
    var labelEl = document.getElementById('mobileThemeLabel');
    if (labelEl) labelEl.textContent = curTheme === 'winter' ? 'Daylight Folio (Winter)' : 'Obsidian Folio (Night)';
  } catch (e) {}
})();

function showVaultToast(message, level) {
  if (!message) return;
  var lvl = level || 'info';
  var region = document.getElementById('vaultToastRegion');
  if (!region) {
    region = document.createElement('div');
    region.id = 'vaultToastRegion';
    region.className = 'v-toast-stack px-4 lg:px-8 pt-3 flex flex-col gap-2 max-w-[1440px] mx-auto w-full';
    region.setAttribute('role', 'region');
    region.setAttribute('aria-label', 'Notifications');
    region.setAttribute('aria-live', 'polite');
    var mainEl = document.getElementById('mainStage') || document.querySelector('main');
    if (mainEl && mainEl.parentNode) {
      mainEl.parentNode.insertBefore(region, mainEl);
    } else {
      document.body.appendChild(region);
    }
  }

  var iconMap = {
    error: 'error',
    warning: 'warning',
    info: 'info',
    success: 'check_circle'
  };
  var clsMap = {
    error: 'v-toast-error',
    warning: 'v-toast-warning',
    info: 'v-toast-info',
    success: 'v-toast-success'
  };

  var toast = document.createElement('div');
  toast.className = 'v-toast ' + (clsMap[lvl] || clsMap.info);
  toast.setAttribute('role', lvl === 'error' ? 'alert' : 'status');

  var icon = document.createElement('span');
  icon.className = 'material-symbols-outlined text-base flex-shrink-0';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = iconMap[lvl] || 'info';

  var text = document.createElement('span');
  text.className = 'flex-1 font-medium';
  text.textContent = message;

  var closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'v-toast-close';
  closeBtn.setAttribute('aria-label', 'Dismiss notification');
  var closeIcon = document.createElement('span');
  closeIcon.className = 'material-symbols-outlined text-base';
  closeIcon.setAttribute('aria-hidden', 'true');
  closeIcon.textContent = 'close';
  closeBtn.appendChild(closeIcon);
  closeBtn.addEventListener('click', function() {
    toast.remove();
  });

  toast.appendChild(icon);
  toast.appendChild(text);
  toast.appendChild(closeBtn);
  region.appendChild(toast);

  setTimeout(function() {
    if (toast.parentNode) toast.remove();
  }, 6000);
}

if (typeof Vault !== 'undefined') {
  Vault.toast = showVaultToast;
}

function initPagination(tableId, rowsPerPage) {
  rowsPerPage = rowsPerPage || 15;
  var table = document.getElementById(tableId);
  if (!table) return;
  var tbody = table.querySelector('tbody');
  if (!tbody) return;
  var rows = Array.from(tbody.querySelectorAll('tr:not(.total-row)'));
  if (rows.length <= rowsPerPage) return;

  var totalPages = Math.ceil(rows.length / rowsPerPage);
  var currentPage = 1;

  var mobileCards = [];
  var tableParent = table.parentElement;
  var navAnchor = tableParent;

  var nextSib = tableParent ? tableParent.nextElementSibling : null;
  if (nextSib && /(sm|md|lg):hidden/.test(nextSib.className || '')) {
    mobileCards = Array.from(nextSib.querySelectorAll('.table-card, .v-mobile-row'));
    navAnchor = nextSib;
  } else if (tableParent && tableParent.parentElement) {
    var parentSib = tableParent.parentElement.nextElementSibling;
    if (parentSib && /(sm|md|lg):hidden/.test(parentSib.className || '')) {
      mobileCards = Array.from(parentSib.querySelectorAll('.table-card, .v-mobile-row'));
      navAnchor = parentSib;
    }
  }

  var insidePanel = !!navAnchor.closest('.v-panel');
  var nav = document.createElement('nav');
  nav.setAttribute('aria-label', 'Table pagination');
  nav.className = 'v-pagination-bar flex flex-wrap items-center justify-between gap-2 px-3 py-2.5' +
    (insidePanel ? ' border-t border-base-content/8' : ' mt-3');
  navAnchor.parentElement.insertBefore(nav, navAnchor.nextSibling);

  function render() {
    var start = (currentPage - 1) * rowsPerPage;
    var end = start + rowsPerPage;
    rows.forEach(function(row, i) {
      row.style.display = (i >= start && i < end) ? '' : 'none';
    });
    mobileCards.forEach(function(card, i) {
      card.style.display = (i >= start && i < end) ? '' : 'none';
    });

    var info = document.createElement('span');
    info.className = 'pagination-info tabular-nums';
    info.textContent = 'Showing ' + (start + 1) + '–' + Math.min(end, rows.length) + ' of ' + rows.length;

    function pageBtn(page, disabled, active, iconName, ariaLabel) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'v-page-btn join-item btn btn-xs ' +
        (active ? 'btn-primary v-btn-primary is-active' : 'btn-ghost v-btn-ghost') +
        (disabled ? ' btn-disabled' : '');
      b.disabled = !!disabled;
      b.setAttribute('data-page', String(page));
      if (ariaLabel) b.setAttribute('aria-label', ariaLabel);
      if (active) b.setAttribute('aria-current', 'page');
      if (iconName) {
        var ic = document.createElement('span');
        ic.className = 'material-symbols-outlined text-base';
        ic.setAttribute('aria-hidden', 'true');
        ic.textContent = iconName;
        b.appendChild(ic);
      } else {
        b.textContent = String(page);
      }
      return b;
    }

    var join = document.createElement('div');
    join.className = 'join v-page-join';
    join.appendChild(pageBtn('prev', currentPage === 1, false, 'chevron_left', 'Previous page'));
    var sp = Math.max(1, currentPage - 2);
    var ep = Math.min(totalPages, sp + 4);
    if (ep - sp < 4) sp = Math.max(1, ep - 4);
    for (var p = sp; p <= ep; p++) {
      join.appendChild(pageBtn(p, false, p === currentPage, null, 'Page ' + p));
    }
    join.appendChild(pageBtn('next', currentPage === totalPages, false, 'chevron_right', 'Next page'));
    nav.replaceChildren(info, join);
  }

  nav.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-page]');
    if (!btn || btn.disabled || btn.classList.contains('btn-disabled')) return;
    var p = btn.getAttribute('data-page');
    if (p === 'prev') currentPage = Math.max(1, currentPage - 1);
    else if (p === 'next') currentPage = Math.min(totalPages, currentPage + 1);
    else currentPage = parseInt(p, 10);
    render();
  });
  render();
}
