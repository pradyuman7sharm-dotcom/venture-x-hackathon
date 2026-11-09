// Sahaayak Pro - Frontend JavaScript (Offline-first, Vanilla JS)

function setLanguage(lang) {
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = '/set-language';
  const input = document.createElement('input');
  input.type = 'hidden';
  input.name = 'language';
  input.value = lang;
  form.appendChild(input);
  document.body.appendChild(form);
  form.submit();
}

function initVoiceInput() {
  const voiceBtn = document.getElementById('voice-btn');
  const symptomInput = document.getElementById('symptom_text');

  if (!voiceBtn || !symptomInput) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voiceBtn.classList.add('hidden');
    return;
  }

  const currentLang = document.documentElement.lang || 'en';
  const langMap = {
    'en': 'en-IN',
    'hi': 'hi-IN',
    'pa': 'pa-IN'
  };

  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = langMap[currentLang] || 'en-IN';

  let isRecording = false;

  voiceBtn.addEventListener('click', function(e) {
    e.preventDefault();
    if (!isRecording) {
      try {
        recognition.start();
        isRecording = true;
        voiceBtn.classList.add('recording');
      } catch (err) {
        console.error('Speech recognition start error:', err);
      }
    } else {
      recognition.stop();
      isRecording = false;
      voiceBtn.classList.remove('recording');
    }
  });

  recognition.onresult = function(event) {
    const transcript = event.results[0][0].transcript;
    if (transcript) {
      if (symptomInput.value.trim().length > 0) {
        symptomInput.value += ', ' + transcript;
      } else {
        symptomInput.value = transcript;
      }
    }
  };

  recognition.onerror = function(event) {
    console.warn('Speech recognition error:', event.error);
    isRecording = false;
    voiceBtn.classList.remove('recording');
  };

  recognition.onend = function() {
    isRecording = false;
    voiceBtn.classList.remove('recording');
  };
}

function initSymptomCheckboxes() {
  const checkboxes = document.querySelectorAll('.symptom-checkbox');
  checkboxes.forEach(function(item) {
    item.addEventListener('click', function() {
      const input = this.querySelector('input[type="checkbox"]');
      if (input) {
        input.checked = !input.checked;
        if (input.checked) {
          this.classList.add('checked');
          const checkIcon = this.querySelector('.sym-check');
          if (checkIcon) checkIcon.textContent = '✓';
        } else {
          this.classList.remove('checked');
          const checkIcon = this.querySelector('.sym-check');
          if (checkIcon) checkIcon.textContent = '';
        }
      }
    });
  });
}

function pollSyncStatus() {
  const offlineBadge = document.getElementById('offline-badge');
  const onlineBadge = document.getElementById('online-badge');
  const pendingCounter = document.getElementById('pending-counter');

  function updateStatus() {
    fetch('/api/sync-status')
      .then(response => response.json())
      .then(data => {
        if (data.is_online) {
          if (offlineBadge) offlineBadge.classList.add('hidden');
          if (onlineBadge) onlineBadge.classList.remove('hidden');
        } else {
          if (offlineBadge) offlineBadge.classList.remove('hidden');
          if (onlineBadge) onlineBadge.classList.add('hidden');
        }

        if (pendingCounter) {
          const count = data.pending_count || 0;
          if (count > 0) {
            pendingCounter.textContent = count + ' pending';
            pendingCounter.classList.remove('hidden');
          } else {
            pendingCounter.classList.add('hidden');
          }
        }
      })
      .catch(err => {
        // If server fails or offline
        if (offlineBadge) offlineBadge.classList.remove('hidden');
        if (onlineBadge) onlineBadge.classList.add('hidden');
      });
  }

  // Poll every 30 seconds
  setInterval(updateStatus, 30000);
}

function toggleExplanation() {
  const box = document.getElementById('explanation-box');
  if (box) {
    box.classList.toggle('show');
  }
}

function printCard() {
  window.print();
}

// ---- Dark Mode Management ----
function initTheme() {
  const saved = localStorage.getItem('sahaayak_theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = saved || (prefersDark ? 'dark' : 'light');

  if (theme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  updateThemeButton(theme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const target = (current === 'dark') ? 'light' : 'dark';

  if (target === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  localStorage.setItem('sahaayak_theme', target);
  updateThemeButton(target);
  showToast(target === 'dark' ? 'Dark Mode Enabled 🌙' : 'Light Mode Enabled ☀️');
}

function updateThemeButton(theme) {
  const btn = document.getElementById('theme-toggle-btn');
  if (btn) {
    btn.innerHTML = (theme === 'dark') ? '☀️' : '🌙';
    btn.title = (theme === 'dark') ? 'Switch to Light Mode' : 'Switch to Dark Mode';
  }
}

// ---- Toast Notification ----
function showToast(message) {
  let toast = document.getElementById('app-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'app-toast';
    toast.className = 'toast-notification';
    document.body.appendChild(toast);
  }
  toast.innerHTML = message;
  toast.classList.add('show');
  setTimeout(function() {
    toast.classList.remove('show');
  }, 3200);
}

// ---- Manual Sync Function ----
function triggerManualSync() {
  const syncBtns = document.querySelectorAll('.sync-btn');
  syncBtns.forEach(btn => btn.classList.add('spinning'));

  showToast('🔄 Checking connectivity & syncing...');

  fetch('/api/sync-now', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
      syncBtns.forEach(btn => btn.classList.remove('spinning'));

      const offlineBadge = document.getElementById('offline-badge');
      const onlineBadge = document.getElementById('online-badge');
      const pendingCounter = document.getElementById('pending-counter');

      if (data.is_online) {
        if (offlineBadge) offlineBadge.classList.add('hidden');
        if (onlineBadge) onlineBadge.classList.remove('hidden');
        showToast('✅ Online: Cases synchronized successfully!');
      } else {
        if (offlineBadge) offlineBadge.classList.remove('hidden');
        if (onlineBadge) onlineBadge.classList.add('hidden');
        showToast('ℹ️ Offline mode: Data saved securely on device.');
      }

      if (pendingCounter) {
        const count = data.pending_count || 0;
        if (count > 0) {
          pendingCounter.textContent = count + ' pending';
          pendingCounter.classList.remove('hidden');
        } else {
          pendingCounter.classList.add('hidden');
        }
      }
    })
    .catch(err => {
      syncBtns.forEach(btn => btn.classList.remove('spinning'));
      showToast('⚠️ Sync check completed (Offline)');
    });
}

// ---- Security Verification Modal ----
function openSecurityModal() {
  const modal = document.getElementById('security-modal');
  if (modal) modal.classList.add('open');
}

function closeSecurityModal() {
  const modal = document.getElementById('security-modal');
  if (modal) modal.classList.remove('open');
}

// Auto-init theme immediately to prevent screen flash
initTheme();

document.addEventListener('DOMContentLoaded', function() {
  initTheme();
  initVoiceInput();
  initSymptomCheckboxes();
  pollSyncStatus();

  // Close modal on click outside
  const modal = document.getElementById('security-modal');
  if (modal) {
    modal.addEventListener('click', function(e) {
      if (e.target === modal) closeSecurityModal();
    });
  }
});
