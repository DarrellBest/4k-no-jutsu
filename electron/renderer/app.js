// --- custom title bar ---

document.getElementById('win-minimize').addEventListener('click', () => window.jutsuUI.minimizeWindow());
document.getElementById('win-maximize').addEventListener('click', () => window.jutsuUI.toggleMaximizeWindow());
document.getElementById('win-close').addEventListener('click', () => window.jutsuUI.closeWindow());

// --- tabs ---

const tabButtons = document.querySelectorAll('.tab-btn');
const tabPanels = document.querySelectorAll('.tab-panel');

function activateTab(name) {
  tabButtons.forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === name));
  tabPanels.forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${name}`));
}

tabButtons.forEach((btn) => btn.addEventListener('click', () => activateTab(btn.dataset.tab)));
document.querySelectorAll('[data-goto-tab]').forEach((el) => {
  el.addEventListener('click', (event) => {
    event.preventDefault();
    activateTab(el.dataset.gotoTab);
  });
});

// --- RUN tab ---

const sourceInput = document.getElementById('source');
const pickSourceBtn = document.getElementById('pick-source');
const profileSelect = document.getElementById('profile');
const targetResSelect = document.getElementById('target-resolution');
const targetResCustom = document.getElementById('target-resolution-custom');
const maxWorkersInput = document.getElementById('max-workers');
const suggestWorkersBtn = document.getElementById('suggest-workers');
const workdirInput = document.getElementById('workdir');
const pickWorkdirBtn = document.getElementById('pick-workdir');
const modeSelect = document.getElementById('mode');
const publishField = document.getElementById('publish-field');
const publishCheckbox = document.getElementById('publish');
const secureFields = document.getElementById('secure-fields');
const vaultDeviceInput = document.getElementById('vault-device');
const pickVaultDeviceBtn = document.getElementById('pick-vault-device');
const vaultMountInput = document.getElementById('vault-mount');
const pickVaultMountBtn = document.getElementById('pick-vault-mount');
const ramfsSizeInput = document.getElementById('ramfs-size');
const form = document.getElementById('job-form');
const runButton = document.getElementById('run-button');
const cancelButton = document.getElementById('cancel-button');
const logEl = document.getElementById('log');
const progressPanel = document.getElementById('progress-panel');
const progressFill = document.getElementById('progress-fill');
const progressText = document.getElementById('progress-text');
const setupWarning = document.getElementById('setup-warning');

let progressInterval = null;

function appendLog(el, text) {
  el.textContent += text;
  el.scrollTop = el.scrollHeight;
}

pickSourceBtn.addEventListener('click', async () => {
  const file = await window.jutsuUI.pickSourceFile();
  if (file) sourceInput.value = file;
});

pickWorkdirBtn.addEventListener('click', async () => {
  const dir = await window.jutsuUI.pickFolder('Select working directory');
  if (dir) workdirInput.value = dir;
});

pickVaultDeviceBtn.addEventListener('click', async () => {
  const file = await window.jutsuUI.pickVaultFile();
  if (file) vaultDeviceInput.value = file;
});

pickVaultMountBtn.addEventListener('click', async () => {
  const dir = await window.jutsuUI.pickFolder('Select vault mount point');
  if (dir) vaultMountInput.value = dir;
});

suggestWorkersBtn.addEventListener('click', async () => {
  maxWorkersInput.value = await window.jutsuUI.suggestMaxWorkers();
});

targetResSelect.addEventListener('change', () => {
  targetResCustom.hidden = targetResSelect.value !== 'custom';
});

modeSelect.addEventListener('change', () => {
  const isSecure = modeSelect.value === 'secure';
  secureFields.hidden = !isSecure;
  publishField.hidden = isSecure; // publish (pCloud/Jellyfin) is a normal-mode-only concept
});

function currentTargetResolution() {
  if (targetResSelect.value === 'custom') return targetResCustom.value.trim() || null;
  return targetResSelect.value || null;
}

function setRunning(running) {
  Array.from(form.elements).forEach((el) => {
    if (el !== cancelButton) el.disabled = running;
  });
  cancelButton.disabled = !running;
}

function startProgressPolling(workdir) {
  progressPanel.hidden = false;
  progressInterval = setInterval(async () => {
    const progress = await window.jutsuUI.readProgress(workdir);
    if (progress && progress.total > 0) {
      const pct = Math.round((progress.done / progress.total) * 100);
      progressFill.style.width = `${pct}%`;
      progressText.textContent = `${progress.done} / ${progress.total} windows (${pct}%)`;
    }
  }, 2000);
}

function stopProgressPolling() {
  if (progressInterval) clearInterval(progressInterval);
  progressInterval = null;
}

window.jutsuUI.onLog((chunk) => appendLog(logEl, chunk));

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  logEl.textContent = '';
  progressFill.style.width = '0%';
  progressText.textContent = 'Starting…';
  setRunning(true);

  const options = {
    source: sourceInput.value.trim(),
    profile: profileSelect.value,
    mode: modeSelect.value,
    outputName: 'output.mp4',
    workdir: workdirInput.value.trim(),
    targetResolution: currentTargetResolution(),
    maxWorkers: parseInt(maxWorkersInput.value, 10) || 1,
    publish: publishCheckbox.checked,
    vaultDevice: vaultDeviceInput.value.trim(),
    vaultMount: vaultMountInput.value.trim(),
    ramfsSizeMb: parseInt(ramfsSizeInput.value, 10) || undefined,
  };

  startProgressPolling(options.workdir);
  appendLog(logEl, `$ jutsu run ... (source: ${options.source})\n\n`);

  try {
    const result = await window.jutsuUI.runJutsu(options);
    appendLog(logEl, `\n[exit code ${result.code}]\n`);
    progressText.textContent = result.code === 0 ? 'Done.' : `Failed (exit ${result.code}).`;
  } catch (err) {
    appendLog(logEl, `\n[error: ${err.message}]\n`);
    progressText.textContent = 'Failed.';
  } finally {
    stopProgressPolling();
    setRunning(false);
  }
});

cancelButton.addEventListener('click', async () => {
  await window.jutsuUI.cancelRun();
  appendLog(logEl, '\n[cancelled]\n');
});

// --- COMPARE tab ---

const compareSourceInput = document.getElementById('compare-source');
const comparePickSourceBtn = document.getElementById('compare-pick-source');
const compareProfileSelect = document.getElementById('compare-profile');
const compareStartInput = document.getElementById('compare-start');
const compareDurationInput = document.getElementById('compare-duration');
const compareWorkdirInput = document.getElementById('compare-workdir');
const comparePickWorkdirBtn = document.getElementById('compare-pick-workdir');
const compareForm = document.getElementById('compare-form');
const compareRunButton = document.getElementById('compare-run-button');
const compareCancelButton = document.getElementById('compare-cancel-button');
const compareOpenReportButton = document.getElementById('compare-open-report');
const compareLogEl = document.getElementById('compare-log');

let lastReportPath = null;

comparePickSourceBtn.addEventListener('click', async () => {
  const file = await window.jutsuUI.pickSourceFile();
  if (file) compareSourceInput.value = file;
});

comparePickWorkdirBtn.addEventListener('click', async () => {
  const dir = await window.jutsuUI.pickFolder('Select working directory');
  if (dir) compareWorkdirInput.value = dir;
});

function setCompareRunning(running) {
  Array.from(compareForm.elements).forEach((el) => {
    if (el !== compareCancelButton) el.disabled = running;
  });
  compareCancelButton.disabled = !running;
}

compareForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  compareLogEl.textContent = '';
  compareOpenReportButton.disabled = true;
  lastReportPath = null;
  setCompareRunning(true);

  const options = {
    source: compareSourceInput.value.trim(),
    profile: compareProfileSelect.value,
    start: parseFloat(compareStartInput.value) || 0,
    duration: parseFloat(compareDurationInput.value) || 15,
    workdir: compareWorkdirInput.value.trim(),
  };

  appendLog(compareLogEl, `$ jutsu compare ... (source: ${options.source})\n\n`);

  try {
    const result = await window.jutsuUI.runCompare(options);
    appendLog(compareLogEl, `\n[exit code ${result.code}]\n`);
    if (result.code === 0) {
      lastReportPath = result.reportPath;
      compareOpenReportButton.disabled = false;
      appendLog(compareLogEl, `Report: ${result.reportPath}\n`);
    }
  } catch (err) {
    appendLog(compareLogEl, `\n[error: ${err.message}]\n`);
  } finally {
    setCompareRunning(false);
  }
});

compareCancelButton.addEventListener('click', async () => {
  await window.jutsuUI.cancelRun();
  appendLog(compareLogEl, '\n[cancelled]\n');
});

compareOpenReportButton.addEventListener('click', async () => {
  if (lastReportPath) await window.jutsuUI.openPath(lastReportPath);
});

// --- SETUP tab ---

const checkEnv = document.getElementById('check-env');
const checkJutsu = document.getElementById('check-jutsu');
const checkBackends = document.getElementById('check-backends');
const runSetupButton = document.getElementById('run-setup-button');
const recheckSetupButton = document.getElementById('recheck-setup-button');
const setupLogEl = document.getElementById('setup-log');

function setItemState(el, state) {
  el.classList.remove('checking', 'ok', 'missing');
  el.classList.add(state);
}

async function refreshSetupStatus() {
  setItemState(checkEnv, 'checking');
  setItemState(checkJutsu, 'checking');
  setItemState(checkBackends, 'checking');

  const status = await window.jutsuUI.checkSetupStatus();
  setItemState(checkEnv, status.condaEnvExists ? 'ok' : 'missing');
  setItemState(checkJutsu, status.jutsuInstalled ? 'ok' : 'missing');
  setItemState(checkBackends, status.backendsInstalled ? 'ok' : 'missing');
  return status;
}

runSetupButton.addEventListener('click', async () => {
  setupLogEl.textContent = '';
  runSetupButton.disabled = true;
  appendLog(setupLogEl, '$ ./scripts/setup.sh\n\n');
  const removeListener = window.jutsuUI.onSetupLog((chunk) => appendLog(setupLogEl, chunk));
  try {
    const result = await window.jutsuUI.runSetup();
    appendLog(setupLogEl, `\n[exit code ${result.code}]\n`);
  } finally {
    removeListener();
    runSetupButton.disabled = false;
    await refreshSetupStatus();
  }
});

recheckSetupButton.addEventListener('click', refreshSetupStatus);

// --- SETTINGS tab ---

const settingsForm = document.getElementById('settings-form');
const settingsPcloudInput = document.getElementById('settings-pcloud');
const settingsJellyfinInput = document.getElementById('settings-jellyfin');
const settingsPickJellyfinBtn = document.getElementById('settings-pick-jellyfin');
const settingsRamfsInput = document.getElementById('settings-ramfs');
const settingsSavedBadge = document.getElementById('settings-saved-badge');

async function loadSettingsIntoForm() {
  const settings = await window.jutsuUI.loadSettings();
  settingsPcloudInput.value = settings.pcloudRemote || '';
  settingsJellyfinInput.value = settings.jellyfinDir || '';
  settingsRamfsInput.value = settings.ramfsSizeMb || 4096;
  // Also prefill the Run tab's secure-mode ramfs size with the saved default.
  ramfsSizeInput.value = settings.ramfsSizeMb || 4096;
}

settingsPickJellyfinBtn.addEventListener('click', async () => {
  const dir = await window.jutsuUI.pickFolder('Select Jellyfin media folder');
  if (dir) settingsJellyfinInput.value = dir;
});

settingsForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const settings = {
    pcloudRemote: settingsPcloudInput.value.trim(),
    jellyfinDir: settingsJellyfinInput.value.trim(),
    ramfsSizeMb: parseInt(settingsRamfsInput.value, 10) || 4096,
  };
  await window.jutsuUI.saveSettings(settings);
  ramfsSizeInput.value = settings.ramfsSizeMb;
  settingsSavedBadge.hidden = false;
  setTimeout(() => { settingsSavedBadge.hidden = true; }, 2000);
});

// --- startup ---

(async () => {
  const available = await window.jutsuUI.checkJutsuAvailable();
  setupWarning.hidden = available;
  await refreshSetupStatus();
  await loadSettingsIntoForm();
})();
