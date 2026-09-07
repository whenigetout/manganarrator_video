import {AudioVideoClient} from './api.js';
const assets = new URL('.', import.meta.url);
const defaultLayer = () => ({enabled:true,kind:'circular',position:'center',width:850,height:850,margin_x:96,margin_y:96,opacity:.95,colors:'0x22d3ee|0xec4899|0xfacc15',mode:'bar',scale:'log',frequency_bins:64,gain:1,radius:.27,bar_width:.55,glow:.6,smoothing:.72,background_opacity:0,min_frequency:40,max_frequency:16000});
const defaults = () => ({output_name:'my_visualizer.mp4',render_config:{viewport_w:2560,viewport_h:1440,fps:30,vcodec:'h264_nvenc',preset:'p1',tune:'hq',cq:23},background:{mode:'generated',generated_style:'aurora',color_a:'#080a10',color_b:'#6b246f',color_c:'#186d78',media_refs:[],playback_rate:1},visualizers:[defaultLayer()]});
const escapeHTML = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const options = (values, chosen) => values.map(v => {const [value,label] = Array.isArray(v) ? v : [v,v.replaceAll('_',' ')];return `<option value="${value}" ${value===chosen?'selected':''}>${label}</option>`;}).join('');
const select = (label,key,values,value) => `<label>${label}<select data-key="${key}">${options(values,value)}</select></label>`;
const range = (label,key,min,max,step,value) => `<label><span>${label}<output>${value}</output></span><input data-key="${key}" type="range" min="${min}" max="${max}" step="${step}" value="${value}"></label>`;
const number = (label,key,value,min=0,max=3840) => `<label>${label}<input data-key="${key}" type="number" value="${Number(value)}" min="${min}" max="${max}"></label>`;

export class AudioVideoStudio extends HTMLElement {
  connectedCallback() {
    if(this.mounted) return;
    this.mounted=true; if(!this.shadowRoot)this.attachShadow({mode:'open'});
    this.config=defaults(); this.layer=0; this.jobs=[]; this.busy=false;
    this.client=new AudioVideoClient(this.getAttribute('api-base') || (location.protocol==='file:'?'http://127.0.0.1:8084':''));
    this.shadowRoot.innerHTML=`
      <link rel="stylesheet" href="${assets}studio.css">
      <header><div class="brand"><div class="brandmark" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div><div><h1>Audio Studio</h1><div class="subtitle">MangaNarrator</div></div></div>
      <div class="connection"><span id="connection">Connecting...</span><input class="api" id="api" aria-label="Backend URL" placeholder="Same-origin backend" value="${escapeHTML(this.client.baseUrl)}"><button class="small" id="connect">Connect</button></div></header>
      <div class="layout"><aside class="settings">
        <section class="section"><h3>Source</h3><label>Audio file<input id="audio-file" type="file" accept=".mp3,.wav,.flac,.m4a,.ogg,.aac,audio/*"></label>
        <label>Background<select id="background-mode"><option value="generated">Animated abstract</option><option value="media">Video clips</option></select></label>
        <div id="generated" class="grid2"><label>Style<select id="background-style">${options(['aurora','nebula','gradient','plasma'],'aurora')}</select></label><label>Base color<input type="color" id="background-color" value="#080a10"></label></div>
        <div id="media" hidden><label>Background clips<input id="clips" type="file" accept="video/*" multiple></label><div class="clip-list" id="clip-list"></div><button id="clear-clips" class="small">Clear clips</button></div></section>
        <section class="section"><div class="row"><h3>Spectrum layers</h3><button id="add-layer" class="small">Add layer</button></div><div class="row"><select id="layers" aria-label="Selected layer"></select><button id="remove-layer" class="small">Remove</button></div><div id="layer-fields" class="spectrum-fields"></div></section>
        <section class="section"><h3>Export</h3><div class="grid2"><label>Resolution<select id="resolution">${options([['1280x720','720p'],['1920x1080','1080p'],['2560x1440','1440p / 2K'],['3840x2160','2160p / 4K'],['1080x1920','Vertical 1080p']], '2560x1440')}</select></label><label>Frame rate<select id="fps">${options(['24','30','60'],'30')}</select></label></div>
        <label>Encoder<select id="encoder"><option value="h264_nvenc">NVIDIA NVENC</option><option value="libx264">CPU / H.264</option></select></label>
        <label>Quality<select id="quality"><option value="28">Draft / fast</option><option value="23" selected>Balanced</option><option value="18">High quality</option></select></label>
        <label>Output filename<input id="filename" value="my_visualizer.mp4"></label></section>
        <details><summary>Configuration JSON</summary><textarea id="json" aria-label="Configuration JSON" spellcheck="false"></textarea><div class="footer-actions"><button id="apply-json" class="small">Apply JSON</button><button id="export-json" class="small">Export JSON</button></div><label>Import JSON<input id="import-json" type="file" accept=".json,application/json"></label></details>
      </aside><main class="workspace"><div id="error" class="error" role="alert" hidden></div>
        <div class="toolbar"><div><h2>Video preview</h2><div class="badge" id="preview-label">No render selected</div></div><div class="actions"><button id="preview">Preview 5 seconds</button><button id="render" class="primary">Render video</button></div></div>
        <div class="stage" id="stage"><img id="poster" src="${assets}preview.png" alt="Radial spectrum sample"><span class="empty-label" id="empty">Choose an audio file</span><video id="video" controls playsinline hidden></video></div>
        <div class="audio-line"><span class="filename" id="audio-name">No audio selected</span><audio id="audio" controls></audio></div>
        <section class="job-section"><div class="job-header"><h2>Render jobs</h2><button id="refresh" class="small">Refresh</button></div><div id="jobs" aria-live="polite"><p class="quiet">No renders yet</p></div>
        <div class="inspect"><input id="job-id" placeholder="Job ID" aria-label="Job ID"><button id="inspect" class="small">Check status</button></div></section>
      </main></div>`;
    this.$('connect').onclick=()=>{this.client=new AudioVideoClient(this.$('api').value.trim());this.connect();};
    this.$('audio-file').onchange=()=>{
      this.file=this.$('audio-file').files[0];
      if(this.audioUrl) URL.revokeObjectURL(this.audioUrl);
      if(this.file){this.audioUrl=URL.createObjectURL(this.file);this.$('audio').src=this.audioUrl;this.$('audio-name').textContent=this.file.name;this.$('empty').textContent='Ready to preview';}
    };
    this.$('background-mode').onchange=e=>{this.config.background.mode=e.target.value;this.syncBackground();this.syncJSON();};
    this.$('background-style').onchange=e=>{this.config.background.generated_style=e.target.value;this.syncJSON();};
    this.$('background-color').oninput=e=>{this.config.background.color_a=e.target.value;this.syncJSON();};
    this.$('clips').onchange=()=>this.uploadClips();
    this.$('clear-clips').onclick=()=>{this.config.background.media_refs=[];this.$('clips').value='';this.$('clip-list').textContent='';this.syncJSON();};
    this.$('layers').onchange=e=>{this.layer=Number(e.target.value);this.renderLayer();};
    this.$('add-layer').onclick=()=>{if(this.config.visualizers.length>=4)return;this.config.visualizers.push({...defaultLayer(),kind:'horizontal',width:Math.round(this.config.render_config.viewport_w*.8),height:220,position:'bottom',margin_y:50});this.layer=this.config.visualizers.length-1;this.renderLayer();};
    this.$('remove-layer').onclick=()=>{this.config.visualizers.splice(this.layer,1);this.layer=Math.max(0,this.layer-1);this.renderLayer();};
    this.$('resolution').onchange=e=>{
      const [w,h]=e.target.value.split('x').map(Number),rc=this.config.render_config;
      const sx=w/rc.viewport_w,sy=h/rc.viewport_h;
      for(const v of this.config.visualizers){v.width=Math.max(32,Math.round(v.width*sx));v.height=Math.max(32,Math.round(v.height*sy));v.margin_x=Math.round(v.margin_x*sx);v.margin_y=Math.round(v.margin_y*sy);}
      rc.viewport_w=w;rc.viewport_h=h;this.renderLayer();
    };
    this.$('fps').onchange=e=>{this.config.render_config.fps=Number(e.target.value);this.syncJSON();};
    this.$('encoder').onchange=e=>{this.config.render_config.vcodec=e.target.value;this.syncJSON();};
    this.$('quality').onchange=e=>{this.config.render_config.cq=Number(e.target.value);this.syncJSON();};
    this.$('filename').oninput=e=>{this.config.output_name=e.target.value;this.syncJSON();};
    this.$('preview').onclick=()=>this.render(true);this.$('render').onclick=()=>this.render(false);
    this.$('refresh').onclick=()=>this.refresh();this.$('inspect').onclick=()=>this.inspect();
    this.$('apply-json').onclick=()=>this.applyJSON(this.$('json').value);
    this.$('import-json').onchange=async()=>{const f=this.$('import-json').files[0];if(f)this.applyJSON(await f.text());};
    this.$('export-json').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(this.config,null,2)],{type:'application/json'}));a.download='audio_video_config.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);};
    this.$('jobs').onclick=e=>{const button=e.target.closest('[data-play]');if(button)this.showVideo(button.dataset.play);};
    this.renderLayer();this.connect();this.timer=setInterval(()=>this.refresh(false),2000);
  }
  disconnectedCallback(){clearInterval(this.timer);if(this.audioUrl)URL.revokeObjectURL(this.audioUrl);this.mounted=false;}
  $(id){return this.shadowRoot.getElementById(id);}
  error(message){this.$('error').textContent=message;this.$('error').hidden=!message;}
  syncJSON(){this.$('json').value=JSON.stringify(this.config,null,2);}
  syncBackground(){this.$('media').hidden=this.config.background.mode!=='media';this.$('generated').hidden=this.config.background.mode!=='generated';}
  renderLayer(){
    this.$('layers').innerHTML=this.config.visualizers.map((v,i)=>`<option value="${i}" ${i===this.layer?'selected':''}>${i+1}. ${escapeHTML(v.kind)}</option>`).join('');
    this.$('add-layer').disabled=this.config.visualizers.length>=4;this.$('remove-layer').disabled=!this.config.visualizers.length;
    const v=this.config.visualizers[this.layer];if(!v){this.$('layer-fields').innerHTML='';this.syncJSON();return;}
    this.$('layer-fields').innerHTML=`
      <label class="check wide"><input type="checkbox" data-key="enabled" ${v.enabled?'checked':''}>Visible</label>
      ${select('Layout','kind',['circular','horizontal','vertical'],v.kind)}
      ${select('Position','position',['center','top_left','top_right','bottom_left','bottom_right','top','bottom','left','right'],v.position)}
      ${select('Shape','mode',['bar','line','dot'],v.mode)}
      ${select('Response scale','scale',['log','sqrt','cbrt','lin'],v.scale)}
      <div class="grid2 wide">${number('Width (px)','width',v.width,32)}${number('Height (px)','height',v.height,32)}${number('X margin','margin_x',v.margin_x)}${number('Y margin','margin_y',v.margin_y)}</div>
      ${range('Bars','frequency_bins',8,192,2,v.frequency_bins)}
      ${range('Sensitivity','gain',.1,5,.1,v.gain)}
      ${range('Radius','radius',.05,.4,.01,v.radius)}
      ${range('Thickness','bar_width',.1,.95,.05,v.bar_width)}
      ${range('Glow','glow',0,2,.1,v.glow)}
      ${range('Smoothing','smoothing',0,.98,.02,v.smoothing)}
      ${range('Opacity','opacity',0,1,.05,v.opacity)}
      <div class="wide"><div class="row"><label>Palette</label><label class="check"><input id="single" type="checkbox" ${!v.colors.includes('|')?'checked':''}>Single color</label></div><div class="row"><div class="swatches"><button data-palette="0x22d3ee|0xec4899|0xfacc15" style="background:conic-gradient(#22d3ee,#ec4899,#facc15,#22d3ee)" title="Candy spectrum" aria-label="Candy spectrum"></button><button data-palette="0xf9a8d4|0xc084fc|0x60a5fa" style="background:linear-gradient(90deg,#f9a8d4,#60a5fa)" title="Pink to blue" aria-label="Pink to blue"></button><button data-palette="0xf97316|0xfacc15|0x4ade80|0x22d3ee|0xa78bfa" style="background:conic-gradient(#f97316,#facc15,#4ade80,#22d3ee,#a78bfa)" title="Rainbow" aria-label="Rainbow"></button></div><input type="color" id="color" aria-label="Primary spectrum color" style="width:48px" value="#${v.colors.split('|')[0].replace(/^0x|#/,'')}"></div></div>`;
    this.$('layer-fields').querySelectorAll('[data-key]').forEach(el=>el.oninput=()=>{
      v[el.dataset.key]=el.type==='checkbox'?el.checked:['number','range'].includes(el.type)?Number(el.value):el.value;
      const output=el.parentElement.querySelector('output');if(output)output.value=el.value;
      if(el.dataset.key==='kind')this.renderLayer();this.syncJSON();
    });
    this.$('layer-fields').querySelectorAll('[data-palette]').forEach(b=>b.onclick=()=>{v.colors=b.dataset.palette;this.renderLayer();});
    this.$('single').onchange=e=>{v.colors=e.target.checked?v.colors.split('|')[0]:'0x22d3ee|0xec4899|0xfacc15';this.renderLayer();};
    this.$('color').oninput=e=>{const colors=v.colors.split('|');colors[0]=e.target.value;v.colors=colors.join('|');this.syncJSON();};
    this.syncJSON();
  }
  applyJSON(text){
    try{
      const raw=JSON.parse(text);
      if(!raw || typeof raw!=='object' || Array.isArray(raw))throw new Error('Configuration must be an object');
      const base=defaults();
      const next={...base,...raw,render_config:{...base.render_config,...raw.render_config},background:{...base.background,...raw.background},visualizers:(raw.visualizers || base.visualizers).map(v=>({...defaultLayer(),...v}))};
      if(next.visualizers.length>4)throw new Error('At most four layers');
      if(next.visualizers.some(v=>!['circular','horizontal','vertical'].includes(v.kind)||typeof v.colors!=='string'||!v.colors.split('|').every(c=>/^(#|0x)?[0-9a-f]{6}$/i.test(c))))throw new Error('Invalid layer layout or hex colors');
      delete next.audio_ref;delete next.preview_seconds;this.config=next;this.layer=0;
      const rc=next.render_config;
      this.$('resolution').value=`${rc.viewport_w}x${rc.viewport_h}`;this.$('fps').value=String(rc.fps);this.$('encoder').value=rc.vcodec;this.$('quality').value=String(rc.cq);this.$('filename').value=next.output_name;
      this.$('background-mode').value=next.background.mode;this.$('background-style').value=next.background.generated_style;this.$('background-color').value=next.background.color_a;
      this.syncBackground();this.renderLayer();this.error('');
    }catch(e){this.error(e.message);}
  }
  async connect(){
    try{const cap=await this.client.capabilities();this.$('connection').innerHTML='<span class="dot"></span>'+(cap.nvenc?'NVIDIA ready':'CPU ready');if(!cap.nvenc){this.config.render_config.vcodec='libx264';this.$('encoder').value='libx264';this.syncJSON();}this.error('');await this.refresh();}
    catch(e){this.$('connection').innerHTML='<span class="dot off"></span>Offline';this.error('Backend connection failed: '+e.message);}
  }
  async uploadClips(){
    this.$('preview').disabled=this.$('render').disabled=true;
    try{for(const file of this.$('clips').files){const ref=await this.client.background(file);this.config.background.media_refs.push(ref);}this.$('clip-list').textContent=`${this.config.background.media_refs.length} clips uploaded`;this.syncJSON();}
    catch(e){this.error(e.message);}
    finally{this.$('preview').disabled=this.$('render').disabled=false;}
  }
  async render(preview){
    if(this.busy)return;
    if(!this.file){this.error('Choose an audio file first.');return;}
    this.busy=true;this.$('preview').disabled=this.$('render').disabled=true;this.error('');
    try{
      const config=structuredClone(this.config);
      if(preview){
        const rc=config.render_config,factor=Math.min(1,960/rc.viewport_w,540/rc.viewport_h);
        rc.viewport_w=Math.max(128,Math.round(rc.viewport_w*factor/2)*2);rc.viewport_h=Math.max(128,Math.round(rc.viewport_h*factor/2)*2);
        for(const v of config.visualizers){v.width=Math.max(32,Math.round(v.width*factor));v.height=Math.max(32,Math.round(v.height*factor));v.margin_x=Math.round(v.margin_x*factor);v.margin_y=Math.round(v.margin_y*factor);}
        config.preview_seconds=5;config.output_name='preview.mp4';
      }
      const job=await this.client.render(this.file,config);this.selectedJob=job.job_id;this.$('preview-label').textContent=preview?'Rendering 5-second preview':'Rendering full video';
      this.dispatchEvent(new CustomEvent('render-started',{detail:job,bubbles:true,composed:true}));await this.refresh();
    }catch(e){this.error(e.message);}finally{this.busy=false;this.$('preview').disabled=this.$('render').disabled=false;}
  }
  async refresh(report=true){
    if(this.polling)return;this.polling=true;
    try{
      this.jobs=await this.client.jobs();this.paintJobs();
      const selected=this.jobs.find(j=>j.job_id===this.selectedJob);
      if(selected?.status==='done'&&this.displayedJob!==selected.job_id){this.showVideo(selected.job_id);this.dispatchEvent(new CustomEvent('render-completed',{detail:selected,bubbles:true,composed:true}));}
      if(selected?.status==='failed')this.$('preview-label').textContent='Render failed';
    }catch(e){if(report)this.error('Unable to fetch job status: '+e.message);this.$('connection').innerHTML='<span class="dot off"></span>Disconnected';}
    finally{this.polling=false;}
  }
  paintJobs(){
    this.$('jobs').innerHTML=this.jobs.length?this.jobs.map(job=>`<div class="job"><div><div class="stage-name">${escapeHTML(job.status==='done'?'Complete':job.stage || job.status)}</div><div class="job-id">${escapeHTML(job.job_id)}</div></div><div><span class="badge">${escapeHTML(job.status)} ${Math.round(job.progress || 0)}%</span><progress value="${Number(job.progress)||0}" max="100"></progress></div><div class="job-actions">${job.status==='done'?`<button class="small" data-play="${escapeHTML(job.job_id)}">View</button><a href="${escapeHTML(this.client.fileUrl(job.job_id,true))}">Download</a>`:''}</div>${job.error?`<div class="job-error">${escapeHTML(job.error)}</div>`:''}</div>`).join(''):'<p class="quiet">No renders yet</p>';
  }
  showVideo(id){this.displayedJob=id;this.$('video').src=this.client.fileUrl(id);this.$('video').hidden=false;this.$('poster').hidden=true;this.$('empty').hidden=true;this.$('preview-label').textContent='Completed render';}
  async inspect(){try{const id=this.$('job-id').value.trim();if(!id)return;const job=await this.client.status(id);if(job.status==='not_found')throw new Error('Job not found');this.jobs=[job,...this.jobs.filter(j=>j.job_id!==id)];this.paintJobs();this.error('');}catch(e){this.error(e.message);}}
}
customElements.define('audio-video-studio', AudioVideoStudio);
