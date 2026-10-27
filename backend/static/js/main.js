/**
 * VPN live-dev - LUXURY INTERACTIVE UX, 60FPS AMBIENT CANVAS & SERVER SWITCHER
 */

document.addEventListener('DOMContentLoaded', () => {
  initBackgroundCanvas();
  initPasswordToggles();
  initCopyButtons();
  initIncyDeeplinkFallback();
  initWhitelistToggle();
  initKeyRegeneration();
  initAutopayToggle();
  initServerSwitcher();
  initBuyTraffic();
  initCustomWhitelist();
  initPromoCode();
  initPaymentModal();
  initModals();
  initGuideTabs();
  initTelegramLink();
  initDevicesManagement();
});


// ==========================================
// 1. VIBRANT 60FPS LUMINOUS SNOWFLAKES & CYBER PARTICLES
// ==========================================
function initBackgroundCanvas() {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let width, height;
  let particles = [];
  const particleCount = 52;

  const mouse = { x: -1000, y: -1000, radius: 150 };

  window.addEventListener('mousemove', (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  });

  window.addEventListener('mouseleave', () => {
    mouse.x = -1000;
    mouse.y = -1000;
  });

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  window.addEventListener('resize', resize);
  resize();

  // Crisp snowflake / cyber aurora palette: Pure Diamond, Icy Cyan, Emerald Neon, Soft Violet
  const colorPalette = [
    '255, 255, 255', // Pure Crystalline White
    '224, 242, 254', // Frost White
    '56, 189, 248',  // Sky Cyan
    '52, 211, 153',  // Cyber Emerald
    '167, 139, 250', // Soft Lavender
  ];

  class Particle {
    constructor(initial = false) {
      this.reset(initial);
    }

    reset(initial = false) {
      this.x = Math.random() * width;
      this.y = initial ? Math.random() * height : -12;
      this.vy = Math.random() * 0.55 + 0.35; // gentle descent like snow
      this.vx = (Math.random() - 0.5) * 0.3; // subtle horizontal drift
      this.swayAngle = Math.random() * Math.PI * 2;
      this.swaySpeed = Math.random() * 0.02 + 0.008;
      this.swayRadius = Math.random() * 0.65 + 0.3;
      this.radius = Math.random() * 2.2 + 1.2;
      this.baseAlpha = Math.random() * 0.35 + 0.4; // clearly visible & radiant
      this.alpha = this.baseAlpha;
      this.twinkleSpeed = Math.random() * 0.03 + 0.012;
      this.twinkleAngle = Math.random() * Math.PI * 2;
      this.color = colorPalette[Math.floor(Math.random() * colorPalette.length)];
    }

    update() {
      this.swayAngle += this.swaySpeed;
      this.twinkleAngle += this.twinkleSpeed;
      this.x += this.vx + Math.sin(this.swayAngle) * this.swayRadius;
      this.y += this.vy;
      this.alpha = Math.max(0.25, Math.min(0.9, this.baseAlpha + Math.sin(this.twinkleAngle) * 0.22));

      // Interactive mouse reaction: gentle swirl / glide away
      const dx = mouse.x - this.x;
      const dy = mouse.y - this.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < mouse.radius) {
        const force = (mouse.radius - dist) / mouse.radius;
        this.x -= (dx / dist) * force * 2.2;
        this.y -= (dy / dist) * force * 2.2;
      }

      // Border wrapping
      if (this.y > height + 15) {
        this.reset(false);
      } else if (this.x < -15) {
        this.x = width + 10;
      } else if (this.x > width + 15) {
        this.x = -10;
      }
    }

    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${this.color}, ${this.alpha})`;
      ctx.shadowBlur = this.radius * 3.5;
      ctx.shadowColor = `rgba(${this.color}, 0.8)`;
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  for (let i = 0; i < particleCount; i++) {
    particles.push(new Particle(true));
  }

  function animate() {
    ctx.clearRect(0, 0, width, height);

    for (let i = 0; i < particles.length; i++) {
      particles[i].update();
      particles[i].draw();

      // Delicate cyber constellation threads between nearby flakes
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < 85) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          const opacity = 0.08 * (1 - dist / 85);
          ctx.strokeStyle = `rgba(255, 255, 255, ${opacity})`;
          ctx.lineWidth = 0.6;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(animate);
  }
  animate();
}

// ==========================================
// 2. PASSWORD TOGGLES
// ==========================================
function initPasswordToggles() {
  document.querySelectorAll('.input-password-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-target');
      const input = document.getElementById(targetId);
      if (!input) return;

      if (input.type === 'password') {
        input.type = 'text';
        btn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;
      } else {
        input.type = 'password';
        btn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
      }
    });
  });
}

// ==========================================
// 3. COPY BUTTONS & TOASTS
// ==========================================
function initCopyButtons() {
  document.querySelectorAll('[data-copy]').forEach(btn => {
    btn.addEventListener('click', () => {
      const textToCopy = btn.getAttribute('data-copy');
      if (!textToCopy) return;

      navigator.clipboard.writeText(textToCopy).then(() => {
        showToast('Скопировано в буфер обмена!');
        const originalHtml = btn.innerHTML;
        btn.innerHTML = `<span>✓ Скопировано</span>`;
        setTimeout(() => {
          btn.innerHTML = originalHtml;
        }, 1800);
      }).catch(err => {
        console.error('Copy failed:', err);
      });
    });
  });
}

function getAppStoreInfo() {
  const ua = navigator.userAgent || navigator.vendor || window.opera || '';
  const platform = navigator.platform || '';

  // 1. Apple Mac
  if (/Macintosh|Mac OS X/i.test(ua) && !(/iPad|iPhone|iPod/.test(ua)) && !(platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
    return {
      platform: 'mac',
      storeName: 'Mac App Store',
      storeUrl: 'https://apps.apple.com/app/incy/id6756943388',
      selector: '.btn-store-mac'
    };
  }

  // 2. iOS (iPhone, iPad, iPod)
  if (/iPad|iPhone|iPod/.test(ua) || (platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
    return {
      platform: 'ios',
      storeName: 'App Store (iOS)',
      storeUrl: 'https://apps.apple.com/app/incy/id6756943388',
      selector: '.btn-store-ios'
    };
  }

  // 3. Android
  if (/android/i.test(ua)) {
    return {
      platform: 'android',
      storeName: 'Google Play',
      storeUrl: 'https://play.google.com/store/apps/details?id=llc.itdev.incy',
      selector: '.btn-store-android'
    };
  }

  // 4. Windows / Linux / other PC
  return {
    platform: 'windows',
    storeName: 'Windows (setup.exe)',
    storeUrl: 'https://github.com/INCY-DEV/incy-platforms/releases/download/latest/incy-windows-setup.exe',
    selector: '.btn-store-windows'
  };
}

function highlightUserPlatformInModal() {
  const store = getAppStoreInfo();
  const targetBtn = document.querySelector(store.selector);
  if (targetBtn && !targetBtn.dataset.tagged) {
    targetBtn.dataset.tagged = 'true';
    targetBtn.classList.add('store-btn-active');
    const tag = document.createElement('span');
    tag.textContent = ' (ваше)';
    tag.style.color = '#34d399';
    tag.style.fontWeight = '800';
    tag.style.fontSize = '0.72rem';
    tag.style.marginLeft = '4px';
    targetBtn.appendChild(tag);
  }
}

function getIncyDownloadInfo() {
  const ua = navigator.userAgent || navigator.vendor || window.opera || '';
  const platform = navigator.platform || '';

  // 1. Apple Mac (macOS) -> Mac App Store
  if (/Macintosh|Mac OS X/i.test(ua) && !(/iPad|iPhone|iPod/.test(ua)) && !(platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
    return {
      name: 'Mac (macOS)',
      url: 'https://apps.apple.com/app/incy/id6756943388',
      icon: '🍎',
      storeName: 'App Store'
    };
  }

  // 2. Apple iPhone / iPad -> App Store
  if (/iPad|iPhone|iPod/.test(ua) || (platform === 'MacIntel' && navigator.maxTouchPoints > 1)) {
    return {
      name: 'iPhone / iPad',
      url: 'https://apps.apple.com/app/incy/id6756943388',
      icon: '🍏',
      storeName: 'App Store'
    };
  }

  // 3. Android -> Google Play
  if (/android/i.test(ua)) {
    return {
      name: 'Android',
      url: 'https://play.google.com/store/apps/details?id=llc.itdev.incy',
      icon: '🤖',
      storeName: 'Google Play'
    };
  }

  // 4. Windows -> Direct setup.exe download
  if (/Windows/i.test(ua)) {
    return {
      name: 'Windows',
      url: 'https://github.com/INCY-DEV/incy-platforms/releases/download/latest/incy-windows-setup.exe',
      icon: '💻',
      storeName: 'setup.exe'
    };
  }

  return {
    name: 'Компьютер',
    url: 'https://github.com/INCY-DEV/incy-platforms/releases/download/latest/incy-windows-setup.exe',
    icon: '💻',
    storeName: 'Скачать INCY'
  };
}

function showDownloadModal(downloadInfo) {
  let modal = document.getElementById('app-not-installed-modal');
  if (modal) {
    try { modal.remove(); } catch (_) {}
  }
  modal = document.createElement('div');
  modal.className = 'modal-overlay active';
  modal.id = 'app-not-installed-modal';
  modal.style.zIndex = '99999';
  modal.innerHTML = `
    <div class="modal-body" style="max-width: 440px; text-align: center; border: 1px solid rgba(16, 185, 129, 0.4); box-shadow: 0 10px 40px rgba(0,0,0,0.8); background: rgba(18, 22, 34, 0.98); border-radius: 1.25rem; padding: 2rem 1.5rem;">
      <div style="width: 64px; height: 64px; margin: 0 auto 1rem; border-radius: 50%; background: rgba(56, 189, 248, 0.15); border: 2px solid rgba(56, 189, 248, 0.4); display: flex; align-items: center; justify-content: center; font-size: 2rem;">
        ${downloadInfo.icon || '📲'}
      </div>
      <h3 style="color: #fff; font-size: 1.25rem; font-weight: 800; margin-bottom: 0.5rem;">
        Приложение INCY ещё не установлено
      </h3>
      <p style="color: var(--text-muted); font-size: 0.85rem; line-height: 1.5; margin-bottom: 1.25rem;">
        Для подключения установите бесплатное приложение INCY в <strong>${downloadInfo.storeName || downloadInfo.name}</strong>.
      </p>
      <a href="${downloadInfo.url}" target="_blank" rel="noopener noreferrer" class="btn btn-primary btn-block" style="font-size: 0.95rem; font-weight: 700; padding: 0.85rem; justify-content: center; margin-bottom: 0.85rem; text-decoration: none; width: 100%;">
        📥 Открыть ${downloadInfo.storeName || downloadInfo.name}
      </a>
      <div style="background: rgba(16, 185, 129, 0.1); border-radius: 8px; padding: 0.6rem; font-size: 0.78rem; color: #34d399; margin-bottom: 1rem; line-height: 1.4;">
        ✓ Ключ уже скопирован в буфер!<br>После установки вернитесь сюда и нажмите <strong>«Подключить»</strong> ещё раз.
      </div>
      <button type="button" class="btn btn-secondary btn-block modal-close" style="font-size: 0.82rem; width: 100%;">Понятно, закрыть</button>
    </div>
  `;
  document.body.appendChild(modal);

  modal.querySelector('.modal-close').addEventListener('click', () => {
    modal.classList.remove('active');
  });
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.classList.remove('active');
  });
}

function initIncyDeeplinkFallback() {
  document.querySelectorAll('a[href^="incy://"], a[href^="vless://"], .btn-smart-connect, #btn-incy-connect').forEach(link => {
    link.addEventListener('click', (e) => {
      // Блокируем стандартную навигацию текущей страницы
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }

      const deeplinkUrl = link.getAttribute('data-connect-url') || link.getAttribute('href');
      if (!deeplinkUrl) return;

      const isSub = deeplinkUrl.startsWith('incy://');
      const vlessBtn = document.getElementById('btn-copy-vless') || document.querySelector('[data-copy^="vless://"]');
      const subBtn = document.querySelector('[data-copy*="/sub/"]');
      
      const copyVal = isSub 
        ? (subBtn ? subBtn.getAttribute('data-copy') : '') 
        : (vlessBtn ? vlessBtn.getAttribute('data-copy') : deeplinkUrl);

      // 1. Копируем ключ в буфер обмена сразу
      if (copyVal && navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(copyVal).catch(() => {});
      }

      const downloadInfo = getIncyDownloadInfo();
      let appLaunched = false;

      // Отслеживаем, открылось ли приложение (потеря фокуса / скрытие вкладки)
      const onBlur = () => {
        appLaunched = true;
      };
      const onVisibility = () => {
        if (document.hidden) {
          appLaunched = true;
        }
      };

      window.addEventListener('blur', onBlur, { once: true });
      document.addEventListener('visibilitychange', onVisibility, { once: true });

      showToast('Запускаем приложение INCY...');

      // 2. Пытаемся запустить приложение через протокол (vless:// или incy://)
      const tempA = document.createElement('a');
      tempA.href = deeplinkUrl;
      tempA.style.display = 'none';
      document.body.appendChild(tempA);
      tempA.click();
      setTimeout(() => { try { tempA.remove(); } catch (_) {} }, 2000);

      // 3. Проверка через 1400 мс: открылось ли приложение?
      setTimeout(() => {
        window.removeEventListener('blur', onBlur);
        document.removeEventListener('visibilitychange', onVisibility);

        // Если окно браузера осталось на месте и не теряло фокус -> приложения НЕТ на устройстве!
        if (!appLaunched && !document.hidden) {
          showToast(`⚠️ INCY не найдено. Открываем скачивание для ${downloadInfo.name}...`);
          
          // Открываем вкладку скачивания в НОВОЙ вкладке (текущая страница никуда не уходит)
          try {
            window.open(downloadInfo.url, '_blank');
          } catch (_) {}
          
          // Показываем понятную модалку со ссылкой на скачивание
          showDownloadModal(downloadInfo);
        } else {
          // Приложение установлено и открылось!
          showToast('✓ Приложение INCY запущено! Сервер добавлен автоматически');
        }
      }, 1400);
    });
  });
}

function showToast(message) {
  let toast = document.getElementById('toast-notification');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast-notification';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.classList.remove('show');
  }, 2400);
}

// ==========================================
// 4. RUSSIAN WHITELIST TOGGLE AJAX
// ==========================================
function initWhitelistToggle() {
  const toggle = document.getElementById('whitelist-toggle');
  if (!toggle) return;

  toggle.addEventListener('change', async () => {
    const isChecked = toggle.checked;
    const badge = document.getElementById('whitelist-badge');

    try {
      const res = await fetch('/api/vpn/toggle-whitelist/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        credentials: 'same-origin',
        body: JSON.stringify({})
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.whitelist_enabled ? '✓ Белый список РФ включен' : '✕ Весь трафик направлен через VPN');
        if (badge) {
          if (data.whitelist_enabled) {
            badge.className = 'status-pill pill-active';
            badge.textContent = '✓ Белый список включен (РФ напрямую)';
          } else {
            badge.className = 'status-pill pill-amber';
            badge.textContent = '✕ Выключен (весь трафик через VPN)';
          }
        }
      }
    } catch (e) {
      console.error('Whitelist toggle error:', e);
      showToast('Ошибка при переключении белого списка');
      toggle.checked = !isChecked;
    }
  });
}

// ==========================================
// 5. AUTOPAY TOGGLE AJAX
// ==========================================
function initAutopayToggle() {
  const toggle = document.getElementById('autopay-toggle');
  if (!toggle) return;

  toggle.addEventListener('change', async () => {
    const isChecked = toggle.checked;
    try {
      const res = await fetch('/billing/toggle-autopay/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCookie('csrftoken'),
          'Content-Type': 'application/json'
        }
      });
      const data = await res.json();
      if (data.success) {
        showToast(isChecked ? 'Автопродление включено' : 'Автопродление выключено');
      }
    } catch (e) {
      showToast('Ошибка при изменении автопродления');
      toggle.checked = !isChecked;
    }
  });
}

// ==========================================
// 6. DYNAMIC SERVER SWITCHER AJAX
// ==========================================
function initServerSwitcher() {
  const container = document.getElementById('server-list-container');
  if (!container) return;

  container.addEventListener('click', async (e) => {
    const card = e.target.closest('.server-item-card, .btn-switch-server');
    if (!card) return;

    const serverId = card.getAttribute('data-server-id');
    if (!serverId) return;

    try {
      const res = await fetch('/api/vpn/switch-server/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        credentials: 'same-origin',
        body: JSON.stringify({ server_id: serverId })
      });
      const data = await res.json();
      if (data.success) {
        // Update hero elements
        const flagElem = document.getElementById('current-server-flag');
        if (flagElem) flagElem.textContent = data.vpn.flag;

        const nameElem = document.getElementById('current-server-name');
        if (nameElem) nameElem.textContent = data.vpn.clean_name;

        const pingElem = document.getElementById('current-server-ping');
        if (pingElem) pingElem.textContent = data.vpn.ping_ms + ' ms';

        // Update links & copy attributes
        const incyBtn = document.getElementById('btn-incy-connect');
        if (incyBtn) {
          const newUrl = data.vpn.vless_url || data.vpn.connect_url;
          incyBtn.setAttribute('data-connect-url', newUrl);
          if (incyBtn.tagName === 'A') incyBtn.href = newUrl;
        }

        const vlessBtn = document.getElementById('btn-copy-vless');
        if (vlessBtn) vlessBtn.setAttribute('data-copy', data.vpn.vless_url);

        const qrImg = document.getElementById('qr-code-img');
        if (qrImg) qrImg.src = data.vpn.qr_url + '?t=' + Date.now();

        // Update selected state in modal cards
        document.querySelectorAll('.server-item-card').forEach(c => {
          const isSelected = c.getAttribute('data-server-id') === String(serverId);
          c.classList.toggle('selected', isSelected);
          const rightCol = c.querySelector('div:last-child');
          if (rightCol) {
            const pingText = `<div style="font-size: 0.85rem; font-weight: 700; color: #34d399;">${c.querySelector('[style*="ms"]')?.textContent || ''}</div>`;
            if (isSelected) {
              rightCol.innerHTML = `${pingText}<span class="status-pill pill-active" style="padding: 0.25rem 0.65rem; font-size: 0.75rem;">✓ Активен</span>`;
            } else {
              rightCol.innerHTML = `${pingText}<button type="button" class="btn btn-secondary btn-switch-server" data-server-id="${c.getAttribute('data-server-id')}" style="padding: 0.35rem 0.85rem; font-size: 0.75rem;">Выбрать</button>`;
            }
          }
        });

        showToast(`Сервер переключен на ${data.vpn.server_name}!`);

        // Close modal after 400ms
        setTimeout(() => {
          const modal = document.getElementById('server-modal');
          if (modal) modal.classList.remove('active');
        }, 400);
      }
    } catch (err) {
      console.error('Server switch error:', err);
      showToast('Ошибка при переключении сервера');
    }
  });
}

// ==========================================
// 6.1 DEVICES MANAGEMENT & RESET SLOTS
// ==========================================
function initDevicesManagement() {
  const btnReset = document.getElementById('btn-reset-devices');
  if (btnReset) {
    btnReset.addEventListener('click', async () => {
      if (!confirm('Вы уверены, что хотите сбросить все привязанные устройства и освободить 5 слотов?')) {
        return;
      }

      try {
        btnReset.disabled = true;
        btnReset.textContent = 'Сбрасываем...';
        const res = await fetch('/api/vpn/devices/reset/', {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
          }
        });
        const data = await res.json();
        if (data.success) {
          showToast('✓ Все устройства сброшены! Все 5 слотов свободны.');
          setTimeout(() => window.location.reload(), 800);
        } else {
          showToast('⚠️ ' + (data.error || 'Не удалось сбросить устройства'));
          btnReset.disabled = false;
          btnReset.textContent = '🗑️ Сбросить все устройства';
        }
      } catch (err) {
        console.error('Reset devices error:', err);
        showToast('⚠️ Ошибка соединения с сервером');
        btnReset.disabled = false;
        btnReset.textContent = '🗑️ Сбросить все устройства';
      }
    });
  }

  // Individual device deletion
  document.querySelectorAll('.btn-delete-device').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const devId = btn.getAttribute('data-device-id');
      const devName = btn.getAttribute('data-device-name') || 'устройство';
      if (!confirm(`Удалить «${devName}» из привязанных устройств? Слот будет немедленно освобожден.`)) {
        return;
      }

      btn.disabled = true;
      const originalText = btn.innerHTML;
      btn.innerHTML = '<span>⏳</span> <span style="font-size: 0.72rem;">Удаляем...</span>';

      try {
        const res = await fetch('/api/vpn/devices/delete/', {
          method: 'POST',
          headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ device_id: devId })
        });
        const data = await res.json();
        if (data.success) {
          showToast('✓ Устройство удалено! Слот освобожден.');
          const row = btn.closest('.device-card-row');
          if (row) {
            row.style.opacity = '0.3';
            row.style.pointerEvents = 'none';
          }
          setTimeout(() => window.location.reload(), 700);
        } else {
          showToast('⚠️ ' + (data.error || 'Не удалось удалить устройство'));
          btn.disabled = false;
          btn.innerHTML = originalText;
        }
      } catch (err) {
        console.error('Delete device error:', err);
        showToast('⚠️ Ошибка соединения с сервером');
        btn.disabled = false;
        btn.innerHTML = originalText;
      }
    });
  });
}

// ==========================================
// 7. REGENERATE VPN KEY
// ==========================================
function initKeyRegeneration() {
  const regenBtn = document.getElementById('btn-regenerate-key');
  if (!regenBtn) return;

  regenBtn.addEventListener('click', async () => {
    if (!confirm('Вы уверены, что хотите обновить ключ? Старый ключ перестанет работать на ваших устройствах.')) {
      return;
    }

    try {
      const res = await fetch('/vpn/regenerate-key/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCookie('csrftoken'),
          'Content-Type': 'application/json'
        }
      });
      const data = await res.json();
      if (data.success) {
        showToast('Ключ успешно обновлен!');
        const incyBtn = document.getElementById('btn-incy-connect');
        if (incyBtn) {
          const newUrl = data.vless_url || data.connect_url;
          incyBtn.setAttribute('data-connect-url', newUrl);
          if (incyBtn.tagName === 'A') incyBtn.href = newUrl;
        }

        const copyBtn = document.getElementById('btn-copy-vless');
        if (copyBtn) copyBtn.setAttribute('data-copy', data.vless_url);

        const qrImg = document.getElementById('qr-code-img');
        if (qrImg) qrImg.src = data.qr_url + '?t=' + Date.now();
      }
    } catch (e) {
      showToast('Ошибка при обновлении ключа');
    }
  });
}

// ==========================================
// 8. BUY TURBO TRAFFIC AJAX (+50 GB)
// ==========================================
function initBuyTraffic() {
  const btnTurbo = document.getElementById('btn-buy-turbo');
  if (!btnTurbo) return;

  btnTurbo.addEventListener('click', async () => {
    btnTurbo.disabled = true;
    const originalText = btnTurbo.innerHTML;
    btnTurbo.innerHTML = '<span>Обработка покупки...</span>';

    try {
      const res = await fetch('/api/vpn/buy-traffic/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        credentials: 'same-origin',
        body: JSON.stringify({})
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message || 'Добавлено +50 ГБ скоростного трафика!');
        
        // Update DOM elements
        const usedElem = document.getElementById('traffic-used-val');
        if (usedElem) usedElem.textContent = data.traffic.used_gb;

        const limitElem = document.getElementById('traffic-limit-val');
        if (limitElem) limitElem.textContent = data.traffic.limit_gb;

        const leftElem = document.getElementById('traffic-left-val');
        if (leftElem) leftElem.textContent = data.traffic.left_gb + ' ГБ';

        const percentElem = document.getElementById('traffic-percent-val');
        if (percentElem) percentElem.textContent = data.traffic.percent;

        const barElem = document.getElementById('traffic-progress-bar');
        if (barElem) barElem.style.width = data.traffic.percent + '%';

        const speedBadge = document.getElementById('speed-indicator-badge');
        if (speedBadge) {
          speedBadge.className = 'status-pill pill-cyan';
          speedBadge.textContent = '⚡ ' + data.traffic.current_speed;
        }

        // Update user balance in header if present
        const balanceHeader = document.querySelector('.header-nav a[href*="tariffs"]');
        if (balanceHeader) {
          balanceHeader.innerHTML = `<span style="color: var(--accent-emerald); font-weight: 700;">💳 ${data.user.balance} ₽</span>`;
        }
      } else {
        showToast(data.error || 'Ошибка при покупке');
      }
    } catch (e) {
      console.error('Buy traffic error:', e);
      showToast('Ошибка сети');
    } finally {
      btnTurbo.disabled = false;
      btnTurbo.innerHTML = originalText;
    }
  });
}

// ==========================================
// 8.5. CUSTOM WHITELIST (USER DOMAINS)
// ==========================================
function initCustomWhitelist() {
  const saveBtn = document.getElementById('save-custom-whitelist-btn');
  const textarea = document.getElementById('custom-whitelist-input');
  if (!saveBtn || !textarea) return;

  const btnBy = document.getElementById('preset-add-by');
  const btnRu = document.getElementById('preset-add-ru');
  const btnClear = document.getElementById('preset-clear-whitelist');

  if (btnBy) {
    btnBy.addEventListener('click', () => {
      const cur = textarea.value.trim();
      const byRule = '*.by';
      if (!cur.includes(byRule)) {
        textarea.value = cur ? cur + '\n' + byRule : byRule;
        showToast('✓ Добавлено правило *.by в список');
      }
    });
  }

  if (btnRu) {
    btnRu.addEventListener('click', () => {
      const cur = textarea.value.trim();
      const ruRules = '*.ru\n*.рф\n*.su';
      if (!cur.includes('*.ru')) {
        textarea.value = cur ? cur + '\n' + ruRules : ruRules;
        showToast('✓ Добавлены правила *.ru, *.рф в список');
      }
    });
  }

  if (btnClear) {
    btnClear.addEventListener('click', () => {
      textarea.value = '';
      showToast('Список очищен (нажмите «Сохранить»)');
    });
  }

  saveBtn.addEventListener('click', async () => {
    const domains = textarea.value;
    saveBtn.disabled = true;
    const oldText = saveBtn.textContent;
    saveBtn.textContent = 'Сохранение...';

    try {
      const res = await fetch('/api/vpn/custom-whitelist/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        credentials: 'same-origin',
        body: JSON.stringify({ domains: domains })
      });
      const data = await res.json();
      if (data.success) {
        showToast('✓ Список исключений обновлен!');
        const countSpan = document.getElementById('custom-whitelist-count');
        if (countSpan) {
          countSpan.textContent = `${data.custom_domains.length} сайтов`;
        }
        const modal = document.getElementById('custom-whitelist-modal');
        if (modal) modal.classList.remove('active');
      } else {
        showToast(data.error || 'Ошибка сохранения');
      }
    } catch (e) {
      console.error('Save custom whitelist error:', e);
      showToast('Ошибка сети');
    } finally {
      saveBtn.disabled = false;
      saveBtn.textContent = oldText;
    }
  });
}

// ==========================================
// 8.6. PROMO CODE ACTIVATION
// ==========================================
function initPromoCode() {
  const btn = document.getElementById('btn-activate-promo');
  const input = document.getElementById('promo-code-input');
  if (!btn || !input) return;

  btn.addEventListener('click', async () => {
    const code = input.value.trim();
    if (!code) {
      showToast('Введите промокод');
      return;
    }

    btn.disabled = true;
    const oldText = btn.textContent;
    btn.textContent = '...';

    try {
      const res = await fetch('/billing/promo/activate/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        credentials: 'same-origin',
        body: JSON.stringify({ code: code })
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message);
        input.value = '';
        const balEl = document.querySelector('.balance-value');
        if (balEl && data.new_balance !== undefined) {
          balEl.innerHTML = `${data.new_balance.toFixed(2)} <span class="balance-currency">₽</span>`;
        }
      } else {
        showToast(data.error || 'Ошибка активации');
      }
    } catch (e) {
      console.error(e);
      showToast('Ошибка сети');
    } finally {
      btn.disabled = false;
      btn.textContent = oldText;
    }
  });
}

// ==========================================
// 8.7. DYNAMIC CHECKOUT MODAL (YOOKASSA & BEPAID)
// ==========================================
function initPaymentModal() {
  const payModal = document.getElementById('pay-modal');
  if (!payModal) return;

  let selectedPkgId = null;
  let selectedMethod = 'yookassa';
  let priceRub = '105';
  let priceByn = '5.00';

  const updateSubmitButton = () => {
    const btn = document.getElementById('btn-submit-pay');
    if (!btn) return;
    if (selectedMethod === 'bepaid') {
      btn.textContent = `🇧🇾 Оплатить ${priceByn} BYN через bePaid`;
    } else {
      btn.textContent = `🇷🇺 Оплатить ${priceRub} ₽ через ЮKassa`;
    }
  };

  // Pre-select initial package
  const firstPkg = payModal.querySelector('.package-select-card.selected') || payModal.querySelector('.package-select-card');
  if (firstPkg) {
    firstPkg.classList.add('selected');
    selectedPkgId = firstPkg.getAttribute('data-pkg-id');
    priceRub = firstPkg.getAttribute('data-price-rub') || '105';
    priceByn = firstPkg.getAttribute('data-price-byn') || '5.00';
    updateSubmitButton();
  }

  // Package select cards click
  payModal.querySelectorAll('.package-select-card').forEach(card => {
    card.addEventListener('click', () => {
      payModal.querySelectorAll('.package-select-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      selectedPkgId = card.getAttribute('data-pkg-id');
      priceRub = card.getAttribute('data-price-rub') || '105';
      priceByn = card.getAttribute('data-price-byn') || '5.00';
      updateSubmitButton();
    });
  });

  // Method select tabs click
  payModal.querySelectorAll('.pay-method-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      payModal.querySelectorAll('.pay-method-tab').forEach(t => t.classList.remove('selected'));
      tab.classList.add('selected');
      selectedMethod = tab.getAttribute('data-method') || 'yookassa';
      updateSubmitButton();
    });
  });

  // Quick buttons on dashboard
  const ruBtn = document.getElementById('btn-yookassa-pay');
  if (ruBtn) {
    ruBtn.addEventListener('click', (e) => {
      e.preventDefault();
      selectedMethod = 'yookassa';
      payModal.querySelectorAll('.pay-method-tab').forEach(t => {
        t.classList.toggle('selected', t.getAttribute('data-method') === 'yookassa');
      });
      updateSubmitButton();
      payModal.classList.add('active');
    });
  }

  const byBtn = document.getElementById('btn-bepaid-pay');
  if (byBtn) {
    byBtn.addEventListener('click', (e) => {
      e.preventDefault();
      selectedMethod = 'bepaid';
      payModal.querySelectorAll('.pay-method-tab').forEach(t => {
        t.classList.toggle('selected', t.getAttribute('data-method') === 'bepaid');
      });
      updateSubmitButton();
      payModal.classList.add('active');
    });
  }

  // Submit payment
  const submitBtn = document.getElementById('btn-submit-pay');
  if (submitBtn) {
    submitBtn.addEventListener('click', async () => {
      submitBtn.disabled = true;
      const oldText = submitBtn.textContent;
      submitBtn.textContent = 'Создание безопасного платежа...';

      const endpoint = selectedMethod === 'bepaid' 
        ? '/billing/bepaid/checkout/' 
        : '/billing/yookassa/create/';

      const payload = {
        package_id: selectedPkgId,
        payment_method: 'sbp'
      };

      try {
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken'),
            'Accept': 'application/json'
          },
          credentials: 'same-origin',
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success && data.checkout_url) {
          window.location.href = data.checkout_url;
        } else {
          showToast(data.error || 'Ошибка создания платежа');
          submitBtn.disabled = false;
          submitBtn.textContent = oldText;
        }
      } catch (e) {
        console.error('Payment checkout error:', e);
        showToast('Ошибка соединения');
        submitBtn.disabled = false;
        submitBtn.textContent = oldText;
      }
    });
  }
}

// ==========================================
// 9. MODALS
// ==========================================
function initModals() {
  document.querySelectorAll('[data-modal-target]').forEach(trigger => {
    trigger.addEventListener('click', () => {

      const targetId = trigger.getAttribute('data-modal-target');
      const modal = document.getElementById(targetId);
      if (modal) {
        modal.classList.add('active');
        if (targetId === 'connect-modal') {
          highlightUserPlatformInModal();
        }
      }
    });
  });

  document.querySelectorAll('.modal-close, .modal-overlay').forEach(closeBtn => {
    closeBtn.addEventListener('click', (e) => {
      if (e.target === closeBtn || closeBtn.classList.contains('modal-close')) {
        const modal = closeBtn.closest('.modal-overlay');
        if (modal) modal.classList.remove('active');
      }
    });
  });
}

// ==========================================
// 10. SETUP GUIDE TABS
// ==========================================
function initGuideTabs() {
  const tabs = document.querySelectorAll('.btn-guide-tab');
  const panes = document.querySelectorAll('.guide-tab-pane');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const targetId = tab.getAttribute('data-guide-target');

      tabs.forEach(t => {
        t.classList.remove('active');
        t.style.background = 'transparent';
        t.style.color = 'var(--text-muted)';
        t.style.fontWeight = '600';
      });

      tab.classList.add('active');
      tab.style.background = 'rgba(255, 255, 255, 0.12)';
      tab.style.color = '#fff';
      tab.style.fontWeight = '700';

      panes.forEach(p => {
        p.style.display = 'none';
        p.classList.remove('active');
      });

      const activePane = document.getElementById(targetId);
      if (activePane) {
        activePane.style.display = 'block';
        activePane.classList.add('active');
      }
    });
  });
}

// Helper: Get CSRF token
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Telegram Link (+2 days bonus & Account Unification)
function initTelegramLink() {
  const btn = document.getElementById('btn-link-telegram');
  const container = document.getElementById('telegram-link-actions');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.innerHTML = '<span>⚡ Подготовка ссылки...</span>';

    try {
      const res = await fetch('/auth/telegram-link-code/');
      const data = await res.json();
      if (data.success && data.bot_url) {
        // Try popup / new tab
        window.open(data.bot_url, '_blank');

        // Provide clickable button in container so even if browser blocked popup, user has 100% guarantee
        if (container) {
          container.innerHTML = `
            <a href="${data.bot_url}" target="_blank" class="btn btn-primary" style="background: linear-gradient(135deg, #0284c7, #38bdf8); border: none; padding: 0.65rem 1.25rem; font-size: 0.88rem; text-decoration: none; display: inline-flex; align-items: center; gap: 0.5rem; box-shadow: 0 0 20px rgba(56, 189, 248, 0.35); border-radius: 0.75rem;">
              <span>👉 Открыть бота @${data.bot_username || 'live_vpn_bot'}</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="5" y1="12" x2="19" y2="12"/>
                <polyline points="12 5 19 12 12 19"/>
              </svg>
            </a>
            <div style="font-size: 0.74rem; color: #38bdf8; margin-top: 0.35rem; text-align: right;">
              Или команда в боте: <code style="background: rgba(56, 189, 248, 0.15); padding: 0.15rem 0.4rem; border-radius: 4px;">/link ${data.code}</code>
            </div>
          `;
        } else {
          btn.innerHTML = '<span>⏳ Ожидание подтверждения в боте...</span>';
        }

        showToast('Открываем Telegram! Нажмите «Запустить» в боте для завершения объединения.');

        // Active Polling: Check every 2s if Telegram account has linked
        let pollCount = 0;
        const pollInterval = setInterval(async () => {
          pollCount++;
          if (pollCount > 60) {
            clearInterval(pollInterval);
            return;
          }
          try {
            const pRes = await fetch('/api/user/profile/');
            const pData = await pRes.json();
            if (pData.success && pData.user && pData.user.telegram_id) {
              clearInterval(pollInterval);
              showToast('🎉 Telegram успешно привязан! Аккаунты объединены.');
              setTimeout(() => {
                window.location.reload();
              }, 1200);
            }
          } catch (e) {
            // silent ignore during poll
          }
        }, 2000);

      } else {
        showToast(data.error || 'Ошибка создания ссылки привязки');
        btn.disabled = false;
        btn.innerHTML = '<span>⚡ Забрать +2 дня в Telegram</span>';
      }
    } catch (e) {
      console.error('Error generating link code:', e);
      showToast('Ошибка сети');
      btn.disabled = false;
      btn.innerHTML = '<span>⚡ Забрать +2 дня в Telegram</span>';
    }
  });
}
