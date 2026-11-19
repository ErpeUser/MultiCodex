'use strict';
// Contract double for the standard Figma API; NOT a live canvas/layout engine.
const test = require('node:test');
const assert = require('node:assert/strict');
const {buildReference} = require('../../plugins/figma/renderer.js');
const config = {
  schema: 1, navWidth: 220, radius: 12,
  themes: {
    dark: {canvas:'#0D1114',rail:'#11161A',panel:'#182126',text:'#F1F5F7',muted:'#9BAAB2',accent:'#8FD3C7',accent_text:'#0D1114',border:'#273137',selected:'#26363B'},
    light: {canvas:'#F6F8F9',rail:'#F3F5F7',panel:'#FFFFFF',text:'#162027',muted:'#64727A',accent:'#1E625B',accent_text:'#FFFFFF',border:'#E4E8EB',selected:'#DDECE9'}
  }
};
function apiFixture(options={}) {
  let next = 0, textCount = 0;
  const fonts = new Set();
  const api = {editorType:'figma', root:{children:[]}};
  class Node {
    constructor(type) {
      this.id = String(++next); this.type=type; this.children=[]; this.parent=null;
      this.width=100; this.height=100; this.layoutMode='NONE'; this.fills=[];
      this.fontName={family:'Inter',style:'Regular'};
      this.removed=false; this.x=0; this.y=0;
    }
    appendChild(child) {
      if (child.parent) child.parent.children=child.parent.children.filter(n=>n!==child);
      child.parent=this; this.children.push(child);
    }
    resize(width,height) {
      assert.ok(Number.isFinite(width) && width>0 && Number.isFinite(height) && height>0);
      this.width=width; this.height=height;
      this._horizontal='FIXED'; this._vertical='FIXED';
    }
    set layoutSizingHorizontal(value) { this.sizing(value); this._horizontal=value; }
    get layoutSizingHorizontal() {return this._horizontal;}
    set layoutSizingVertical(value) {this.sizing(value); this._vertical=value;}
    get layoutSizingVertical() {return this._vertical;}
    sizing(value) {
      assert.ok(['FIXED','HUG','FILL'].includes(value));
      if (value==='FILL') assert.ok(this.parent && this.parent.layoutMode!=='NONE');
      if (value==='HUG') assert.ok(this.layoutMode!=='NONE' || this.type==='TEXT' && this.parent && this.parent.layoutMode!=='NONE');
    }
    set characters(value) {
      assert.equal(this.type,'TEXT');
      assert.ok(fonts.has(JSON.stringify(this.fontName)), 'font must finish loading before text is edited');
      assert.equal(typeof value,'string'); this._characters=value;
    }
    get characters() {return this._characters;}
    remove() {
      this.removed=true;
      if (this.parent) this.parent.children=this.parent.children.filter(n=>n!==this);
      else api.root.children=api.root.children.filter(n=>n!==this);
    }
  }
  const original=new Node('PAGE'); original.name='Existing user page';
  const existing=new Node('FRAME'); existing.name='Do not replace me'; original.appendChild(existing);
  api.root.children.push(original); api.currentPage=original;
  api.listAvailableFontsAsync=async()=>options.noFonts?[]:[
    {fontName:{family:'Inter',style:'Regular'}}, {fontName:{family:'Inter',style:'Semi Bold'}}];
  api.loadFontAsync=async font=>{
    await Promise.resolve();
    if(options.fontFailure) throw new Error('private backend message');
    fonts.add(JSON.stringify(font));
  };
  api.createPage=()=>{const n=new Node('PAGE');api.root.children.push(n);return n;};
  api.setCurrentPageAsync=async page=>{
    await Promise.resolve();
    if (page===original && options.cleanupFailure) throw new Error('cannot restore');
    api.currentPage=page;
  };
  api.createFrame=()=>{const n=new Node('FRAME');api.currentPage.appendChild(n);return n;};
  api.createText=()=>{
    if(options.failAtText && ++textCount===options.failAtText) throw new Error('private backend message');
    const n=new Node('TEXT');api.currentPage.appendChild(n);return n;
  };
  api.viewport={scrollAndZoomIntoView() {}};
  Object.defineProperty(api,'clientStorage',{get(){throw new Error('No storage access is allowed');}});
  return {api,original,existing};
}
function all(node) {return [node,...node.children.flatMap(all)];}

test('creates 12 editable screens with the approved native navigation order',async()=>{
  const {api,original,existing}=apiFixture();
  const result=await buildReference(api,structuredClone(config));
  assert.equal(api.root.children.length,2);
  const page=api.root.children.find(n=>n!==original);
  assert.equal(page.children.length,12);
  assert.deepEqual(result.screens.map(s=>s.page), ['Overview','Accounts','Instances','Usage','Diagnostics','Settings'].flatMap(p=>[p,p]));
  assert.deepEqual([...new Set(result.screens.map(s=>s.theme))],['dark','light']);
  assert.equal(existing.name,'Do not replace me');
  const nodes=all(page);
  assert.ok(nodes.filter(n=>n.type==='TEXT').length>100);
  assert.deepEqual(new Set(result.createdNodeIds),new Set(nodes.map(n=>n.id)));
  assert.ok(nodes.every(n=>n.fills.every(fill=>fill.type==='SOLID')),'no flattened screenshots');
});

test('each screen declares design-only sample data, not a runtime or acceptance result',async()=>{
  const {api}=apiFixture(); const result=await buildReference(api,structuredClone(config));
  for (const screen of api.currentPage.children) {
    assert.ok(all(screen).some(n=>n.type==='TEXT' && n.characters.includes('Beispieldaten') && n.characters.includes('Laufzeitnachweis')));
  }
  assert.equal(result.screens.length,12);
});

test('uses source theme values and keeps screen frames separated',async()=>{
  const {api}=apiFixture();await buildReference(api,structuredClone(config));
  const screens=api.currentPage.children;
  assert.deepEqual(screens[0].fills[0].color,{r:13/255,g:17/255,b:20/255});
  assert.deepEqual(screens[1].fills[0].color,{r:246/255,g:248/255,b:249/255});
  for(let i=0;i<screens.length;i++) for(let j=i+1;j<screens.length;j++) {
    const a=screens[i],b=screens[j];
    assert.ok(a.x+a.width<=b.x || b.x+b.width<=a.x || a.y+a.height<=b.y || b.y+b.height<=a.y);
  }
});

test('repeated generation is additive and preserves user edits in earlier generated pages',async()=>{
  const {api}=apiFixture();await buildReference(api,structuredClone(config));
  const previous=api.currentPage;
  const text=all(previous).find(n=>n.type==='TEXT');text.characters='User-edited reference';
  await buildReference(api,structuredClone(config));
  assert.equal(api.root.children.length,3);
  assert.notEqual(api.currentPage,previous);
  assert.equal(text.characters,'User-edited reference');
  assert.equal(previous.removed,false);
});

test('missing or failing fonts leave the entire existing canvas unchanged',async()=>{
  for(const options of [{noFonts:true},{fontFailure:true}]) {
    const {api,original}=apiFixture(options);
    await assert.rejects(buildReference(api,structuredClone(config)));
    assert.deepEqual(api.root.children,[original]);
    assert.equal(original.children.length,1);
  }
});

test('a partial construction failure removes only this run and restores the previous page',async()=>{
  const {api,original,existing}=apiFixture({failAtText:7});
  await assert.rejects(buildReference(api,structuredClone(config)),/REFERENCE_BUILD_FAILED/);
  assert.deepEqual(api.root.children,[original]);
  assert.equal(api.currentPage,original);
  assert.deepEqual(original.children,[existing]);
});

test('rollback failure is reported without deleting an existing page or leaking API text',async()=>{
  const {api,original,existing}=apiFixture({failAtText:7,cleanupFailure:true});
  await assert.rejects(buildReference(api,structuredClone(config)),error=>{
    assert.equal(error.message,'REFERENCE_BUILD_FAILED');
    assert.ok(error.partialPageId); return true;
  });
  assert.ok(api.root.children.includes(original));
  assert.deepEqual(original.children,[existing]);
});

test('unsupported editors are rejected without making any nodes',async()=>{
  const {api,original}=apiFixture();api.editorType='figjam';
  await assert.rejects(buildReference(api,structuredClone(config)),/DESIGN_EDITOR_REQUIRED/);
  assert.deepEqual(api.root.children,[original]);
});

test('invalid theme configuration is rejected before changing the document',async()=>{
  const cases=[];
  let c=structuredClone(config);c.themes.dark.canvas='#GGGGGG';cases.push(c);
  c=structuredClone(config);delete c.themes.light;cases.push(c);
  c=structuredClone(config);c.navWidth=0;cases.push(c);
  c=structuredClone(config);c.schema=2;cases.push(c);
  for(const value of cases) {
    const {api,original}=apiFixture();
    await assert.rejects(buildReference(api,value),/INVALID_CONFIG/);
    assert.deepEqual(api.root.children,[original]);
  }
});
