/**
 * VPN LIVE DEV - SENIOR INTERACTIVE UX & MICRO-ANIMATIONS
 */

document.addEventListener('DOMContentLoaded', () => {
  initBackgroundCanvas();
  initPasswordToggles();
  initCopyButtons();
  initWhitelistToggle();
  initKeyRegeneration();
  initAutopayToggle();
  initModals();
});

// ==========================================
// 1. LIGHTWEIGHT 60FPS AMBIENT CANVAS
// ==========================================
function initBackgroundCanvas() {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let width, height;
  let particles = [];
  const particleCount = 28;

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  window.addEventListener('resize', resize);
  resize();

  class Particle {
    constructor() {
      this.reset();
    }
    reset() {
      this.x = Math.random() * width;
      this.y = Math.random() * height;
      this.vx = (Math.random() - 0.5) * 0.4;
      this.vy = (Math.random() - 0.5) * 0.4;
      this.radius = Math.random() * 2 + 1;
      this.alpha = Math.random() * 0.3 + 0.1;
      this.color = Math.random() > 0.5 ? '16, 185, 129' : '99, 102, 241';
    }
    update() {
      this.x += this.vx;
      this.y += this.vy;
      if (this.x < 0 || this.x > width || this.y < 0 || this.y > height) {
        this.reset();
      }
    }
    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(${this.color}, ${this.alpha})`;
      ctx.fill();
    }
  }

  for (let i = 0; i < particleCount; i++) {
    particles.push(new Particle());
  }

  function animate() {
    ctx.clearRect(0, 0, width, height);

    // Subtle gradient glow in corners
    const grad1 = ctx.createRadialGradient(0, 0, 10, 0, 0, width * 0.7);
    grad1.addColorStop(0, 'rgba(16, 185, 129, 0.04)');
    grad1.addColorStop(1, 'transparent');
    ctx.fillStyle = grad1;
    ctx.fillRect(0, 0, width, height);

    const grad2 = ctx.createRadialGradient(width, height, 10, width, height, width * 0.7);
    grad2.addColorStop(0, 'rgba(99, 102, 241, 0.05)');
    grad2.addColorStop(1, 'transparent');
    ctx.fillStyle = grad2;
    ctx.fillRect(0, 0, width, height);

    // Particles and connections
    for (let i = 0; i < particles.length; i++) {
      particles[i].update();
      particles[i].draw();

      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.strokeStyle = `rgba(255, 255, 255, ${0.03 * (1 - dist / 120)})`;
          ctx.stroke();
        }
      }
    }
    requestAnimationFrame(animate);
  }
  animate();
}

// ==========================================
// 2. PASSWORD VISIBILITY TOGGLE
// ==========================================
function initPasswordToggles() {
  document.querySelectorAll('.input-password-toggle').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = btn.getAttribute('data-target');
      const input = document.getElementById(targetId);
      if (input) {
        if (input.type === 'password') {
          input.type = 'text';
          btn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
              <line x1="1" y1="1" x2="23" y2="23"/>
            </svg>`;
        } else {
          input.type = 'password';
          btn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
              <circle cx="12" cy="12" r="3"/>
            </svg>`;
        }
      }
    });
  });
}

// ==========================================
// 3. COPY TO CLIPBOARD WITH TOAST
// ==========================================
function initCopyButtons() {
  document.querySelectorAll('[data-copy]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const textToCopy = btn.getAttribute('data-copy');
      if (!textToCopy) return;

      try {
        await navigator.clipboard.writeText(textToCopy);
        showToast('Скопировано в буфер обмена! 🚀');
        
        const originalText = btn.innerHTML;
        btn.innerHTML = `
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          Скопировано!
        `;
        setTimeout(() => {
          btn.innerHTML = originalText;
        }, 2000);
      } catch (err) {
        showToast('Не удалось скопировать', 'error');
      }
    });
  });
}

// ==========================================
// 4. TOAST NOTIFICATIONS
// ==========================================
function showToast(message, type = 'success') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      z-index: 9999;
      display: flex;
      flex-direction: column;
      gap: 10px;
    `;
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  const bg = type === 'success' ? 'rgba(16, 185, 129, 0.95)' : 'rgba(239, 68, 68, 0.95)';
  toast.style.cssText = `
    background: ${bg};
    color: #fff;
    padding: 12px 20px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 600;
    box-shadow: 0 10px 25px rgba(0,0,0,0.4);
    backdrop-filter: blur(8px);
    transition: all 0.3s ease;
    transform: translateY(20px);
    opacity: 0;
  `;
  toast.innerText = message;
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.style.transform = 'translateY(0)';
    toast.style.opacity = '1';
  });

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(20px)';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ==========================================
// 5. WHITELIST TOGGLE AJAX
// ==========================================
function initWhitelistToggle() {
  const toggle = document.getElementById('whitelist-toggle');
  if (!toggle) return;

  toggle.addEventListener('change', async () => {
    const isChecked = toggle.checked;
    const csrfToken = getCookie('csrftoken');
    const badge = document.getElementById('whitelist-badge');

    try {
      const res = await fetch('/vpn/toggle-whitelist/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
          'Content-Type': 'application/json'
        }
      });
      const data = await res.json();
      if (data.success) {
        showToast(isChecked ? 'Белый список РФ включен' : 'Весь трафик направлен через VPN');
        if (badge) {
          badge.textContent = isChecked ? 'Активен (РФ напрямую)' : 'Выключен (все через VPN)';
          badge.className = isChecked ? 'status-pill' : 'status-pill text-muted';
        }
      }
    } catch (e) {
      showToast('Ошибка при переключении', 'error');
      toggle.checked = !isChecked;
    }
  });
}

// ==========================================
// 5.1. AUTOPAY TOGGLE AJAX
// ==========================================
function initAutopayToggle() {
  const toggle = document.getElementById('autopay-toggle');
  if (!toggle) return;

  toggle.addEventListener('change', async () => {
    const isChecked = toggle.checked;
    const csrfToken = getCookie('csrftoken');

    try {
      const res = await fetch('/billing/toggle-autopay/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
          'Content-Type': 'application/json'
        }
      });
      const data = await res.json();
      if (data.success) {
        showToast(isChecked ? 'Автоплатеж включен' : 'Автоплатеж отключен');
      }
    } catch (e) {
      showToast('Ошибка при переключении автоплатежа', 'error');
      toggle.checked = !isChecked;
    }
  });
}

// ==========================================
// 6. REGENERATE VPN KEY
// ==========================================
function initKeyRegeneration() {
  const regenBtn = document.getElementById('btn-regenerate-key');
  if (!regenBtn) return;

  regenBtn.addEventListener('click', async () => {
    if (!confirm('Вы уверены, что хотите обновить ключ? Старый ключ перестанет работать на ваших устройствах.')) {
      return;
    }

    const csrfToken = getCookie('csrftoken');
    try {
      const res = await fetch('/vpn/regenerate-key/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
          'Content-Type': 'application/json'
        }
      });
      const data = await res.json();
      if (data.success) {
        showToast('Ключ успешно обновлен!');
        // Update attributes and displays
        const vlessInput = document.getElementById('vless-key-display');
        if (vlessInput) vlessInput.value = data.vless_url;

        const incyBtn = document.getElementById('btn-incy-connect');
        if (incyBtn) incyBtn.href = data.incy_url;

        const copyBtn = document.getElementById('btn-copy-vless');
        if (copyBtn) copyBtn.setAttribute('data-copy', data.vless_url);

        const qrImg = document.getElementById('qr-code-img');
        if (qrImg) qrImg.src = qrImg.src + '?t=' + Date.now();
      }
    } catch (e) {
      showToast('Ошибка при обновлении ключа', 'error');
    }
  });
}

// ==========================================
// 7. MODALS
// ==========================================
function initModals() {
  document.querySelectorAll('[data-modal-target]').forEach(trigger => {
    trigger.addEventListener('click', () => {
      const targetId = trigger.getAttribute('data-modal-target');
      const modal = document.getElementById(targetId);
      if (modal) modal.classList.add('active');
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
