const labels = {overview:'نظرة عامة', assessment:'التقييمات', roadmap:'خارطة التحسين', reports:'التقارير', researcher:'مساحة الباحث', methodology:'المنهجية', 'admin-users':'إدارة المستخدمين', participant:'دخول المشارك'};
const colors = ['#18a999', '#4d9da0', '#d97063', '#e49c50', '#e4b658', '#5c9e8c', '#d58b5c'];
const apiBase = window.location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
let apiToken = localStorage.getItem('mcm_api_token');
async function api(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(apiToken ? { Authorization: `Bearer ${apiToken}` } : {}), ...(options.headers || {}) } });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'تعذر الاتصال بالخادم');
  return data;
}
function scoreFor(scores, code) { return scores.find((item) => item.dimension_code === code)?.score ?? null; }
function renderDimensions(scores) {
  document.querySelector('#dimensions').innerHTML = scores.map((item, index) => `<article class="dimension-card" style="--card-color:${colors[index % colors.length]};--score:${item.score}%"><span class="dimension-code">${item.dimension_code}</span><h3>${item.name || item.dimension_code}</h3><div class="dimension-score">${Math.round(item.score)}<small>/ 100</small></div><div class="mini-bar"><span></span></div></article>`).join('');
}
async function loadDashboard() {
  if (window.location.hash.startsWith('#participant')) return renderParticipantEntry();
  if (!apiToken) return showLogin();
  try {
    const data = await api('/api/dashboard');
    const currentUser = await api('/api/me');
    document.querySelector('#admin-users-nav').hidden = currentUser.role !== 'super_admin';
    const mcm = data.scores.MCM || []; const smce = data.scores.SMCE || [];
    renderDimensions(mcm);
    const mcmTotal = mcm.length ? Math.round(mcm.reduce((sum, item) => sum + item.score, 0) / mcm.length) : null;
    const smceTotal = smce.length ? Math.round(smce.reduce((sum, item) => sum + item.score, 0) / smce.length) : null;
    document.querySelector('#mcm-total').firstChild.textContent = mcmTotal ?? '--';
    document.querySelector('#mcm-bar').style.width = `${mcmTotal || 0}%`;
    document.querySelector('#mcm-level').textContent = mcmTotal === null ? 'لم يبدأ' : mcmTotal >= 75 ? 'مؤسسي' : mcmTotal >= 50 ? 'متطور' : 'ناشئ';
    document.querySelector('#smce-total').textContent = smceTotal ?? '--';
    document.querySelector('#smce-level').textContent = smceTotal === null ? 'لم يبدأ' : smceTotal >= 75 ? 'مؤسسي' : smceTotal >= 50 ? 'يحتاج تطويرًا' : 'ناشئ';
    document.querySelector('#smce-stats').innerHTML = smce.map((item) => `<div><span>${item.name || item.dimension_code}</span><b>${Math.round(item.score)}</b></div>`).join('');
    const assessmentRoute = window.location.hash.match(/^#assessment\/(\d+)$/);
    if (assessmentRoute) renderAssessment(assessmentRoute[1]);
  } catch (error) { showToast(error.message); }
}
function showLogin() {
  document.querySelector('#app-view').innerHTML = `<section class="page-heading"><div><div class="eyebrow">مساحة العمل <span>•</span> دخول آمن</div><h1>تسجيل الدخول</h1><p>استخدم حساب مؤسستك للوصول إلى بيانات التقييم.</p></div></section><section class="upload-panel" style="max-width:520px"><form id="login-form"><label>البريد الإلكتروني<input name="email" type="email" required value="sara@example.com"></label><label>كلمة المرور<input name="password" type="password" required value="ChangeMe-2026"></label><button class="primary-button" type="submit">دخول</button></form><a class="text-link" href="#participant" id="participant-login-link">لديك دعوة؟ الدخول كمشارك ←</a></section>`;
  document.querySelector('#login-form').addEventListener('submit', async (event) => { event.preventDefault(); try { const data = await api('/api/auth/login', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.target))) }); apiToken = data.token; localStorage.setItem('mcm_api_token', apiToken); window.location.hash = 'overview'; window.location.reload(); } catch (error) { showToast('بيانات الدخول غير صحيحة'); } });
  document.querySelector('#participant-login-link').addEventListener('click', (event) => { event.preventDefault(); renderParticipantEntry(); });
}
document.querySelectorAll('[data-view]').forEach((link) => link.addEventListener('click', (event) => {
  event.preventDefault();
  document.querySelectorAll('.nav-item').forEach((item) => item.classList.remove('active'));
  link.classList.add('active');
  document.querySelector('#page-label').textContent = labels[link.dataset.view];
  if (link.dataset.view === 'researcher') renderResearcher();
  else if (link.dataset.view === 'admin-users') renderAdminUsers();
  else if (link.dataset.view === 'participant') renderParticipantEntry();
  else if (link.dataset.view === 'assessment') renderAssessments();
  else if (link.dataset.view === 'roadmap') renderRoadmap();
  else if (link.dataset.view === 'reports') renderReports();
  else if (link.dataset.view === 'methodology') renderMethodology();
  else loadDashboard();
}));
document.querySelector('#new-assessment').addEventListener('click', async () => { try { const assessment = await api('/api/assessments', { method: 'POST', body: '{}' }); window.location.hash = `assessment/${assessment.id}`; renderAssessment(assessment.id); } catch (error) { showToast(error.message); } });
document.querySelector('.org-switcher').addEventListener('click', async () => { try { const data = await api('/api/organizations'); showToast(data.organizations.map((organization) => `${organization.name} · ${organization.role}`).join(' | ')); } catch (error) { showToast(error.message); } });
document.querySelector('.top-actions .icon-button').addEventListener('click', renderNotifications);
document.querySelector('.user-chip').addEventListener('click', () => { if (window.confirm('تسجيل الخروج من مساحة العمل؟')) { localStorage.removeItem('mcm_api_token'); apiToken = null; window.location.reload(); } });
document.querySelector('.sidebar-bottom .icon-button').addEventListener('click', renderSettings);
document.querySelector('.outline-button').addEventListener('click', renderParticipants);
document.querySelector('.insight-panel .text-link').addEventListener('click', (event) => { event.preventDefault(); renderRoadmap(); });
document.querySelector('.priorities .text-link').addEventListener('click', (event) => { event.preventDefault(); renderRoadmap(); });
document.querySelectorAll('.filter-button,.more-button').forEach((button) => button.addEventListener('click', () => showToast('تتطلب هذه القراءة تقييمًا محددًا من قائمة التقييمات.')));
function showToast(message) {
  const toast = document.querySelector('#toast');
  toast.textContent = message;
  toast.classList.add('show');
  window.clearTimeout(window.toastTimer);
  window.toastTimer = window.setTimeout(() => toast.classList.remove('show'), 2400);
}

async function createAssessment() { try { const assessment = await api('/api/assessments', { method: 'POST', body: '{}' }); window.location.hash = `assessment/${assessment.id}`; renderAssessment(assessment.id); } catch (error) { showToast(error.message); } }
async function renderAssessments() { const data = await api('/api/assessments'); document.querySelector('#app-view').innerHTML = `<section class="page-heading"><div><div class="eyebrow">مساحة العمل <span>•</span> التقييمات</div><h1>التقييمات</h1><p>أنشئ تقييمًا جديدًا أو استأنف مسودة محفوظة.</p></div><button class="primary-button" id="create-assessment">＋ تقييم جديد</button></section><section class="section-block"><div class="priority-table"><div class="table-head"><span>المعرف</span><span>الحالة</span><span>الإصدار</span><span>التاريخ</span><span></span></div>${data.assessments.map((item) => `<div class="table-row"><span>#${item.id}</span><strong>${item.status === 'draft' ? 'مسودة' : 'مكتمل'}</strong><span>v${item.version_id}</span><span>${new Date(item.created_at * 1000).toLocaleDateString('ar')}</span><button class="row-arrow" data-assessment="${item.id}" aria-label="فتح التقييم">←</button></div>`).join('')}</div></section>`; document.querySelector('#create-assessment').addEventListener('click', createAssessment); document.querySelectorAll('[data-assessment]').forEach((button) => button.addEventListener('click', () => renderAssessment(button.dataset.assessment))); }
async function renderAssessment(id) { const data = await api(`/api/assessments/${id}`); document.querySelector('#app-view').innerHTML = `<section class="page-heading"><div><div class="eyebrow">التقييمات <span>•</span> ${data.assessment.status === 'draft' ? 'مسودة محفوظة' : 'مكتمل'}</div><h1>التقييم ${id}</h1><p>الإجابة من 0 إلى 5. تحفظ الإجابات تلقائيًا على الخادم.</p></div><button class="primary-button" id="submit-assessment">إرسال وحساب النتيجة</button></section><form id="assessment-form" class="section-block">${data.items.map((item) => `<label class="assessment-item"><span>${item.code} · ${item.prompt_ar}</span><input type="number" min="0" max="5" step="1" name="${item.id}" value="${data.answers?.[item.id] || ''}" required></label>`).join('')}</form>`; let timer; document.querySelector('#assessment-form').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => saveAnswers(id), 500); }); document.querySelector('#submit-assessment').addEventListener('click', async () => { await saveAnswers(id); const result = await api(`/api/assessments/${id}/submit`, { method: 'POST', body: '{}' }); showToast(`تم الحساب: ${Math.round(result.scores.MCM.reduce((sum, item) => sum + item.score, 0) / result.scores.MCM.length)} / 100`); }); }
async function saveAnswers(id) { const answers = [...document.querySelectorAll('#assessment-form input')].filter((input) => input.value !== '').map((input) => ({ item_id: Number(input.name), value: Number(input.value) })); if (answers.length) await api(`/api/assessments/${id}/answers`, { method: 'POST', body: JSON.stringify({ answers }) }); }
function renderRoadmap() { document.querySelector('#app-view').innerHTML = '<section class="page-heading"><div><div class="eyebrow">مساحة العمل <span>•</span> خطة التحسين</div><h1>خارطة التحسين</h1><p>تظهر التوصيات بعد إكمال تقييم يعتمد على إصدار أداة منشور.</p></div></section>'; }
function renderReports() { document.querySelector('#app-view').innerHTML = '<section class="page-heading"><div><div class="eyebrow">مساحة العمل <span>•</span> التقارير</div><h1>التقارير التنفيذية</h1><p>ستُتاح التقارير بعد اكتمال التقييم وحفظ التشخيص.</p></div></section>'; }
function renderMethodology() { document.querySelector('#app-view').innerHTML = '<section class="page-heading"><div><div class="eyebrow">البحث والتحليل <span>•</span> المنهجية</div><h1>منهجية MCM وSMCE</h1><p>MCM وSMCE مقياسان مستقلان. تجمع الدرجة من متوسط بنود البعد، ثم تضرب في 20، وتحدد مستويات النضج بقواعد ثابتة على الخادم.</p></div></section>'; }
function renderParticipantEntry() { const hashToken = new URLSearchParams(window.location.hash.split('?')[1] || '').get('token') || ''; document.querySelector('#app-view').innerHTML = `<section class="page-heading"><div><div class="eyebrow">نضج MCM <span>•</span> بوابة المشارك</div><h1>ابدأ تقييمك من هنا</h1><p>أدخل رمز الدعوة الذي وصلك من مؤسستك للوصول إلى التقييم المخصص لك.</p></div></section><section class="upload-panel" style="max-width:620px"><form id="participant-entry-form"><label>رمز الدعوة<input name="token" required autocomplete="one-time-code" value="${escapeHtml(hashToken)}" placeholder="أدخل رمز الدعوة" /></label><button class="primary-button" type="submit">التحقق من الدعوة</button></form><div id="participant-entry-result" class="import-result" hidden></div></section>`; document.querySelector('#participant-entry-form').addEventListener('submit', async (event) => { event.preventDefault(); const token = new FormData(event.target).get('token').trim(); const result = document.querySelector('#participant-entry-result'); result.hidden = false; result.innerHTML = '<div class="loading-state">جارٍ التحقق من الدعوة...</div>'; try { const invitation = await api(`/api/invitations/${encodeURIComponent(token)}`); result.innerHTML = `<div class="preview-top"><div><div class="eyebrow">دعوة صالحة <span>•</span> ${escapeHtml(invitation.email)}</div><h2>أنت مدعو للمشاركة</h2><p>حالة الدعوة: ${escapeHtml(invitation.status)}. يمكنك متابعة التقييم من الرابط المرسل لك.</p></div><span class="validation-state valid">صالحة</span></div>`; } catch (error) { result.innerHTML = '<div class="error-state"><b>تعذر التحقق من الدعوة</b><p>تأكد من الرمز وأن الدعوة لم تنتهِ.</p></div>'; } }); if (hashToken) document.querySelector('#participant-entry-form').requestSubmit(); }
async function renderParticipants() { const data = await api('/api/invitations'); document.querySelector('#app-view').innerHTML = `<section class="page-heading"><div><div class="eyebrow">مساحة العمل <span>•</span> المشاركون</div><h1>مشاركة التقييم</h1><p>أرسل دعوة محددة الدور، وتبقى صالحة لمدة سبعة أيام.</p></div></section><section class="upload-panel" style="max-width:720px"><form id="invite-form"><label>البريد الإلكتروني<input name="email" type="email" required></label><label>الدور<select name="role"><option value="respondent">مشارك</option><option value="assessor">مقيّم</option></select></label><button class="primary-button" type="submit">إرسال الدعوة</button></form><div class="priority-table" style="margin-top:20px">${data.invitations.map((item) => `<div class="table-row"><span>${item.email}</span><strong>${item.role}</strong><span>${item.status}</span></div>`).join('') || '<p>لا توجد دعوات بعد.</p>'}</div></section>`; document.querySelector('#invite-form').addEventListener('submit', async (event) => { event.preventDefault(); try { await api('/api/invitations', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.target))) }); showToast('تم إنشاء الدعوة'); renderParticipants(); } catch (error) { showToast(error.message); } }); }
async function renderNotifications() { const data = await api('/api/notifications'); document.querySelector('#app-view').innerHTML = `<section class="page-heading"><div><div class="eyebrow">مساحة العمل <span>•</span> التنبيهات</div><h1>الإشعارات</h1><p>متابعة الأحداث المرتبطة بمؤسستك وتقييماتك.</p></div><button class="primary-button" id="read-notifications">تحديد الكل كمقروء</button></section><section class="section-block">${data.notifications.map((item) => `<article class="dimension-card"><span class="dimension-code">${item.read_at ? 'مقروء' : 'جديد'}</span><h3>${item.title}</h3><p>${item.body}</p></article>`).join('') || '<p>لا توجد إشعارات.</p>'}</section>`; document.querySelector('#read-notifications').addEventListener('click', async () => { await api('/api/notifications/read', { method: 'POST', body: '{}' }); showToast('تم تحديث الإشعارات'); renderNotifications(); }); }
async function renderSettings() { const data = await api('/api/settings'); document.querySelector('#app-view').innerHTML = `<section class="page-heading"><div><div class="eyebrow">مساحة العمل <span>•</span> الإعدادات</div><h1>إعدادات الحساب</h1><p>تحكم في اللغة وإشعارات البريد الخاصة بالمستخدم الحالي.</p></div></section><section class="upload-panel" style="max-width:720px"><form id="settings-form"><label>اللغة<select name="locale"><option value="ar" ${data.user.locale === 'ar' ? 'selected' : ''}>العربية RTL</option><option value="en" ${data.user.locale === 'en' ? 'selected' : ''}>English LTR</option></select></label><label><input name="email_notifications" type="checkbox" ${data.user.email_notifications ? 'checked' : ''}> إشعارات البريد</label><button class="primary-button" type="submit">حفظ الإعدادات</button></form></section>`; document.querySelector('#settings-form').addEventListener('submit', async (event) => { event.preventDefault(); const form = new FormData(event.target); try { await api('/api/settings', { method: 'POST', body: JSON.stringify({ locale: form.get('locale'), email_notifications: form.has('email_notifications') }) }); showToast('تم حفظ الإعدادات'); } catch (error) { showToast(error.message); } }); }
async function renderAdminUsers() { try { const data = await api('/api/admin/users'); document.querySelector('#app-view').innerHTML = `<section class="page-heading"><div><div class="eyebrow">إدارة المنصة <span>•</span> الحسابات والصلاحيات</div><h1>المستخدمون</h1><p>إدارة حسابات المنصة والأدوار بصلاحية مدير المنصة فقط.</p></div></section><section class="upload-panel" style="max-width:900px"><form id="admin-user-form"><label>الاسم الكامل<input name="name" required></label><label>البريد الإلكتروني<input name="email" type="email" required></label><label>كلمة المرور<input name="password" type="password" minlength="8" required></label><label>الدور<select name="role"><option value="company_respondent">مشارك شركة</option><option value="company_admin">مدير شركة</option><option value="consultant">استشاري</option><option value="researcher">باحث</option><option value="super_admin">مدير منصة</option></select></label><button class="primary-button" type="submit">إنشاء المستخدم</button></form><div class="priority-table" style="margin-top:20px"><div class="table-head"><span>المستخدم</span><span>البريد</span><span>الدور</span><span>المؤسسة</span></div>${data.users.map((item) => `<div class="table-row"><strong>${item.name}</strong><span>${item.email}</span><span>${item.role}</span><span>${item.organization_id || '--'}</span></div>`).join('')}</div></section>`; document.querySelector('#admin-user-form').addEventListener('submit', async (event) => { event.preventDefault(); try { await api('/api/admin/users', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(event.target))) }); showToast('تم إنشاء المستخدم'); renderAdminUsers(); } catch (error) { showToast(error.message); } }); } catch (error) { showToast(error.message); } }
loadDashboard();

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
async function approveImport() { const button = document.querySelector('#approve-import'); button.disabled = true; try { const draft = await api('/api/instrument-versions/import', { method: 'POST', body: JSON.stringify({ tables: latestImport.tables }) }); await api(`/api/instrument-versions/${draft.id}/approve`, { method: 'POST', body: '{}' }); button.textContent = `تم نشر الإصدار ${draft.version}`; showToast('تم حفظ ونشر إصدار الأداة'); } catch (error) { button.disabled = false; showToast(error.message); } }
