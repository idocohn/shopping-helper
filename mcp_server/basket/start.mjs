const loading = document.getElementById('app-loading');

import('./app.mjs?v=9').then(() => {
  loading.hidden = true;
}).catch(() => {
  loading.textContent = 'The comparison tools could not load. Refresh the page and try again.';
  loading.classList.add('error');
  loading.setAttribute('role', 'alert');
});
