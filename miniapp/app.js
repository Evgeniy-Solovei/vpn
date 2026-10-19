/**
 * Telegram Mini App Logic
 */

let tg = window.Telegram?.WebApp;
let userData = null;
let vpnData = null;

document.addEventListener('DOMContentLoaded', async () => {
  if (tg) {
    tg.ready();
    tg.expand();
  }

  // Get user info from Telegram WebApp
  const tgUser = tg?.initDataUnsafe?.user || {
    id: 828956887, // fallback demo ID for browser preview
    first_name: 'Пользователь',
    username: 'vpn_user'
  };

  const startParam = tg?.initDataUnsafe?.start_param || null;

  // Sync with Backend API
  try {
    const res = await fetch('/api/tg/sync/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        telegram_id: tgUser.id,
        telegram_username: tgUser.username,
        ref_code: startParam
      })
    });
    const data = await res.json();
    if (data.success) {
      userData = data.user;
      vpnData = data.vpn;
      renderUI();
    }
  } catch (err) {
    console.error('Error syncing with API:', err);
  }
});

function renderUI() {
  if (!userData || !vpnData) return;

  document.getElementById('user-name').textContent = userData.username;
  document.getElementById('user-id').textContent = `ID: ${userData.telegram_id || userData.id}`;
  document.getElementById('user-balance').textContent = `${userData.balance} ₽`;
  document.getElementById('user-days').textContent = `на ${userData.days_left} дн.`;
  document.getElementById('user-avatar').textContent = (userData.username[0] || 'V').toUpperCase();

  document.getElementById('server-name').textContent = vpnData.server_name;
  document.getElementById('server-ping').textContent = `${vpnData.ping_ms} ms`;

  const btnIncy = document.getElementById('btn-incy');
  btnIncy.href = vpnData.incy_url;

  const powerBtn = document.getElementById('power-btn');
  powerBtn.onclick = () => {
    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
    window.location.href = vpnData.incy_url;
  };

  // Copy Buttons
  document.getElementById('btn-copy-vless').onclick = () => {
    navigator.clipboard.writeText(vpnData.vless_url);
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    alert('VLESS ключ скопирован!');
  };

  document.getElementById('btn-copy-sub').onclick = () => {
    navigator.clipboard.writeText(vpnData.sub_url);
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    alert('Ссылка подписки скопирована!');
  };

  // Whitelist Switch
  const wlSwitch = document.getElementById('whitelist-switch');
  if (!vpnData.whitelist_enabled) {
    wlSwitch.classList.remove('active');
  }

  wlSwitch.onclick = async () => {
    if (tg?.HapticFeedback) tg.HapticFeedback.selectionChanged();
    try {
      const res = await fetch('/api/vpn/toggle-whitelist/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ telegram_id: userData.telegram_id })
      });
      const data = await res.json();
      if (data.success) {
        wlSwitch.classList.toggle('active', data.whitelist_enabled);
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Share ref
  document.getElementById('btn-share-ref').onclick = () => {
    const text = `🔥 Попробуй быстрый VPN без блокировок для РФ и РБ! Получи бонус на баланс при регистрации: ${userData.referral_url}`;
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(userData.referral_url)}&text=${encodeURIComponent(text)}`);
    } else {
      navigator.clipboard.writeText(userData.referral_url);
      alert('Реферальная ссылка скопирована!');
    }
  };
}
