const rememberedAccount = 'warehouse.pc-login.username';

function isPC() {
  return !window.WarehouseNative && !/Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
}

function savedUsername() {
  try { return localStorage.getItem(rememberedAccount) || ''; }
  catch { return ''; }
}

function passwordManager() {
  return window.isSecureContext && window.PasswordCredential && navigator.credentials;
}

export function rememberLoginField() {
  return isPC() ? '<label class="check"><input type="checkbox" id="remember-login">이 PC에 로그인 정보 저장</label>' : '';
}

export async function fillRememberedLogin(form) {
  const option = form.querySelector('#remember-login');
  const saved = savedUsername();
  if (!option || !saved) return;
  option.checked = true;
  const {username, password} = form.elements;
  if (!username.value) username.value = saved;
  const manager = passwordManager();
  if (!manager) return;
  let edited = false;
  const onEdit = () => { edited = true; };
  form.addEventListener('input', onEdit);
  try {
    const account = await manager.get({password:true, mediation:'silent'});
    if (form.isConnected && option.checked && !edited && account?.id === saved &&
        username.value === saved && !password.value) password.value = account.password;
  } catch { /* Native browser autofill remains available. */ }
  finally { form.removeEventListener('input', onEdit); }
}

export async function saveSuccessfulLogin(username, password, remember) {
  if (!isPC()) return;
  try {
    if (remember) localStorage.setItem(rememberedAccount, username);
    else localStorage.removeItem(rememberedAccount);
  } catch { /* Browser policy can disable site storage. */ }
  const manager = passwordManager();
  if (remember && manager) {
    try { await manager.store(new PasswordCredential({id:username, password})); }
    catch { /* The password manager controls whether the user can save. */ }
  }
}
