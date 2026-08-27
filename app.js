const dimensions = [
  ['MCM01', 'الحوكمة والتوجيه الاستراتيجي', 86, '#18a999'],
  ['MCM02', 'ذكاء أصحاب المصلحة والسياق', 78, '#4d9da0'],
  ['MCM03', 'حوكمة المعلومات والنزاهة', 58, '#d97063'],
  ['MCM04', 'التنسيق ورحلة العميل', 64, '#e49c50'],
  ['MCM05', 'مواءمة الوعد والتجربة', 73, '#e4b658'],
  ['MCM06', 'الأدلة والتعلم التكيفي', 69, '#5c9e8c'],
  ['MCM07', 'المأسسة وقابلية التوسع', 61, '#d58b5c']
];
const dimensionsRoot = document.querySelector('#dimensions');
dimensionsRoot.innerHTML = dimensions.map(([code, title, score, color]) => `
  <article class="dimension-card" style="--card-color:${color};--score:${score}%">
    <span class="dimension-code">${code}</span><h3>${title}</h3>
    <div class="dimension-score">${score}<small>/ 100</small></div><div class="mini-bar"><span></span></div>
  </article>`).join('');

const labels = {overview:'نظرة عامة', assessment:'التقييمات', roadmap:'خارطة التحسين', reports:'التقارير', researcher:'مساحة الباحث', methodology:'المنهجية'};
document.querySelectorAll('[data-view]').forEach((link) => link.addEventListener('click', (event) => {
  event.preventDefault();
  document.querySelectorAll('.nav-item').forEach((item) => item.classList.remove('active'));
  link.classList.add('active');
  document.querySelector('#page-label').textContent = labels[link.dataset.view];
  if (link.dataset.view === 'researcher') renderResearcher();
  else if (link.dataset.view !== 'overview') showToast(`تم فتح قسم ${labels[link.dataset.view]}`);
}));

document.querySelector('#new-assessment').addEventListener('click', () => showToast('سيتم فتح تقييم جديد قريبًا'));
document.querySelectorAll('.row-arrow,.outline-button,.filter-button,.more-button').forEach((button) => button.addEventListener('click', () => showToast('تم تسجيل التفاعل')));
function showToast(message) {
  const toast = document.querySelector('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  window.clearTimeout(window.toastTimer);
  window.toastTimer = window.setTimeout(() => toast.classList.remove('show'), 2400);
}

const supportedTables = ['INSTRUMENT_METADATA', 'SCALE_VALUES', 'DIMENSIONS', 'ITEMS', 'ITEM_SETTINGS', 'PROFILE_FIELDS', 'MATURITY_LEVELS'];
let latestImport = null;

function renderResearcher() {
  document.querySelector('#app-view').innerHTML = `<section class="page-heading researcher-heading"><div><div class="eyebrow">البحث والتحليل <span>•</span> إدارة أداة القياس</div><h1>استيراد أداة القياس</h1><p>أضف إصدارًا جديدًا من ملف DOCX المنظم، راجعه، ثم اطلب موافقة الباحث قبل إنشائه.</p></div><span class="draft-pill">لا نشر تلقائي</span></section><section class="import-flow"><div class="flow-step active"><b>01</b><span>رفع DOCX</span></div><div class="flow-line"></div><div class="flow-step"><b>02</b><span>تحليل وتحقق</span></div><div class="flow-line"></div><div class="flow-step"><b>03</b><span>معاينة</span></div><div class="flow-line"></div><div class="flow-step"><b>04</b><span>موافقة الباحث</span></div><div class="flow-line"></div><div class="flow-step"><b>05</b><span>إنشاء إصدار</span></div></section><section class="import-layout"><article class="upload-panel"><div class="section-heading compact"><div><h2>ملف الأداة</h2><p>يجب أن يحتوي الملف على علامات TABLE والجداول التابعة لها.</p></div><span class="docx-badge">DOCX</span></div><label class="dropzone" for="instrument-file"><input id="instrument-file" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" /><span class="upload-icon">↑</span><strong>اسحب ملف DOCX هنا أو اختره</strong><small>الامتداد المسموح: .docx</small></label><div class="table-contract"><span>الجداول المدعومة</span><div>${supportedTables.map((name) => `<code>TABLE:${name}</code>`).join('')}</div></div></article><article class="contract-panel"><div class="panel-title"><span>قواعد الاستيراد</span><span class="lock-icon">⌑</span></div><ul><li>الصف الأول في كل جدول هو أسماء الحقول.</li><li>يتم ربط <b>ITEMS</b> مع <b>ITEM_SETTINGS</b> بواسطة <b>item_code</b>.</li><li>لا يتم تعديل أو استبدال إصدار موجود.</li><li>كل تقييم يحتفظ بـ <b>instrument_version_id</b> الخاص به.</li></ul><div class="contract-note">المعاينة لا تنشئ إصدارًا ولا تنشر الأداة.</div></article></section><section id="import-result" class="import-result" hidden></section>`;
  document.querySelector('#instrument-file').addEventListener('change', handleInstrumentUpload);
}

async function handleInstrumentUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  const result = document.querySelector('#import-result');
  result.hidden = false;
  result.innerHTML = '<div class="loading-state">جارٍ تحليل ملف DOCX والتحقق من الجداول...</div>';
  try { latestImport = await parseDocxInstrument(file); renderImportPreview(latestImport, file.name); }
  catch (error) { result.innerHTML = `<div class="error-state"><b>تعذر تحليل الملف</b><p>${escapeHtml(error.message)}</p></div>`; }
}

async function parseDocxInstrument(file) {
  const entries = await readZipEntries(await file.arrayBuffer());
  const documentXml = entries['word/document.xml'];
  if (!documentXml) throw new Error('لم يتم العثور على word/document.xml داخل ملف DOCX.');
  const xml = new DOMParser().parseFromString(new TextDecoder().decode(documentXml), 'application/xml');
  if (xml.querySelector('parsererror')) throw new Error('ملف XML داخل DOCX غير صالح.');
  const body = xml.getElementsByTagNameNS('*', 'body')[0];
  const parsed = {};
  [...body.children].forEach((node, index, nodes) => {
    const marker = node.localName === 'p' && textOf(node).trim().match(/^TABLE:([A-Z0-9_]+)$/);
    const nextTable = nodes[index + 1];
    if (marker && supportedTables.includes(marker[1]) && nextTable && nextTable.localName === 'tbl') parsed[marker[1]] = parseOpenXmlTable(nextTable);
  });
  const missing = supportedTables.filter((name) => !parsed[name]);
  const errors = []; const warnings = missing.map((name) => `الجدول TABLE:${name} غير موجود.`);
  const items = parsed.ITEMS || []; const settings = parsed.ITEM_SETTINGS || [];
  const itemCodes = items.map((item) => item.item_code).filter(Boolean); const settingCodes = new Set(settings.map((item) => item.item_code).filter(Boolean));
  const duplicates = new Set(itemCodes.filter((code, index) => itemCodes.indexOf(code) !== index));
  items.forEach((item, index) => { if (!item.item_code) errors.push(`ITEMS: السجل ${index + 1} لا يحتوي item_code.`); if (duplicates.has(item.item_code)) errors.push(`ITEMS: item_code مكرر (${item.item_code}).`); if (settings.length && !settingCodes.has(item.item_code)) errors.push(`ITEMS: لا توجد إعدادات مرتبطة بـ ${item.item_code}.`); });
  const dimensions = parsed.DIMENSIONS || []; const dimensionCodes = new Set(dimensions.map((dimension) => dimension.dimension_code || dimension.code).filter(Boolean));
  items.forEach((item) => { const dimensionCode = item.dimension_code || item.dimension; if (dimensionCode && dimensionCodes.size && !dimensionCodes.has(dimensionCode)) errors.push(`ITEMS: البعد ${dimensionCode} غير موجود للبند ${item.item_code}.`); });
  const category = (item) => String(item.construct || item.measure || item.domain || item.item_type || '').toUpperCase();
  return { tables: parsed, missing, warnings, errors, stats: { total: items.length, mcm: items.filter((item) => category(item).includes('MCM')).length, smce: items.filter((item) => category(item).includes('SMCE')).length, enablers: items.filter((item) => category(item).includes('ENABLER')).length, outcomes: items.filter((item) => category(item).includes('OUTCOME')).length, dimensions: dimensions.length } };
}

function parseOpenXmlTable(table) {
  const rows = [...table.getElementsByTagNameNS('*', 'tr')].map((row) => [...row.getElementsByTagNameNS('*', 'tc')].map((cell) => textOf(cell).trim())).filter((row) => row.some(Boolean));
  const headers = rows.shift() || [];
  return rows.map((row) => headers.reduce((record, header, index) => { if (header) record[header] = row[index] || ''; return record; }, {}));
}
function textOf(node) { return [...node.getElementsByTagNameNS('*', 't')].map((text) => text.textContent).join(' '); }
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, (character) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character])); }

async function readZipEntries(buffer) {
  const bytes = new Uint8Array(buffer); const view = new DataView(buffer); const entries = {};
  for (let offset = 0; offset < bytes.length - 30;) {
    if (view.getUint32(offset, true) !== 0x04034b50) { offset += 1; continue; }
    const method = view.getUint16(offset + 8, true); const compressedSize = view.getUint32(offset + 18, true); const nameLength = view.getUint16(offset + 26, true); const extraLength = view.getUint16(offset + 28, true);
    const name = new TextDecoder().decode(bytes.slice(offset + 30, offset + 30 + nameLength)); const start = offset + 30 + nameLength + extraLength; const compressed = bytes.slice(start, start + compressedSize);
    if (method === 0) entries[name] = compressed; else if (method === 8) entries[name] = new Uint8Array(await new Response(new Blob([compressed]).stream().pipeThrough(new DecompressionStream('deflate-raw'))).arrayBuffer());
    offset = start + compressedSize;
  }
  return entries;
}

function renderImportPreview(data, fileName) {
  const stats = data.stats; const result = document.querySelector('#import-result');
  result.innerHTML = `<div class="preview-top"><div><div class="eyebrow">نتيجة التحليل <span>•</span> ${escapeHtml(fileName)}</div><h2>معاينة أداة القياس</h2><p>راجع السجلات قبل إرسالها لموافقة الباحث.</p></div><span class="validation-state ${data.errors.length ? 'invalid' : 'valid'}">${data.errors.length ? 'يحتاج تصحيحًا' : 'اجتاز التحقق'}</span></div><div class="stat-grid"><div><b>${stats.total}</b><span>إجمالي البنود</span></div><div><b>${stats.mcm}</b><span>MCM</span></div><div><b>${stats.smce}</b><span>SMCE</span></div><div><b>${stats.enablers}</b><span>Enablers</span></div><div><b>${stats.outcomes}</b><span>Optional outcomes</span></div><div><b>${stats.dimensions}</b><span>الأبعاد</span></div></div><div class="validation-grid"><article><h3>تحذيرات <span>${data.warnings.length}</span></h3>${data.warnings.length ? `<ul>${data.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join('')}</ul>` : '<p class="empty-message">لا توجد تحذيرات.</p>'}</article><article class="errors-box"><h3>أخطاء التحقق <span>${data.errors.length}</span></h3>${data.errors.length ? `<ul>${data.errors.map((error) => `<li>${escapeHtml(error)}</li>`).join('')}</ul>` : '<p class="empty-message">لا توجد أخطاء تمنع الإنشاء.</p>'}</article></div><div class="approval-bar"><div><b>حالة الإصدار</b><span>DRAFT · لم يتم النشر</span></div><button class="primary-button" id="approve-import" ${data.errors.length ? 'disabled' : ''}>موافقة الباحث وإنشاء إصدار</button></div>`;
  document.querySelector('#approve-import').addEventListener('click', approveImport);
}
function approveImport() { const button = document.querySelector('#approve-import'); button.disabled = true; button.textContent = 'تم إنشاء إصدار DRAFT'; showToast('تم إنشاء إصدار جديد غير منشور'); }
