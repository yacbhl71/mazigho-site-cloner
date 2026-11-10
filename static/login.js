const form = document.querySelector('#login-form');
const error = document.querySelector('#error');
const password = document.querySelector('#password');
const resetForm = document.querySelector('#reset-form');

document.querySelector('#show-password').addEventListener('change', (event) => {
  password.type = event.target.checked ? 'text' : 'password';
});
document.querySelector('#show-new-password').addEventListener('change', (event) => {
  document.querySelector('#new-password').type = event.target.checked ? 'text' : 'password';
});
document.querySelector('#forgot-toggle').addEventListener('click', () => resetForm.classList.toggle('hidden'));

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  error.textContent = '';
  const response = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: document.querySelector('#username').value, password: password.value }),
  });
  password.value = '';
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    error.textContent = data.detail || 'Connexion impossible.';
    return;
  }
  window.location.assign('/');
});

resetForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = document.querySelector('#reset-message');
  message.textContent = '';
  const response = await fetch('/auth/reset', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      username: document.querySelector('#username').value,
      recovery_code: document.querySelector('#recovery-code').value,
      new_password: document.querySelector('#new-password').value,
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    message.textContent = data.detail || 'Réinitialisation impossible.';
    return;
  }
  message.textContent = data.message || 'Mot de passe réinitialisé.';
  document.querySelector('#new-password').value = '';
  document.querySelector('#recovery-code').value = '';
});
