'use strict';
/* Standard Figma Plugin API only. No network, storage, credentials or screenshots.
 * This is an editable design reference, not a clone or runtime acceptance result.
 */
const MC_PAGES = [
  ['Overview','\u00dcbersicht'], ['Accounts','Konten'], ['Instances','Instanzen'],
  ['Usage','Nutzung'], ['Diagnostics','Diagnose'], ['Settings','Einstellungen']
];
const MC_TOKEN_NAMES = ['canvas','rail','panel','text','muted','accent','accent_text','border','selected'];

function validateConfig(config) {
  if (!config || config.schema!==1 || !Number.isInteger(config.navWidth) ||
      config.navWidth<180 || config.navWidth>300 || !Number.isInteger(config.radius) ||
      config.radius<0 || config.radius>32) throw new Error('INVALID_CONFIG');
  for (const theme of ['dark','light']) {
    const palette=config.themes && config.themes[theme];
    if (!palette || MC_TOKEN_NAMES.some(key=>typeof palette[key]!=='string' || !/^#[0-9a-f]{6}$/i.test(palette[key]))) {
      throw new Error('INVALID_CONFIG');
    }
  }
}
function paint(hex) {
  return {type:'SOLID',color:{r:parseInt(hex.slice(1,3),16)/255,
    g:parseInt(hex.slice(3,5),16)/255,b:parseInt(hex.slice(5,7),16)/255}};
}

async function buildReference(api, configuration) {
  if (api.editorType!=='figma') throw new Error('DESIGN_EDITOR_REQUIRED');
  validateConfig(configuration);
  const config=JSON.parse(JSON.stringify(configuration));
  let regular, emphasis;
  try {
    const available=await api.listAvailableFontsAsync();
    regular=available.find(item=>item.fontName.family==='Inter' && item.fontName.style==='Regular');
    emphasis=available.find(item=>item.fontName.family==='Inter' &&
      ['Semi Bold','SemiBold','Medium','Bold'].includes(item.fontName.style));
    if (!regular) throw new Error('FONT_UNAVAILABLE');
    regular=regular.fontName; emphasis=emphasis?emphasis.fontName:regular;
    await api.loadFontAsync(regular);
    await api.loadFontAsync(emphasis);
  } catch (_) { throw new Error('FONT_UNAVAILABLE'); }

  const previous=api.currentPage;
  const createdNodeIds=[];
  const remember=node=>{createdNodeIds.push(node.id);return node;};
  const page=remember(api.createPage());
  page.name='MultiCodex | Designreferenz | '+new Date().toISOString()+' | '+api.root.children.length;
  const screens=[];
  try {
    await api.setCurrentPageAsync(page);
    const frame=(parent,name,width,direction='VERTICAL',fill=null)=>{
      const node=remember(api.createFrame());
      node.name=name; node.layoutMode=direction; node.resize(width,10);
      node.primaryAxisSizingMode=direction==='VERTICAL'?'AUTO':'FIXED';
      node.counterAxisSizingMode=direction==='VERTICAL'?'FIXED':'AUTO';
      node.itemSpacing=12; node.clipsContent=false; node.fills=fill?[paint(fill)]:[];
      parent.appendChild(node);
      node.layoutSizingHorizontal='FIXED'; node.layoutSizingVertical='HUG';
      return node;
    };
    const text=(parent,value,width,palette,size=13,strong=false,muted=false)=>{
      const node=remember(api.createText());
      node.name=value.slice(0,72); node.fontName=strong?emphasis:regular;
      node.fontSize=size; node.lineHeight={unit:'PERCENT',value:140};
      node.fills=[paint(muted?palette.muted:palette.text)];
      node.characters=value; node.textAutoResize='HEIGHT'; node.resize(width,Math.ceil(size*1.4));
      parent.appendChild(node); node.layoutSizingHorizontal='FIXED';
      return node;
    };
    const card=(parent,title,width,palette)=>{
      const node=frame(parent,title,width,'VERTICAL',palette.panel);
      node.cornerRadius=config.radius;
      node.paddingTop=node.paddingBottom=node.paddingLeft=node.paddingRight=16;
      node.strokes=[paint(palette.border)];node.strokeWeight=1;
      text(node,title,width-32,palette,16,true);
      return node;
    };
    const actions=(parent,labels,width,palette,selected=0)=>{
      const row=frame(parent,'Aktionen',width,'HORIZONTAL');
      for (const [index,label] of labels.entries()) {
        const buttonWidth=Math.min(300,Math.max(148,label.length*7+24));
        const button=frame(row,label,buttonWidth,'VERTICAL',index===selected?palette.accent:palette.selected);
        button.paddingLeft=button.paddingRight=12;button.paddingTop=button.paddingBottom=10;
        button.cornerRadius=8;
        const labelNode=text(button,label,buttonWidth-24,palette,13,true);
        if(index===selected) labelNode.fills=[paint(palette.accent_text)];
      }
      return row;
    };
    const table=(parent,title,headers,rows,width,palette)=>{
      const section=card(parent,title,width,palette);
      const inner=width-32,cellWidth=(inner-16-(headers.length-1)*12)/headers.length;
      for (const [index,values] of [headers,...rows].entries()) {
        const row=frame(section,index===0?'Spalten':'Datensatz '+index,inner,'HORIZONTAL',index===0?palette.selected:null);
        row.paddingLeft=row.paddingRight=8;row.paddingTop=row.paddingBottom=7;
        values.forEach(value=>text(row,value,cellWidth,palette,12,index===0));
      }
      return section;
    };
    const metrics=(parent,items,width,palette)=>{
      const strip=frame(parent,'Beispielkennzahlen',width,'HORIZONTAL');
      const cellWidth=(width-24)/3;
      for(const [label,value] of items) {
        const cell=card(strip,label,cellWidth,palette);
        text(cell,value,cellWidth-32,palette,26,true);
      }
    };
    const content=(key,main,width,p,theme)=>{
      if(key==='Overview') {
        metrics(main,[['Profile (Beispiel)','2'],['Prozess erkannt (Beispiel)','1'],['Zu pr\u00fcfen (Beispiel)','1']],width,p);
        table(main,'Profil\u00fcbersicht',['Profil','Gespeicherte Identit\u00e4t','Prozess','Zugriff'],[
          ['Entwicklung','dev-a@example.test','L\u00e4uft (Beispiel)','Unbest\u00e4tigt'],
          ['Testumgebung','dev-b@example.test','Unbekannt','Pr\u00fcfung erforderlich']],width,p);
        text(main,'Gespeicherte Identit\u00e4ten und erkannte Prozesse beweisen keine aktuelle Anmeldung oder freie Quota.',width,p,13,false,true);
        actions(main,['Profil anlegen','Bestehendes Profil verkn\u00fcpfen'],width,p);
      } else if(key==='Accounts') {
        actions(main,['Profil-Anmeldungen','Globaler Pool: nur lesen'],width,p);
        table(main,'Gespeicherte Anmeldungen',['Profil','Anmeldung','Status'],[
          ['Entwicklung','dev-a@example.test','Lokal gespeichert'],
          ['Testumgebung','dev-b@example.test','Erneute Pr\u00fcfung erforderlich']],width,p);
        const section=card(main,'Ausgew\u00e4hlte Anmeldung',width,p);
        text(section,'Neue Anmeldungen verwenden den offiziellen Client. Der globale Pool wird nicht als aktive Instanz-Zuordnung dargestellt.',width-32,p);
        actions(section,['Anmelden','Erneut anmelden','Umbenennen'],width-32,p);
      } else if(key==='Instances') {
        table(main,'Isolierte Instanzen',['Profil','Prozessstatus','Gespeicherte Anmeldung'],[
          ['Entwicklung','L\u00e4uft (Beispiel)','dev-a@example.test'],
          ['Testumgebung','Unbekannt','dev-b@example.test']],width,p);
        const section=card(main,'Ausgew\u00e4hltes Profil: Entwicklung',width,p);
        text(section,'Benutzerdaten: %LOCALAPPDATA%\\MultiCodex\\profiles\\demo\nNur die exakt zugeordnete Instanz darf gestartet oder gestoppt werden.',width-32,p);
        actions(section,['Starten','Nur diese Instanz stoppen'],width-32,p);
        text(main,'Vor dem Stoppen: ungespeicherte Arbeit pr\u00fcfen. Unbekannte Prozesssicht ist kein Nachweis f\u00fcr eine gestoppte Instanz.',width,p,13,false,true);
      } else if(key==='Usage') {
        metrics(main,[['Gespeicherte Kontexte','2'],['Verbrauch (Beispiel)','72 %'],['Frisch best\u00e4tigte Kapazit\u00e4t','Unbekannt']],width,p);
        table(main,'Quota-Historie',['Konto / Kontext','Verbrauch','Aktualit\u00e4t / Reset'],[
          ['dev-a@example.test / demo','72 % (Beispiel)','Historisch; erneut pr\u00fcfen'],
          ['dev-b@example.test / unbekannt','Unbekannt','Keine best\u00e4tigte Reset-Zeit']],width,p);
        actions(main,['Quota pr\u00fcfen','Historie \u00f6ffnen'],width,p);
        table(main,'Explizit freigegebene Profilstarts',['Profil','Zielkonto','Zustand'],[
          ['Entwicklung','dev-a@example.test','Wartet auf Best\u00e4tigung']],width,p);
        text(main,'Historische Werte bleiben erhalten. Keine Konto- oder Seat-Rotation bei ersch\u00f6pfter Quota.',width,p,13,false,true);
      } else if(key==='Diagnostics') {
        const runtime=card(main,'Lokale Diagnose',width,p);
        text(runtime,'Prozesssicht: unbest\u00e4tigt\nNative Abnahme: kein Nachweis in dieser Designreferenz',width-32,p);
        const workspace=card(main,'Workspace-Verwaltung',width,p);
        text(workspace,'Workspace-ID: demo-workspace\nAdmin-Key: nur f\u00fcr die jeweilige Aktion, nicht gespeichert\nAPI-Vertrag: noch nicht geladen',width-32,p);
        actions(workspace,['Vertrag laden','Mitglieder lesen'],width-32,p);
        table(main,'Geplante Aktion pr\u00fcfen',['Ziel','Rolle / Seat','Freigabe'],[
          ['dev-a@example.test','Aus ver\u00f6ffentlichtem API-Vertrag','Vorschau erforderlich']],width,p);
        text(main,'Unklare Serverantworten werden nur nachgelesen, nicht automatisch erneut geschrieben. Workspace-Aktionen bleiben von Quota-Warnungen getrennt.',width,p,13,false,true);
      } else if(key==='Settings') {
        const appearance=card(main,'Darstellung',width,p);
        actions(appearance,['Dunkel','Hell'],width-32,p,theme==='dark'?0:1);
        const monitor=card(main,'Quota-Monitoring',width,p);
        text(monitor,'Monitoring: pausiert (Beispiel)\nIntervall: 60 Sekunden (Beispiel)\nProfilauswahl: explizite Freigabe\nProfilstarts: nur vorgemerkte, genaue Zuordnungen',width-32,p);
        actions(monitor,['Einstellungen speichern'],width-32,p);
        text(main,'Keine Anmeldedaten in Einstellungen. Gespeicherte Quota-Werte bleiben auch ohne Workspace-Zugriff erhalten.',width,p,13,false,true);
      }
    };
    for(const [pageIndex,[key,label]] of MC_PAGES.entries()) {
      for(const [themeIndex,theme] of ['dark','light'].entries()) {
        const p=config.themes[theme];
        const screen=frame(page,label+' / '+theme,1280,'HORIZONTAL',p.canvas);
        screen.resize(1280,920);screen.itemSpacing=0;
        screen.primaryAxisSizingMode='FIXED';screen.counterAxisSizingMode='FIXED';
        screen.layoutSizingHorizontal='FIXED';screen.layoutSizingVertical='FIXED';
        screen.x=40+themeIndex*1400;screen.y=40+pageIndex*1040;
        const rail=frame(screen,'Navigation',config.navWidth,'VERTICAL',p.rail);
        rail.paddingLeft=rail.paddingRight=20;rail.paddingTop=rail.paddingBottom=28;
        rail.layoutSizingVertical='FILL';
        text(rail,'MultiCodex',config.navWidth-40,p,23,true);
        text(rail,'Lokale Profile.\nKlare Zuordnung.',config.navWidth-40,p,12,false,true);
        for(const [navKey,navLabel] of MC_PAGES) {
          const item=frame(rail,navLabel,config.navWidth-40,'VERTICAL',navKey===key?p.selected:null);
          item.paddingLeft=item.paddingRight=12;item.paddingTop=item.paddingBottom=10;item.cornerRadius=8;
          text(item,navLabel,config.navWidth-64,p,13,navKey===key);
        }
        text(rail,'Designreferenz\nKeine Live-Verbindung',config.navWidth-40,p,11,false,true);
        const main=frame(screen,'Inhalt',1280-config.navWidth);
        main.paddingTop=main.paddingBottom=main.paddingLeft=main.paddingRight=32;
        main.itemSpacing=18;main.layoutSizingVertical='FILL';
        const width=1280-config.navWidth-64;
        text(main,label,width,p,28,true);
        text(main,'Designreferenz | Beispieldaten | kein Laufzeitnachweis',width,p,11,false,true);
        content(key,main,width,p,theme);
        screens.push({page:key,theme,nodeId:screen.id});
      }
    }
    api.viewport.scrollAndZoomIntoView(page.children.slice(0,2));
    return {pageId:page.id,createdNodeIds,screens};
  } catch (_) {
    let partialPageId=null;
    try {await api.setCurrentPageAsync(previous);page.remove();}
    catch (_) {partialPageId=page.id;}
    const error=new Error('REFERENCE_BUILD_FAILED');
    error.partialPageId=partialPageId;
    throw error;
  }
}

if(typeof module!=='undefined') module.exports={buildReference};
