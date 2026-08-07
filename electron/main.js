const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { spawn } = require('child_process');

let mainWindow;
let runningProcess = null;
const REPO_ROOT = path.join(__dirname, '..');

function settingsPath() {
  return path.join(app.getPath('userData'), 'settings.json');
}

function loadSettings() {
  try {
    return JSON.parse(fs.readFileSync(settingsPath(), 'utf-8'));
  } catch (e) {
    return { pcloudRemote: '', jellyfinDir: '', ramfsSizeMb: 4096 };
  }
}

function childEnv(settings) {
  const env = { ...process.env };
  if (settings.pcloudRemote) env.JUTSU_PCLOUD_REMOTE = settings.pcloudRemote;
  if (settings.jellyfinDir) env.JUTSU_JELLYFIN_DIR = settings.jellyfinDir;
  return env;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1480,
    height: 1040,
    minWidth: 1000,
    minHeight: 760,
    backgroundColor: '#0b0a19',
    frame: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.setMenuBarVisibility(false);
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// --- custom title bar (frame: false, so these replace the OS window controls) ---

ipcMain.handle('window-minimize', () => mainWindow.minimize());
ipcMain.handle('window-toggle-maximize', () => {
  if (mainWindow.isMaximized()) mainWindow.unmaximize();
  else mainWindow.maximize();
});
ipcMain.handle('window-close', () => mainWindow.close());
ipcMain.handle('window-is-maximized', () => mainWindow.isMaximized());

// --- file/folder pickers ---

ipcMain.handle('pick-source-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Select source video',
    properties: ['openFile'],
    filters: [{ name: 'Video', extensions: ['mp4', 'mkv', 'avi', 'mov', 'webm', 'ts', 'm4v'] }, { name: 'All files', extensions: ['*'] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('pick-folder', async (_event, title) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: title || 'Select folder',
    properties: ['openDirectory', 'createDirectory'],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('pick-vault-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Select VeraCrypt volume file',
    properties: ['openFile'],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('open-path', async (_event, targetPath) => {
  await shell.openPath(targetPath);
});

// --- settings (publish destinations + defaults, persisted locally) ---

ipcMain.handle('load-settings', async () => loadSettings());

ipcMain.handle('save-settings', async (_event, settings) => {
  fs.mkdirSync(app.getPath('userData'), { recursive: true });
  fs.writeFileSync(settingsPath(), JSON.stringify(settings, null, 2));
  return true;
});

// --- job config + jutsu invocation ---

function buildJobYaml({ source, profile, mode, outputName }) {
  const escapedSource = String(source).replace(/'/g, "''");
  return [
    `source: '${escapedSource}'`,
    `profile: ${profile}`,
    `mode: ${mode}`,
    `output_name: ${outputName || 'output.mp4'}`,
    '',
  ].join('\n');
}

function streamChild(child, channel = 'jutsu-log') {
  runningProcess = child;
  child.stdout.on('data', (data) => mainWindow.webContents.send(channel, data.toString()));
  child.stderr.on('data', (data) => mainWindow.webContents.send(channel, data.toString()));
  return new Promise((resolve) => {
    child.on('error', (err) => {
      runningProcess = null;
      mainWindow.webContents.send(channel, `\n[failed to start: ${err.message}]\n`);
      resolve({ code: -1 });
    });
    child.on('close', (code) => {
      runningProcess = null;
      resolve({ code });
    });
  });
}

ipcMain.handle('check-jutsu-available', async () => {
  return new Promise((resolve) => {
    const child = spawn('jutsu', ['--help']);
    let found = true;
    child.on('error', () => { found = false; });
    child.on('close', () => resolve(found));
  });
});

ipcMain.handle('check-setup-status', async () => {
  return new Promise((resolve) => {
    const check = spawn('bash', ['-lc', 'conda env list 2>/dev/null | grep -q "^4k-no-jutsu " && echo ENV_OK; jutsu --help >/dev/null 2>&1 && echo JUTSU_OK']);
    let out = '';
    check.stdout.on('data', (d) => { out += d.toString(); });
    check.on('close', () => {
      resolve({
        condaEnvExists: out.includes('ENV_OK'),
        jutsuInstalled: out.includes('JUTSU_OK'),
        backendsInstalled: fs.existsSync(path.join(REPO_ROOT, 'vendor', 'realesrgan', 'realesrgan-ncnn-vulkan'))
          && fs.existsSync(path.join(REPO_ROOT, 'vendor', 'realcugan', 'realcugan-ncnn-vulkan')),
      });
    });
    check.on('error', () => resolve({ condaEnvExists: false, jutsuInstalled: false, backendsInstalled: false }));
  });
});

ipcMain.handle('run-setup', async () => {
  const child = spawn('bash', [path.join(REPO_ROOT, 'scripts', 'setup.sh')], { cwd: REPO_ROOT });
  return streamChild(child, 'setup-log');
});

ipcMain.handle('run-jutsu', async (_event, options) => {
  if (runningProcess) {
    throw new Error('A job is already running');
  }

  const workdir = options.workdir;
  fs.mkdirSync(workdir, { recursive: true });
  const configPath = path.join(workdir, '.jutsu-ui-job.yaml');
  fs.writeFileSync(configPath, buildJobYaml(options));

  const args = ['run', configPath, workdir];
  if (options.targetResolution) {
    args.push('--target-resolution', options.targetResolution);
  }
  if (options.maxWorkers) {
    args.push('--max-workers', String(options.maxWorkers));
  }
  if (!options.publish) {
    args.push('--no-publish');
  }
  if (options.mode === 'secure') {
    args.push('--vault-device', options.vaultDevice);
    args.push('--vault-mount', options.vaultMount);
    if (options.ramfsSizeMb) {
      args.push('--ramfs-size-mb', String(options.ramfsSizeMb));
    }
  }

  const child = spawn('jutsu', args, { cwd: os.homedir(), env: childEnv(loadSettings()) });
  return streamChild(child);
});

ipcMain.handle('run-compare', async (_event, options) => {
  if (runningProcess) {
    throw new Error('A job is already running');
  }

  const workdir = options.workdir;
  fs.mkdirSync(workdir, { recursive: true });
  const configPath = path.join(workdir, '.jutsu-ui-compare.yaml');
  fs.writeFileSync(configPath, buildJobYaml({
    source: options.source, profile: options.profile, mode: 'normal', outputName: 'output.mp4',
  }));

  const args = ['compare', configPath, workdir, '--start', String(options.start), '--duration', String(options.duration)];
  const child = spawn('jutsu', args, { cwd: os.homedir() });
  const result = await streamChild(child);
  return { ...result, reportPath: path.join(workdir, 'comparison.html') };
});

ipcMain.handle('cancel-run', async () => {
  if (runningProcess) {
    runningProcess.kill('SIGTERM');
    return true;
  }
  return false;
});

ipcMain.handle('read-progress', async (_event, workdir) => {
  try {
    const raw = fs.readFileSync(path.join(workdir, 'state.json'), 'utf-8');
    const state = JSON.parse(raw);
    return { done: state.done_windows.length, total: state.total_windows };
  } catch (e) {
    return null;
  }
});

ipcMain.handle('suggest-max-workers', async () => {
  return Math.max(1, os.cpus().length - 2);
});
