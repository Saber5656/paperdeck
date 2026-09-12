(function () {
  'use strict';
  const pd = window.pd = {};
  pd.qs = (selector, root = document) => root.querySelector(selector);
  pd.qsa = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  pd.on = (target, event, handler, opts) => target.addEventListener(event, handler, opts);
  pd.store = {
    get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (_) {} },
    remove(key) { try { localStorage.removeItem(key); } catch (_) {} }
  };
  try { pd.data = JSON.parse(pd.qs('#pd-data').textContent); } catch (_) { pd.data = {}; }
  pd.docId = String(pd.data.docId || '');
  pd.motion = () => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  pd.element = (tag, id, text) => { const el = document.createElement(tag); if (id) el.id = id; if (text) el.textContent = text; return el; };
  pd.editing = event => event.ctrlKey || event.metaKey || event.altKey || event.isComposing || event.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName);
  function ready() {
    // ---- feature: math ----
    (() => {
      const selector = '.pd-math[data-latex], .pd-eq[data-latex]';
      function render(el) {
        if (el.dataset.pdRendered === '1') return;
        const display = el.classList.contains('pd-eq');
        let target = el;
        if (display) { target = pd.element('span'); target.className = 'pd-eq-body'; el.prepend(target); }
        try {
          katex.render(el.dataset.latex, target, {throwOnError: false, displayMode: display, macros: {...pd.data.macros}, trust: false, strict: 'ignore', maxExpand: 1000, maxSize: 10});
          if (target.querySelector('.katex-error')) throw new Error('Math unsupported');
        } catch (_) {
          el.classList.add('pd-math-error'); const code = pd.element('code', null, el.dataset.latex); target.replaceChildren(code);
        }
        el.dataset.pdRendered = '1';
      }
      pd.math = {renderInto(root) { if (root.matches && root.matches(selector)) render(root); pd.qsa(selector, root).forEach(render); }};
      const observer = 'IntersectionObserver' in window ? new IntersectionObserver(entries => entries.forEach(entry => { if (entry.isIntersecting) { render(entry.target); observer.unobserve(entry.target); } }), {rootMargin: '200%'}) : null;
      pd.qsa(selector).forEach(el => { const rect = el.getBoundingClientRect(); if (!observer || (rect.top < innerHeight && rect.bottom > 0)) render(el); else observer.observe(el); });
      pd.on(document, 'click', async event => {
        const button = event.target.closest('.pd-copy-latex'); if (!button) return;
        const text = button.dataset.latex || '';
        try { await navigator.clipboard.writeText(text); }
        catch (_) {
          const area = pd.element('textarea'); area.value = text; area.setAttribute('aria-label', 'LaTeX to copy'); document.body.append(area); area.select();
          const copied = document.execCommand('copy'); area.remove(); button.focus();
          if (!copied) { button.textContent = 'Copy unavailable'; return; }
        }
        button.textContent = 'Copied (unverified LaTeX)'; setTimeout(() => { button.textContent = 'Copy LaTeX (unverified)'; }, 2000);
      });
    })();
    // ---- feature: popup ----
    (() => {
      const popup = pd.element('div', 'pd-popup'); popup.setAttribute('role', 'tooltip'); popup.hidden = true; document.body.append(popup);
      let showTimer, hideTimer, focusFrame, active;
      function hide() { clearTimeout(showTimer); clearTimeout(hideTimer); cancelAnimationFrame(focusFrame); popup.hidden = true; if (active) active.removeAttribute('aria-describedby'); active = null; }
      function show(link) {
        hide(); const target = document.getElementById(link.hash.slice(1)); if (!target) return;
        let source = target; if (target.tagName === 'SECTION') source = target.querySelector('h2,h3,h4,h5,h6') || target;
        const clone = source.cloneNode(true); clone.removeAttribute('id');
        pd.qsa('[id]', clone).forEach(el => el.removeAttribute('id'));
        pd.qsa('a', clone).forEach(el => { el.removeAttribute('href'); el.removeAttribute('aria-describedby'); el.removeAttribute('tabindex'); });
        pd.qsa('button', clone).forEach(el => el.disabled = true);
        pd.math.renderInto(clone); popup.replaceChildren(clone); popup.hidden = false; active = link; link.setAttribute('aria-describedby', 'pd-popup');
        const rect = link.getBoundingClientRect(); const box = popup.getBoundingClientRect();
        popup.style.left = Math.max(8, Math.min(rect.left, innerWidth - box.width - 8)) + 'px';
        popup.style.top = Math.max(8, Math.min(rect.top > innerHeight / 2 ? rect.top - box.height - 10 : rect.bottom + 10, innerHeight - box.height - 8)) + 'px';
      }
      const later = () => { clearTimeout(showTimer); clearTimeout(hideTimer); hideTimer = setTimeout(hide, 300); };
      pd.qsa('a.pd-ref[href^="#"]').forEach(link => {
        pd.on(link, 'mouseenter', () => { clearTimeout(hideTimer); clearTimeout(showTimer); showTimer = setTimeout(() => show(link), 150); });
        pd.on(link, 'mouseleave', later); pd.on(link, 'focus', () => { hide(); focusFrame = requestAnimationFrame(() => { if (document.activeElement === link) show(link); }); }); pd.on(link, 'blur', later);
      });
      pd.on(popup, 'mouseenter', () => clearTimeout(hideTimer)); pd.on(popup, 'mouseleave', later);
      pd.on(window, 'scroll', () => { clearTimeout(showTimer); if (!popup.hidden) hide(); }, {passive: true}); pd.on(window, 'resize', hide); pd.popup = {hide};
    })();
    // ---- feature: jump/back ----
    (() => {
      const stack = []; const button = pd.element('button', 'pd-back'); button.hidden = true; document.body.append(button);
      const update = () => { button.hidden = !stack.length; button.textContent = 'Back (' + stack.length + ')'; };
      function go(id, remember = true) {
        const target = document.getElementById(id); if (!target) return;
        if (remember) { stack.push({y: scrollY}); if (stack.length > 50) stack.shift(); update(); }
        pd.popup.hide(); pd.math.renderInto(target); target.scrollIntoView({behavior: pd.motion(), block: 'start'});
        target.classList.add('pd-flash'); setTimeout(() => target.classList.remove('pd-flash'), 1200);
      }
      function back() { const pos = stack.pop(); if (pos) { window.scrollTo({top: pos.y, behavior: 'instant'}); update(); } }
      pd.on(button, 'click', back);
      pd.on(document, 'click', event => {
        const link = event.target.closest('a.pd-ref[href^="#"],a.pd-fn-back[href^="#"]');
        if (!link || link.closest('#pd-popup') || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
        event.preventDefault(); go(link.hash.slice(1));
      });
      pd.jump = {go, back};
      if (location.hash) {
        // A fragment opens below the initial viewport. Finish math and font layout
        // before measuring its destination so lazy rendering cannot move the anchor.
        pd.math.renderInto(pd.qs('#pd-content') || document.body);
        const fontsReady = document.fonts ? document.fonts.ready : Promise.resolve();
        fontsReady.then(() => requestAnimationFrame(() => requestAnimationFrame(() => go(decodeURIComponent(location.hash.slice(1)), false))));
      }
    })();
    // ---- feature: toc ----
    (() => {
      const nav = pd.qs('#pd-toc'), button = pd.qs('#pd-toc-toggle'); if (!nav || !button) return;
      const media = matchMedia('(min-width: 900px)'); const stored = pd.store.get('pd-toc');
      const backdrop = pd.element('div', 'pd-toc-backdrop'); backdrop.hidden = true; document.body.append(backdrop);
      function set(open, persist = true) {
        document.body.classList.toggle('pd-toc-open', open); button.setAttribute('aria-expanded', String(open));
        backdrop.hidden = !open || media.matches; if (persist) pd.store.set('pd-toc', open ? 'open' : 'closed');
      }
      button.setAttribute('aria-controls', 'pd-toc');
      set(media.matches && stored !== 'closed', false); pd.on(button, 'click', () => set(!document.body.classList.contains('pd-toc-open')));
      pd.on(backdrop, 'click', () => set(false)); pd.on(media, 'change', () => set(media.matches && pd.store.get('pd-toc') !== 'closed', false));
      pd.on(nav, 'click', event => { const link = event.target.closest('a.pd-toc-link'); if (link) current(link.hash.slice(1)); if (link && !media.matches) set(false); });
      const links = pd.qsa('a.pd-toc-link', nav); const branches = new Map();
      function reveal(current) {
        branches.forEach((branch, li) => {
          const ancestor = current && li.contains(current) && li.querySelector(':scope > a') !== current;
          const open = branch.expanded || ancestor;
          branch.children.hidden = !open;
          branch.button.setAttribute('aria-expanded', String(Boolean(open)));
          branch.button.textContent = open ? 'Collapse' : 'Expand';
        });
      }
      pd.qsa('li', nav).forEach(li => { const children = li.querySelector(':scope > ol'); if (!children || !children.querySelector('li')) return;
        const disclosure = pd.element('button', null, 'Expand'); disclosure.className = 'pd-disclosure'; li.prepend(disclosure);
        const branch = {children, button: disclosure, expanded: Number(li.dataset.level) < 2}; branches.set(li, branch);
        pd.on(disclosure, 'click', () => { branch.expanded = children.hidden; reveal(null); });
      });
      function current(id) {
        let active = null; links.forEach(link => { const yes = link.hash.slice(1) === id; link.classList.toggle('pd-current', yes); if (yes) { link.setAttribute('aria-current', 'location'); active = link; } else link.removeAttribute('aria-current'); });
        reveal(active);
        if (active) { const r = active.getBoundingClientRect(), n = nav.getBoundingClientRect(); if (r.top < n.top || r.bottom > n.bottom) nav.scrollTop += r.top - n.top - 30; }
      }
      let pending = false, next;
      if ('IntersectionObserver' in window) {
        const spy = new IntersectionObserver(entries => { entries.forEach(entry => { if (entry.isIntersecting) next = entry.target.parentElement.id; }); if (!pending && next) { pending = true; requestAnimationFrame(() => { current(next); pending = false; }); } }, {rootMargin: '-54px 0px -75% 0px'});
        pd.qsa('main section > h2,main section > h3,main section > h4,main section > h5,main section > h6').forEach(heading => spy.observe(heading));
      }
      reveal(null); pd.toc = {toggle: () => set(!document.body.classList.contains('pd-toc-open'))};
    })();
    // ---- feature: theme ----
    (() => {
      const media = matchMedia('(prefers-color-scheme: dark)'), root = document.documentElement, button = pd.qs('#pd-theme-toggle');
      let mode = root.dataset.themeMode || 'auto';
      function apply() { root.dataset.themeMode = mode; root.dataset.theme = mode === 'auto' ? (media.matches ? 'dark' : 'light') : mode; if (button) button.textContent = 'Theme: ' + mode; }
      function cycle() { mode = ['auto', 'light', 'dark'][(['auto', 'light', 'dark'].indexOf(mode) + 1) % 3]; pd.store.set('pd-theme', mode); apply(); }
      if (button) { button.setAttribute('aria-live', 'polite'); pd.on(button, 'click', cycle); }
      pd.on(media, 'change', apply); apply(); pd.theme = {cycle};
    })();
    // ---- feature: position ----
    (() => {
      // Keep native reload restoration from racing the per-document anchor restore.
      if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
      const key = 'pd-pos:' + pd.docId, nodes = pd.qsa('main [id]').filter(el => /^[a-z]+-\d+$/.test(el.id));
      const toast = pd.element('button', 'pd-toast', 'Resumed — press T to go to top'); toast.setAttribute('role', 'status'); toast.hidden = true; document.body.append(toast);
      let timer, cleared = false;
      function save() {
        if (cleared && scrollY < innerHeight) return;
        cleared = false; let chosen = null;
        for (const node of nodes) { const rect = node.getBoundingClientRect(); if (rect.top <= innerHeight / 3 && rect.bottom >= 0) chosen = node; }
        if (chosen) pd.store.set(key, JSON.stringify({anchor: chosen.id, offset: chosen.getBoundingClientRect().top, at: Date.now()}));
      }
      function goTop() { clearTimeout(timer); cleared = true; toast.hidden = true; pd.store.remove(key); window.scrollTo({top: 0, behavior: 'instant'}); }
      pd.on(toast, 'click', goTop);
      pd.on(window, 'scroll', () => { clearTimeout(timer); timer = setTimeout(save, 500); }, {passive: true});
      pd.on(window, 'beforeunload', () => { clearTimeout(timer); save(); });
      pd.position = {goTop, toast};
      if (!location.hash) {
        try {
          const saved = JSON.parse(pd.store.get(key));
          if (saved && typeof saved.anchor === 'string' && /^[a-z]+-\d+$/.test(saved.anchor) && Number.isFinite(saved.offset) && Number.isFinite(saved.at)) {
            const target = document.getElementById(saved.anchor);
            if (target) requestAnimationFrame(() => requestAnimationFrame(() => {
              const y = target.getBoundingClientRect().top + scrollY - saved.offset;
              if (y > innerHeight * 1.5) { pd.math.renderInto(target); window.scrollTo({top: y, behavior: 'instant'}); toast.hidden = false; setTimeout(() => { toast.hidden = true; }, 4000); }
            }));
          }
        } catch (_) {}
      }
    })();
    // ---- feature: keys ----
    (() => {
      const registry = new Map(); let previous;
      const overlay = pd.element('div', 'pd-help'); overlay.setAttribute('role', 'dialog'); overlay.setAttribute('aria-modal', 'true'); overlay.setAttribute('aria-label', 'Keyboard shortcuts'); overlay.hidden = true;
      const panel = pd.element('div'); panel.className = 'pd-help-panel'; panel.append(pd.element('h2', null, 'Keyboard shortcuts'));
      const table = pd.element('table'), close = pd.element('button', null, 'Close'); panel.append(table, close); overlay.append(panel); document.body.append(overlay);
      function hide() { overlay.hidden = true; if (previous && previous.isConnected) previous.focus(); }
      function toggle(opener) { if (!overlay.hidden) return hide(); previous = opener || document.activeElement; table.replaceChildren(); registry.forEach((value, key) => { const row = pd.element('tr'); row.append(pd.element('th', null, key), pd.element('td', null, value.description)); table.append(row); }); overlay.hidden = false; close.focus(); }
      function register(key, description, handler) { if (registry.has(key)) throw new Error('Duplicate shortcut: ' + key); registry.set(key, {description, handler}); }
      const headings = pd.qsa('main section > h2,main section > h3,main section > h4,main section > h5,main section > h6');
      function section(direction) {
        const candidates = headings.filter(h => direction > 0 ? h.getBoundingClientRect().top > 80 : h.getBoundingClientRect().top < 40);
        const target = direction > 0 ? candidates[0] : candidates.at(-1); if (target) window.scrollTo({top: target.getBoundingClientRect().top + scrollY - 72, behavior: pd.motion()});
      }
      register('j', 'Next section', () => section(1)); register('k', 'Previous section', () => section(-1));
      register('t', 'Toggle contents', () => pd.toc && pd.toc.toggle()); register('d', 'Cycle theme', () => pd.theme.cycle());
      register('Backspace', 'Back to reading position', pd.jump.back); register('?', 'Keyboard shortcuts', toggle);
      register('Escape', 'Close preview or help', () => { pd.popup.hide(); if (!overlay.hidden) hide(); });
      pd.on(close, 'click', hide); pd.on(overlay, 'click', event => { if (event.target === overlay) hide(); });
      const helpButton = pd.qs('#pd-help-toggle'); if (helpButton) pd.on(helpButton, 'click', () => toggle(helpButton));
      pd.on(document, 'keydown', event => {
        if (pd.editing(event)) return;
        if (!overlay.hidden) { if (event.key === 'Tab') { event.preventDefault(); close.focus(); return; } if (!['?', 'Escape'].includes(event.key)) return; }
        if (event.key === 'T' && !pd.position.toast.hidden) { event.preventDefault(); pd.position.goTop(); return; }
        const entry = registry.get(event.key); if (entry) { event.preventDefault(); entry.handler(); }
      });
      pd.keys = {register, registry};
    })();
  }
  if (document.readyState === 'loading') pd.on(document, 'DOMContentLoaded', ready); else ready();
})();
