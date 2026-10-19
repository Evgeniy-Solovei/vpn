/**
 * Telegram Mini App Logic - Production Ready & Pure Real Data
 */

let tg = window.Telegram?.WebApp;
let userData = null;
let vpnData = null;

const loadingView = document.getElementById('loading-view');
const miniappView = document.getElementById('miniapp-view');
const unauthView = document.getElementById('unauth-view');
const browserBanner = document.getElementById('browser-banner');
const browserBannerText = document.getElementById('browser-banner-text');

document.addEventListener('DOMContentLoaded', async () => {
  if (tg) {
    try {
      tg.ready();
      tg.expand();
    } catch (e) {
      console.log('TG WebApp ready error:', e);
    }
  }

  const tgUser = tg?.initDataUnsafe?.user;
  const startParam = tg?.initDataUnsafe?.start_param || null;

  if (tgUser && tgUser.id) {
    // 1. We are inside Telegram WebApp
    try {
      const res = await fetch('/api/tg/sync/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          telegram_id: tgUser.id,
          telegram_username: tgUser.username,
          first_name: tgUser.first_name,
          ref_code: startParam
        })
      });
      const data = await res.json();
      if (data.success) {
        userData = data.user;
        vpnData = data.vpn;
        renderUI();
      } else {
        showError(data.error || 'Ошибка синхронизации Telegram');
      }
    } catch (err) {
      console.error('Error syncing TG WebApp:', err);
      showError('Не удалось подключиться к API сервера.');
    }
  } else {
    // 2. Opened in standard browser (Desktop / Mobile outside TG)
    await checkWebSession();
  }

  // Setup Demo Login button
  const btnLoginDemo = document.getElementById('btn-login-demo');
  if (btnLoginDemo) {
    btnLoginDemo.onclick = async () => {
      btnLoginDemo.disabled = true;
      btnLoginDemo.innerHTML = '<span>Вход в Demo...</span>';
      try {
        const res = await fetch('/api/auth/demo-login/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin'
        });
        const data = await res.json();
        if (data.success) {
          userData = data.user;
          vpnData = data.vpn;
          if (browserBanner) {
            browserBanner.style.display = 'flex';
            if (browserBannerText) {
              browserBannerText.textContent = `🌐 Аккаунт: ${userData.username} (Demo)`;
            }
          }
          renderUI();
        } else {
          alert('Ошибка входа в демо: ' + (data.error || 'попробуйте позже'));
          btnLoginDemo.disabled = false;
        }
      } catch (e) {
        console.error('Demo login error:', e);
        btnLoginDemo.disabled = false;
      }
    };
  }
});

async function checkWebSession() {
  try {
    const res = await fetch('/api/user/profile/', {
      credentials: 'same-origin'
    });
    const data = await res.json();

    if (data.authenticated && data.success) {
      userData = data.user;
      vpnData = data.vpn;
      if (browserBanner) {
        browserBanner.style.display = 'flex';
        if (browserBannerText) {
          browserBannerText.textContent = `🌐 Сессия сайта: ${userData.username}`;
        }
      }
      renderUI();
    } else {
      // User is not authenticated in browser
      if (loadingView) loadingView.style.display = 'none';
      if (unauthView) unauthView.style.display = 'flex';
    }
  } catch (err) {
    console.error('Check web session error:', err);
    if (loadingView) loadingView.style.display = 'none';
    if (unauthView) unauthView.style.display = 'flex';
  }
}

function renderUI() {
  if (!userData || !vpnData) return;

  if (loadingView) loadingView.style.display = 'none';
  if (unauthView) unauthView.style.display = 'none';
  if (miniappView) miniappView.style.display = 'flex';

  document.getElementById('user-name').textContent = userData.username;
  document.getElementById('user-id').textContent = userData.telegram_id
    ? `TG ID: ${userData.telegram_id}`
    : `ID: ${userData.id}`;
  document.getElementById('user-balance').textContent = `${userData.balance} ₽`;
  document.getElementById('user-days').textContent = `на ${userData.days_left} дн.`;
  document.getElementById('user-avatar').textContent = (userData.username[0] || 'V').toUpperCase();

  document.getElementById('server-name').textContent = vpnData.server_name;
  document.getElementById('server-ping').textContent = `${vpnData.ping_ms} ms`;

  const btnIncy = document.getElementById('btn-incy');
  btnIncy.href = vpnData.connect_url || vpnData.incy_url;

  const powerBtn = document.getElementById('power-btn');
  powerBtn.onclick = () => {
    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('medium');
    window.location.href = vpnData.connect_url || vpnData.incy_url;
  };

  // Copy Buttons
  document.getElementById('btn-copy-vless').onclick = () => {
    navigator.clipboard.writeText(vpnData.vless_url);
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    showFeedback('Ключ VLESS скопирован!');
  };

  document.getElementById('btn-copy-sub').onclick = () => {
    navigator.clipboard.writeText(vpnData.sub_url);
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
    showFeedback('Ссылка подписки скопирована!');
  };

  // Whitelist Switch
  const wlSwitch = document.getElementById('whitelist-switch');
  if (vpnData.whitelist_enabled) {
    wlSwitch.classList.add('active');
  } else {
    wlSwitch.classList.remove('active');
  }

  wlSwitch.onclick = async () => {
    if (tg?.HapticFeedback) tg.HapticFeedback.selectionChanged();
    try {
      const res = await fetch('/api/vpn/toggle-whitelist/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          telegram_id: userData.telegram_id,
          user_id: userData.id
        })
      });
      const data = await res.json();
      if (data.success) {
        wlSwitch.classList.toggle('active', data.whitelist_enabled);
        vpnData.whitelist_enabled = data.whitelist_enabled;
        showFeedback(data.whitelist_enabled ? 'Белый список РФ включен' : 'Весь трафик через VPN');
      }
    } catch (e) {
      console.error('Toggle whitelist error:', e);
    }
  };

  // Share ref
  document.getElementById('btn-share-ref').onclick = () => {
    const text = `🔥 Попробуй быстрый VPN без блокировок для РФ и РБ! Получи бонус на баланс при регистрации: ${userData.referral_url}`;
    if (tg?.openTelegramLink) {
      tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(userData.referral_url)}&text=${encodeURIComponent(text)}`);
    } else {
      navigator.clipboard.writeText(userData.referral_url);
      showFeedback('Реферальная ссылка скопирована!');
    }
  };
}

function showFeedback(msg) {
  let toast = document.getElementById('toast-feedback');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast-feedback';
    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.left = '50%';
    toast.style.transform = 'translateX(-50%)';
    toast.style.background = 'rgba(16, 185, 129, 0.95)';
    toast.style.color = '#fff';
    toast.style.padding = '0.6rem 1.25rem';
    toast.style.borderRadius = '999px';
    toast.style.fontSize = '0.85rem';
    toast.style.fontWeight = '600';
    toast.style.zIndex = '9999';
    toast.style.boxShadow = '0 4px 15px rgba(0,0,0,0.4)';
    toast.style.transition = 'opacity 0.25s ease';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.opacity = '1';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.style.opacity = '0';
  }, 2200);
}

function showError(msg) {
  if (loadingView) {
    loadingView.style.display = 'block';
    loadingView.innerHTML = `<div style="color: #f87171; padding: 2rem;">⚠️ ${msg}</div>`;
  }
}
