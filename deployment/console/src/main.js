// Must load before Monaco modules so menus, find widget and command palette use Chinese labels.
import 'monaco-editor/nls/lang/zh-cn.js';
import * as monaco from 'monaco-editor/editor/editor.api.js';
import 'monaco-editor/editor/contrib/clipboard/browser/clipboard.js';
import 'monaco-editor/editor/contrib/find/browser/findController.js';
import 'monaco-editor/editor/contrib/bracketMatching/browser/bracketMatching.js';
import 'monaco-editor/editor/contrib/folding/browser/folding.js';
import 'monaco-editor/editor/contrib/comment/browser/comment.js';
import 'monaco-editor/editor/contrib/multicursor/browser/multicursor.js';
import 'monaco-editor/editor/contrib/linesOperations/browser/linesOperations.js';
import 'monaco-editor/editor/contrib/wordHighlighter/browser/wordHighlighter.js';
import 'monaco-editor/editor/contrib/hover/browser/hoverContribution.js';
import 'monaco-editor/editor/contrib/contextmenu/browser/contextmenu.js';
import 'monaco-editor/editor/contrib/stickyScroll/browser/stickyScrollContribution.js';
import 'monaco-editor/editor/standalone/browser/quickAccess/standaloneGotoLineQuickAccess.js';
import 'monaco-editor/editor/standalone/browser/quickAccess/standaloneCommandsQuickAccess.js';
import 'monaco-editor/languages/definitions/yaml/register.js';
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker';
import { parseDocument } from 'yaml';
import '@fontsource-variable/jetbrains-mono';
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
  redo: '<path d="M20 10h-9a6 6 0 0 0 0 12M20 10l-6-6M20 10l-6 6"/>',
  replace: '<path d="M4 7h11l-3-3M20 17H9l3 3"/>',
  hash: '<path d="M9 4 7 20M17 4l-2 16M4 9h16M3 15h16"/>',
  command: '<path d="M4 6l6 6-6 6M12 19h8"/>',
  fold: '<path d="m7 20 5-5 5 5M7 4l5 5 5-5"/>',
  unfold: '<path d="m7 15 5 5 5-5M7 9l5-5 5 5"/>',
  comment: '<path d="M9 4 5 20M15 12h5M15 7h5M15 17h5"/>',
  sort: '<path d="M4 6h10M4 12h7M4 18h4M18 5v14m-3-3 3 3 3-3"/>',
  braces: '<path d="M8 3H7a2 2 0 0 0-2 2v4a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5a2 2 0 0 0 2 2h1M16 3h1a2 2 0 0 1 2 2v4a2 2 0 0 0 2 2 2 2 0 0 0-2 2v5a2 2 0 0 1-2 2h-1"/>',
  wrap: '<path d="M3 6h18M3 12h15a3 3 0 0 1 0 6h-4m2-3-3 3 3 3M3 18h7"/>',
  minimap: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M15 3v18M7 8h4M7 12h4M7 16h2"/>',
  pilcrow: '<path d="M13 4v16M17 4v16M19 4H9.5a4.5 4.5 0 0 0 0 9H13"/>',
  minus: '<path d="M5 12h14"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  diff: '<path d="M12 3v18M5 8h4M7 6v4M15 8h4M5 16h4M15 16h4"/>',
  iphone: '<rect x="7" y="2" width="10" height="20" rx="2.5"/><path d="M11 18h2"/>',
  mac: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M1.5 20h21"/>',
  router: '<rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 16.5h.01M11 16.5h.01M8 13l-2-6M16 13l2-6M9.5 6.5a4 4 0 0 1 5 0M7.5 4a7 7 0 0 1 9 0"/>',
  person: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  maximize: '<path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/>',
  minimize: '<path d="M9 4v5H4M20 9h-5V4M15 20v-5h5M4 15h5v5"/>',
  logo: '<circle cx="5" cy="12" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 12h1.5c3.5 0 4-6 8.5-6M8.5 12c3.5 0 4 6 8.5 6"/>',
  history: '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1L3.5 8.5"/><path d="M3.5 4v4.5H8M12 7.5V12l3 2"/>',
  chevron: '<path d="m7 10 5 5 5-5"/>',
  sliders: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  lan: '<rect x="9" y="3" width="6" height="5" rx="1.2"/><rect x="3" y="16" width="6" height="5" rx="1.2"/><rect x="15" y="16" width="6" height="5" rx="1.2"/><path d="M12 8v4M6 16v-2a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2"/>',
  outline: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M9 4v16M5.5 8.5h1M5.5 12h1M5.5 15.5h1"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6 6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"/>',
  server: '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/><path d="M7 7.5h.01M7 16.5h.01"/>',
  restore: '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/>',
};
const iconSVG = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]}</svg>`;
for (const element of document.querySelectorAll('[data-icon]')) element.innerHTML = iconSVG(element.dataset.icon);
for (const element of document.querySelectorAll('.app-mark')) element.setAttribute('aria-hidden', 'true');

monaco.languages.register({ id: 'proxy-conf' });
monaco.languages.register({ id: 'private-json' });
monaco.languages.setMonarchTokensProvider('private-json', {
  tokenizer: { root: [[/"(?:[^"\\]|\\.)*"(?=\s*:)/, 'attribute.name'], [/"(?:[^"\\]|\\.)*"/, 'string'],
    [/\b(?:true|false|null)\b/, 'keyword'], [/-?\d+(?:\.\d+)?/, 'number'], [/[{}\[\]:,]/, 'delimiter']] },
});
// Section-aware highlighting: policies are colored by outcome so DIRECT / PROXY / REJECT stand out in rules.
const common = [
  [/^\s*\[Proxy Group\]/, { token: 'section', switchTo: '@groups' }],
  [/^\s*\[Proxy\]/, { token: 'section', switchTo: '@proxies' }],
  [/^\s*\[[^\]]+\]/, { token: 'section', switchTo: '@root' }],
  [/^\s*[#;].*$/, 'comment'],
  [/(?:https?|vmess|vless|trojan|ss):\/\/[^\s,"]+/, 'string.url'],
  [/"[^"]*"/, 'string'],
  [/\bDIRECT\b/, 'policy.direct'], [/\bREJECT(?:-DROP|-TINYGIF|-NO-DROP)?\b/, 'policy.reject'], [/\bPROXY\b/, 'policy.proxy'],
  [/\b(?:DOMAIN(?:-SUFFIX|-KEYWORD|-SET|-WILDCARD)?|IP-CIDR6?|IP-ASN|GEOIP|GEOSITE|RULE-SET|AND|OR|NOT|PROCESS-NAME|PROTOCOL|DEST-PORT|DST-PORT|SRC-IP|SRC-PORT|IN-PORT|USER-AGENT|URL-REGEX|SUBNET|FINAL|MATCH)\b/, 'type'],
  [/\b(?:true|false|no-resolve)\b/, 'keyword'],
  [/\b[A-Z][A-Z0-9_]*(?:-[A-Z0-9_]+)*\b/, 'policy.group'],
  [/[a-z_][\w.-]*/, ''],
  [/\d+(?:\.\d+)*/, 'number'],
  [/[=,]/, 'delimiter'],
];
monaco.languages.setMonarchTokensProvider('proxy-conf', { tokenizer: {
  root: [[/^[\w.-]+(?=\s*=)/, 'attribute.name'], { include: '@common' }],
  proxies: [[/^[^=#;\[\s][^=]*?(?=\s*=)/, 'node.name'], { include: '@common' }],
  groups: [[/^[^=#;\[\s][^=]*?(?=\s*=)/, 'policy.define'], { include: '@common' }],
  common,
} });
monaco.languages.setLanguageConfiguration('proxy-conf', { comments: { lineComment: '#' } });
monaco.languages.registerFoldingRangeProvider('proxy-conf', { provideFoldingRanges(model) {
  const ranges = [], count = model.getLineCount(); let start = 0;
  const close = (end) => { while (end > start && !model.getLineContent(end).trim()) end--; if (start && end > start) ranges.push({ start, end }); };
  for (let line = 1; line <= count; line++) if (/^\s*\[[^\]]+\]/.test(model.getLineContent(line))) { close(line - 1); start = line; }
  close(count); return ranges;
} });
const themeRules = (c) => [
  { token: '', foreground: c.text }, { token: 'comment', foreground: c.comment }, { token: 'section', foreground: c.section, fontStyle: 'bold' },
  { token: 'attribute.name', foreground: c.key }, { token: 'node.name', foreground: c.text, fontStyle: 'bold' },
  { token: 'policy.direct', foreground: c.direct, fontStyle: 'bold' }, { token: 'policy.proxy', foreground: c.proxy, fontStyle: 'bold' },
  { token: 'policy.reject', foreground: c.reject, fontStyle: 'bold' }, { token: 'policy.group', foreground: c.proxy },
  { token: 'policy.define', foreground: c.proxy, fontStyle: 'bold' }, { token: 'type', foreground: c.type },
  { token: 'string.url', foreground: c.url }, { token: 'string', foreground: c.string }, { token: 'number', foreground: c.number },
  { token: 'keyword', foreground: c.keyword }, { token: 'delimiter', foreground: c.delimiter },
  { token: 'type.yaml', foreground: c.key }, { token: 'string.yaml', foreground: c.string }, { token: 'keyword.yaml', foreground: c.keyword },
  { token: 'number.yaml', foreground: c.number }, { token: 'operators.yaml', foreground: c.delimiter },
];
monaco.editor.defineTheme('private-light', { base: 'vs', inherit: true, rules: themeRules({
  text: '1F2633', comment: '8C95A6', section: '4338CA', key: '1D4F91', direct: '0D7A4C', proxy: '6D3FE0', reject: 'C3264B',
  type: '0E7490', url: '6F7C93', string: '9A4F0B', number: 'B45309', keyword: '0369A1', delimiter: 'A0A8B6',
}), colors: {
  'editor.background': '#FFFFFF', 'editor.foreground': '#1F2633', 'editorLineNumber.foreground': '#C3C8D2', 'editorLineNumber.activeForeground': '#4A5263',
  'editor.lineHighlightBackground': '#F5F6F9', 'editor.lineHighlightBorder': '#00000000', 'editor.selectionBackground': '#D9DEFF',
  'editor.inactiveSelectionBackground': '#E8EBF5', 'editorGutter.background': '#FFFFFF', 'editorIndentGuide.background1': '#EDEFF3',
  'editorIndentGuide.activeBackground1': '#D3D8E1', 'editorWhitespace.foreground': '#CFD4DD', 'editorCursor.foreground': '#4F46E5',
  'editorStickyScroll.background': '#FFFFFF', 'editorStickyScrollHover.background': '#F3F4F8', 'editorStickyScroll.shadow': '#0F141E14',
  'scrollbarSlider.background': '#1F263312', 'scrollbarSlider.hoverBackground': '#1F263322', 'scrollbarSlider.activeBackground': '#1F263330',
  'editorOverviewRuler.border': '#00000000', 'editorWidget.background': '#FFFFFF', 'editorWidget.border': '#E3E6EB',
} });
monaco.editor.defineTheme('private-dark', { base: 'vs-dark', inherit: true, rules: themeRules({
  text: 'D5DAE3', comment: '687184', section: 'A9B1FF', key: '8DB8F2', direct: '4CD08F', proxy: 'B7A4FF', reject: 'FF7D95',
  type: '5FCBDB', url: '7D879A', string: 'E9B07A', number: 'F2B266', keyword: '7CC7F2', delimiter: '596274',
}), colors: {
  'editor.background': '#161920', 'editor.foreground': '#D5DAE3', 'editorLineNumber.foreground': '#3E4553', 'editorLineNumber.activeForeground': '#A3AAB8',
  'editor.lineHighlightBackground': '#1C2029', 'editor.lineHighlightBorder': '#00000000', 'editor.selectionBackground': '#3A3F72',
  'editor.inactiveSelectionBackground': '#2A2E45', 'editorGutter.background': '#161920', 'editorIndentGuide.background1': '#232833',
  'editorIndentGuide.activeBackground1': '#3A4150', 'editorWhitespace.foreground': '#363C49', 'editorCursor.foreground': '#8D86FF',
  'editorStickyScroll.background': '#161920', 'editorStickyScrollHover.background': '#1E222B', 'editorStickyScroll.shadow': '#00000066',
  'scrollbarSlider.background': '#FFFFFF12', 'scrollbarSlider.hoverBackground': '#FFFFFF20', 'scrollbarSlider.activeBackground': '#FFFFFF2A',
  'editorOverviewRuler.border': '#00000000', 'editorWidget.background': '#1C2029', 'editorWidget.border': '#2B303B',
} });

const $ = (id) => document.getElementById(id);
// Each account gets a device identity so downloads for the iPhone, Mac and router are hard to mix up.
const devices = {
  iphone: { name: 'iPhone', color: '#2b6cee' }, mac: { name: 'Mac', color: '#8250f0' },
  router: { name: '路由器', color: '#0e9467' }, person: { name: '朋友', color: '#d1810b' },
};
function deviceOf(account) {
  const label = account.label.toLowerCase();
  return label.includes('iphone') ? 'iphone' : /\bmac\b|macbook/.test(label) ? 'mac' : /路由|router/.test(label) ? 'router' : 'person';
}
const appNames = { 'surge.conf': 'Surge', 'mihomo.yaml': 'Mihomo', 'stash.yaml': 'Stash', 'shadowrocket.conf': 'Shadowrocket', 'loon.conf': 'Loon' };
const state = { accounts: [], account: null, client: 'surge', file: 'surge.conf', baseline: '', etag: '', edited: false, loading: false, dirty: false, version: 0 };
const clients = {
  personal: { files: ['personal.json'], title: '个人策略 · 自动合并', help: '设置各组默认选择、个人例外和 Surge Ponte 路径，仅作用于本账号的五种 App。保存前自动备份，公共规则更新会继承这些设置。非 Surge 的 HOME、COMPANY_LAN 仅支持本地访问，远程访问需要另行配置通道。' },
  loon: { files: ['loon.conf'], title: '导入 Loon', help: '下载 loon.conf，在 Loon 中导入本地配置，已包含此账号的节点。规则集放在 [Remote Rule]，由 jsDelivr 提供；Loon 总是先匹配 [Rule] 中的本地规则。策略切换（含按家里 Wi-Fi 自动切换 HOME）时会断开旧连接，让 App 立即经新线路重连。' },
  stash: { files: ['stash.yaml'], title: '导入 Stash', help: '手机 Stash 请导入 stash.yaml。内网规则直接内嵌，公开规则从 CDN 下载；APPLE 默认 DIRECT，可在策略组切换。' },
  lan: { files: ['lan-com.list'], title: '私有内网规则', help: '只填写 DOMAIN,域名 或 DOMAIN-SUFFIX,域名，每行一条，固定直连。保存后同步到你的三个设备配置；不进入 GitHub 或 CDN。WAN、券商及通用规则由 jsDelivr 提供。' },
  surge: { files: ['surge.conf'], title: '导入 Surge', help: '下载 surge.conf，在 Surge 中导入本地配置。公共规则仍由 jsDelivr 提供。' },
  mihomo: { files: ['mihomo.yaml'], title: '导入 Clash / Mihomo', help: '下载 mihomo.yaml，在支持 Mihomo 的客户端中导入本地配置。公共规则经 DIRECT 下载。' },
  shadowrocket: { files: ['shadowrocket.conf', 'node.txt', 'shadowrocket.txt'], title: '导入 Shadowrocket', help: '导入并启用 shadowrocket.conf，文件已包含此账号的节点和分流规则。node.txt 可用于单独导入节点；shadowrocket.txt 是 Base64 节点格式。' },
};
const prefs = { wordWrap: true, minimap: false, whitespace: false, fontSize: 13, outline: true };
try { Object.assign(prefs, JSON.parse(localStorage.getItem('console-editor-prefs') || '{}')); } catch {}
const editorOptions = () => ({
  fontSize: prefs.fontSize, lineHeight: Math.round(prefs.fontSize * 1.75), wordWrap: prefs.wordWrap ? 'on' : 'off',
  minimap: { enabled: prefs.minimap }, renderWhitespace: prefs.whitespace ? 'all' : 'none',
});
const fontFamily = '"JetBrains Mono Variable", "SF Mono", Menlo, Consolas, monospace';
// Shared by the editor and the diff view: quiet chrome, section headers stick while scrolling long rule lists.
const chrome = {
  fontFamily, fontLigatures: false, scrollBeyondLastLine: false, lineNumbersMinChars: 3, lineDecorationsWidth: 12,
  scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10, useShadows: false }, overviewRulerBorder: false,
  hideCursorInOverviewRuler: true, stickyScroll: { enabled: true, defaultModel: 'foldingProviderModel', maxLineCount: 2 },
};
const editor = monaco.editor.create($('editor'), {
  value: '', language: 'proxy-conf', theme: 'private-light', automaticLayout: true, ...chrome,
  padding: { top: 10, bottom: 16 }, renderLineHighlight: 'line', smoothScrolling: true, cursorSmoothCaretAnimation: 'on',
  roundedSelection: true, tabSize: 2, readOnly: true, folding: true, showFoldingControls: 'mouseover',
  guides: { indentation: true, highlightActiveIndentation: true },
  ...editorOptions(),
});
// The bundled code font arrives after Monaco measures glyphs; re-measure so the cursor lines up.
document.fonts?.load(`13px ${fontFamily}`).then(() => monaco.editor.remeasureFonts()).catch(() => {});
let diffEditor = null, originalModel = null;
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
function editableInput() { return ['lan', 'personal'].includes(state.client); }
function setLoading(value) {
  state.loading = value; editor.updateOptions({ readOnly: value || !state.account || !editableInput() }); diffEditor?.updateOptions({ readOnly: value || !state.account || !editableInput() });
  for (const button of document.querySelectorAll('.editor-tools .tool-btn[data-action]')) if (!['outline', 'wrap', 'minimap', 'whitespace', 'font-down', 'font-up', 'fullscreen', 'diff'].includes(button.dataset.action)) button.disabled = value || !state.account;
  $('file-select').disabled = value || !state.account;
  for (const tab of document.querySelectorAll('.client-tab')) tab.disabled = value || !state.account;
  for (const button of document.querySelectorAll('.account')) button.disabled = value;
  updateStatus();
}
function updateStatus() {
  state.dirty = editor.getValue() !== state.baseline;
  $('save-status').className = state.dirty ? 'unsaved' : 'saved';
  $('save-status').innerHTML = `<span class="connection-dot"></span>${state.loading ? '正在处理…' : state.dirty ? '有未保存的编辑' : state.client === 'lan' ? '私有规则 · 已同步' : state.edited ? '旧覆盖 · 只读，待迁移' : editableInput() ? '个人策略 · 已同步' : '自动生成 · 只读'}`;
  $('save').hidden = !editableInput();
  $('save').disabled = state.loading || !state.account || !state.dirty || !editableInput();
  $('restore').disabled = state.loading || !state.account || !state.edited || ['lan', 'personal'].includes(state.client);
  for (const id of ['copy', 'download-file', 'download-account', 'refresh']) $(id).disabled = state.loading || !state.account;
  $('diff-toggle').disabled = !diffEditor && (state.loading || !state.account || !state.dirty);
  $('line-count').textContent = `${editor.getModel().getLineCount()} 行`;
  document.querySelector('[data-action="format"]').disabled = state.loading || !state.account || !state.file.endsWith('.json');
  $('file-origin').textContent = state.client === 'lan' ? 'SSH 私有' : state.edited ? '个人编辑' : '自动生成';
  $('file-origin').classList.toggle('custom', state.edited);
}
// Default policy per group, shown as chips colored by outcome (same colors as the editor).
function renderPolicies(account) {
  const items = account.personal
    ? [['FINAL', account.finalPolicy], ['MICROSOFT', account.defaults.MICROSOFT], ['PAYPAL', account.defaults.PAYPAL]]
    : [['FINAL', account.finalPolicy || (account.businessRules ? 'PROXY' : 'DIRECT')], ['AI', 'PROXY'], ['APPLE', 'DIRECT']];
  $('account-subtitle').replaceChildren(...items.map(([group, policy]) => {
    const chip = document.createElement('span'); chip.className = 'policy'; chip.dataset.tip = `${group} 组默认走 ${policy}`;
    const key = document.createElement('span'); key.className = 'policy-key'; key.textContent = group;
    const value = document.createElement('span'); value.className = 'policy-value ' + (['PROXY', 'DIRECT', 'REJECT'].includes(policy) ? policy.toLowerCase() : 'group'); value.textContent = policy;
    chip.append(key, ' ', value); return chip;
  }));
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
function accountRow(account) {
  const device = deviceOf(account), apps = Object.keys(appNames).filter(name => account.files.includes(name));
  const button = document.createElement('button'); button.className = 'account' + (state.account?.id === account.id ? ' selected' : '');
  button.setAttribute('aria-current', state.account?.id === account.id ? 'true' : 'false'); button.style.setProperty('--device', devices[device].color);
  const avatar = document.createElement('span'); avatar.className = 'avatar device-avatar'; avatar.innerHTML = iconSVG(device);
  const details = document.createElement('span'); details.className = 'account-details';
  const name = document.createElement('strong'); name.textContent = account.label;
  const hint = document.createElement('small'); hint.textContent = `${devices[device].name} · ${apps.length} 个 App`; details.append(name, hint);
  // Mini coverage chart: one bar per app, in tab order, so the router (Mihomo only) is obvious at a glance.
  const coverage = document.createElement('span'); coverage.className = 'coverage';
  coverage.dataset.tip = apps.length ? '已生成：' + apps.map(file => appNames[file]).join('、') : '没有可导入的 App 配置';
  coverage.setAttribute('aria-label', coverage.dataset.tip);
  for (const file of Object.keys(appNames)) { const bar = document.createElement('i'); if (apps.includes(file)) bar.className = 'on'; coverage.append(bar); }
  button.append(avatar, details, coverage); button.onclick = () => selectAccount(account);
  return button;
}
function renderAccounts() {
  const query = $('search').value.trim().toLowerCase(); $('accounts').replaceChildren();
  const filtered = state.accounts.filter(account => account.label.toLowerCase().includes(query));
  for (const [title, mine] of [['我的设备', true], ['朋友', false]]) {
    const members = filtered.filter(account => (deviceOf(account) !== 'person') === mine)
      .sort((a, b) => Number(b.id === '4dda2b1a6e3d4a4173942cc9' || b.label === '我的路由器') - Number(a.id === '4dda2b1a6e3d4a4173942cc9' || a.label === '我的路由器'));
    if (!members.length) continue;
    const heading = document.createElement('div'); heading.className = 'side-group';
    const label = document.createElement('span'); label.textContent = title;
    const count = document.createElement('span'); count.textContent = members.length; heading.append(label, count);
    $('accounts').append(heading, ...members.map(accountRow));
  }
  if (!filtered.length) { const empty = document.createElement('div'); empty.className = 'placeholder'; empty.textContent = '没有匹配的账号'; $('accounts').append(empty); }
  $('account-count').textContent = state.accounts.length;
}
async function selectAccount(account) {
  if (state.loading || !confirmDiscard()) return;
  state.account = account;
  $('personal-tab').hidden = !account.personal; $('version-bar').hidden = !account.personal; closePopovers();
  for (const tab of document.querySelectorAll('.client-tab')) tab.hidden = !clientAvailable(tab.dataset.client, account);
  $('tab-divider').hidden = $('personal-tab').hidden && $('lan-tab').hidden;
  if (!clientAvailable(state.client, account)) state.client = ['surge', 'mihomo', 'stash', 'shadowrocket', 'loon', 'personal', 'lan'].find(client => clientAvailable(client, account));
  if (!availableFiles(state.client, account).includes(state.file)) state.file = availableFiles(state.client, account)[0];
  const device = deviceOf(account);
  document.documentElement.style.setProperty('--device', devices[device].color); document.documentElement.dataset.device = device;
  $('device-chip').hidden = false; $('device-chip').textContent = devices[device].name;
  $('account-avatar').innerHTML = iconSVG(device); $('account-avatar').title = devices[device].name;
  $('download-account-label').textContent = '下载「' + account.label + '」文件包';
  updateClient(); $('account-title').textContent = account.label; document.title = account.label + ' · DMIT 私有配置台';
  $('node-names').textContent = account.nodes.join(' · ');
  renderPolicies(account);
  $('rules-scope').lastChild.textContent = account.personal ? '个人策略 · 公共 + 专项规则' : account.businessRules ? '公共 + 个人专项规则' : '公共分流规则';
  renderAccounts(); await loadFile(); if (account.personal && state.account?.id === account.id) await loadVersions();
}
async function loadFile() {
  const version = ++state.version; setLoading(true);
  try {
    const result = await api(fileURL()); if (version !== state.version) return;
    closeDiff();
    state.baseline = result.content; state.etag = result.etag; state.edited = result.edited;
    monaco.editor.setModelLanguage(editor.getModel(), languageOf(state.file));
    editor.setValue(result.content); editor.setPosition({ lineNumber: 1, column: 1 }); editor.revealLine(1);
    $('language-label').textContent = state.client === 'lan' ? 'DOMAIN RULES' : state.file.endsWith('.json') ? 'JSON' : state.file.endsWith('.yaml') ? 'YAML' : state.file.endsWith('.conf') ? 'Proxy INI' : 'TEXT';
    validate(); renderOutline();
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
  if (!editableInput() || !state.account || !state.dirty || state.loading) return false;
  if (!validate()) { toast('请先修复配置语法问题', true); return false; }
  setLoading(true);
  try {
    const result = await api(fileURL(), { method: 'PUT', body: JSON.stringify({ content: editor.getValue(), etag: state.etag }) });
    state.baseline = result.content; state.etag = result.etag; state.edited = state.client !== 'personal'; originalModel?.setValue(result.content);
    if (state.client === 'personal') {
      state.accounts = (await api('/api/accounts')).accounts; state.account = state.accounts.find(a => a.id === state.account.id);
      renderPolicies(state.account);
    }
    if (state.account.personal) await loadVersions();
    toast(state.client === 'personal' ? '个人策略已保存，五种 App 已重新生成，旧版本已备份' : state.client === 'lan' ? '内网规则已保存，已同步到你的设备配置' : '编辑已保存，定时生成会保留此文件的个人版本'); return true;
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
    option.textContent = `${new Date(item.created_ns / 1e6).toLocaleString('zh-CN', { hour12: false })} · ${item.digest.slice(0, 8)}`; return option;
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
  if (!window.confirm('先备份当前配置，再恢复此版本的各 App 输出（早于 Loon 支持的版本不含 Loon，Loon 保持当前配置）。恢复后作为整文件覆盖保留；恢复默认可重新采用个人策略生成的配置。')) return;
  const identifier = state.account.id, version = $('version-select').value; setLoading(true);
  try {
    const result = await api(`/api/accounts/${identifier}/versions/${version}/restore`, { method: 'POST', body: JSON.stringify({ etag: state.versionEtag }) });
    state.accounts = result.accounts; state.dirty = false; setLoading(false); await selectAccount(state.accounts.find(a => a.id === identifier)); toast('已回滚各 App 配置，回滚前版本已备份');
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
$('download-file').onclick = () => {
  // The account name in the file name keeps an iPhone profile from being imported on the Mac by mistake.
  const name = state.client === 'lan' ? state.file : state.account.label + '-' + state.file;
  download(editor.getValue(), name); toast(state.dirty ? '已下载「' + state.account.label + '」的当前编辑内容，服务器版本尚未保存' : '已下载「' + state.account.label + '」的 ' + state.file);
};
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
let theme = 'light';
try { theme = localStorage.getItem('console-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); } catch {}
function applyTheme() {
  document.documentElement.dataset.theme = theme; monaco.editor.setTheme(theme === 'dark' ? 'private-dark' : 'private-light');
  $('theme').setAttribute('aria-label', theme === 'dark' ? '切换浅色主题' : '切换深色主题'); $('theme').dataset.tip = $('theme').getAttribute('aria-label'); $('theme').removeAttribute('title');
  $('theme').firstChild.innerHTML = iconSVG(theme === 'dark' ? 'sun' : 'moon');
}
$('theme').onclick = () => { theme = theme === 'light' ? 'dark' : 'light'; try { localStorage.setItem('console-theme', theme); } catch {} applyTheme(); }; applyTheme();
const activeEditor = () => diffEditor?.getModifiedEditor() || editor;
function updateCursor() {
  const target = activeEditor(), position = target.getPosition(), model = target.getModel();
  if (!position || !model) return;
  const selected = target.getSelections().reduce((total, range) => total + model.getValueLengthInRange(range), 0);
  $('cursor-position').textContent = `Ln ${position.lineNumber}, Col ${position.column}${selected ? ` · 已选 ${selected}` : ''}`;
}
function savePrefs() {
  try { localStorage.setItem('console-editor-prefs', JSON.stringify(prefs)); } catch {}
  editor.updateOptions(editorOptions()); diffEditor?.updateOptions(editorOptions());
  $('wrap-toggle').setAttribute('aria-pressed', String(prefs.wordWrap));
  $('minimap-toggle').setAttribute('aria-pressed', String(prefs.minimap));
  $('whitespace-toggle').setAttribute('aria-pressed', String(prefs.whitespace));
  $('outline-toggle').setAttribute('aria-pressed', String(prefs.outline)); document.querySelector('.editor-card').classList.toggle('no-outline', !prefs.outline);
  $('font-size').textContent = prefs.fontSize;
}
function languageOf(file) { return file.endsWith('.json') ? 'private-json' : file.endsWith('.yaml') ? 'yaml' : file === 'shadowrocket.txt' ? 'plaintext' : 'proxy-conf'; }
function openDiff() {
  if (!state.account || diffEditor) return;
  originalModel = monaco.editor.createModel(state.baseline, languageOf(state.file));
  $('diff-editor').hidden = false; $('editor').hidden = true;
  diffEditor = monaco.editor.createDiffEditor($('diff-editor'), {
    automaticLayout: true, originalEditable: false, readOnly: state.loading || !editableInput(), renderSideBySide: true, useInlineViewWhenSpaceIsLimited: true,
    ...chrome, ...editorOptions(),
  });
  diffEditor.setModel({ original: originalModel, modified: editor.getModel() });
  diffEditor.getModifiedEditor().onDidChangeCursorSelection(updateCursor);
  diffEditor.getModifiedEditor().onDidScrollChange(trackOutline);
  diffEditor.getModifiedEditor().addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, save);
  $('diff-toggle').setAttribute('aria-pressed', 'true'); $('diff-toggle').lastChild.textContent = '返回编辑';
  diffEditor.getModifiedEditor().focus(); updateStatus();
}
function closeDiff() {
  if (!diffEditor) return;
  const position = diffEditor.getModifiedEditor().getPosition();
  diffEditor.setModel(null); diffEditor.dispose(); originalModel.dispose(); diffEditor = originalModel = null;
  $('diff-editor').replaceChildren(); $('diff-editor').hidden = true; $('editor').hidden = false;
  $('diff-toggle').setAttribute('aria-pressed', 'false'); $('diff-toggle').lastChild.textContent = '对比改动';
  if (position) editor.setPosition(position);
  editor.focus(); updateStatus();
}
function setFullscreen(on) {
  const card = document.querySelector('.editor-card');
  if (on === card.classList.contains('fullscreen')) return;
  card.classList.toggle('fullscreen', on); document.body.classList.toggle('editor-fullscreen', on);
  $('fullscreen').setAttribute('aria-pressed', String(on));
  $('fullscreen').firstChild.innerHTML = iconSVG(on ? 'minimize' : 'maximize'); $('fullscreen').setAttribute('aria-label', on ? '退出全屏' : '全屏'); $('fullscreen').dataset.tip = on ? '退出全屏 (Esc)' : '全屏编辑 (⌘/Ctrl+Shift+Enter，Esc 退出)'; hideTip();
  if (on) document.documentElement.requestFullscreen?.().catch(() => {});
  else if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  activeEditor().focus();
}
function formatJSON() {
  const target = activeEditor();
  try {
    const text = JSON.stringify(JSON.parse(target.getValue()), null, 2) + '\n';
    if (text === target.getValue()) return toast('JSON 已是标准格式');
    target.pushUndoStop(); target.executeEdits('format', [{ range: target.getModel().getFullModelRange(), text }]); target.pushUndoStop();
  } catch (error) { toast(`无法格式化：${error.message}`, true); }
}
// Instant Chinese tooltips; a fixed element avoids clipping by the scrollable toolbar.
const tooltip = document.createElement('div'); tooltip.id = 'tooltip'; tooltip.setAttribute('role', 'tooltip'); document.body.append(tooltip);
for (const element of document.querySelectorAll('button[title], .file-picker[title], .meta-item[title]')) { element.dataset.tip = element.title; element.removeAttribute('title'); }
function showTip(element) {
  const rect = element.getBoundingClientRect(); tooltip.textContent = element.dataset.tip; tooltip.className = 'visible';
  const width = tooltip.offsetWidth, below = rect.bottom + 8 + tooltip.offsetHeight < innerHeight;
  tooltip.style.left = `${Math.min(Math.max(8, rect.left + rect.width / 2 - width / 2), innerWidth - width - 8)}px`;
  tooltip.style.top = `${below ? rect.bottom + 8 : rect.top - tooltip.offsetHeight - 8}px`;
}
const hideTip = () => { tooltip.className = ''; };
document.addEventListener('pointerover', event => { const element = event.target.closest?.('[data-tip]'); element ? showTip(element) : hideTip(); });
document.addEventListener('focusin', event => { const element = event.target.closest?.('[data-tip]'); if (element?.matches(':focus-visible')) showTip(element); });
for (const type of ['focusout', 'pointerdown', 'scroll']) document.addEventListener(type, hideTip, true);
const tools = {
  undo: () => activeEditor().trigger('toolbar', 'undo'), redo: () => activeEditor().trigger('toolbar', 'redo'),
  find: () => activeEditor().getAction('actions.find').run(), replace: () => activeEditor().getAction(editableInput() ? 'editor.action.startFindReplaceAction' : 'actions.find').run(),
  goto: () => activeEditor().getAction('editor.action.gotoLine').run(), palette: () => activeEditor().getAction('editor.action.quickCommand').run(),
  fold: () => activeEditor().getAction('editor.foldAll').run(), unfold: () => activeEditor().getAction('editor.unfoldAll').run(),
  comment: () => activeEditor().getAction('editor.action.commentLine').run(), sort: () => activeEditor().getAction('editor.action.sortLinesAscending').run(),
  format: () => state.file.endsWith('.json') ? formatJSON() : toast('仅 JSON 文件支持格式化', true),
  wrap: () => { prefs.wordWrap = !prefs.wordWrap; savePrefs(); }, minimap: () => { prefs.minimap = !prefs.minimap; savePrefs(); },
  whitespace: () => { prefs.whitespace = !prefs.whitespace; savePrefs(); }, outline: () => { prefs.outline = !prefs.outline; savePrefs(); },
  'font-down': () => { prefs.fontSize = Math.max(10, prefs.fontSize - 1); savePrefs(); }, 'font-up': () => { prefs.fontSize = Math.min(24, prefs.fontSize + 1); savePrefs(); },
  diff: () => diffEditor ? closeDiff() : openDiff(),
  fullscreen: () => setFullscreen(!document.querySelector('.editor-card').classList.contains('fullscreen')),
};
for (const button of document.querySelectorAll('.editor-tools .tool-btn[data-action]')) {
  button.onmousedown = event => event.preventDefault();
  button.onclick = () => { const action = tools[button.dataset.action]; if (!button.disabled && action) { action(); if (!['diff', 'fullscreen'].includes(button.dataset.action)) activeEditor().focus(); } };
}
// Right-click menu entries (groups sort after Monaco's cut/copy/paste and command palette).
const menuActions = [
  ['console.save', '保存编辑', '1_console', [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS], save],
  ['console.diff', '与已保存版本对比', '1_console', [], tools.diff],
  ['console.fullscreen', '切换全屏编辑', '1_console', [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.Enter], tools.fullscreen],
  ['console.format', '格式化 JSON', '2_edit', [monaco.KeyMod.Shift | monaco.KeyMod.Alt | monaco.KeyCode.KeyF], tools.format],
  ['console.sort', '排序行（升序）', '2_edit', [], tools.sort],
  ['console.fold', '折叠全部', '3_view', [], tools.fold],
  ['console.unfold', '展开全部', '3_view', [], tools.unfold],
  ['console.wrap', '切换自动换行', '3_view', [monaco.KeyMod.Alt | monaco.KeyCode.KeyZ], tools.wrap],
  ['console.minimap', '切换代码缩略图', '3_view', [], tools.minimap],
  ['console.whitespace', '切换空白字符显示', '3_view', [], tools.whitespace],
  ['console.outline', '切换配置大纲', '3_view', [], tools.outline],
  ['console.copy-all', '复制全文', '4_file', [], () => $('copy').click()],
  ['console.download', '下载当前文件', '4_file', [], () => $('download-file').click()],
];
menuActions.forEach(([id, label, contextMenuGroupId, keybindings, run], index) =>
  editor.addAction({ id, label, keybindings, contextMenuGroupId, contextMenuOrder: index, run: () => run() }));
document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement) setFullscreen(false); });
savePrefs();
editor.onDidChangeCursorSelection(updateCursor);
let outlineTimer;
editor.onDidChangeModelContent(() => { updateStatus(); validate(); clearTimeout(outlineTimer); outlineTimer = setTimeout(renderOutline, 200); });
editor.onDidScrollChange(trackOutline);
editor.onDidChangeCursorPosition(trackOutline);
window.addEventListener('keydown', event => { if (event.key === 'Escape' && openPopover) { closePopovers(true); return; } if (event.key === 'Escape' && !event.defaultPrevented && document.querySelector('.editor-card.fullscreen')) { setFullscreen(false); return; } if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key === 'Enter' && !event.defaultPrevented) { event.preventDefault(); tools.fullscreen(); return; } if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); $('search').focus(); } if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save(); } });
window.addEventListener('beforeunload', event => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
// Outline: one entry per [Section], top-level YAML key or JSON key, sized by how many entries it holds.
// Rule lists without sections (private LAN rules) get a breakdown by rule type instead.
let outline = [];
function sections(model, file) {
  const lines = model.getLinesContent(), found = [];
  const pattern = file.endsWith('.conf') ? /^\s*\[([^\]]+)\]/ : file.endsWith('.yaml') ? /^([A-Za-z][\w-]*):\s*(?:#.*)?$/ : file.endsWith('.json') ? /^ {2}"([^"]+)":\s*(.*?),?$/ : null;
  if (!pattern) {
    const types = new Map();
    lines.forEach((text, index) => { const type = /^\s*([A-Z][A-Z0-9-]+),/.exec(text)?.[1]; if (type) { const entry = types.get(type) || { name: type, line: index + 1, end: index + 1, count: 0 }; entry.count++; entry.end = index + 1; types.set(type, entry); } });
    return [...types.values()].map(entry => ({ ...entry, kind: 'type' }));
  }
  lines.forEach((text, index) => {
    const match = pattern.exec(text); if (!match) return;
    const scalar = file.endsWith('.json') && match[2] && !/^[[{]/.test(match[2]) ? match[2].replace(/^"|"$/g, '') : null;
    found.push({ name: match[1], line: index + 1, value: scalar });
  });
  if (file.endsWith('.yaml') && found.length && found[0].line > 1 && lines.slice(0, found[0].line - 1).some(text => text.trim() && !text.trimStart().startsWith('#'))) found.unshift({ name: '基础设置', line: 1 });
  found.forEach((section, index) => {
    section.end = (found[index + 1]?.line ?? lines.length + 1) - 1;
    const body = lines.slice(section.line, section.end);
    // YAML: list items or child keys (proxies, providers); INI: non-comment lines (rules, groups, nodes).
    const items = body.filter(text => /^ {2}- ?/.test(text)).length, keys = body.filter(text => /^ {2}[^\s#-][^:]*:/.test(text)).length;
    section.count = section.value != null ? null : file.endsWith('.yaml') && (items || keys) ? items || keys
      : body.filter(text => text.trim() && !/^\s*[#;]/.test(text) && !/^\s*[\]}],?$/.test(text)).length;
  });
  return found;
}
function renderOutline() {
  outline = sections(editor.getModel(), state.file);
  const max = Math.max(1, ...outline.map(section => section.count || 0)), types = outline[0]?.kind === 'type';
  $('outline').firstChild.firstChild.textContent = types ? '规则构成' : '大纲';
  $('outline-total').textContent = !outline.length ? '' : types ? `${outline.reduce((total, entry) => total + entry.count, 0)} 条` : `${outline.length} 节`;
  if (!outline.length) {
    const empty = document.createElement('li'); empty.className = 'outline-empty'; empty.textContent = '此文件没有分节';
    $('outline-list').replaceChildren(empty); return;
  }
  $('outline-list').replaceChildren(...outline.map(section => {
    const item = document.createElement('li'), button = document.createElement('button'); button.className = 'outline-item';
    button.dataset.tip = types ? `${section.name} · ${section.count} 条，跳到第 ${section.line} 行` : section.count == null ? `第 ${section.line} 行 · ${section.value}` : `第 ${section.line}–${section.end} 行 · ${section.count} 项`;
    const row = document.createElement('span'); row.className = 'outline-row';
    const name = document.createElement('span'); name.className = 'outline-name'; name.textContent = section.name;
    const count = document.createElement('span'); count.className = 'outline-count' + (section.count == null ? ' value' : ''); count.textContent = section.count ?? section.value;
    row.append(name, count); button.append(row);
    if (section.count != null) {
      const bar = document.createElement('span'); bar.className = 'outline-bar'; const fill = document.createElement('span');
      fill.style.width = `${Math.max(4, Math.round(section.count / max * 100))}%`; bar.append(fill); button.append(bar);
    }
    button.onmousedown = event => event.preventDefault();
    button.onclick = () => { const target = activeEditor(); target.setPosition({ lineNumber: section.line, column: 1 }); target.revealLineNearTop(section.line, monaco.editor.ScrollType.Smooth); target.focus(); trackOutline(); };
    item.append(button); return item;
  }));
  trackOutline();
}
// Highlight the section holding the cursor while it is on screen, otherwise the one at the top of the view.
function trackOutline() {
  if (!outline.length || outline[0].kind === 'type') return;
  const target = activeEditor(), range = target.getVisibleRanges()[0], cursor = target.getPosition()?.lineNumber || 1;
  const line = !range || (cursor >= range.startLineNumber && cursor <= range.endLineNumber) ? cursor : range.startLineNumber;
  const index = Math.max(0, outline.findLastIndex(section => section.line <= line));
  document.querySelectorAll('.outline-item').forEach((item, position) => item.classList.toggle('active', position === index));
}
// Popovers for version history and import help; one open at a time, closed by Esc or an outside click.
let openPopover = null;
function closePopovers(refocus = false) {
  if (!openPopover) return;
  const trigger = openPopover; openPopover = null;
  trigger.setAttribute('aria-expanded', 'false'); $(trigger.getAttribute('aria-controls')).hidden = true;
  if (refocus) trigger.focus();
}
for (const trigger of [$('version-toggle'), $('help-toggle')]) trigger.onclick = () => {
  const open = openPopover === trigger; closePopovers(); if (open) return;
  openPopover = trigger; trigger.setAttribute('aria-expanded', 'true'); $(trigger.getAttribute('aria-controls')).hidden = false; hideTip();
};
document.addEventListener('pointerdown', event => { if (openPopover && !openPopover.parentElement.contains(event.target)) closePopovers(); });
async function start() {
  try { state.accounts = (await api('/api/accounts')).accounts; renderAccounts(); if (state.accounts.length) await selectAccount(state.accounts[0]); else toast('暂无启用账号，请检查面板后刷新', true); }
  catch (error) { $('accounts').textContent = '无法读取配置'; toast(error.message, true); }
}
start();
