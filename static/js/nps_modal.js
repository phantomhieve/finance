(function() {
  function setNpsTitle(el, iconName, label) {
    var icon = document.createElement('span');
    icon.className = 'material-symbols-outlined text-primary text-xl';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = iconName;
    el.replaceChildren(icon, document.createTextNode(label));
  }

  function updateNpsTotal() {
    var form = document.getElementById('npsForm');
    if (!form) return;
    var prevEl = document.getElementById('npsPrevBalance');
    if (!prevEl) return;
    var contribInput = form.querySelector('[name=contribution]');
    var interestInput = form.querySelector('[name=interest_earned]');
    var totalInput = form.querySelector('[name=total_balance]');
    if (!contribInput || !interestInput || !totalInput) return;

    var prev = parseFloat(prevEl.value || '0');
    var contrib = parseFloat(contribInput.value || '0');
    var interest = parseFloat(interestInput.value || '0');
    var total = prev + contrib + interest;
    if (!isNaN(total)) {
      totalInput.value = total.toFixed(2);
    }
  }

  window.openNpsAddModal = function() {
    var form = document.getElementById('npsForm');
    if (!form) return;
    form.action = form.dataset.addUrl || '/portfolio/nps/add/';
    form.reset();
    var delBtn = document.getElementById('npsDeleteBtn');
    if (delBtn) {
      delBtn.classList.add('hidden');
      delBtn.style.display = 'none';
    }
    var titleEl = document.getElementById('npsModalTitle');
    if (titleEl) {
      setNpsTitle(titleEl, 'assured_workload', ' Add NPS Entry');
    }
    var prevEl = document.getElementById('npsPrevBalance');
    if (prevEl) {
      var rawBase = prevEl.getAttribute('data-current-balance') || '0';
      var numBase = parseFloat(rawBase);
      prevEl.value = isNaN(numBase) ? '0' : String(numBase);
    }
    updateNpsTotal();
    openModal('addNpsModal');
  };

  document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-edit-nps]');
    if (!btn) return;

    var form = document.getElementById('npsForm');
    if (!form) return;

    var npsId = parseInt(btn.dataset.id, 10);
    if (isNaN(npsId) || npsId <= 0) return;

    form.action = form.dataset.editUrl
      ? form.dataset.editUrl.replace('/0/', '/' + npsId + '/')
      : '/portfolio/nps/' + npsId + '/edit/';
    var delForm = document.getElementById('deleteNpsForm');
    if (delForm) {
      delForm.action = form.dataset.deleteUrl
        ? form.dataset.deleteUrl.replace('/0/', '/' + npsId + '/')
        : '/portfolio/nps/' + npsId + '/delete/';
    }
    var delBtn = document.getElementById('npsDeleteBtn');
    if (delBtn) {
      delBtn.classList.remove('hidden');
      delBtn.style.display = 'inline-flex';
    }
    var titleEl = document.getElementById('npsModalTitle');
    if (titleEl) {
      setNpsTitle(titleEl, 'edit', ' Edit NPS Entry');
    }

    form.querySelector('[name=date]').value = btn.dataset.date || '';
    form.querySelector('[name=contribution]').value = btn.dataset.contrib || '';
    form.querySelector('[name=interest_earned]').value = btn.dataset.interest || '';
    form.querySelector('[name=total_balance]').value = btn.dataset.balance || '';
    form.querySelector('[name=remarks]').value = btn.dataset.remarks || '';

    // prev balance = existing total - contrib - interest
    var prev = parseFloat(btn.dataset.balance || '0') -
               parseFloat(btn.dataset.contrib || '0') -
               parseFloat(btn.dataset.interest || '0');
    var prevEl = document.getElementById('npsPrevBalance');
    if (prevEl) prevEl.value = isNaN(prev) ? '0' : prev.toString();

    updateNpsTotal();
    openModal('addNpsModal');
  });

  document.addEventListener('DOMContentLoaded', function() {
    var form = document.getElementById('npsForm');
    if (!form) return;
    var contribInput = form.querySelector('[name=contribution]');
    var interestInput = form.querySelector('[name=interest_earned]');
    if (contribInput) contribInput.addEventListener('input', updateNpsTotal);
    if (interestInput) interestInput.addEventListener('input', updateNpsTotal);
  });
})();
