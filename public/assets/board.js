(function () {
  var table = document.getElementById('board');
  var tbody = table.tBodies[0];
  var rows = Array.prototype.slice.call(tbody.rows);
  function val(row, key) {
    var i = {rank:0, name:1, season:2, acc:3, life:4, bucks:5, perfect:6, global:7}[key];
    var cell = row.cells[i];
    if (key === 'name') return cell.querySelector('.pname').textContent.toLowerCase();
    var raw = (cell.querySelector('.num, .rank') || cell).textContent.replace(/[^0-9.]/g, '');
    return raw === '' ? -1 : parseFloat(raw);
  }
  var btn = document.getElementById('toggle-unconfirmed');
  if (btn) {
    var hiddenCount = document.querySelectorAll('tr.unconfirmed').length;
    btn.addEventListener('click', function () {
      var on = document.body.classList.toggle('show-unconfirmed');
      btn.setAttribute('aria-pressed', String(on));
      btn.textContent = on ? 'Hide unconfirmed' : 'Show unconfirmed (' + hiddenCount + ')';
      // The board ranks whoever is on screen, so the numbers change with it.
      rows.forEach(function (r) {
        r.querySelector('.rank').textContent =
          on ? r.dataset.rankAll : (r.dataset.rankConfirmed || '—');
      });
      document.querySelectorAll('[data-all]').forEach(function (el) {
        el.textContent = on ? el.dataset.all : el.dataset.confirmed;
      });
    });
  }

  table.tHead.addEventListener('click', function (e) {
    var th = e.target.closest('th');
    if (!th) return;
    var key = th.dataset.key;
    var dir = th.getAttribute('aria-sort') === 'descending' ? 'asc' : 'desc';
    if (!th.hasAttribute('aria-sort')) dir = th.dataset.dir;
    Array.prototype.forEach.call(table.tHead.rows[0].cells, function (c) { c.setAttribute('aria-sort', 'none'); });
    th.setAttribute('aria-sort', dir === 'asc' ? 'ascending' : 'descending');
    var sorted = rows.slice().sort(function (a, b) {
      var x = val(a, key), y = val(b, key);
      var c = x < y ? -1 : x > y ? 1 : 0;
      return dir === 'asc' ? c : -c;
    });
    sorted.forEach(function (r) { tbody.appendChild(r); });
  });
})();
