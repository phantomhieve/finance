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
    select.replaceChildren();
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
      var na = document.createElement('option');
      na.value = '';
      na.textContent = 'N/A';
      puritySelect.replaceChildren(na);
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
    var file = input && input.files ? input.files[0] : null;
    var container = document.getElementById(previewContainerId);
    var box = document.getElementById(uploadBoxId);
    var img = document.getElementById(previewImgId);
    var loader = container ? container.querySelector('[data-photo-loader]') : null;

    if (!file) {
      if (container) container.classList.add('hidden');
      if (box) box.classList.remove('hidden');
      if (img) img.removeAttribute('src');
      return;
    }

    var allowedTypes = ['image/jpeg', 'image/png', 'image/webp'];
    if (!file.type || allowedTypes.indexOf(file.type.toLowerCase()) === -1) {
      if (input) input.value = '';
      if (container) container.classList.add('hidden');
      if (box) box.classList.remove('hidden');
      if (img) img.removeAttribute('src');
      return;
    }

    if (box) box.classList.add('hidden');
    if (container) container.classList.remove('hidden');
    if (img) img.classList.add('opacity-0');
    if (loader) loader.classList.remove('hidden');

    var started = Date.now();
    var reader = new FileReader();

    reader.onload = function (e) {
      var result = e.target && e.target.result;
      var isSafeDataUrl = typeof result === 'string' && (
        result.indexOf('data:image/jpeg;base64,') === 0 ||
        result.indexOf('data:image/png;base64,') === 0 ||
        result.indexOf('data:image/webp;base64,') === 0
      ) && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=\s]+$/.test(result);

      if (isSafeDataUrl) {
        var wait = Math.max(0, 550 - (Date.now() - started));
        setTimeout(function () {
          if (loader) loader.classList.add('hidden');
          if (img) {
            img.src = result;
            img.classList.remove('opacity-0');
          }
        }, wait);
      } else {
        if (loader) loader.classList.add('hidden');
        if (box) box.classList.remove('hidden');
        if (container) container.classList.add('hidden');
        if (img) img.removeAttribute('src');
      }
    };

    reader.onerror = function () {
      if (loader) loader.classList.add('hidden');
      if (box) box.classList.remove('hidden');
      if (container) container.classList.add('hidden');
      if (img) img.removeAttribute('src');
    };

    reader.readAsDataURL(file);
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

      var info = document.createElement('span');
      info.className = 'text-[10px] uppercase tracking-wider opacity-40 font-bold';
      info.textContent = 'Showing ' + (start + 1) + ' – ' + Math.min(end, items.length) + ' of ' + items.length;

      var pageBtn = function (page, disabled, active, iconName) {
        var b = document.createElement('button');
        b.className = 'join-item btn btn-xs ' + (active ? 'btn-primary' : 'btn-ghost') + (disabled ? ' btn-disabled' : '');
        b.setAttribute('data-page', String(page));
        if (iconName) {
          var ic = document.createElement('span');
          ic.className = 'material-symbols-outlined text-sm';
          ic.textContent = iconName;
          b.appendChild(ic);
        } else {
          b.textContent = String(page);
        }
        return b;
      };

      var join = document.createElement('div');
      join.className = 'join';
      join.appendChild(pageBtn('prev', currentPage === 1, false, 'chevron_left'));
      var sp = Math.max(1, currentPage - 2);
      var ep = Math.min(totalPages, sp + 4);
      if (ep - sp < 4) sp = Math.max(1, ep - 4);
      for (var p = sp; p <= ep; p++) {
        join.appendChild(pageBtn(p, false, p === currentPage));
      }
      join.appendChild(pageBtn('next', currentPage === totalPages, false, 'chevron_right'));
      nav.replaceChildren(info, join);
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
