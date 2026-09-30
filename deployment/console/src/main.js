import * as monaco from 'monaco-editor/editor/editor.api.js';
import 'monaco-editor/editor/contrib/find/browser/findController.js';
import 'monaco-editor/editor/contrib/bracketMatching/browser/bracketMatching.js';
import 'monaco-editor/languages/definitions/yaml/register.js';
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker';
import { parseDocument } from 'yaml';
import './style.css';

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
const paths = {
  search: '<circle cx="11" cy="11" r="7"/><path d="m16 16 4 4"/>',
  moon: '<path d="M20 13a8 8 0 0 1-9-9 8 8 0 1 0 9 9Z"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 3M4 15l2 3a7 7 0 0 0 12-1"/>',
  package: '<path d="m12 3 9 5-9 5-9-5 9-5ZM3 8v9l9 5 9-5V8M12 13v9M7 5l9 5"/>',
  'arrow-down': '<path d="M12 4v16m-6-6 6 6 6-6"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5"/>',
  route: '<circle cx="6" cy="5" r="3"/><circle cx="18" cy="19" r="3"/><path d="M6 8v9a2 2 0 0 0 2 2h7M9 5h7a3 3 0 0 1 0 6H8"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6ZM14 2v6h6M8 13h8M8 17h5"/>',
  undo: '<path d="M4 10h9a6 6 0 0 1 0 12M4 10l6-6M4 10l6 6"/>',
  copy: '<rect x="8" y="8" width="13" height="13" rx="3"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4"/>',
  check: '<path d="m5 12 4 4 10-10"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
};
for (const element of document.querySelectorAll('[data-icon]')) element.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[element.dataset.icon]}</svg>`;
for (const element of document.querySelectorAll('.app-mark')) element.setAttribute('aria-hidden', 'true');

monaco.languages.register({ id: 'proxy-conf' });
monaco.languages.register({ id: 'private-json' });
monaco.languages.setMonarchTokensProvider('private-json', {
  tokenizer: { root: [[/"(?:[^"\\]|\\.)*"(?=\s*:)/, 'attribute.name'], [/"(?:[^"\\]|\\.)*"/, 'string'],
    [/\b(?:true|false|null)\b/, 'keyword'], [/-?\d+(?:\.\d+)?/, 'number'], [/[{}\[\]:,]/, 'delimiter']] },
});
monaco.languages.setMonarchTokensProvider('proxy-conf', {
  tokenizer: { root: [
    [/^\s*[#;].*$/, 'comment'], [/^\s*\[[^\]]+\]/, 'section'],
    [/https?:\/\/[^\s,]+|vmess:\/\/[^\s]+/, 'string'],
    [/\b(DIRECT|PROXY|REJECT|REJECT-DROP|FINAL|MATCH)\b/, 'keyword'],
    [/\b(DOMAIN(?:-SUFFIX|-KEYWORD|-SET)?|IP-CIDR6?|RULE-SET|AND|OR|PROCESS-NAME|PROTOCOL)\b/, 'type'],
    [/^[\w.-]+(?=\s*=)/, 'attribute.name'], [/\b(?:true|false|no-resolve)\b/, 'keyword'],
    [/\b\d+\b/, 'number'], [/[=,]/, 'delimiter'],
  ]},
});
monaco.editor.defineTheme('private-light', { base: 'vs', inherit: true, rules: [
  { token: 'section', foreground: '4338CA', fontStyle: 'bold' },
  { token: 'keyword', foreground: '8B48B4' }, { token: 'type', foreground: '177E8B' },
  { token: 'attribute.name', foreground: '324F88' }, { token: 'comment', foreground: '94A0B5' },
], colors: { 'editor.background': '#FFFFFF', 'editorLineNumber.foreground': '#B4BDCD', 'editorLineNumber.activeForeground': '#5E6782', 'editor.lineHighlightBackground': '#F8F9FE', 'editor.selectionBackground': '#E6E5FF', 'editorGutter.background': '#FFFFFF' } });

const $ = (id) => document.getElementById(id);
const state = { accounts: [], account: null, client: 'surge', file: 'surge.conf', baseline: '', etag: '', edited: false, loading: false, dirty: false, version: 0 };
const clients = {
  personal: { files: ['personal.json'], title: '个人策略 · 自动合并', help: '设置各组默认选择、个人例外和 Surge Ponte 路径，仅作用于本账号的四种 App。保存前自动备份，公共规则更新会继承这些设置。非 Surge 的 HOME、COMPANY_LAN 仅支持本地访问，远程访问需要另行配置通道。' },
  stash: { files: ['stash.yaml'], title: '导入 Stash', help: '手机 Stash 请导入 stash.yaml。内网规则直接内嵌，公开规则从 CDN 下载；APPLE 默认 DIRECT，可在策略组切换。' },
  lan: { files: ['lan-com.list'], title: '私有内网规则', help: '只填写 DOMAIN,域名 或 DOMAIN-SUFFIX,域名，每行一条，固定直连。保存后同步到你的三个设备配置；不进入 GitHub 或 CDN。WAN、券商及通用规则由 jsDelivr 提供。' },
  surge: { files: ['surge.conf'], title: '导入 Surge', help: '下载 surge.conf，在 Surge 中导入本地配置。公共规则仍由 jsDelivr 提供。' },
  mihomo: { files: ['mihomo.yaml'], title: '导入 Clash / Mihomo', help: '下载 mihomo.yaml，在支持 Mihomo 的客户端中导入本地配置。公共规则经 DIRECT 下载。' },
  shadowrocket: { files: ['shadowrocket.conf', 'node.txt', 'shadowrocket.txt'], title: '导入 Shadowrocket', help: '导入并启用 shadowrocket.conf，文件已包含此账号的节点和分流规则。node.txt 可用于单独导入节点；shadowrocket.txt 是 Base64 节点格式。' },
};
const editor = monaco.editor.create($('editor'), {
  value: '', language: 'proxy-conf', theme: 'private-light', automaticLayout: true,
  fontSize: 13, lineHeight: 24, fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", monospace',
  minimap: { enabled: false }, padding: { top: 22, bottom: 24 }, scrollBeyondLastLine: false,
  renderLineHighlight: 'all', lineNumbersMinChars: 4, wordWrap: 'on', smoothScrolling: true,
  roundedSelection: true, tabSize: 2, readOnly: true,
});
document.querySelector('.editor-loading')?.remove();
let toastTimer;
function toast(message, error = false) {
  $('toast').textContent = message; $('toast').className = `visible${error ? ' error' : ''}`;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').className = '', 4200);
}
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers }, cache: 'no-store' });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || '请求失败');
  return body;
}
function fileURL() { if (state.client === 'lan') return '/api/private-rules/lan-com'; if (state.client === 'personal') return `/api/accounts/${state.account.id}/personal`; return `/api/accounts/${state.account.id}/files/${state.file}`; }
function confirmDiscard() { return !state.dirty || window.confirm('还有未保存的编辑，是否放弃这些修改？'); }
function setLoading(value) {
  state.loading = value; editor.updateOptions({ readOnly: value || !state.account });
  $('file-select').disabled = value || !state.account;
  for (const tab of document.querySelectorAll('.client-tab')) tab.disabled = value || !state.account;
  for (const button of document.querySelectorAll('.account')) button.disabled = value;
  updateStatus();
}
function updateStatus() {
  state.dirty = editor.getValue() !== state.baseline;
  $('save-status').className = state.dirty ? 'unsaved' : 'saved';
  $('save-status').innerHTML = `<span class="connection-dot"></span>${state.loading ? '正在处理…' : state.dirty ? '有未保存的编辑' : state.client === 'lan' ? '私有规则 · 已同步' : state.edited ? '已保存个人编辑' : '自动生成 · 未修改'}`;
  $('save').disabled = state.loading || !state.account || !state.dirty;
  $('restore').disabled = state.loading || !state.account || !state.edited || ['lan', 'personal'].includes(state.client);
  for (const id of ['copy', 'download-file', 'download-account', 'refresh']) $(id).disabled = state.loading || !state.account;
  $('file-origin').textContent = state.client === 'lan' ? 'SSH 私有' : state.edited ? '个人编辑' : '自动生成';
  $('file-origin').classList.toggle('custom', state.edited);
}
function accountSubtitle(account) {
  return account.personal ? `个人策略 · 自动版本备份 · FINAL ${account.finalPolicy} · MICROSOFT ${account.defaults.MICROSOFT} · PAYPAL ${account.defaults.PAYPAL}` : `选择客户端，编辑或下载。FINAL 默认 ${account.finalPolicy || (account.businessRules ? 'PROXY' : 'DIRECT')} · AI 默认 PROXY · APPLE 默认 DIRECT`;
}
function validate() {
  const model = editor.getModel();
  if (state.file.endsWith('.json')) {
    try { JSON.parse(editor.getValue()); $('validation-status').textContent = 'JSON 语法通过'; return true; }
    catch { $('validation-status').textContent = 'JSON 语法错误'; return false; }
  }
  if (!state.file.endsWith('.yaml')) {
    monaco.editor.setModelMarkers(model, 'yaml', []);
    $('validation-status').textContent = '语法高亮 · 客户端导入验证';
    return true;
  }
  const doc = parseDocument(editor.getValue());
  const markers = doc.errors.map(error => {
    const start = model.getPositionAt(error.pos?.[0] || 0), end = model.getPositionAt(error.pos?.[1] || 1);
    return { startLineNumber: start.lineNumber, startColumn: start.column, endLineNumber: end.lineNumber, endColumn: end.column, message: error.message, severity: monaco.MarkerSeverity.Error };
  });
  monaco.editor.setModelMarkers(model, 'yaml', markers);
  $('validation-status').textContent = markers.length ? `YAML 有 ${markers.length} 处语法问题` : 'YAML 语法通过';
  return !markers.length;
}
function renderAccounts() {
  const query = $('search').value.trim().toLowerCase(); $('accounts').replaceChildren();
  const filtered = state.accounts.filter(account => account.label.toLowerCase().includes(query));
  for (const account of filtered) {
    const button = document.createElement('button'); button.className = 'account' + (state.account?.id === account.id ? ' selected' : '');
    button.setAttribute('aria-current', state.account?.id === account.id ? 'true' : 'false');
    const avatar = document.createElement('span'); avatar.className = 'avatar'; avatar.textContent = account.label[0].toUpperCase();
    const details = document.createElement('span'); details.className = 'account-details';
    const name = document.createElement('strong'); name.textContent = account.label;
    const hint = document.createElement('small'); hint.textContent = account.businessRules ? '含个人专项规则' : '公共分流规则'; details.append(name, hint);
    const arrow = document.createElement('span'); arrow.className = 'account-arrow'; arrow.textContent = '›';
    button.append(avatar, details, arrow); button.onclick = () => selectAccount(account); $('accounts').append(button);
  }
  if (!filtered.length) { const empty = document.createElement('div'); empty.className = 'placeholder'; empty.textContent = '没有匹配的账号'; $('accounts').append(empty); }
  $('account-count').textContent = state.accounts.length;
}
async function selectAccount(account) {
  if (state.loading || !confirmDiscard()) return;
  state.account = account;
  $('personal-tab').hidden = !account.personal; $('version-bar').hidden = !account.personal;
  for (const tab of document.querySelectorAll('.client-tab')) tab.hidden = !clientAvailable(tab.dataset.client, account);
  if (!clientAvailable(state.client, account)) state.client = ['surge', 'mihomo', 'stash', 'shadowrocket', 'personal', 'lan'].find(client => clientAvailable(client, account));
  if (!availableFiles(state.client, account).includes(state.file)) state.file = availableFiles(state.client, account)[0];
  updateClient(); $('breadcrumb-account').textContent = account.label; $('account-title').textContent = account.label;
  $('node-names').textContent = account.nodes.join(' · ');
  $('account-subtitle').textContent = accountSubtitle(account);
  $('rules-scope').lastChild.textContent = account.businessRules ? '公共规则 + 个人专项规则' : '公共分流规则';
  renderAccounts(); await loadFile(); if (account.personal && state.account?.id === account.id) await loadVersions();
}
async function loadFile() {
  const version = ++state.version; setLoading(true);
  try {
    const result = await api(fileURL()); if (version !== state.version) return;
    state.baseline = result.content; state.etag = result.etag; state.edited = result.edited;
    monaco.editor.setModelLanguage(editor.getModel(), state.file.endsWith('.json') ? 'private-json' : state.file.endsWith('.yaml') ? 'yaml' : state.file === 'shadowrocket.txt' ? 'plaintext' : 'proxy-conf');
    editor.setValue(result.content); editor.setPosition({ lineNumber: 1, column: 1 }); editor.revealLine(1);
    $('language-label').textContent = state.client === 'lan' ? 'DOMAIN RULES' : state.file.endsWith('.json') ? 'JSON' : state.file.endsWith('.yaml') ? 'YAML' : state.file.endsWith('.conf') ? 'Proxy INI' : 'TEXT';
    validate();
  } catch (error) { state.account = null; editor.setValue(''); toast(error.message, true); }
  finally { setLoading(false); }
}
function availableFiles(client, account) {
  return clients[client].files.filter(name => client === 'lan' || client === 'personal' || account.files.includes(name));
}
function clientAvailable(client, account) {
  if (client === 'lan') return account.businessRules && !account.personal;
  if (client === 'personal') return account.personal;
  return availableFiles(client, account).length > 0;
}
function updateClient() {
  for (const tab of document.querySelectorAll('.client-tab')) { const active = tab.dataset.client === state.client; tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active)); }
  $('file-select').replaceChildren(...availableFiles(state.client, state.account).map(name => { const option = document.createElement('option'); option.value = option.textContent = name; return option; }));
  $('file-select').value = state.file; $('import-title').textContent = clients[state.client].title; $('import-help').textContent = clients[state.client].help;
}
async function save() {
  if (!state.account || !state.dirty || state.loading) return false;
  if (!validate()) { toast('请先修复配置语法问题', true); return false; }
  setLoading(true);
  try {
    const result = await api(fileURL(), { method: 'PUT', body: JSON.stringify({ content: editor.getValue(), etag: state.etag }) });
    state.baseline = result.content; state.etag = result.etag; state.edited = state.client !== 'personal';
    if (state.client === 'personal') {
      state.accounts = (await api('/api/accounts')).accounts; state.account = state.accounts.find(a => a.id === state.account.id);
      $('account-subtitle').textContent = accountSubtitle(state.account);
    }
    if (state.account.personal) await loadVersions();
    toast(state.client === 'personal' ? '个人策略已保存，四种 App 已重新生成，旧版本已备份' : state.client === 'lan' ? '内网规则已保存，已同步到你的设备配置' : '编辑已保存，定时生成会保留此文件的个人版本'); return true;
  } catch (error) { toast(error.message, true); return false; }
  finally { setLoading(false); }
}
function download(content, name) {
  const url = URL.createObjectURL(new Blob([content], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function loadVersions() {
  const identifier = state.account.id;
  const result = await api(`/api/accounts/${identifier}/versions`);
  if (identifier !== state.account?.id) return;
  state.versionEtag = result.etag;
  $('version-select').replaceChildren(...result.versions.map(item => {
    const option = document.createElement('option'); option.value = item.version;
    option.textContent = `${new Date(item.created_ns / 1e6).toLocaleString()} · ${item.digest.slice(0, 8)}`; return option;
  }));
  $('download-version').disabled = $('rollback-version').disabled = !result.versions.length;
}
$('backup-version').onclick = async () => {
  if (state.loading || !state.account?.personal) return;
  try { await api(`/api/accounts/${state.account.id}/versions`, { method: 'POST', body: '{}' }); await loadVersions(); toast('当前版本已备份'); }
  catch (error) { toast(error.message, true); }
};
$('download-version').onclick = () => {
  if (!state.account?.personal || !$('version-select').value) return;
  const link = document.createElement('a'); link.href = `/api/accounts/${state.account.id}/versions/${$('version-select').value}/download`; link.download = '历史配置.zip'; link.click();
};
$('rollback-version').onclick = async () => {
  if (state.loading || !state.account?.personal || !$('version-select').value || !confirmDiscard()) return;
  if (!window.confirm('先备份当前配置，再恢复此版本的四种 App 输出。恢复后作为整文件覆盖保留；恢复默认可重新采用个人策略生成的配置。')) return;
  const identifier = state.account.id, version = $('version-select').value; setLoading(true);
  try {
    const result = await api(`/api/accounts/${identifier}/versions/${version}/restore`, { method: 'POST', body: JSON.stringify({ etag: state.versionEtag }) });
    state.accounts = result.accounts; state.dirty = false; setLoading(false); await selectAccount(state.accounts.find(a => a.id === identifier)); toast('已回滚四种 App，回滚前版本已备份');
  } catch (error) { toast(error.message, true); } finally { setLoading(false); }
};
$('search').oninput = renderAccounts;
for (const tab of document.querySelectorAll('.client-tab')) tab.onclick = async () => { if (state.loading || !state.account || tab.dataset.client === state.client || !confirmDiscard()) return; state.client = tab.dataset.client; state.file = clients[state.client].files[0]; updateClient(); await loadFile(); };
$('file-select').onchange = async () => { if (state.loading || !confirmDiscard()) { $('file-select').value = state.file; return; } state.file = $('file-select').value; await loadFile(); };
$('save').onclick = save;
$('restore').onclick = async () => {
  if (!state.edited || !window.confirm('移除此文件的个人编辑，恢复当前规则和模板生成的版本？')) return;
  setLoading(true);
  try { await api(fileURL(), { method: 'DELETE', body: JSON.stringify({ etag: state.etag }) }); await loadFile(); toast('已恢复自动生成版本'); }
  catch (error) { toast(error.message, true); }
  finally { setLoading(false); }
};
$('copy').onclick = async () => { try { await navigator.clipboard.writeText(editor.getValue()); toast('当前配置已复制'); } catch { toast('复制未获浏览器许可，请使用编辑器快捷键', true); } };
$('download-file').onclick = () => { download(editor.getValue(), state.file); toast(state.dirty ? '已下载当前编辑内容，服务器版本尚未保存' : '配置文件已下载'); };
$('download-account').onclick = async () => {
  if (state.dirty) { if (!window.confirm('此文件有未保存编辑，先保存再下载整人文件包？') || !await save()) return; }
  try {
    const response = await fetch(`/api/accounts/${state.account.id}/download`); if (!response.ok) throw new Error('文件包下载失败');
    const blob = await response.blob(), url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = state.account.label + '.zip'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); toast('文件包已下载，请只分享给对应账号本人');
  } catch (error) { toast(error.message, true); }
};
$('refresh').onclick = async () => {
  if (!confirmDiscard()) return; setLoading(true);
  try { state.accounts = (await api('/api/refresh', { method: 'POST', body: '{}' })).accounts; const current = state.accounts.find(a => a.id === state.account?.id) || state.accounts[0]; setLoading(false); state.dirty = false; if (current) await selectAccount(current); else { state.account = null; editor.setValue(''); renderAccounts(); updateStatus(); } toast('已加载服务器最新配置，个人编辑保持不变'); }
  catch (error) { toast(error.message, true); }
  finally { setLoading(false); }
};
let theme = localStorage.getItem('console-theme') || 'light';
function applyTheme() { document.documentElement.dataset.theme = theme; monaco.editor.setTheme(theme === 'dark' ? 'vs-dark' : 'private-light'); $('theme').setAttribute('aria-label', theme === 'dark' ? '切换浅色主题' : '切换深色主题'); }
$('theme').onclick = () => { theme = theme === 'light' ? 'dark' : 'light'; localStorage.setItem('console-theme', theme); applyTheme(); }; applyTheme();
editor.onDidChangeCursorPosition(event => $('cursor-position').textContent = `Ln ${event.position.lineNumber}, Col ${event.position.column}`);
editor.onDidChangeModelContent(() => { updateStatus(); validate(); });
editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, save);
window.addEventListener('keydown', event => { if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); $('search').focus(); } if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save(); } });
window.addEventListener('beforeunload', event => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
async function start() {
  try { state.accounts = (await api('/api/accounts')).accounts; renderAccounts(); if (state.accounts.length) await selectAccount(state.accounts[0]); else toast('暂无启用账号，请检查面板后刷新', true); }
  catch (error) { $('accounts').textContent = '无法读取配置'; toast(error.message, true); }
}
start();
