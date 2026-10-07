// Small helper script - only what is really needed.
document.addEventListener("DOMContentLoaded", function () {
  // 1. Confirmation before delete (any form with data-confirm="message")
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!confirm(form.dataset.confirm)) e.preventDefault();
    });
  });

  // 2. Open / close sidebar on mobile
  var btn = document.getElementById("menuBtn");
  var sidebar = document.getElementById("sidebar");
  if (btn && sidebar) {
    btn.addEventListener("click", function () { sidebar.classList.toggle("open"); });
    document.addEventListener("click", function (e) {
      if (sidebar.classList.contains("open") && !sidebar.contains(e.target) && e.target !== btn) {
        sidebar.classList.remove("open");
      }
    });
  }

  // 3. "Mark all Present / Absent" buttons on the attendance page
  document.querySelectorAll("[data-mark-all]").forEach(function (b) {
    b.addEventListener("click", function () {
      document.querySelectorAll('input[type=radio][value="' + b.dataset.markAll + '"]')
        .forEach(function (r) { r.checked = true; });
    });
  });
});
