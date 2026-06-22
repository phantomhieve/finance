/* Jewellery — shared helpers for dashboard & detail views. */
(function (window, document) {
  'use strict';

  var GOLD_PURITIES = [
    { value: '24k', label: '24k (999)' },
    { value: '22k', label: '22k (916)' },
    { value: '18k', label: '18k (750)' },
    { value: '14k', label: '14k (585)' }
  ];
  var SILVER_PURITIES = [
    { value: '999', label: '999 (Fine Silver)' },
    { value: '925', label: '925 (Sterling)' },
    { value: '900', label: '900' },
    { value: '800', label: '800' }
  ];

  function fill(select, list, prev, fallback) {
    select.innerHTML = '';
    list.forEach(function (p) {
      var opt = document.createElement('option');
      opt.value = p.value;
      opt.textContent = p.label;
      select.appendChild(opt);
    });
    select.disabled = false;
    var found = list.some(function (p) { return p.value === prev; });
    select.value = found ? prev : fallback;
  }

  function updatePurityChoices(metalSelect, puritySelect, keepValue) {
    var metal = metalSelect.value;
    var prev = keepValue || puritySelect.value;
    if (metal === 'GOLD' || metal === 'DIAMOND_OTHER') {
      var fallback = (metal === 'DIAMOND_OTHER') ? '18k' : '22k';
      fill(puritySelect, GOLD_PURITIES, prev, fallback);
    } else if (metal === 'SILVER') {
      fill(puritySelect, SILVER_PURITIES, prev, '999');
    } else {
      puritySelect.innerHTML = '<option value="">N/A</option>';
      puritySelect.disabled = true;
    }
  }

  // ── Location chips ───────────────────────────────────────────────
  var _locFns = {};

  // Elements expected: <prefix>_location (hidden) and <prefix>_location_chips
  // (container with [data-loc] buttons).
  function initLocation(prefix) {
    var hidden = document.getElementById(prefix + '_location');
    var chips = document.querySelectorAll('#' + prefix + '_location_chips [data-loc]');
    if (!hidden) return;

    function select(loc) {
      hidden.value = loc;
      chips.forEach(function (b) {
        var on = b.getAttribute('data-loc') === loc;
        b.classList.toggle('btn-primary', on);
        b.classList.toggle('btn-ghost', !on);
      });
    }

    chips.forEach(function (b) {
      b.addEventListener('click', function () { select(b.getAttribute('data-loc')); });
    });

    _locFns[prefix] = select;
    select(hidden.value || 'BANK_LOCKER');
  }

  function selectLocation(prefix, loc) {
    if (_locFns[prefix]) _locFns[prefix](loc);
  }

  // ── Photo preview ────────────────────────────────────────────────
  // Shows a brief "processing" spinner, then reveals the selected image —
  // mimicking the feel of the server receiving the upload.
  function handlePhotoSelect(input, previewContainerId, previewImgId, uploadBoxId) {
    var file = input.files[0];
    var container = document.getElementById(previewContainerId);
    var box = document.getElementById(uploadBoxId);
    var img = document.getElementById(previewImgId);
    var loader = container.querySelector('[data-photo-loader]');

    if (!file) {
      container.classList.add('hidden');
      box.classList.remove('hidden');
      return;
    }

    box.classList.add('hidden');
    container.classList.remove('hidden');
    img.classList.add('opacity-0');
    if (loader) loader.classList.remove('hidden');

    var objectUrl = URL.createObjectURL(file);
    var started = Date.now();

    img.onload = function () {
      // Keep the spinner visible for at least ~550ms so it reads as work.
      var wait = Math.max(0, 550 - (Date.now() - started));
      setTimeout(function () {
        if (loader) loader.classList.add('hidden');
        img.classList.remove('opacity-0');
        URL.revokeObjectURL(objectUrl);
      }, wait);
    };
    img.onerror = function () {
      if (loader) loader.classList.add('hidden');
      img.classList.remove('opacity-0');
      URL.revokeObjectURL(objectUrl);
    };
    img.src = objectUrl;
  }

  // ── Grid pagination ──────────────────────────────────────────────
  function initGridPagination(gridId, itemsPerPage) {
    var grid = document.getElementById(gridId);
    if (!grid) return;
    var items = Array.prototype.slice.call(grid.children);
    if (items.length <= itemsPerPage) return;

    var totalPages = Math.ceil(items.length / itemsPerPage);
    var currentPage = 1;

    var nav = document.createElement('div');
    nav.className = 'flex items-center justify-between mt-4 px-1';
    grid.parentNode.insertBefore(nav, grid.nextSibling);

    function render() {
      var start = (currentPage - 1) * itemsPerPage;
      var end = start + itemsPerPage;
      items.forEach(function (item, i) {
        item.style.display = (i >= start && i < end) ? '' : 'none';
      });

      var info = '<span class="text-[10px] uppercase tracking-wider opacity-40 font-bold">Showing ' +
        (start + 1) + ' – ' + Math.min(end, items.length) + ' of ' + items.length + '</span>';
      var btns = '<div class="join">';
      btns += '<button class="join-item btn btn-xs btn-ghost' + (currentPage === 1 ? ' btn-disabled' : '') +
        '" data-page="prev"><span class="material-symbols-outlined text-sm">chevron_left</span></button>';
      var sp = Math.max(1, currentPage - 2);
      var ep = Math.min(totalPages, sp + 4);
      if (ep - sp < 4) sp = Math.max(1, ep - 4);
      for (var p = sp; p <= ep; p++) {
        btns += '<button class="join-item btn btn-xs' + (p === currentPage ? ' btn-primary' : ' btn-ghost') +
          '" data-page="' + p + '">' + p + '</button>';
      }
      btns += '<button class="join-item btn btn-xs btn-ghost' + (currentPage === totalPages ? ' btn-disabled' : '') +
        '" data-page="next"><span class="material-symbols-outlined text-sm">chevron_right</span></button></div>';
      nav.innerHTML = info + btns;
    }

    nav.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-page]');
      if (!btn || btn.classList.contains('btn-disabled')) return;
      var p = btn.getAttribute('data-page');
      if (p === 'prev') currentPage = Math.max(1, currentPage - 1);
      else if (p === 'next') currentPage = Math.min(totalPages, currentPage + 1);
      else currentPage = parseInt(p, 10);
      render();
      window.scrollTo({ top: grid.offsetTop - 100, behavior: 'smooth' });
    });

    render();
  }

  window.Jewellery = {
    updatePurityChoices: updatePurityChoices,
    handlePhotoSelect: handlePhotoSelect,
    initLocation: initLocation,
    selectLocation: selectLocation,
    initGridPagination: initGridPagination
  };
  // Expose for inline onchange="" handlers in markup.
  window.handlePhotoSelect = handlePhotoSelect;
})(window, document);
