import { DEFAULT_CSV, parseCSV, profileCSV, generateOfflineSpec, runSpec, zipFiles } from './engine.js';
import { generateOnline, providerProfile } from './provider.js';

const $ = (id) => document.getElementById(id);
let dataset, profile, fileName = 'sample.csv', output, receipt, abortController, running = false;
const number = (value) => value === null || value === undefined ? 'No numeric values' : new Intl.NumberFormat('en', { maximumFractionDigits: 4 }).format(value);
const el = (tag, text, className) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; };
const pause = () => new Promise((resolve) => setTimeout(resolve, 40));

function table(headers, rows) {
  const table = el('table'), head = el('thead'), tr = el('tr');
  for (const header of headers) { const th = el('th', header); th.scope = 'col'; tr.append(th); }
  head.append(tr); table.append(head);
  const body = el('tbody');
  for (const row of rows) { const rowEl = el('tr'); for (const value of row) rowEl.append(el('td', String(value ?? ''))); body.append(rowEl); }
  table.append(body); return table;
}
function payloadPreview() { $('payload-preview').textContent = JSON.stringify({ goal: $('goal').value.trim(), metadata: providerProfile(profile) }, null, 2); }
function setDataset(text, name, sample = false) {
  const parsed = parseCSV(text), nextProfile = profileCSV(parsed);
  dataset = parsed; profile = nextProfile; fileName = name;
  const status = $('dataset-status'); status.replaceChildren(el('span', `${name} · ${number(profile.rowCount)} rows · ${profile.columns.length} columns`), el('small', sample ? 'Fictional sample data. No supplied or private dataset.' : 'Loaded in your browser. The CSV is not uploaded to a server.'));
  $('profile-summary').textContent = profile.columns.map((c) => `${c.name}: ${c.type} (${c.nullCount} missing)`).join(' · ');
  $('input-preview').replaceChildren(table(dataset.headers, dataset.rows.slice(0, 5)));
  payloadPreview(); invalidateResults();
}
function invalidateResults() { output = undefined; receipt = undefined; $('results').hidden = true; $('idle-state').hidden = false; $('error').hidden = true; }
function showError(message) { $('error').textContent = message; $('error').hidden = false; }
function updateMode() {
  const online = Boolean($('api-key').value.trim());
  $('mode-title').textContent = online ? 'AI planning with Gemini' : 'Local simulation';
  $('mode-description').textContent = online ? 'Google proposes a report plan. Your browser calculates the metrics and builds the project.' : 'No API key needed. The browser chooses a simple report plan and calculates it using your CSV.';
  $('mode-badge').textContent = online ? 'Online' : 'Offline';
  $('run-button').firstChild.textContent = online ? 'Build with Gemini ' : 'Build my report ';
}
function progress(message, percentage) { $('progress-text').textContent = message; $('progress-fill').style.width = `${percentage}%`; }
function setRunning(value) {
  running = value; $('run-button').disabled = value; $('csv-file').disabled = value; $('sample-button').disabled = value;
  $('api-key').disabled = value; $('provider').disabled = value; $('goal').disabled = value; $('clear-key').disabled = value;
  $('progress').hidden = !value; $('cancel-button').hidden = !value;
}
function download(bytes, name, type) {
  const url = URL.createObjectURL(new Blob([bytes], { type })), link = el('a'); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function renderDetail(index) {
  const result = output.results[index], root = $('result-detail'); root.replaceChildren();
  const rows = result.rows ?? [], grouped = Boolean(result.groupBy);
  if (grouped && rows.length && result.chart !== 'table') {
    const chart = el('div', undefined, 'chart'); const max = Math.max(...rows.map((r) => Math.abs(Number(r.value))), 1);
    for (const row of rows.slice(0, 20)) {
      const line = el('div', undefined, 'bar-row'), track = el('div', undefined, 'bar-track'), fill = el('div', undefined, 'bar-fill');
      fill.style.width = `${Math.abs(Number(row.value)) / max * 100}%`; track.append(fill); line.append(el('span', String(row.category ?? '(empty)'), 'bar-label'), track, el('span', number(row.value), 'bar-value')); chart.append(line);
    }
    root.append(chart);
    if (result.chart === 'line') root.append(el('p', 'Values are displayed as bars here; the downloaded project uses the planned chart type.', 'result-note'));
  }
  const scroll = el('div', undefined, 'table-scroll'); scroll.append(table(grouped ? [result.groupBy, result.name] : ['Metric', 'Value'], rows.map((r) => [grouped ? String(r.category ?? '(empty)') : result.name, number(r.value)]))); root.append(scroll);
  const count = result.totalGroups ?? rows.length;
  root.append(el('p', `${result.operation} ${result.column ? `of ${result.column}` : 'of rows'}${grouped ? `, grouped by ${result.groupBy}` : ''}. ${count > rows.length ? `Showing ${rows.length} of ${count} groups.` : ''}`, 'result-note'));
}
function renderOutput(mode) {
  $('idle-state').hidden = true; $('results').hidden = false;
  $('run-mode').textContent = mode === 'online' ? 'AI plan · calculated locally' : 'Local simulation · no AI call';
  $('report-title').textContent = output.spec.title || 'Your report';
  $('run-summary').textContent = `${number(profile.rowCount)} rows · ${output.results.length} metrics · a new project generated from ${fileName}`;
  const warnings = [...new Set([...(profile.warnings ?? []), ...(output.warnings ?? [])])];
  $('warnings').textContent = warnings.join(' '); $('warnings').hidden = !warnings.length;
  const cards = output.results.filter((r) => !r.groupBy && r.rows.length);
  $('metric-grid').replaceChildren(...cards.slice(0, 4).map((r) => { const card = el('div', undefined, 'metric'); card.append(el('p', r.name), el('strong', number(r.rows[0].value)), el('small', `${r.operation}${r.column ? ` · ${r.column}` : ' · rows'}`)); return card; }));
  $('metric-grid').hidden = !cards.length;
  $('result-selector').replaceChildren(...output.results.map((r, i) => { const option = el('option', r.name); option.value = String(i); return option; }));
  $('spec-preview').textContent = JSON.stringify(output.spec, null, 2); renderDetail(0);
}

$('csv-file').addEventListener('change', async (event) => {
  const file = event.target.files[0]; if (!file) return;
  try { if (file.size > 5 * 1024 * 1024) throw new Error('Choose a CSV smaller than 5 MB.'); setDataset(await file.text(), file.name); }
  catch (error) { showError(`The file could not be loaded: ${error.message}. Your previously loaded data is still selected.`); }
});
$('sample-button').addEventListener('click', () => { $('csv-file').value = ''; setDataset(DEFAULT_CSV, 'sample.csv', true); });
$('api-key').addEventListener('input', () => { updateMode(); invalidateResults(); });
$('goal').addEventListener('input', () => { payloadPreview(); invalidateResults(); });
$('provider').addEventListener('input', invalidateResults);
$('clear-key').addEventListener('click', () => { $('api-key').value = ''; updateMode(); invalidateResults(); });
$('cancel-button').addEventListener('click', () => abortController?.abort());
$('result-selector').addEventListener('change', (event) => renderDetail(Number(event.target.value)));
$('download-zip').addEventListener('click', () => { if (output) download(output.zipBytes, 'AgenticBI-project.zip', 'application/zip'); });
$('download-csv').addEventListener('click', () => { if (output) download(dataset.csvText, 'input.csv', 'text/csv;charset=utf-8'); });
$('download-receipt').addEventListener('click', () => { if (receipt) download(JSON.stringify(receipt, null, 2), 'run-receipt.json', 'application/json'); });
$('builder').addEventListener('submit', async (event) => {
  event.preventDefault(); if (running) return; invalidateResults(); setRunning(true); $('idle-state').hidden = true;
  abortController = new AbortController(); const mode = $('api-key').value.trim() ? 'online' : 'offline';
  try {
    progress('1 of 3 · Checking the column profile', 20); await pause();
    progress(mode === 'online' ? '2 of 3 · Asking Gemini for a report plan' : '2 of 3 · Choosing a local report plan', 45);
    const spec = mode === 'online' ? await generateOnline(profile, $('api-key').value.trim(), $('provider').value.trim(), $('goal').value.trim(), abortController.signal) : generateOfflineSpec(profile);
    if (abortController.signal.aborted) throw new DOMException('Request cancelled', 'AbortError');
    progress('3 of 3 · Calculating results and building your project', 75); await pause();
    output = runSpec(dataset, spec);
    const csvHash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(dataset.csvText)))].map(b => b.toString(16).padStart(2, '0')).join('');
    receipt = { createdAt: new Date().toISOString(), mode, provider: mode === 'online' ? 'Google Gemini' : null, model: mode === 'online' ? $('provider').value.trim() : null, inputFile: fileName, rowCount: profile.rowCount, profile, goal: $('goal').value.trim(), spec: output.spec, results: output.results, warnings: output.warnings ?? [], limitations: ['Browser implementation; no Power BI Desktop rendering verified.', 'Online planning receives profile metadata and goal only; no CSV rows.', 'Offline planning is deterministic and does not call AI.'] };
    receipt.inputCsvSha256 = csvHash;
    receipt.inputCsvPath = 'input.csv';
    output.files['run-receipt.json'] = JSON.stringify(receipt, null, 2);
    output.zipBytes = zipFiles(output.files);
    renderOutput(mode); progress('Ready to download', 100);
  } catch (error) {
    output = undefined; receipt = undefined;
    showError(error.name === 'AbortError' ? 'Request cancelled. No report was generated.' : `${mode === 'online' ? 'Online generation failed. No offline fallback was used. ' : 'The report could not be built. '}${error.message}`);
  } finally { $('api-key').value = ''; updateMode(); setRunning(false); abortController = undefined; }
});
setDataset(DEFAULT_CSV, 'sample.csv', true); updateMode();
