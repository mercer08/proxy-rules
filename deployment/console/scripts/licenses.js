import { readFileSync, writeFileSync } from 'node:fs';
const notices = ['monaco-editor/LICENSE', 'monaco-editor/ThirdPartyNotices.txt', 'yaml/LICENSE'];
writeFileSync('dist/THIRD-PARTY-NOTICES.txt', notices.map(path => `=== ${path} ===\n${readFileSync('node_modules/' + path, 'utf8')}\n`).join('\n'));
