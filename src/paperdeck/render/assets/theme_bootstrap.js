(function () {
  let mode = 'auto'; try { mode = localStorage.getItem('pd-theme') || 'auto'; } catch (_) {}
  if (!['auto', 'light', 'dark'].includes(mode)) mode = 'auto';
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.dataset.theme = mode === 'auto' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : mode;
})();
