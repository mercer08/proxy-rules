import { test, expect } from '@playwright/test';

test('a user click from another site opens the console and its same-origin API', async ({ page }) => {
  await page.goto('http://localhost:8766/');
  await page.setContent('<a href="http://127.0.0.1:8766/">Open console</a>');
  const navigation = page.waitForRequest(request =>
    request.isNavigationRequest() && request.url() === 'http://127.0.0.1:8766/');
  await page.getByRole('link', { name: 'Open console' }).click();
  const headers = await (await navigation).allHeaders();
  expect(headers['sec-fetch-site']).toBe('cross-site');
  expect(headers['sec-fetch-mode']).toBe('navigate');
  expect(headers['sec-fetch-dest']).toBe('document');
  expect(headers['sec-fetch-user']).toBe('?1');
  await expect(page.locator('#account-title')).toHaveText('我的电脑');
  await expect(page.locator('.monaco-editor')).toBeVisible();
});

test('select clients, highlight, edit, preserve, restore, download and use mobile layout', async ({ page }, testInfo) => {
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  await page.goto('/');
  await expect(page.locator('#account-title')).toHaveText('我的电脑');
  await expect(page.locator('#save-status')).toContainText('自动生成');
  await expect(page.locator('.monaco-editor')).toBeVisible();
  await expect(page.locator('.view-lines .mtk1').first()).toBeVisible();
  const getFile = () => page.evaluate(async () => {
    const accounts = await (await fetch('/api/accounts')).json();
    return (await fetch(`/api/accounts/${accounts.accounts[0].id}/files/surge.conf`)).json();
  });
  const original = await getFile();
  await page.locator('.monaco-editor').click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+End' : 'Control+End');
  await page.keyboard.type('\n# private editor smoke test');
  await expect(page.locator('#save')).toBeEnabled();
  await page.locator('#save').click();
  await expect(page.locator('#save-status')).toContainText('已保存个人编辑');
  expect((await getFile()).content).toContain('private editor smoke test');
  await page.locator('#refresh').click();
  await expect(page.locator('#save-status')).toContainText('已保存个人编辑');
  const downloadEvent = page.waitForEvent('download');
  await page.locator('#download-account').click();
  expect((await downloadEvent).suggestedFilename()).toBe('我的电脑.zip');
  page.once('dialog', dialog => dialog.accept());
  await page.locator('#restore').click();
  await expect(page.locator('#save-status')).toContainText('自动生成');
  expect((await getFile()).content).toBe(original.content);
  await page.getByRole('tab', { name: 'Clash / Mihomo' }).click();
  await expect(page.locator('#language-label')).toHaveText('YAML');
  await expect(page.locator('#validation-status')).toHaveText('YAML 语法通过');
  await page.getByRole('tab', { name: 'Shadowrocket' }).click();
  await page.locator('#file-select').selectOption('node.txt');
  await expect(page.locator('#language-label')).toHaveText('TEXT');
  await expect(page.locator('#editor')).toContainText('vmess://');
  await page.locator('#search').fill('演示');
  await page.locator('.account').click();
  await expect(page.locator('#account-title')).toHaveText('演示账号');
  await page.locator('#search').fill('');
  await page.getByRole('button', { name: '切换深色主题' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('button', { name: '切换浅色主题' }).click();
  await page.getByRole('tab', { name: 'Surge', exact: true }).click();
  await page.screenshot({ path: testInfo.outputPath('desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: testInfo.outputPath('mobile.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
  expect(requests.every(url => url.startsWith('http://127.0.0.1:8766/') || url.startsWith('blob:'))).toBeTruthy();
});
