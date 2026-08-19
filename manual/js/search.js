function tokenize(q) {
  return q
    .toLowerCase()
    .split(/[^a-z0-9+\-\/]+/)
    .filter((t) => t.length > 1);
}

function snippet(text, terms) {
  const lower = text.toLowerCase();
  let at = 0;
  for (const t of terms) {
    const i = lower.indexOf(t);
    if (i >= 0) {
      at = i;
      break;
    }
  }
  const start = Math.max(0, at - 80);
  const end = Math.min(text.length, at + 180);
  let s = (start ? "…" : "") + text.slice(start, end) + (end < text.length ? "…" : "");
  for (const t of terms.sort((a, b) => b.length - a.length)) {
    const re = new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
    s = s.replace(re, "<mark>$1</mark>");
  }
  return s;
}

function search(q) {
  const terms = tokenize(q);
  if (!terms.length || !window.TONIQ_SEARCH_DOCS) return [];
  const hits = [];
  for (const doc of window.TONIQ_SEARCH_DOCS) {
    const hay = (doc.title + " " + doc.heading + " " + doc.text).toLowerCase();
    let score = 0;
    for (const t of terms) {
      if (hay.includes(t)) score += hay.split(t).length - 1;
      if (doc.heading.toLowerCase().includes(t)) score += 4;
      if (doc.title.toLowerCase().includes(t)) score += 2;
    }
    if (score > 0) hits.push({ score, doc });
  }
  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, 60);
}

function render() {
  const q = document.getElementById("q").value.trim();
  const box = document.getElementById("results");
  if (!q) {
    box.innerHTML = "<p>Type a parameter, button, mode, or term. Results link to the heading in context.</p>";
    return;
  }
  const terms = tokenize(q);
  const hits = search(q);
  if (!hits.length) {
    box.innerHTML = "<p>No matches.</p>";
    return;
  }
  box.innerHTML = hits
    .map(({ doc }) => {
      const crumb = [doc.title, doc.heading].filter(Boolean).join(" · ");
      return (
        '<article class="search-hit">' +
        "<p class=\"search-crumb\">" +
        crumb.replace(/</g, "&lt;") +
        "</p>" +
        "<h2><a href=\"" +
        doc.url +
        "\">" +
        (doc.heading || doc.title).replace(/</g, "&lt;") +
        "</a></h2>" +
        "<p>" +
        snippet(doc.text, terms) +
        "</p></article>"
      );
    })
    .join("");
}

document.getElementById("q").addEventListener("input", render);
document.getElementById("search-form").addEventListener("submit", (e) => {
  e.preventDefault();
  render();
});
if (location.search.indexOf("q=") >= 0) {
  const q = new URLSearchParams(location.search).get("q") || "";
  document.getElementById("q").value = q;
  render();
}
