const form = document.querySelector('#login-form');
const error = document.querySelector('#error');
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  error.textContent = '';
  const response = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: document.querySelector('#username').value, password: document.querySelector('#password').value }),
  });
  document.querySelector('#password').value = '';
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    error.textContent = data.detail || 'Connexion impossible.';
    return;
  }
  window.location.assign('/');
});
