import { REPORT_TEMPLATE, MODEL_TEMPLATE } from './templates.js';
import { THEMES } from './themes.js';
export const DEFAULT_CSV = 'InvoiceDate,BillingCountry,Total,Tracks,Artist\n2026-01-05,Kenya,10,2,Artist A\n2026-01-06,Kenya,11,3,Artist B\n2026-01-05,Ghana,12,3,Artist A\n2026-01-06,Ghana,13,4,Artist B\n2026-02-05,Kenya,20,2,Artist A\n2026-02-06,Kenya,21,3,Artist B\n2026-02-05,Ghana,22,3,Artist A\n2026-02-06,Ghana,23,4,Artist B\n2026-03-05,Kenya,30,2,Artist A\n2026-03-06,Kenya,31,3,Artist B\n2026-03-05,Ghana,32,3,Artist A\n2026-03-06,Ghana,33,4,Artist B\n';
const numeric = s => /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(s) && Number.isFinite(Number(s));
const encoder = new TextEncoder();
export function parseCSV(text) {
 if(typeof text!=='string'||encoder.encode(text).length>5*1024*1024) throw Error('Use a UTF-8 CSV smaller than 5 MiB.');
 text=text.replace(/^\uFEFF/,''); let rows=[],row=[],cell='',quoted=false,closed=false,started=false;
 const finishCell=()=>{row.push(cell);cell='';closed=false;started=false;};
 const finishRow=()=>{finishCell();rows.push(row);row=[];if(rows.length>20001) throw Error('CSV exceeds 20,000 data rows.');};
 for(let i=0;i<text.length;i++) {const c=text[i]; if(quoted){if(c==='"'){if(text[i+1]==='"'){cell+='"';i++;}else {quoted=false;closed=true;}} else cell+=c;continue;}
  if(c==='"'){if(started||closed) throw Error('Unexpected quote in CSV. Quote the whole field.');quoted=true;started=true;}
  else if(c===','){finishCell();}
  else if(c==='\n'||c==='\r'){if(c==='\r'&&text[i+1]==='\n')i++;finishRow();}
  else {if(closed)throw Error('Unexpected text after a closing CSV quote.');cell+=c;started=true;}
 }
 if(quoted)throw Error('CSV has an unclosed quoted field.');
 if(cell!==''||row.length||started||closed)finishRow();
 if(rows.length<2)throw Error('CSV needs a header and at least one data row.');
 const headers=rows.shift().map(x=>x.trim());
 if(headers.length>60||headers.some(x=>!x||x.length>120||/[\x00-\x1f]/.test(x))||new Set(headers).size!==headers.length)throw Error('Use 1–60 unique nonempty headers, at most 120 characters each.');
 if(rows.some(r=>r.length!==headers.length))throw Error('Every CSV row must have the same number of fields as its header.');
 if(rows.some(r=>r.some(v=>v.length>10000||v.includes('\0'))))throw Error('CSV contains an unsupported long or null-character cell.');
 rows=rows.map(r=>r.map(v=>v.trim()));
 const quote=s=>'"'+s.replaceAll('"','""')+'"';
 return {headers,rows,csvText:[headers,...rows].map(r=>r.map(quote).join(',')).join('\r\n')+'\r\n'};
}
export function profileCSV(data) {
 const columns=data.headers.map((name,i)=>{const values=data.rows.map(r=>r[i]).filter(v=>v!==''); const numbers=values.length&&values.every(numeric); const c={name,type:numbers?'number':'string',nullCount:data.rows.length-values.length,distinctCount:new Set(numbers?values.map(Number):values).size}; if(numbers){c.min=Math.min(...values.map(Number));c.max=Math.max(...values.map(Number));}return c;});
 return {rowCount:data.rows.length,columns,warnings:columns.filter(c=>c.nullCount).map(c=>`${c.name}: ${c.nullCount} empty cells are treated as missing.`)};
}
export function generateOfflineSpec(profile) {
 const num=profile.columns.find(c=>c.type==='number'&&!/(^id$|id$)/i.test(c.name))||profile.columns.find(c=>c.type==='number');
 const cat=profile.columns.find(c=>c.type==='string'&&c.distinctCount>1&&c.distinctCount<=50&&!/date|time/i.test(c.name))||profile.columns.find(c=>c.type==='string'&&c.distinctCount<=500);
 const date=profile.columns.find(c=>/date|time/i.test(c.name)&&c.type==='string'&&c.distinctCount<=500);
 let kpis=[{name:'Rows in dataset',operation:'count',column:null,groupBy:null,chart:'card'}];
 if(num){kpis.push({name:`Total ${num.name}`,operation:'sum',column:num.name,groupBy:null,chart:'card'},{name:`Average ${num.name}`,operation:'average',column:num.name,groupBy:null,chart:'card'}); if(cat)kpis.push({name:`${num.name} by ${cat.name}`,operation:'sum',column:num.name,groupBy:cat.name,chart:'bar'});if(date)kpis.push({name:`${num.name} by ${date.name}`,operation:'sum',column:num.name,groupBy:date.name,chart:'line'});if(kpis.length<4)kpis.push({name:`Maximum ${num.name}`,operation:'max',column:num.name,groupBy:null,chart:'card'});}
 else { const c=cat||profile.columns[0];kpis.push({name:`Distinct ${c.name}`,operation:'distinctCount',column:c.name,groupBy:null,chart:'card'},{name:`Rows by ${c.name}`,operation:'count',column:null,groupBy:c.name,chart:'bar'},{name:`${c.name} breakdown`,operation:'count',column:null,groupBy:c.name,chart:'table'}); }
 return {title:'My CSV report',kpis};
}
export function validateSpec(spec,profile) {
 if(!spec||typeof spec.title!=='string'||!spec.title.trim()||spec.title.length>100||/[\x00-\x1f]/.test(spec.title)||!Array.isArray(spec.kpis)||spec.kpis.length<4||spec.kpis.length>8)throw Error('Report specification must have a short title and 4–8 metrics.');
 const names=new Set();const allowed=['sum','average','count','min','max','distinctCount'];
 for(const k of spec.kpis){if(!k||typeof k.name!=='string'||!k.name.trim()||k.name.length>100||/[\x00-\x1f]/.test(k.name)||k.name!==k.name.trim()||names.has(k.name.toLocaleLowerCase('en-US')))throw Error('Metric names must be unique, nonempty and at most 100 characters.');names.add(k.name.toLocaleLowerCase('en-US'));
 if(!allowed.includes(k.operation)||!['card','bar','line','table'].includes(k.chart))throw Error('Unsupported metric operation or chart.');
 for(const f of ['column','groupBy'])if(k[f]!==null&&!profile.columns.some(c=>c.name===k[f]))throw Error(`Unknown column in ${k.name}.`);
 if(k.operation!=='count'&&k.column===null)throw Error('This metric needs a column.');
 if(['sum','average','min','max'].includes(k.operation)&&profile.columns.find(c=>c.name===k.column)?.type!=='number')throw Error('Numeric metric requires a numeric column.');
 if(k.chart==='card'&&k.groupBy!==null||['bar','line'].includes(k.chart)&&k.groupBy===null)throw Error('Chart type does not match grouping.');
 if(k.groupBy!==null&&(profile.columns.find(c=>c.name===k.groupBy).distinctCount+(profile.columns.find(c=>c.name===k.groupBy).nullCount?1:0))>500)throw Error('Choose a grouping with at most 500 distinct values.');
 const keys=Object.keys(k);if(keys.some(x=>!['name','operation','column','groupBy','chart'].includes(x)))throw Error('Metric contains unsupported fields.');
 }
 return spec;
}
function execute(data,k,profile){ const normalized=(name,value)=>value!==''&&profile.columns.find(c=>c.name===name)?.type==='number'?String(Number(value)):value; const groups=new Map();for(const row of data.rows){const key=k.groupBy===null?'':normalized(k.groupBy,row[data.headers.indexOf(k.groupBy)]);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(k.column===null?null:normalized(k.column,row[data.headers.indexOf(k.column)]));}
 const rows=[...groups].map(([category,raw])=>{const values=raw.filter(x=>x!==null&&x!=='');let value;if(k.operation==='count')value=k.column===null?raw.length:values.length;else if(k.operation==='distinctCount')value=new Set(values).size;else if(!values.length)value=null;else {const nums=values.map(Number);value=k.operation==='sum'?nums.reduce((a,b)=>a+b,0):k.operation==='average'?nums.reduce((a,b)=>a+b,0)/nums.length:k.operation==='min'?Math.min(...nums):Math.max(...nums);}return k.groupBy===null?{value}:{category,value};});
 if(k.groupBy!==null)rows.sort((a,b)=>k.chart==='line'?a.category.localeCompare(b.category):(b.value??-Infinity)-(a.value??-Infinity)||a.category.localeCompare(b.category));
 if(rows.some(r=>r.value!==null&&!Number.isFinite(r.value)))throw Error('Metric exceeds supported numeric range.');return {...k,rows,totalGroups:rows.length};
}
const id = n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const tq = s=>"'"+s.replaceAll("'","''")+"'";
function compile(data,profile,spec){const files={};const put=(p,v)=>files[p]=typeof v==='string'?v:JSON.stringify(v,null,2);const report='BrowserDemo.Report',model='BrowserDemo.SemanticModel';
 put('BrowserDemo.pbip',{version:'1.0',artifacts:[{report:{path:report}}],settings:{enableAutoRecovery:true}});
 for(const [folder,type,n] of [[report,'Report',1],[model,'SemanticModel',2]])put(folder+'/.platform',{$schema:'https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json',metadata:{type,displayName:'BrowserDemo'},config:{version:'2.0',logicalId:id(n)}});
 put(report+'/definition.pbir',{version:'4.0',datasetReference:{byPath:{path:'../'+model}}});put(model+'/definition.pbism',{version:'4.2',settings:{}});put(report+'/definition/report.json',REPORT_TEMPLATE);put(report+'/definition/version.json',{$schema:'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json',version:'2.0.0'});
 for(const [path,value] of Object.entries(THEMES))put(report+'/StaticResources/SharedResources/'+path,value);
 put(model+'/definition/database.tmdl','database\n\tcompatibilityLevel: 1600\n');put(model+'/definition/model.tmdl',MODEL_TEMPLATE);
 let prefix='c'; while(data.headers.some(h=>new RegExp(`^${prefix}\\d+$`).test(h))) prefix='_'+prefix;
 const columns=profile.columns.map((c,i)=>({...c,internal:`${prefix}${i+1}`}));const internal=n=>columns.find(c=>c.name===n).internal;
 let lines=['table Data',`\tlineageTag: ${id(3)}`,''];
 for(let i=0;i<spec.kpis.length;i++){const k=spec.kpis[i];const column=k.column===null?null:`Data[${internal(k.column)}]`;const exp=k.operation==='count'?(column?`COUNT(${column})`:'COUNTROWS(Data)'):k.operation==='distinctCount'?`COUNTROWS(FILTER(VALUES(${column}), NOT(ISBLANK(${column}))))`:`${{sum:'SUM',average:'AVERAGE',min:'MIN',max:'MAX'}[k.operation]}(${column})`;lines.push(`\tmeasure ${tq(k.name)} = ${exp}`,'\t\tformatString: #,0.##',`\t\tlineageTag: ${id(100+i)}`,'');}
 for(let i=0;i<columns.length;i++){const c=columns[i];lines.push(`\tcolumn ${c.internal}`,`\t\tdataType: ${c.type==='number'?'double':'string'}`,`\t\tlineageTag: ${id(200+i)}`,'\t\tsummarizeBy: none',`\t\tsourceColumn: ${c.internal}`,'');}
 const mq=s=>'"'+s.replaceAll('"','""').replaceAll('#','#(#)')+'"';const pairs=columns.map(c=>`{${mq(c.name)}, ${mq(c.internal)}}`).join(', ');const types=columns.map(c=>`{${mq(c.internal)}, ${c.type==='number'?'type number':'type text'}}`).join(', ');
 lines.push('\tpartition Data = m','\t\tmode: import','\t\tsource =','\t\t\t\tlet','\t\t\t\t    Source = Csv.Document(File.Contents("C:/AgenticBIDemo/input.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),','\t\t\t\t    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',`\t\t\t\t    Renamed = Table.RenameColumns(Headers, {${pairs}}),`,'\t\t\t\t    Missing = Table.ReplaceValue(Renamed, "", null, Replacer.ReplaceValue, Table.ColumnNames(Renamed)),',`\t\t\t\t    Typed = Table.TransformColumnTypes(Missing, {${types}}, "en-US")`,'\t\t\t\tin','\t\t\t\t    Typed','','\tannotation PBI_ResultType = Table','');put(model+'/definition/tables/Data.tmdl',lines.join('\n'));
 const pages=Array.from({length:Math.ceil(spec.kpis.length/4)},(_,i)=>`page${i+1}`);put(report+'/definition/pages/pages.json',{$schema:'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json',pageOrder:pages,activePageName:pages[0]});
 pages.forEach((page,p)=>{put(`${report}/definition/pages/${page}/page.json`,{$schema:'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json',name:page,displayName:p===0?spec.title:'More metrics',displayOption:'FitToPage',height:720,width:1280});});
 spec.kpis.forEach((k,i)=>{const field=(type,name)=>({[type]:{Expression:{SourceRef:{Entity:'Data'}},Property:name}});const projection=(type,name,active=false)=>({field:field(type,name),queryRef:`Data.${name}`,nativeQueryRef:type==='Column'?columns.find(c=>c.internal===name).name:name,...(active?{active:true}:{})});const m=projection('Measure',k.name,true);const c=k.groupBy===null?null:projection('Column',internal(k.groupBy),true);const queryState=k.chart==='card'?{Data:{projections:[m]}}:k.chart==='table'?{Values:{projections:c?[c,m]:[m]}}:{Category:{projections:[c]},Y:{projections:[m]}};const visual=`visual${i+1}`;put(`${report}/definition/pages/${pages[Math.floor(i/4)]}/visuals/${visual}/visual.json`,{$schema:'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.10.0/schema.json',name:visual,position:{x:20+(i%2)*630,y:20+Math.floor(i%4/2)*350,z:i,height:330,width:610,tabOrder:i},visual:{visualType:{card:'cardVisual',bar:'clusteredColumnChart',line:'lineChart',table:'tableEx'}[k.chart],query:{queryState},objects:{},visualContainerObjects:{title:[{properties:{show:{expr:{Literal:{Value:'true'}}},text:{expr:{Literal:{Value:tq(k.name)}}}},selector:{id:'default'}}]},drillFilterOtherVisuals:true},filterConfig:{filters:[...(c?[{name:`${visual}_0`,field:c.field,type:'Categorical'}]:[]),{name:`${visual}_1`,field:m.field,type:'Advanced'}]}});});
 put('input.csv',data.csvText);put('report-spec.json',spec);put('OPEN_IN_POWER_BI.txt','Extract this ZIP. Save input.csv as C:\\AgenticBIDemo\\input.csv (create the folder), or edit File.Contents in BrowserDemo.SemanticModel/definition/tables/Data.tmdl. Open BrowserDemo.pbip in Windows Power BI Desktop and Refresh. Enable Power BI Project/PBIR preview settings if your Desktop version requires them. This is a browser-generated single-table adapter, not the full Python/LangGraph application. It generates editable PBIP source files, not a PBIX. No fresh Power BI Desktop verification is claimed. Internal column names c1 etc. map to the CSV headers in Table.RenameColumns. Browser previews summarize the same declared operations; Power BI recalculates DAX measures on refresh.\n');return files;
}
// ZIP store format, CRC32; no executable dependencies or external upload.
export function zipFiles(files){const chunks=[];let offset=0;const central=[];const crc=bytes=>{let c=0xffffffff;for(const b of bytes){c^=b;for(let i=0;i<8;i++)c=(c>>>1)^((c&1)?0xedb88320:0);}return(c^0xffffffff)>>>0;};
 const header=(len,values)=>{const a=new Uint8Array(len),d=new DataView(a.buffer);for(const [off,value,size]of values)size===2?d.setUint16(off,value,true):d.setUint32(off,value,true);return a;};
 for(const [path,text]of Object.entries(files)){const name=encoder.encode(path),body=encoder.encode(text),sum=crc(body);const h=header(30,[[0,0x04034b50,4],[4,20,2],[6,0x800,2],[8,0,2],[14,sum,4],[18,body.length,4],[22,body.length,4],[26,name.length,2]]);chunks.push(h,name,body);central.push(header(46,[[0,0x02014b50,4],[4,20,2],[6,20,2],[8,0x800,2],[16,sum,4],[20,body.length,4],[24,body.length,4],[28,name.length,2],[42,offset,4]]),name);offset+=h.length+name.length+body.length;}
 const size=central.reduce((n,c)=>n+c.length,0),count=Object.keys(files).length;chunks.push(...central,header(22,[[0,0x06054b50,4],[8,count,2],[10,count,2],[12,size,4],[16,offset,4]]));const output=new Uint8Array(chunks.reduce((n,c)=>n+c.length,0));let at=0;for(const c of chunks){output.set(c,at);at+=c.length;}return output;
}
export function runSpec(dataset,spec){const profile=profileCSV(dataset);validateSpec(spec,profile);for(const k of spec.kpis){for(const name of [k.groupBy,...(k.operation==='distinctCount'?[k.column]:[])]){if(name!==null&&profile.columns.find(c=>c.name===name)?.type==='string'){const seen=new Map();for(const row of dataset.rows){const value=row[dataset.headers.indexOf(name)],folded=value.toLocaleLowerCase('en-US');if(seen.has(folded)&&seen.get(folded)!==value)throw Error(`Column ${name} has labels differing only by case. Standardize their case before grouping or counting distinct values so the browser and Power BI agree.`);seen.set(folded,value);}}}}const results=spec.kpis.map(k=>execute(dataset,k,profile));const files=compile(dataset,profile,spec);files['results.json']=JSON.stringify({profile,results},null,2);return {spec,profile,results,files,zipBytes:zipFiles(files),warnings:[...profile.warnings,'Browser adapter: single CSV, no joins or arbitrary SQL; Power BI Desktop required to open PBIP.']};}
