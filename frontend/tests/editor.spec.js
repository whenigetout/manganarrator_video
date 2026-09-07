import {test, expect} from '@playwright/test';

async function setColor(page, color) {
  await page.getByLabel('Spectrum color 1').evaluate((input, value) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
    input.dispatchEvent(new Event('input', {bubbles:true}));
  }, color);
}

test('a delayed frame cannot overwrite a newer edit', async ({page}) => {
  await page.goto('./'); await ready(page);
  await changeFrame(page, () => page.getByLabel('Single color', {exact:true}).check());
  await page.route('**/video/audio/frame', async route => {
    try {
      const response = await route.fetch();
      if(route.request().postDataJSON().config.visualizers[0].colors === '#ff0000') await new Promise(resolve => setTimeout(resolve, 900));
      await route.fulfill({response});
    } catch(e) { /* A superseded browser request may already be aborted. */ }
  });
  const redRequest = page.waitForRequest(r => r.url().endsWith('/frame') && r.postDataJSON().config.visualizers[0].colors === '#ff0000');
  await setColor(page, '#ff0000'); await redRequest;
  await changeFrame(page, () => setColor(page, '#0000ff'));
  const newest = await page.getByTestId('live-frame').getAttribute('src');
  await page.waitForTimeout(1100);
  await expect(page.getByTestId('live-frame')).toHaveAttribute('src', newest);
  await expect(page.getByLabel('Spectrum color 1')).toHaveValue('#0000ff');
});

function recording() {
  const rate = 44100, count = rate * 2;
  const wav = Buffer.alloc(44 + count * 2);
  wav.write('RIFF');wav.writeUInt32LE(wav.length - 8, 4);wav.write('WAVEfmt ', 8);
  wav.writeUInt32LE(16, 16);wav.writeUInt16LE(1, 20);wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(rate, 24);wav.writeUInt32LE(rate * 2, 28);wav.writeUInt16LE(2, 32);wav.writeUInt16LE(16, 34);
  wav.write('data', 36);wav.writeUInt32LE(count * 2, 40);
  for(let i=0;i<count;i++)wav.writeInt16LE(Math.round(14000*Math.sin(2*Math.PI*(i<rate?440:1800)*i/rate)),44+i*2);
  return {name:'Live editor singing.wav',mimeType:'audio/wav',buffer:wav};
}
async function ready(page) {
  await expect(page.locator('[aria-label="Live frame editor"] .stage')).toHaveAttribute('aria-busy','false');
  await expect(page.getByTestId('live-frame')).toBeVisible();
  await expect.poll(()=>page.getByTestId('live-frame').evaluate(img=>img.complete&&img.naturalWidth>0)).toBe(true);
}
async function changeFrame(page, action) {
  const before=await page.getByTestId('live-frame').getAttribute('src');
  await action();
  await expect(page.getByTestId('live-frame')).not.toHaveAttribute('src',before);
  await ready(page);
}
async function pixelHash(page) {
  return page.getByTestId('live-frame').evaluate(img=>{
    const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
    const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);
    const data=ctx.getImageData(0,0,canvas.width,canvas.height).data;
    let hash=2166136261;for(let i=0;i<data.length;i+=4)hash=Math.imul(hash^data[i]^data[i+1]^data[i+2],16777619);
    return hash>>>0;
  });
}

test('live frame changes, metadata, preserved video, mobile and reload', async ({page, request})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  let renders=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/video/build/audio'))renders++;});
  await page.goto('./');await ready(page);
  await expect(page.getByTestId('live-frame')).toHaveJSProperty('naturalWidth',2560);
  await page.locator('input[type=file]').first().setInputFiles(recording());
  await expect(page.getByRole('button',{name:'Preview 5 seconds'})).toBeEnabled();
  await ready(page);
  await changeFrame(page,()=>page.getByRole('spinbutton',{name:'Frame time seconds'}).fill('0.5'));
  const original=await pixelHash(page);
  await changeFrame(page,()=>page.getByLabel('Single color',{exact:true}).check());
  await changeFrame(page,()=>page.getByLabel('Spectrum color 1').evaluate(input=>{
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'#ff0000');
    input.dispatchEvent(new Event('input',{bubbles:true}));
  }));
  expect(await pixelHash(page)).not.toBe(original);
  await changeFrame(page,()=>page.getByLabel('Layout',{exact:true}).selectOption('horizontal'));
  await changeFrame(page,()=>page.getByRole('spinbutton',{name:'Height (px)',exact:true}).fill('200'));
  await changeFrame(page,()=>page.getByLabel('Position',{exact:true}).selectOption('bottom'));
  await changeFrame(page,()=>page.getByLabel('Response scale',{exact:true}).selectOption('lin'));
  await changeFrame(page,()=>page.getByLabel('Visible',{exact:true}).uncheck());
  await changeFrame(page,()=>page.getByLabel('Visible',{exact:true}).check());
  await page.getByRole('tab',{name:'Export',exact:true}).click();
  await changeFrame(page,()=>page.getByLabel('Resolution',{exact:true}).selectOption('1280x720'));
  await expect(page.getByTestId('live-frame')).toHaveJSProperty('naturalWidth',1280);
  expect(renders).toBe(0);
  await page.screenshot({path:'../local_tmp/react-editor-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Preview 5 seconds'}).click();
  await expect(page.getByRole('tab',{name:'Rendered video',exact:true})).toHaveAttribute('aria-selected','true',{timeout:90000});
  const video=page.locator('video');await expect(video).toBeVisible();
  await expect.poll(()=>video.evaluate(v=>v.readyState)).toBeGreaterThanOrEqual(2);
  const job=page.locator('.job').first();
  await expect(job).toContainText('Live editor singing.wav');
  await expect(job).toContainText('1280 x 720');
  await expect(job).toContainText('5-second preview');
  await expect(job).toContainText('preview.mp4');
  await video.evaluate(async v=>{v.muted=true;await v.play();});
  await page.waitForTimeout(350);await video.evaluate(v=>v.pause());
  await page.getByRole('tab',{name:'Live editor',exact:true}).click();await ready(page);
  await page.getByRole('tab',{name:'Rendered video',exact:true}).click();
  await expect(video).toBeVisible();
  const url=await page.locator('.download-link').getAttribute('href');
  expect((await request.get(url)).status()).toBe(200);
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('tab',{name:'Live editor',exact:true}).click();await ready(page);
  await page.screenshot({path:'../local_tmp/react-editor-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  await page.reload();await expect(page.locator('.job').first()).toContainText('Live editor singing.wav');
  expect(errors).toEqual([]);
});
