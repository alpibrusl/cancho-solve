(function () {
  var box = document.querySelector(".replay"), btn = document.getElementById("replay");
  var tabs = box ? box.querySelectorAll("[role=tab]") : [], pres = box ? box.querySelectorAll("pre.screen") : [];
  if (!btn || !tabs.length || tabs.length !== pres.length) { return; }
  var logs = Array.prototype.map.call(pres, function (p) { return Array.prototype.map.call(p.children, function (s) { return [s.className, s.textContent]; }); });
  function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;"); }
  function span(c, t) { return "<span" + (c ? ' class="' + c + '"' : "") + ">" + esc(t) + "</span>"; }
  var timer = null, cur = 0, reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  function full(i) { pres[i].innerHTML = logs[i].map(function (l) { return span(l[0], l[1]); }).join("\n"); pres[i].removeAttribute("aria-busy"); }
  function show(i, focus) {
    clearTimeout(timer); cur = i;
    Array.prototype.forEach.call(tabs, function (t, k) { t.setAttribute("aria-selected", k === i ? "true" : "false"); t.tabIndex = k === i ? 0 : -1; pres[k].hidden = k !== i; });
    if (focus) { tabs[i].focus(); }
    if (reduce) { full(i); } else { play(i); }
  }
  function play(i) {
    var lines = logs[i], pre = pres[i], n = 0, j = 0, html = "";
    clearTimeout(timer); pre.style.minHeight = ""; full(i); pre.style.minHeight = pre.offsetHeight + "px";
    pre.innerHTML = ""; pre.setAttribute("aria-busy", "true");
    (function tick() {
      if (n >= lines.length) { pre.removeAttribute("aria-busy"); return; }
      var l = lines[n], step = l[0] === "a" ? 3 : 16;
      j += step;
      pre.innerHTML = html + span(l[0], l[1].slice(0, j));
      if (j >= l[1].length) { html += span(l[0], l[1]) + "\n"; n++; j = 0; timer = setTimeout(tick, l[0] === "d" ? 300 : 420); }
      else { timer = setTimeout(tick, 12); }
    })();
  }
  box.classList.add("js"); box.querySelector("[role=tablist]").hidden = false; btn.hidden = false;
  Array.prototype.forEach.call(tabs, function (t, k) {
    t.addEventListener("click", function () { show(k, false); });
    t.addEventListener("keydown", function (ev) {
      var d = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
      if (d) { ev.preventDefault(); show((k + d + tabs.length) % tabs.length, true); }
    });
  });
  btn.addEventListener("click", function () { show(cur, false); });
  show(0, false);
})();
