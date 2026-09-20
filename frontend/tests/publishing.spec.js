import {test,expect} from '@playwright/test';

function audio(){
  const rate=8000,count=rate;
  const b=Buffer.alloc(44+count*2);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(rate,24);b.writeUInt32LE(rate*2,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(count*2,40);
  for(let i=0;i<count;i++)b.writeInt16LE(Math.round(10000*Math.sin(2*Math.PI*440*i/rate)),44+i*2);
  return {name:'Channel recording.wav',mimeType:'audio/wav',buffer:b};
}

test('profile, automatic preparation, review gate, upload progress and reusable editor',async({page,request})=>{
  const preset={render_config:{viewport_w:1280,viewport_h:720,fps:30,vcodec:'libx264'},visualizers:[{kind:'circular',position:'center',width:420,height:420,colors:'#22d3ee|#ec4899'}]};
  const profile={id:'channel-one',name:'Singing',channel_name:'My music channel',channel_id:'UC_music',connected:true,preset,provider_id:'provider',prompt:'Accurate recording metadata',category:'10',tags:[],privacy:'private',language:'en',made_for_kids:false,contains_synthetic_media:false};
  let run=null,uploads=0,prepared=0,legacyId='';
  await page.route('**/video/publishing/**',async route=>{
    const path=new URL(route.request().url()).pathname.replace('/video/publishing','');
    const method=route.request().method();let body={ok:true};
    if(path==='/info')body={enabled:true};
    else if(path==='/configuration')body={google_configured:true,redirect_uri:'http://127.0.0.1:8084/video/publishing/oauth/callback'};
    else if(path==='/profiles')body=[profile];
    else if(path==='/providers')body=[{id:'provider',name:'Configured provider',model:'test-model'}];
    else if(path==='/runs'&&method==='POST'){
      prepared++;const data=route.request().postDataJSON();
      expect(data.profile_id).toBe(profile.id);
      run={id:'run-one',created_at:Date.now()/1000,revision:1,profile,source_name:data.source_name,state:'awaiting_review',stage:'Ready for review',progress:100,artifact:{ref:{}},metadata:{title:'My recording',description:'My recorded performance.',tags:['recording']},review:{privacy:'private',category:'10',made_for_kids:false,contains_synthetic_media:false}};body=run;
    } else if(path==='/runs')body=run?[run]:[];
    else if(path.endsWith('/file'))return route.fulfill({status:302,headers:{location:`/video/audio/jobs/${legacyId}/file`}});
    else if(path.endsWith('/upload')){
      uploads++;const review=route.request().postDataJSON();expect(review.privacy).toBe('private');expect(review.metadata.title).toBe('My reviewed recording');
      run={...run,revision:2,state:'uploading',stage:'Uploading to My music channel',progress:42,upload_bytes:420000,upload_total:1000000};body=run;
    }
    await route.fulfill({json:body});
  });
  await page.goto('./');
  await expect(page.getByLabel('Channel profile',{exact:true})).toHaveValue(profile.id);
  const sourceResponse=page.waitForResponse(r=>r.url().endsWith('/video/audio/source'));
  await page.getByLabel('Audio file',{exact:true}).setInputFiles(audio());
  const source=await (await sourceResponse).json();
  const render=await request.post('/video/build/audio',{data:{audio_ref:source.audio_ref,render_config:{viewport_w:320,viewport_h:180,fps:5,vcodec:'libx264'}}});
  legacyId=(await render.json()).job_id;
  await expect.poll(async()=> (await (await request.get(`/video/status/${legacyId}`)).json()).status).toBe('done');
  await page.getByRole('button',{name:'Prepare for YouTube',exact:true}).click();
  await expect(page.getByLabel('Video title',{exact:true})).toHaveValue('My recording');
  expect(prepared).toBe(1);expect(uploads).toBe(0);
  await expect(page.getByRole('button',{name:'Approve & upload',exact:true})).toBeDisabled();
  await expect(page.getByLabel('Publishing video review')).toBeVisible();
  await expect.poll(()=>page.getByLabel('Publishing video review').evaluate(v=>v.readyState)).toBeGreaterThanOrEqual(2);
  await page.getByLabel('Video title',{exact:true}).fill('My reviewed recording');
  await page.getByLabel('I reviewed this video, metadata, channel and disclosure settings').check();
  await page.screenshot({path:'../local_tmp/publishing-review-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Approve & upload',exact:true}).click();
  await expect(page.locator('.publishing')).toContainText('42%');expect(uploads).toBe(1);
  run={...run,state:'completed',stage:'Ready on YouTube',video_id:'abcdefghijk',video_url:'https://www.youtube.com/watch?v=abcdefghijk',actual_privacy:'private'};
  await expect(page.locator('.publishing a').filter({hasText:'abcdefghijk'})).toBeVisible();
  await page.getByTitle('Channel profiles and setup').click();
  await page.getByLabel('Profile name',{exact:true}).fill('Unsaved profile edit');
  await page.waitForTimeout(3400);
  await expect(page.getByLabel('Profile name',{exact:true})).toHaveValue('Unsaved profile edit');
  await page.getByTitle('Close profiles').click();
  await expect(page.getByRole('button',{name:'Preview 5 seconds'})).toBeEnabled();
  await expect(page.getByRole('tab',{name:'Rendered video',exact:true})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'../local_tmp/publishing-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
});

test('background inspection and editor history do not alter export configuration',async({page})=>{
  await page.route('**/video/publishing/**',route=>route.fulfill({status:404,json:{detail:'disabled'}}));
  await page.goto('./');
  const frame=page.getByTestId('live-frame');await expect(frame).toBeVisible();
  const original=await page.getByLabel('Configuration JSON').inputValue();
  let last=await frame.getAttribute('src');
  await page.getByLabel('Background only',{exact:true}).check();
  await expect(frame).not.toHaveAttribute('src',last);
  expect(await page.getByLabel('Configuration JSON').inputValue()).toBe(original);
  await page.getByLabel('Framing guides',{exact:true}).check();
  await expect(page.locator('.framing-guides')).toBeVisible();
  await page.getByLabel('Background only',{exact:true}).uncheck();
  await page.getByLabel('Composition preset').selectOption('bottom');
  await page.getByRole('button',{name:'Apply',exact:true}).click();
  await expect(page.getByLabel('Layout',{exact:true})).toHaveValue('horizontal');
  await page.getByTitle('Undo visual settings').click();
  await expect(page.getByLabel('Layout',{exact:true})).toHaveValue('circular');
  await page.getByTitle('Redo visual settings').click();
  await expect(page.getByLabel('Layout',{exact:true})).toHaveValue('horizontal');
  await page.getByRole('tab',{name:'Background',exact:true}).click();
  last=await frame.getAttribute('src');
  await page.getByLabel('Style',{exact:true}).selectOption('plasma');
  await expect(frame).not.toHaveAttribute('src',last);
  const pixels=await frame.evaluate(img=>{const c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;const ctx=c.getContext('2d');ctx.drawImage(img,0,0);return [...ctx.getImageData(0,0,16,16).data].some((v,i)=>i%4!==3&&v>0);});
  expect(pixels).toBe(true);
});
