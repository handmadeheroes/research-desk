import {test,expect} from '@playwright/test';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import path from 'node:path';

test.beforeEach(async({page})=>{
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await page.locator('#login-password').fill(fs.readFileSync('.test-data/.test-password','utf8'));
  await page.getByRole('button',{name:'Open workspace',exact:true}).click();
  await expect(page.locator('.grid-stack-item')).toHaveCount(6);
  page.on('dialog',dialog=>dialog.accept());
});

test('dashboard drag, resize, save and reset persist across reloads',async({page})=>{
  const original=(await(await page.request.get('/api/bootstrap')).json()).layout;
  await page.getByRole('button',{name:'Edit dashboard',exact:true}).click();
  const card=page.locator('[gs-id="portfolio"]');
  const grip=await card.locator('.card-head').boundingBox();
  await page.mouse.move(grip.x+80,grip.y+18);
  await page.mouse.down();
  await page.mouse.move(grip.x-480,grip.y+18,{steps:20});
  await page.mouse.up();
  const handle=card.locator('.ui-resizable-se');
  await handle.hover();
  const box=await handle.boundingBox();
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
  await page.mouse.down();
  await page.mouse.move(box.x+box.width/2,box.y+box.height/2+90,{steps:15});
  await page.mouse.up();
  const [response]=await Promise.all([
    page.waitForResponse(r=>r.url().endsWith('/api/layout')&&r.request().method()==='PUT'),
    page.getByRole('button',{name:'Save layout',exact:true}).click()
  ]);
  expect(response.ok(),JSON.stringify(await response.json())).toBeTruthy();
  await expect(page.getByRole('button',{name:'Edit dashboard',exact:true})).toBeVisible();
  const saved=(await(await page.request.get('/api/bootstrap')).json()).layout;
  expect(saved).not.toEqual(original);
  expect(saved.find(x=>x.id==='portfolio').x).toBeLessThan(8);
  expect(saved.find(x=>x.id==='portfolio').h).toBeGreaterThan(6);
  await page.reload();
  await expect(page.locator('.grid-stack-item')).toHaveCount(6);
  expect((await(await page.request.get('/api/bootstrap')).json()).layout).toEqual(saved);
  await page.getByRole('button',{name:'Edit dashboard',exact:true}).click();
  await page.getByRole('button',{name:'Reset',exact:true}).click();
  const reset=(await(await page.request.get('/api/bootstrap')).json()).layout;
  expect(reset.find(x=>x.id==='portfolio').x).toBe(8);
});

test('stock add, edit, manual price and remove work through the UI',async({page})=>{
  await page.locator('[data-nav="portfolio"]').click();
  await page.getByRole('button',{name:'Add stock',exact:true}).click();
  await page.getByLabel('Ticker symbol', {exact:true}).fill('QATEST');
  await page.getByLabel('List',{exact:true}).selectOption('holding');
  await page.getByLabel('Number of shares',{exact:true}).fill('3');
  await page.getByLabel('Average cost per share (optional)',{exact:true}).fill('10');
  await page.locator('#stock-form button[type="submit"]').click();
  const row=page.locator('tr').filter({has:page.locator('.stock-symbol',{hasText:'QATEST'})});
  await expect(row).toBeVisible();
  await page.getByRole('button',{name:'Edit QATEST',exact:true}).click();
  await page.getByLabel('Notes',{exact:true}).fill('A synthetic browser-test holding.');
  await page.locator('#stock-form button[type="submit"]').click();
  await page.getByRole('button',{name:'Set price for QATEST',exact:true}).click();
  await page.getByLabel('Price in USD',{exact:true}).fill('12');
  await page.getByLabel('Previous close (optional)',{exact:true}).fill('11');
  await page.locator('#price-form button[type="submit"]').click();
  await expect(row).toContainText('$12.00');
  await expect(row).toContainText('+9.09%');
  const stocks=(await(await page.request.get('/api/stocks')).json()).stocks;
  expect(stocks.find(s=>s.symbol==='QATEST').notes).toContain('synthetic');
  await page.getByRole('button',{name:'Remove QATEST',exact:true}).click();
  await expect(page.locator('.stock-symbol',{hasText:'QATEST'})).toHaveCount(0);
});

test('file import, search, safe rendering, task and Markdown download',async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.locator('#file-input').setInputFiles({
    name:'qa-cloud-evidence.md',mimeType:'text/markdown',
    buffer:Buffer.from('# QACloudEvidence\n\nMicrosoft cloud earnings source for a synthetic workflow test.\n\n<button data-action="delete-stock" data-id="bad">Untrusted action</button><script>window.bad=true</script>')
  });
  await expect.poll(async()=>(await(await page.request.get('/api/documents?q=QACloudEvidence')).json()).total).toBe(1);
  await page.locator('#global-search').fill('QACloudEvidence');
  await page.locator('#global-search').press('Enter');
  await page.getByRole('button',{name:'qa-cloud-evidence',exact:true}).click();
  await expect(page.locator('.markdown')).toContainText('Microsoft cloud earnings');
  await expect(page.locator('.markdown button,.markdown [data-action],.markdown script')).toHaveCount(0);
  expect(await page.evaluate(()=>window.bad)).toBeUndefined();
  const [download]=await Promise.all([page.waitForEvent('download'),page.getByRole('link',{name:'Markdown',exact:true}).click()]);
  expect(download.suggestedFilename()).toContain('.md');
  await page.getByRole('button',{name:'Add review task',exact:true}).click();
  await page.getByLabel('Task',{exact:true}).fill('QA review linked evidence');
  await page.locator('#task-form button[type="submit"]').click();
  await page.locator('[data-nav="calendar"]').click();
  await expect(page.locator('.task-title',{hasText:'QA review linked evidence'}).first()).toBeVisible();
  const tasks=(await(await page.request.get('/api/tasks')).json()).filter(t=>t.title==='QA review linked evidence');
  expect(tasks[0].document_id).toBeTruthy();
  const ics=await page.request.get('/api/calendar.ics');
  expect(await ics.text()).toContain('QA review linked evidence');
  expect(errors).toEqual([]);
});

test('ChatGPT migration selects research and excludes unrelated conversations',async({page})=>{
  const make=(id,title,text)=>({id,title,create_time:1729000000,mapping:{
    first:{parent:null,message:{author:{role:'user'},create_time:1729000000,content:{parts:['Research '+title]}}},
    second:{parent:'first',message:{author:{role:'assistant'},create_time:1729000001,content:{parts:[text]}}}
  }});
  const content=[make('qa-ai-research','QAImportedResearch','Cloud investment analysis with source references.'),
    make('qa-personal-chat','QAPersonalExcluded','Unrelated private recipe.')];
  await page.locator('#file-input').setInputFiles({name:'qa-conversations.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(content))});
  await expect(page.getByRole('heading',{name:'Review your ChatGPT import',exact:true})).toBeVisible();
  await page.locator('[data-conversation="qa-personal-chat"]').uncheck();
  await page.getByRole('button',{name:'Import selected research',exact:true}).click();
  await expect.poll(async()=>(await(await page.request.get('/api/documents?q=QAImportedResearch')).json()).total).toBe(1);
  expect((await(await page.request.get('/api/documents?q=QAPersonalExcluded')).json()).total).toBe(0);
  await page.locator('#global-search').fill('QAImportedResearch');await page.locator('#global-search').press('Enter');
  await page.getByRole('button',{name:'QAImportedResearch',exact:true}).click();
  await expect(page.locator('.badge.ai')).toContainText('AI-generated research');
  await expect(page.locator('.markdown')).toContainText('Parent: first');
});

test('connections, explicit profile, dot CLI, and narrow viewport',async({page})=>{
  await page.locator('[data-nav="connections"]').click();
  await page.getByRole('button',{name:'Add connection',exact:true}).first().click();
  await page.getByLabel('Source name',{exact:true}).fill('QA manual source');
  await page.getByLabel('Connection type',{exact:true}).selectOption('manual');
  await page.locator('#source-form button[type="submit"]').click();
  await expect(page.locator('.connection-card',{hasText:'QA manual source'})).toBeVisible();
  await page.locator('[data-nav="settings"]').click();
  await page.getByLabel('Research instructions',{exact:true}).fill('QA profile: always cite saved original evidence.');
  await page.locator('#settings-form button[type="submit"]').click();
  await expect(page.getByText('Preferences saved.',{exact:true})).toBeVisible();
  const env={...process.env,RD_DATA_DIR:path.resolve('.test-data/e2e-run'),RD_PORT:'8407'};
  const result=JSON.parse(execFileSync('.venv/bin/research-desk-agent',['call','search_library','--json','{"query":"QACloudEvidence"}'],{env,encoding:'utf8'}));
  expect(result.total).toBe(1);
  const logs=(await(await page.request.get('/api/activity')).json());
  expect(logs.some(a=>a.actor==='Dot'&&a.action==='Searched research library')).toBeTruthy();
  await page.setViewportSize({width:390,height:844});
  await page.locator('[data-nav="overview"]').click();
  await expect(page.locator('.grid-stack-item')).toHaveCount(6);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2)).toBeTruthy();
});
