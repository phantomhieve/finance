function openModal(id) {
  var el = document.getElementById(id);
  if (el && el.tagName === 'DIALOG') el.showModal();
}
function closeModal(id) {
  var el = document.getElementById(id);
  if (el && el.tagName === 'DIALOG') el.close();
}
var _pendingDeleteFormId = null;
function confirmDelete(formId, msg) {
  _pendingDeleteFormId = formId;
  var el = document.getElementById('confirmDeleteMsg');
  el.textContent = msg || 'Are you sure you want to delete this entry? This action cannot be undone.';
  document.getElementById('confirmDeleteModal').showModal();
}
function confirmDeleteProceed() {
  document.querySelectorAll('dialog[open]').forEach(function(d){ d.close(); });
  if (!_pendingDeleteFormId) return;
  Vault.showLoader();
  var form = document.getElementById(_pendingDeleteFormId);
  Vault.afterPaint(function(){ form.submit(); });
}
function toggleVaultTheme() {
  var theme = document.documentElement.getAttribute('data-theme') === 'night' ? 'winter' : 'night';
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('vault-theme', theme);
  var tc = theme === 'night' ? '#1a1b26' : '#e2e8f2';
  var m = document.getElementById('metaThemeColor');
  if (m) m.setAttribute('content', tc);
  var bg = document.getElementById('bodyBgHint');
  if (bg) bg.textContent = 'body{background-color:' + tc + '}';
  var btn = document.getElementById('themeToggleBtn');
  if (btn) {
    btn.classList.add('theme-toggle-spin');
    setTimeout(function(){ btn.classList.remove('theme-toggle-spin'); }, 500);
  }
}
function toggleSidebar() {
  var sb = document.getElementById('desktopSidebar');
  var mc = document.getElementById('mainContent');
  if (!sb) return;
  var collapsed = sb.classList.toggle('sidebar-collapsed');
  if (mc) mc.classList.toggle('main-content-collapsed', collapsed);
  localStorage.setItem('vault-sidebar', collapsed ? 'collapsed' : 'expanded');
}
(function(){
  if (localStorage.getItem('vault-sidebar') === 'collapsed') {
    var sb = document.getElementById('desktopSidebar');
    var mc = document.getElementById('mainContent');
    if (sb) sb.classList.add('sidebar-collapsed');
    if (mc) mc.classList.add('main-content-collapsed');
  }
})();

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

  if (tableParent.className.indexOf('hidden') !== -1) {
    var nextSib = tableParent.nextElementSibling;
    if (nextSib && nextSib.className.indexOf('md:hidden') !== -1) {
      mobileCards = Array.from(nextSib.querySelectorAll('.table-card'));
      navAnchor = nextSib;
    }
  }

  var nav = document.createElement('div');
  nav.className = 'flex items-center justify-between mt-3 px-1';
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
    var info = '<span class="pagination-info">Showing ' + (start + 1) + ' – ' + Math.min(end, rows.length) + ' of ' + rows.length + '</span>';
    var btns = '<div class="join">';
    btns += '<button class="join-item btn btn-xs btn-ghost' + (currentPage === 1 ? ' btn-disabled' : '') + '" data-page="prev"><span class="material-symbols-outlined text-sm">chevron_left</span></button>';
    var sp = Math.max(1, currentPage - 2);
    var ep = Math.min(totalPages, sp + 4);
    if (ep - sp < 4) sp = Math.max(1, ep - 4);
    for (var p = sp; p <= ep; p++) {
      btns += '<button class="join-item btn btn-xs' + (p === currentPage ? ' btn-primary' : ' btn-ghost') + '" data-page="' + p + '">' + p + '</button>';
    }
    btns += '<button class="join-item btn btn-xs btn-ghost' + (currentPage === totalPages ? ' btn-disabled' : '') + '" data-page="next"><span class="material-symbols-outlined text-sm">chevron_right</span></button>';
    btns += '</div>';
    nav.innerHTML = info + btns;
  }

  nav.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-page]');
    if (!btn || btn.classList.contains('btn-disabled')) return;
    var p = btn.getAttribute('data-page');
    if (p === 'prev') currentPage = Math.max(1, currentPage - 1);
    else if (p === 'next') currentPage = Math.min(totalPages, currentPage + 1);
    else currentPage = parseInt(p, 10);
    render();
  });
  render();
}
