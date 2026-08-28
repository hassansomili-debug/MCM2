const state = {
  token: localStorage.getItem('mcm_token') || '',
  me: null,
  routeRequest: 0,
  authMode: 'login',
  assessment: null,
  pendingAnswers: new Map(),
  saveTimer: null,
  saveInFlight: null,
  routeController: null,
  publicConfig: {registration_enabled:true,demo_enabled:false,storage:'unknown'},
  importPreview: null,
  importPayload: null,
};

const appView = document.querySelector('#app-view');
const appShell = document.querySelector('#app-shell');
const toast = document.querySelector('#toast');
const dialog = document.querySelector('#app-dialog');
const dialogContent = document.querySelector('#dialog-content');

const roleLabels = {
  COMPANY_RESPONDENT: 'مشارك شركة', COMPANY_ADMIN: 'مدير شركة', CONSULTANT: 'استشاري',
  RESEARCHER: 'باحث', SUPER_ADMIN: 'مدير المنصة',
};
const statusLabels = {
  DRAFT: 'مسودة', IN_PROGRESS: 'قيد التنفيذ', COMPLETED: 'مكتمل', PILOT: 'نسخة تجريبية',
  VALIDATED: 'مُعتمد', ARCHIVED: 'مؤرشف', PENDING: 'بانتظار القبول', ACCEPTED: 'مقبولة',
  NOT_STARTED: 'لم يبدأ', IN_PROGRESS_ROADMAP: 'قيد التنفيذ', DEFERRED: 'مؤجل',
};
const errorLabels = {
  invalid_credentials: 'بيانات الدخول غير صحيحة.', session_expired: 'انتهت الجلسة. سجّل الدخول مرة أخرى.',
  authentication_required: 'يلزم تسجيل الدخول.', permission_denied: 'ليست لديك صلاحية لهذا الإجراء.',
  required_answers_missing: 'لا يزال هناك بنود مطلوبة بلا إجابة.', assessment_locked: 'هذا التقييم مكتمل ومقفل.',
  password_policy_failed: 'استخدم 10 أحرف على الأقل تتضمن حرفًا كبيرًا وصغيرًا ورقمًا.',
  email_already_exists: 'البريد مستخدم بالفعل.', invitation_invalid_or_expired: 'رابط الدعوة غير صالح أو منتهي.',
  instrument_validation_failed: 'ملف الأداة لم يجتز التحقق.', rate_limit_exceeded: 'محاولات كثيرة. حاول لاحقًا.',
  internal_error: 'حدث خطأ غير متوقع. حاول مرة أخرى.', route_not_found: 'المسار المطلوب غير موجود.',
  registration_disabled: 'إنشاء الحسابات معطل في بيئة العرض المؤقتة.',
};

function e(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
function number(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
  return new Intl.NumberFormat(document.documentElement.lang === 'en' ? 'en' : 'ar-SA', {maximumFractionDigits: digits, minimumFractionDigits: digits}).format(Number(value));
}
function dateText(timestamp) {
  if (!timestamp) return '--';
  const date = typeof timestamp === 'number' ? new Date(timestamp * 1000) : new Date(timestamp);
  return new Intl.DateTimeFormat(document.documentElement.lang === 'en' ? 'en' : 'ar-SA', {year:'numeric',month:'short',day:'numeric'}).format(date);
}
function showToast(message, type = 'success') {
  toast.textContent = message;
  toast.dataset.type = type;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 3400);
}
function openDialog(content) {
  dialogContent.innerHTML = content;
  if (!dialog.open) dialog.showModal();
}
function closeDialog() { if (dialog.open) dialog.close(); }
function apiMessage(error) { return errorLabels[error?.code] || error?.message || 'تعذر إكمال الطلب.'; }

async function api(path, options = {}) {
  const {routeScoped = true, ...requestOptions} = options;
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const signal = options.signal || (routeScoped ? state.routeController?.signal : undefined);
  const response = await fetch(path, {...requestOptions, headers, signal});
  const type = response.headers.get('content-type') || '';
  const payload = type.includes('application/json') ? await response.json() : null;
  if (!response.ok) {
    if (response.status === 401 && !path.includes('/participant/')) {
      state.token = ''; state.me = null; localStorage.removeItem('mcm_token');
    }
    const error = new Error(errorLabels[payload?.error] || payload?.error || `HTTP ${response.status}`);
    error.code = payload?.error; error.details = payload?.details; error.status = response.status;
    throw error;
  }
  return payload;
}

async function downloadApi(path) {
  const headers = new Headers();
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  const response = await fetch(path, {headers});
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(errorLabels[payload.error] || payload.error || 'تعذر التنزيل.');
    error.code = payload.error; throw error;
  }
  const blob = await response.blob();
  const disposition = response.headers.get('content-disposition') || '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const filename = match ? match[1] : 'download';
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function parseRoute() {
  const raw = (location.hash.slice(1) || (state.token ? 'overview' : 'login'));
  const [path, queryString = ''] = raw.split('?');
  return {path: path.replace(/^\/+|\/+$/g, '') || 'overview', parts: path.split('/').filter(Boolean), query: new URLSearchParams(queryString)};
}
function navigate(route) {
  const target = `#${String(route).replace(/^#/, '')}`;
  if (location.hash === target) router(); else location.hash = target;
}
function loading(label = 'جارٍ تحميل البيانات...') { appView.innerHTML = `<section class="loading-page"><span class="spinner" aria-hidden="true"></span><p>${e(label)}</p></section>`; }
function emptyState(title, copy, action = '') { return `<section class="empty-state"><b>${e(title)}</b><p>${e(copy)}</p>${action}</section>`; }
function errorState(error) { return `<section class="route-state"><div>${emptyState('تعذر تحميل الصفحة', apiMessage(error), '<button class="primary-button" data-action="retry-route" type="button">إعادة المحاولة</button>')}</div></section>`; }
function pageHeading(kicker, title, copy, actions = '') { return `<section class="page-heading"><div><div class="eyebrow">${e(kicker)}</div><h1>${e(title)}</h1><p>${copy}</p></div>${actions ? `<div class="page-heading-actions">${actions}</div>` : ''}</section>`; }
function researchNotice(status = 'PILOT') { return `<div class="research-notice"><strong>Research Beta</strong><span>إصدار الأداة الحالي ${e(status)} وقيد التحقق التجريبي. النتائج تشخيصية أولية ولا تمثل ادعاء صلاحية سيكومترية.</span></div>`; }
function badge(value, tone = '') { return `<span class="status-badge ${tone}">${e(statusLabels[value] || value || '--')}</span>`; }
function table(headers, rows, columns = headers.length, min = 720) {
  return `<div class="table-scroll"><div class="data-table" style="--table-columns:repeat(${columns},minmax(130px,1fr));--table-min:${min}px"><div class="data-table__row header">${headers.map(item => `<span>${e(item)}</span>`).join('')}</div>${rows.join('')}</div></div>`;
}

function hasRole(...roles) { return roles.includes(state.me?.user?.role); }
function canManageAssessments() { return hasRole('COMPANY_ADMIN','CONSULTANT','SUPER_ADMIN'); }
function canManageCompany() { return hasRole('COMPANY_ADMIN','SUPER_ADMIN'); }
function canManageRoadmap() { return hasRole('COMPANY_ADMIN','SUPER_ADMIN'); }

function applyShell() {
  const isGuest = !state.me;
  appShell.classList.toggle('is-guest', isGuest);
  document.documentElement.lang = 'ar';
  document.documentElement.dir = 'rtl';
  document.querySelectorAll('[data-roles]').forEach(node => {
    const roles = node.dataset.roles.split(',');
    node.hidden = isGuest || !roles.includes(state.me?.user?.role);
  });
  if (isGuest) return;
  document.querySelector('#user-name').textContent = state.me.user.name;
  document.querySelector('#user-avatar').textContent = (state.me.user.name || 'م').trim()[0];
  document.querySelector('#active-org-name').textContent = state.me.organization.name;
  document.querySelector('#active-org-role').textContent = roleLabels[state.me.user.role] || state.me.user.role;
  const count = document.querySelector('#notification-count');
  count.textContent = state.me.unread_notifications || 0; count.hidden = !state.me.unread_notifications;
}

const publicRoutes = new Set(['login', 'participant', 'participant-assessment', 'forgot', 'reset']);
const researchRoutes = new Set(['research', 'dataset', 'instruments', 'instrument', 'data-quality', 'statistics', 'exports']);
async function router() {
  const request = ++state.routeRequest;
  state.routeController?.abort();
  state.routeController = new AbortController();
  const route = parseRoute();
  if (state.pendingAnswers.size && !['assessment','participant-assessment'].includes(route.parts[0])) {
    try { await flushAnswers(); } catch (error) { showToast(apiMessage(error),'error'); }
  }
  document.querySelectorAll('.nav-item').forEach(item => item.classList.toggle('active', item.dataset.route === route.parts[0]));
  document.querySelector('#sidebar').classList.remove('open');
  document.querySelector('#menu-button').setAttribute('aria-expanded', 'false');
  if (!state.token && !publicRoutes.has(route.parts[0])) return navigate('login');
  if (state.token && !state.me) {
    try { state.me = await api('/api/me'); applyShell(); }
    catch { applyShell(); if (!publicRoutes.has(route.parts[0])) return navigate('login'); }
  }
  if (researchRoutes.has(route.parts[0]) && !['RESEARCHER','SUPER_ADMIN'].includes(state.me?.user?.role)) return navigate('overview');
  if (route.parts[0] === 'admin' && state.me?.user?.role !== 'SUPER_ADMIN') return navigate('overview');
  if (route.parts[0] === 'participants' && !canManageAssessments()) return navigate('overview');
  const labels = {overview:'نظرة عامة',assessments:'التقييمات',assessment:'التقييم',results:'النتائج',dimension:'تفاصيل البعد',diagnosis:'التشخيص',gaps:'تحليل الفجوات',priorities:'الأولويات',roadmap:'خارطة التحسين',history:'مسار النضج',benchmark:'المقارنة المرجعية',reports:'التقارير',participants:'المشاركون',participant:'دخول المشارك','participant-assessment':'تقييم المشارك',notifications:'الإشعارات',settings:'الإعدادات',methodology:'المنهجية',research:'لوحة الباحث',dataset:'مجموعة البيانات',instruments:'إصدارات الأداة',instrument:'تفاصيل الأداة','data-quality':'جودة البيانات',statistics:'الإحصاءات',exports:'التصدير',admin:'إدارة المنصة'};
  document.querySelector('#page-label').textContent = labels[route.parts[0]] || 'نضج MCM';
  const handlers = {login:renderAuth,forgot:renderForgot,reset:renderReset,overview:renderOverview,assessments:renderAssessments,assessment:renderAssessment,results:renderResults,dimension:renderDimension,diagnosis:renderDiagnosis,gaps:renderGaps,priorities:renderPriorities,roadmap:renderRoadmap,history:renderHistory,benchmark:renderBenchmark,reports:renderReports,participants:renderParticipants,participant:renderParticipant,'participant-assessment':renderParticipantAssessment,notifications:renderNotifications,settings:renderSettings,methodology:renderMethodology,research:renderResearch,dataset:renderDataset,instruments:renderInstruments,instrument:renderInstrument,'data-quality':renderDataQuality,statistics:renderStatistics,exports:renderExports,admin:renderAdmin};
  const handler = handlers[route.parts[0]];
  if (!handler) { appView.innerHTML = emptyState('الصفحة غير موجودة', 'تحقق من الرابط أو عد إلى لوحة البيانات.', '<a class="primary-button" href="#overview">العودة للرئيسية</a>'); return; }
  try { await handler(route); if (request === state.routeRequest) appView.focus({preventScroll:true}); }
  catch (error) { if (error.name !== 'AbortError' && request === state.routeRequest) appView.innerHTML = errorState(error); }
}

function renderAuth() {
  state.me = null; applyShell();
  if (!state.publicConfig.registration_enabled && state.authMode === 'register') state.authMode = 'login';
  const register = state.authMode === 'register';
  const localDemo = state.publicConfig.demo_enabled || ['localhost','127.0.0.1'].includes(location.hostname);
  const demoEmail = state.publicConfig.demo_email || 'sara@example.com';
  const demoPassword = state.publicConfig.demo_password || 'ChangeMe-2026';
  const ephemeralNotice = state.publicConfig.storage === 'ephemeral-demo' ? `<div class="research-notice"><strong>بيئة عرض مؤقتة</strong><span>${e(state.publicConfig.notice || 'لا تستخدم بيانات حقيقية؛ قد يعاد ضبط البيانات.')}</span></div>` : '';
  const registerTab = state.publicConfig.registration_enabled ? `<button class="${register ? 'active' : ''}" data-action="auth-mode" data-mode="register" type="button">إنشاء حساب</button>` : '';
  const demoBlock = localDemo ? `<div class="demo-access">حساب العرض: <code>${e(demoEmail)}</code> / <code>${e(demoPassword)}</code></div>` : '';
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>نضج MCM</div><div class="auth-copy"><div class="eyebrow">MARKETING COMMUNICATION MATURITY</div><h1>قِس الاتصال.<br><i>طوّر الأثر.</i></h1><p>منصة تشخيصية تساعد المؤسسة على فهم قدراتها الاتصالية، ترتيب فجواتها، وتحويل النتائج إلى خارطة تطوير قابلة للتنفيذ.</p><div class="auth-features"><span>قياس حتمي على الخادم</span><span>MCM وSMCE منفصلان</span><span>بحث وتصدير مجهول</span></div></div><small>Research Beta · Provisional Instrument</small></div><div class="auth-panel"><div class="auth-box">${ephemeralNotice}<div class="auth-tabs"><button class="${register ? '' : 'active'}" data-action="auth-mode" data-mode="login" type="button">تسجيل الدخول</button>${registerTab}</div><h2>${register ? 'أنشئ مساحة مؤسستك' : 'مرحبًا بعودتك'}</h2><p>${register ? 'ابدأ بملف المؤسسة ثم نفّذ التقييم الأول.' : 'ادخل إلى النتائج والتقييمات وخارطة التحسين.'}</p><form id="auth-form" class="form-grid">${register ? `<label class="field"><span>الاسم الكامل</span><input name="name" required autocomplete="name"></label><label class="field"><span>اسم المؤسسة</span><input name="organization_name" required></label>` : ''}<label class="field ${register ? '' : 'full'}"><span>البريد الإلكتروني</span><input name="email" type="email" required autocomplete="email" value="${!register && localDemo ? e(demoEmail) : ''}"></label><label class="field ${register ? '' : 'full'}"><span>كلمة المرور</span><input name="password" type="password" required autocomplete="${register ? 'new-password' : 'current-password'}" value="${!register && localDemo ? e(demoPassword) : ''}"></label>${register ? `<label class="checkbox-field full"><input name="service_consent" type="checkbox" required><span>أوافق على معالجة البيانات لأغراض التشخيص وتقديم الخدمة.</span></label>` : ''}<div id="auth-error" class="form-error full" hidden></div><button class="primary-button full" type="submit">${register ? 'إنشاء الحساب' : 'دخول المنصة'}</button></form>${register ? '' : `<div class="button-row"><button class="secondary-button" data-action="forgot-password" type="button">نسيت كلمة المرور</button><a class="secondary-button" href="#participant">لدي دعوة مشاركة</a></div>${demoBlock}`}</div></div></section>`;
}

function renderForgot() {
  state.me = null; applyShell();
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>نضج MCM</div><div class="auth-copy"><h1>استعادة<br><i>آمنة للحساب.</i></h1><p>لن نكشف ما إذا كان البريد مسجلًا أم لا.</p></div></div><div class="auth-panel"><div class="auth-box"><h2>نسيت كلمة المرور</h2><p>أدخل بريدك لاستلام تعليمات الاستعادة عبر القناة المضبوطة.</p><form id="forgot-form" class="form-grid"><label class="field full"><span>البريد</span><input name="email" type="email" required></label><button class="primary-button full">إرسال الطلب</button></form><p><a href="#login">العودة لتسجيل الدخول</a></p></div></div></section>`;
}
function renderReset(route) {
  state.me = null; applyShell();
  const token = route.query.get('token') || '';
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>نضج MCM</div><div class="auth-copy"><h1>كلمة مرور<br><i>جديدة.</i></h1></div></div><div class="auth-panel"><div class="auth-box"><h2>إعادة ضبط كلمة المرور</h2><form id="reset-form" class="form-grid"><input type="hidden" name="token" value="${e(token)}"><label class="field full"><span>كلمة المرور الجديدة</span><input name="password" type="password" minlength="10" required></label><button class="primary-button full">حفظ كلمة المرور</button></form></div></div></section>`;
}

async function renderOverview() {
  loading('جارٍ تحميل لوحة النضج...');
  const data = await api('/api/dashboard');
  const actions = canManageAssessments() ? `<button class="primary-button" data-action="create-assessment" type="button">تقييم جديد</button>` : '';
  if (!data.latest) {
    const emptyAction = canManageAssessments() ? '<button class="primary-button" data-action="create-assessment" type="button">ابدأ أول تقييم</button>' : '<a class="primary-button" href="#assessments">عرض التقييمات المعيّنة</a>';
    appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · نظرة عامة', `مرحبًا، ${state.me.user.name}`, `ابدأ أول قياس لمؤسسة <strong>${e(data.organization.name)}</strong>.`, actions)}${researchNotice()}<div class="card-grid"><article class="card metric-card span-4"><small>اكتمال ملف المؤسسة</small><strong>${number(data.profile_completion)}<em>%</em></strong><a href="#settings">عرض الملف</a></article><article class="card metric-card span-4"><small>تقييمات قيد التنفيذ</small><strong>${number(data.draft_count)}</strong><a href="#assessments">عرض المسودات</a></article><article class="card metric-card span-4"><small>النتائج المتاحة</small><strong>0</strong><span>تظهر بعد إرسال التقييم</span></article></div>${emptyState('لم يتم تنفيذ تقييم بعد.', 'تظهر هنا النتائج بعد اكتمال تقييم يستخدم إصدار الأداة الحالي.', emptyAction)}</div>`;
    return;
  }
  const result = data.latest; const mcm = result.scores.MCM; const smce = result.scores.SMCE;
  const dimensions = mcm.dimensions.map(item => `<div class="dimension-line"><a href="#dimension/${result.assessment_id}/${e(item.code)}">${e(item.code)} · ${e(item.name)}</a><div class="dimension-track"><i style="--score:${Number(item.score)}%"></i></div><b>${number(item.score,1)}</b></div>`).join('');
  const history = data.history.map(item => `<div class="trend-column" title="${e(dateText(item.completed_at))}: ${number(item.mcm,1)}"><i style="--score:${Number(item.mcm || 0)}"></i><span>${e(dateText(item.completed_at))}</span></div>`).join('');
  const diagnoses = data.diagnoses.length ? data.diagnoses.map(item => `<article class="card diagnosis-card ${item.severity === 'HIGH' ? 'high' : ''}">${badge(item.severity, item.severity === 'HIGH' ? 'danger' : 'warning')}<h3>${e(item.name)}</h3><p>${e(item.business_implication)}</p><a href="#diagnosis/${result.assessment_id}">عرض الأدلة</a></article>`).join('') : `<article class="card"><h3>لا توجد قواعد تشخيص مفعلة على النتيجة</h3><p>لا يعني ذلك اعتماد الأداة؛ راجع الأبعاد والأولويات المتاحة.</p></article>`;
  const priorityRows = data.priorities.map(item => `<div class="data-table__row"><span>${number(item.rank)}</span><strong>${e(item.dimension_code)}<small>${e(item.problem)}</small></strong><span>${number(item.current_score,1)}</span><span>${number(item.gap,1)}</span><span>${e(item.suggested_owner || '--')}</span><a href="#priorities/${result.assessment_id}">فتح</a></div>`);
  appView.innerHTML = `<div class="page">${pageHeading(`آخر تقييم · ${dateText(result.completed_at)}`, `صباح الخير، ${state.me.user.name}`, `هذه قراءة آخر تقييم مكتمل لمؤسسة <strong>${e(data.organization.name)}</strong> · مصدر البيانات ${e(result.data_origin)}.`, actions)}${researchNotice(result.instrument_status)}<div class="card-grid"><article class="card metric-card teal span-4"><small>درجة MCM الكلية</small><strong>${number(mcm.total,1)}<em>/100</em></strong><span>${e(mcm.maturity_level?.label_ar || 'تصنيف غير متاح')}</span></article><article class="card metric-card span-4"><small>كفاءة التواصل SMCE</small><strong>${number(smce.total,1)}<em>/100</em></strong><span>نتيجة مستقلة عن MCM</span></article><article class="card metric-card span-4"><small>اكتمال ملف المؤسسة</small><strong>${number(data.profile_completion)}<em>%</em></strong><a href="#settings">عرض الملف</a></article><article class="card span-8"><div class="card-title"><div><h2>أبعاد النضج الاتصالي</h2><p>الأبعاد السبعة مستقلة وقابلة للتشخيص.</p></div><a href="#results/${result.assessment_id}">كل النتائج</a></div><div class="dimension-list">${dimensions}</div></article><article class="card span-4"><div class="card-title"><div><h2>قراءة تشخيصية</h2><p>قواعد حتمية لا تعتمد على الذكاء الاصطناعي.</p></div></div>${diagnoses}</article><article class="card span-12"><div class="card-title"><div><h2>مسار النضج</h2><p>التقييمات المكتملة فقط.</p></div><a href="#history">التاريخ الكامل</a></div><div class="trend-chart">${history}</div></article></div><section class="panel"><div class="card-title"><div><h2>أولويات التطوير</h2><p>ترتيب قابل للتدقيق من الفجوة والأثر والاعتمادية والجهد.</p></div><a href="#roadmap/${result.assessment_id}">عرض الخارطة</a></div>${data.priorities.length ? table(['الترتيب','البعد','الحالي','الفجوة','المالك',''], priorityRows, 6, 820) : emptyState('لا توجد أولويات بعد', 'لم تُولد أولويات لهذه النتيجة.')}</section></div>`;
}

async function renderAssessments() {
  loading(); const data = await api('/api/assessments');
  const createAction = canManageAssessments() ? '<button class="primary-button" data-action="create-assessment" type="button">تقييم جديد</button>' : '';
  const rows = data.assessments.map(item => `<div class="data-table__row"><strong>#${item.id}<small>${e(item.assessment_type)}</small></strong><span>${badge(item.status, item.status === 'COMPLETED' ? '' : 'warning')}</span><span>${e(item.instrument_version)} · ${e(item.instrument_status)}</span><span>${dateText(item.created_at)}</span><span>${number(item.mcm_total,1)}</span><span class="button-row">${item.status === 'COMPLETED' ? `<a class="secondary-button" href="#results/${item.id}">النتائج</a>${canManageAssessments() ? `<button class="secondary-button" data-action="repeat-assessment" data-id="${item.id}">إعادة</button>` : ''}` : `<a class="primary-button" href="#assessment/${item.id}">فتح</a>`}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · التقييمات','التقييمات المؤسسية','الحفظ والاستكمال مرتبطان بالمشارك وصلاحيته داخل المؤسسة.', createAction)}${researchNotice()}<section class="panel">${rows.length ? table(['التقييم','الحالة','إصدار الأداة','تاريخ البدء','MCM','الإجراء'], rows, 6, 850) : emptyState('لا توجد تقييمات', 'لا توجد تقييمات معيّنة لهذا الحساب.', createAction)}</section></div>`;
}

function questionCard(item, response, disabled = false) {
  const value = response?.value;
  const type = String(item.response_type || 'LIKERT').toUpperCase();
  const minimum = Number(item.min_value ?? 1); const maximum = Number(item.max_value ?? 5);
  const lock = disabled ? ' disabled' : '';
  let control;
  if (type === 'TEXT') {
    control = `<label class="field answer-field"><span>الإجابة النصية</span><textarea name="q_${item.id}" data-answer-input data-item-id="${item.id}" rows="4"${lock}>${response?.missing_type ? '' : e(value)}</textarea></label>`;
  } else if (type === 'NUMERIC' && (!Number.isInteger(minimum) || !Number.isInteger(maximum) || maximum - minimum > 10)) {
    control = `<label class="field answer-field"><span>قيمة من ${number(minimum)} إلى ${number(maximum)}</span><input name="q_${item.id}" data-answer-input data-item-id="${item.id}" type="number" min="${minimum}" max="${maximum}" step="any" value="${response?.missing_type || value === null || value === undefined ? '' : e(value)}"${lock}></label>`;
  } else {
    const values = type === 'BOOLEAN' ? [minimum, maximum] : Array.from({length:Math.max(1,Math.min(11,Math.floor(maximum)-Math.ceil(minimum)+1))},(_,index)=>Math.ceil(minimum)+index);
    const choices = values.map((choice,index) => `<label><input type="radio" name="q_${item.id}" value="${choice}" data-answer-input data-item-id="${item.id}" ${Number(value) === choice && !response?.missing_type ? 'checked' : ''}${lock}><span>${type === 'BOOLEAN' ? (index ? 'نعم' : 'لا') : number(choice)}</span></label>`).join('');
    control = `<div class="choice-scale" style="--choice-count:${values.length}">${choices}</div>`;
  }
  const disabledButton = disabled ? ' disabled' : '';
  return `<fieldset class="question-card" data-question="${item.id}"${disabled ? ' disabled' : ''}><legend class="question-title"><code>${e(item.code)}</code><span>${e(item.prompt_ar)}${item.required ? ' <b class="required-mark">*</b>' : ''}</span></legend>${control}<details class="missing-control"><summary>${response?.missing_type ? `حالة الغياب: ${e(response.missing_type)}` : 'لا يمكنني الإجابة'}</summary><div class="missing-options"><button type="button" data-action="missing-answer" data-item-id="${item.id}" data-missing="NOT_APPLICABLE"${disabledButton}>لا ينطبق</button><button type="button" data-action="missing-answer" data-item-id="${item.id}" data-missing="SKIPPED"${disabledButton}>تخطي</button><button type="button" data-action="clear-answer" data-item-id="${item.id}"${disabledButton}>مسح</button></div></details></fieldset>`;
}

async function renderAssessment(route) {
  const id = Number(route.parts[1]); if (!id) return navigate('assessments');
  await flushAnswers();
  loading('جارٍ تحميل بنود التقييم...'); const data = await api(`/api/assessments/${id}`);
  if (data.assessment.status === 'COMPLETED') return navigate(`results/${id}`);
  state.assessment = data; state.pendingAnswers.clear();
  const locked = !data.can_respond;
  const constructs = [
    ['ENABLER','العوامل التمكينية والسياق','لا تدخل في درجة MCM.'],
    ['MCM','النضج الاتصالي MCM','سبعة أبعاد تُحتسب بصورة مستقلة.'],
    ['SMCE','كفاءة الاتصال عبر التواصل الاجتماعي SMCE','نتيجة مستقلة عن MCM.'],
    ['OUTCOME','النتائج الاختيارية','لا تدخل في الدرجة العلمية الأساسية.'],
  ];
  const sections = constructs.map(([construct,title,copy]) => {
    const items = data.items.filter(item => item.construct === construct);
    if (!items.length) return '';
    const byDimension = items.reduce((acc,item) => ((acc[item.dimension_code] ||= []).push(item),acc),{});
    return `<section class="assessment-section"><header><div><h2>${e(title)}</h2><p>${e(copy)}</p></div><span>${items.length} بندًا</span></header>${Object.entries(byDimension).map(([code, rows]) => `<div class="panel"><div class="card-title"><div><h3>${e(code)}</h3><p>${rows.length} بنود</p></div></div>${rows.map(item => questionCard(item,data.responses[item.id],locked)).join('')}</div>`).join('')}</section>`;
  }).join('');
  const footer = locked ? emptyState('وضع عرض فقط','أنت مخوّل لعرض حالة التقييم، ولست مشاركًا معيّنًا للإجابة عليه.','<a class="secondary-button" href="#assessments">العودة للتقييمات</a>') : `<div class="button-row"><button class="primary-button" data-action="submit-assessment" data-id="${id}" type="button">مراجعة وإرسال</button><a class="secondary-button" href="#assessments">حفظ والاستكمال لاحقًا</a></div><p class="save-state">لن تُحسب النتائج قبل التحقق من جميع البنود المطلوبة وإرسال التقييم.</p>`;
  appView.innerHTML = `<div class="page assessment-page">${pageHeading(`التقييم #${id} · ${e(data.instrument.version)}`,'التقييم المؤسسي','اختر الإجابة التي تصف الممارسة الحالية، لا الحالة المرغوبة.', '<a class="secondary-button" href="#assessments">حفظ وخروج</a>')} ${researchNotice(data.instrument.status)}<section class="assessment-header"><div class="progress-row"><strong>التقدم <span id="progress-value">${number(data.review.progress,0)}%</span></strong><span class="save-state" id="save-state">محفوظ على الخادم</span></div><div class="progress-track"><span id="progress-bar" style="--progress:${data.review.progress}%"></span></div></section><form id="assessment-form">${sections}</form><section class="panel">${footer}</section></div>`;
}

async function renderResults(route) {
  const id = Number(route.parts[1]); if (!id) return navigate('assessments');
  loading('جارٍ تحميل النتائج...'); const data = await api(`/api/results/${id}`);
  const mcm = data.scores.MCM; const smce = data.scores.SMCE;
  const dimLines = mcm.dimensions.map(item => `<div class="dimension-line"><a href="#dimension/${id}/${e(item.code)}">${e(item.code)} · ${e(item.name)}</a><div class="dimension-track"><i style="--score:${Number(item.score)}%"></i></div><b>${number(item.score,1)}</b></div>`).join('');
  const smceLines = smce.dimensions.map(item => `<div class="dimension-line"><span>${e(item.code)} · ${e(item.name)}</span><div class="dimension-track"><i style="--score:${Number(item.score)}%"></i></div><b>${number(item.score,1)}</b></div>`).join('');
  const actions = `<a class="secondary-button" href="#diagnosis/${id}">التشخيص</a><a class="secondary-button" href="#gaps/${id}">الفجوات</a><a class="secondary-button" href="#priorities/${id}">الأولويات</a><a class="primary-button" href="#roadmap/${id}">خارطة التحسين</a>`;
  const reportAction = canManageAssessments() ? `<button class="primary-button" data-action="generate-report" data-id="${id}" data-type="EXECUTIVE">5. إنشاء التقرير</button>` : '';
  appView.innerHTML = `<div class="page">${pageHeading(`نتائج التقييم #${id}`,`نتيجة ${e(data.organization_name)}`,`اكتمل القياس بتاريخ ${e(dateText(data.completed_at))}.`, actions)}${researchNotice(data.instrument_status)}<div class="card-grid"><article class="card span-6"><div class="card-title"><div><h2>النضج الاتصالي MCM</h2><p>متوسط موزون للأبعاد السبعة فقط.</p></div>${badge(mcm.maturity_level?.label_ar || 'غير مصنف')}</div><div class="score-layout"><div class="score-ring" style="--score:${Number(mcm.total || 0)}"><div><strong>${number(mcm.total,1)}</strong><small>/100</small></div></div><div class="dimension-list">${dimLines}</div></div></article><article class="card span-6"><div class="card-title"><div><h2>كفاءة التواصل SMCE</h2><p>Communication Efficiency Outcome · مستقل عن MCM.</p></div></div><div class="score-layout"><div class="score-ring" style="--score:${Number(smce.total || 0)}"><div><strong>${number(smce.total,1)}</strong><small>/100</small></div></div><div class="dimension-list">${smceLines}</div></div></article></div><section class="panel"><div class="card-title"><div><h2>من النتيجة إلى التنفيذ</h2><p>انتقل بالتسلسل من الأدلة إلى الفجوة والأولوية ثم خارطة العمل.</p></div></div><div class="button-row"><a class="secondary-button" href="#diagnosis/${id}">1. التشخيص العميق</a><a class="secondary-button" href="#gaps/${id}">2. تحليل الفجوات</a><a class="secondary-button" href="#priorities/${id}">3. ترتيب الأولويات</a><a class="secondary-button" href="#benchmark/${id}">4. المقارنة المرجعية</a>${reportAction}</div></section></div>`;
}

async function renderDimension(route) {
  const id = Number(route.parts[1]); const code = route.parts[2]; if (!id || !code) return navigate(`results/${id || ''}`);
  loading(); const data = await api(`/api/results/${id}/dimensions/${encodeURIComponent(code)}`); const item = data.dimension;
  const diagnoses = data.diagnoses.map(row => `<article class="card diagnosis-card ${row.severity === 'HIGH' ? 'high' : ''}">${badge(row.severity,row.severity === 'HIGH' ? 'danger':'warning')}<h3>${e(row.name)}</h3><p>${e(row.interpretation)}</p></article>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading(`نتائج #${id} · ${e(code)}`,e(item.name || code),e(item.name_en || ''),`<a class="secondary-button" href="#results/${id}">العودة للنتائج</a>`)}${researchNotice()}<div class="card-grid"><article class="card metric-card teal span-4"><small>درجة البعد</small><strong>${number(item.score,1)}<em>/100</em></strong><span>${number(item.answered_count)} من ${number(item.eligible_count)} بندًا</span></article><article class="card span-8"><h2>التفسير والإجراء</h2>${data.recommendation ? `<h3>${e(data.recommendation.problem)}</h3><p>${e(data.recommendation.action)}</p><div class="pill-list"><span>المالك: ${e(data.recommendation.suggested_owner)}</span><span>الأثر: ${e(data.recommendation.expected_impact)}</span><span>الجهد: ${e(data.recommendation.effort)}</span><span>KPI: ${e(data.recommendation.kpi)}</span></div>` : '<p>لا توجد توصية مرتبطة بهذا الإصدار.</p>'}</article></div><section><div class="card-title"><div><h2>التشخيصات المرتبطة</h2><p>${e(data.evidence_notice)}</p></div></div><div class="card-grid">${diagnoses || emptyState('لا توجد قاعدة مطابقة', 'لم تتحقق شروط تشخيص مرتبطة بهذا البعد.')}</div></section></div>`;
}

async function renderDiagnosis(route) {
  const id = Number(route.parts[1]) || await latestCompletedId(); if (!id) return navigate('assessments');
  loading(); const data = await api(`/api/diagnostics/${id}`);
  const cards = data.diagnoses.map(item => `<article class="card diagnosis-card ${item.severity === 'HIGH' ? 'high' : ''}"><div class="card-title"><div>${badge(item.severity,item.severity === 'HIGH' ? 'danger':'warning')}<h3>${e(item.name)}</h3></div><strong>${number(item.confidence * 100)}%</strong></div><div class="evidence-list">${Object.entries(item.evidence).map(([key,value]) => `<span>${e(key)}: ${number(value,1)}</span>`).join('')}</div><p><strong>التفسير:</strong> ${e(item.interpretation)}</p><p><strong>الأثر:</strong> ${e(item.business_implication)}</p></article>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading(`التقييم #${id}`,'التشخيص العميق','قواعد بيانات حتمية مع أدلة ظاهرة وثقة مسجلة.',`<a class="secondary-button" href="#results/${id}">النتائج</a><a class="primary-button" href="#priorities/${id}">الأولويات</a>`)}${researchNotice()}<div class="card-grid">${cards || emptyState('لا توجد تشخيصات مطابقة', 'لم تتحقق الشروط الرقمية للقواعد النشطة في هذا الإصدار.')}</div></div>`;
}

async function renderGaps(route) {
  const id = Number(route.parts[1]) || await latestCompletedId(); if (!id) return navigate('assessments');
  loading(); const data = await api(`/api/gaps/${id}`);
  const rows = data.gaps.map(item => `<div class="data-table__row"><strong>${e(item.name)}<small>${e(item.code)}</small></strong><span>${e(item.source)}</span><span>${e(item.target)}</span><span>${number(item.gap,1)}</span><span>${number(item.threshold,1)}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading(`التقييم #${id}`,'تحليل الفجوات',`تظهر الفجوة عندما يتجاوز الفرق الحد المضبوط (${number(data.threshold,1)} نقطة).`,`<a class="secondary-button" href="#diagnosis/${id}">التشخيص</a><a class="primary-button" href="#priorities/${id}">ترتيب الأولويات</a>`)}<section class="panel">${rows.length ? table(['النمط','المصدر','الهدف','الفجوة','الحد'],rows,5,760) : emptyState('لا توجد فجوات عابرة للأبعاد', 'لم يتجاوز أي نمط حد الفجوة المضبوط.')}</section></div>`;
}

async function renderPriorities(route) {
  const id = Number(route.parts[1]) || await latestCompletedId(); if (!id) return navigate('assessments');
  loading(); const data = await api(`/api/priorities/${id}`);
  const cards = data.priorities.map(item => `<article class="card"><div class="card-title"><div><span class="status-badge">الأولوية ${number(item.rank)}</span><h3>${e(item.problem)}</h3><p>${e(item.dimension_code)}</p></div><strong>${number(item.priority_score,1)}</strong></div><p>${e(item.action)}</p><div class="pill-list"><span>الحالي ${number(item.current_score,1)}</span><span>الفجوة ${number(item.gap,1)}</span><span>المالك ${e(item.suggested_owner)}</span><span>الجهد ${e(item.effort)}</span></div></article>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading(`التقييم #${id}`,'أولويات التطوير','ترتيب حتمي قابل للتدقيق، ولا تدخل الفجوات السالبة في الأولوية.',`<a class="secondary-button" href="#gaps/${id}">الفجوات</a><a class="primary-button" href="#roadmap/${id}">تحويلها إلى خطة</a>`)}<div class="card-grid">${cards || emptyState('لا توجد أولويات', 'لم تُولد توصيات قابلة للترتيب لهذا الإصدار.')}</div></div>`;
}

async function latestCompletedId() {
  const data = await api('/api/assessments');
  return data.assessments.find(item => item.status === 'COMPLETED')?.id || null;
}

async function renderRoadmap(route) {
  const id = Number(route.parts[1]) || await latestCompletedId();
  if (!id) { appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل','خارطة التحسين','تُنشأ الخارطة بعد اكتمال تقييم.','<a class="primary-button" href="#assessments">اذهب للتقييمات</a>')}${emptyState('لا توجد خارطة بعد','أكمل أول تقييم ليحوّل المحرك الأولويات إلى خطة 30/90/180 يومًا.')}</div>`; return; }
  loading(); const data = await api(`/api/roadmap/${id}`);
  const columns = [['0-30','0–30 يومًا'],['31-90','31–90 يومًا'],['3-6','3–6 أشهر']].map(([key,label]) => `<section class="roadmap-column"><h2>${label}</h2>${(data.roadmap[key] || []).map(item => `<article class="roadmap-item"><h3>${e(item.title)}</h3><p>${e(item.description)}</p><div class="roadmap-meta"><span>${e(item.owner || 'غير معيّن')}</span><span>${e(item.target_date || '--')}</span>${badge(item.status,item.status === 'COMPLETED' ? '' : 'neutral')}</div>${['COMPANY_ADMIN','SUPER_ADMIN'].includes(state.me.user.role) ? `<button class="secondary-button" data-action="edit-roadmap" data-assessment-id="${id}" data-id="${item.id}" data-owner="${e(item.owner || '')}" data-date="${e(item.target_date || '')}" data-status="${e(item.status)}" type="button">تحديث</button>` : ''}</article>`).join('') || '<p>لا توجد إجراءات في هذا الأفق.</p>'}</section>`).join('');
  const reportAction = canManageAssessments() ? `<button class="primary-button" data-action="generate-report" data-id="${id}" data-type="DETAILED">تقرير تفصيلي</button>` : '';
  appView.innerHTML = `<div class="page">${pageHeading(`التقييم #${id}`,'خارطة التحسين','حوّل التشخيص إلى مالك وتاريخ وحالة ومؤشر قياس.',`<a class="secondary-button" href="#priorities/${id}">الأولويات</a>${reportAction}`)}<div class="roadmap-board">${columns}</div></div>`;
}

async function renderHistory() {
  loading(); const data = await api('/api/history?range=all');
  const trend = data.history.map(item => `<div class="trend-column"><i style="--score:${Number(item.mcm_total || 0)}"></i><span>${e(dateText(item.completed_at))}</span></div>`).join('');
  const rows = data.history.map(item => `<div class="data-table__row"><strong>#${item.id}<small>${e(item.assessment_type)}</small></strong><span>${dateText(item.completed_at)}</span><span>${e(item.instrument_version)}</span><span>${number(item.mcm_total,1)}</span><span>${e(item.maturity_level || '--')}</span><span>${number(item.smce_total,1)}</span><a href="#results/${item.id}">فتح</a></div>`);
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · التاريخ','مسار النضج','كل نقطة مرتبطة بتاريخ تقييم فعلي وإصدار أداة محفوظ.')}<section class="card"><div class="trend-chart">${trend || '<p>لا توجد نقاط بعد.</p>'}</div></section><section class="panel">${rows.length ? table(['التقييم','التاريخ','الإصدار','MCM','المستوى','SMCE',''],rows,7,900) : emptyState('لا يوجد تاريخ بعد','أكمل تقييمين على الأقل لمقارنة المسار.')}</section></div>`;
}

async function renderBenchmark(route) {
  const id = Number(route.parts[1]) || await latestCompletedId(); if (!id) return navigate('assessments');
  loading(); const cohort = route.query.get('cohort') || 'overall'; const data = await api(`/api/benchmark/${id}?cohort=${encodeURIComponent(cohort)}`);
  const filters = `<div class="button-row"><a class="secondary-button" href="#benchmark/${id}?cohort=overall">الإجمالي</a><a class="secondary-button" href="#benchmark/${id}?cohort=sector">القطاع</a><a class="secondary-button" href="#benchmark/${id}?cohort=size">الحجم</a></div>`;
  const content = data.available ? `<div class="card-grid"><article class="card metric-card span-4"><small>نتيجة المؤسسة</small><strong>${number(data.company_score,1)}</strong></article><article class="card metric-card span-4"><small>متوسط المجموعة</small><strong>${number(data.cohort_average,1)}</strong></article><article class="card metric-card span-4"><small>الربع الأعلى</small><strong>${number(data.top_quartile,1)}</strong></article></div><p>حجم العينة: ${number(data.sample_size)} · وحدة التحليل: آخر تقييم مكتمل لكل مؤسسة.</p>` : emptyState('لا تتوفر عينة كافية حاليًا لإظهار مقارنة موثوقة.', data.reason === 'NON_REAL_ASSESSMENT' ? 'التقييمات التجريبية لا تدخل في المقارنة الواقعية.' : `تُحجب المقارنة عندما تكون العينة أقل من ${number(data.minimum_sample)}، دون كشف حجم الخلية الدقيق.`);
  appView.innerHTML = `<div class="page">${pageHeading(`التقييم #${id}`,'المقارنة المرجعية','تطبيق صارم للموافقة، مصدر البيانات، الإصدار، والحد الأدنى للعينة.',filters)}${content}</div>`;
}

async function renderReports() {
  loading(); const data = await api('/api/reports'); const assessments = await api('/api/assessments');
  const completed = assessments.assessments.filter(item => item.status === 'COMPLETED');
  const form = completed.length && canManageAssessments() ? `<form id="report-form" class="filter-bar"><label class="field"><span>التقييم</span><select name="assessment_id">${completed.map(item => `<option value="${item.id}">#${item.id} · ${dateText(item.completed_at)}</option>`).join('')}</select></label><label class="field"><span>نوع التقرير</span><select name="report_type"><option value="EXECUTIVE">تنفيذي</option><option value="DETAILED">تفصيلي</option></select></label><button class="primary-button">إنشاء PDF</button></form>` : '';
  const rows = data.reports.map(item => `<div class="data-table__row"><strong>#${item.id}<small>تقييم ${item.assessment_id}</small></strong><span>${e(item.report_type)}</span><span>${badge(item.status)}</span><span>${dateText(item.created_at)}</span><button class="secondary-button" data-action="download-report" data-id="${item.id}">تنزيل PDF</button></div>`);
  const reportEmpty = canManageAssessments() ? emptyState('لا يوجد تقييم مكتمل','أكمل تقييمًا قبل إنشاء التقرير.') : emptyState('عرض التقارير','يمكنك تنزيل التقارير المتاحة، وإنشاؤها مخصص لمدير الشركة أو الاستشاري.');
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · التقارير','التقارير التنفيذية','تقارير PDF حقيقية مرتبطة بنسخة التقييم والأداة.')}${researchNotice()}<section class="panel"><div class="card-title"><div><h2>تقرير جديد</h2><p>اختر تقييمًا مكتملًا.</p></div></div>${form || reportEmpty}</section><section class="panel">${rows.length ? table(['التقرير','النوع','الحالة','الإنشاء',''],rows,5,720) : emptyState('لا توجد تقارير','لم تُنشأ تقارير متاحة بعد.')}</section></div>`;
}

async function renderParticipants() {
  loading(); const [invitations, assessments] = await Promise.all([api('/api/invitations'), api('/api/assessments')]);
  const active = assessments.assessments.filter(item => ['DRAFT','IN_PROGRESS'].includes(item.status));
  const form = active.length ? `<form id="invite-form" class="form-grid"><label class="field"><span>التقييم</span><select name="assessment_id">${active.map(item => `<option value="${item.id}">#${item.id} · ${e(statusLabels[item.status])}</option>`).join('')}</select></label><label class="field"><span>البريد</span><input name="email" type="email" required></label><label class="field"><span>الاسم</span><input name="full_name"></label><label class="field"><span>المسمى الوظيفي</span><input name="job_title"></label><label class="field"><span>القسم</span><select name="department"><option>Executive</option><option>Marketing</option><option>Sales</option><option>Operations</option><option>Customer Experience</option><option>Product</option><option>Other</option></select></label><label class="field"><span>دور التقييم</span><select name="assessment_role"><option value="RESPONDENT">مشارك</option><option value="OBSERVER">مراقب</option></select></label><button class="primary-button full">إنشاء رابط دعوة آمن</button></form>` : emptyState('يلزم تقييم نشط','أنشئ تقييمًا أو استكمل مسودة لإضافة المشاركين.','<a class="primary-button" href="#assessments">التقييمات</a>');
  const rows = invitations.invitations.map(item => `<div class="data-table__row"><strong>${e(item.full_name || item.email)}<small>${e(item.email)}</small></strong><span>#${item.assessment_id || '--'}</span><span>${e(item.department || '--')}</span><span>${e(item.role)}</span><span>${badge(item.status,item.status === 'PENDING' ? 'warning':'')}</span><span>${dateText(item.expires_at)}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · الفريق','المشاركون والدعوات','تُربط كل دعوة بتقييم وتنتهي صلاحيتها تلقائيًا.')}<section class="panel"><div class="card-title"><div><h2>دعوة مشارك</h2><p>رابط آمن مع موافقة خدمة مستقلة عن موافقة البحث.</p></div></div>${form}</section><section class="panel">${rows.length ? table(['المشارك','التقييم','القسم','الدور','الحالة','الانتهاء'],rows,6,850) : emptyState('لا توجد دعوات','أنشئ رابط دعوة للتقييم النشط.')}</section></div>`;
}

async function renderParticipant(route) {
  state.me = state.token ? state.me : null; applyShell();
  const token = route.query.get('token') || '';
  let invitation = null;
  if (token) invitation = await api(`/api/invitations/${encodeURIComponent(token)}`);
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>نضج MCM</div><div class="auth-copy"><div class="eyebrow">SECURE PARTICIPANT PORTAL</div><h1>شارك خبرتك.<br><i>بخصوصية واضحة.</i></h1><p>تُحفظ إجابتك في التقييم المحدد، ولا تظهر بياناتك الشخصية في مجموعة البحث الافتراضية.</p></div><small>Research consent is optional and separate</small></div><div class="auth-panel"><div class="auth-box"><h2>${invitation ? `دعوة من ${e(invitation.organization_name)}` : 'دخول المشارك'}</h2>${invitation ? `<p>التقييم #${invitation.assessment_id} · ${e(invitation.email)}</p><form id="accept-invitation-form" class="form-grid"><input type="hidden" name="token" value="${e(token)}"><label class="field full"><span>الاسم الكامل</span><input name="full_name" value="${e(invitation.full_name || '')}" required></label><label class="checkbox-field full"><input name="service_consent" type="checkbox" required><span>أوافق على معالجة إجاباتي لتقديم التشخيص للمؤسسة.</span></label><label class="checkbox-field full"><input name="research_consent" type="checkbox"><span>أوافق اختياريًا على استخدام بيانات مجهولة لأغراض البحث.</span></label><button class="primary-button full">قبول وبدء التقييم</button></form>` : `<p>ألصق رمز الدعوة الذي استلمته من مسؤول التقييم.</p><form id="invitation-token-form" class="form-grid"><label class="field full"><span>رمز الدعوة</span><input name="token" required autocomplete="off"></label><button class="primary-button full">التحقق من الدعوة</button></form>`}${state.token ? '<p><a href="#overview">العودة لمساحة العمل</a></p>' : '<p><a href="#login">دخول مستخدمي المنصة</a></p>'}</div></div></section>`;
}

async function renderParticipantAssessment(route) {
  state.me = state.token ? state.me : null; applyShell();
  const participantToken = sessionStorage.getItem('mcm_participant_token');
  if (!participantToken) return navigate('participant');
  await flushAnswers();
  loading(); const data = await api(`/api/participant/session/${encodeURIComponent(participantToken)}`);
  if (data.assessment.status === 'COMPLETED' || data.assessment.participant_status === 'COMPLETED') {
    sessionStorage.removeItem('mcm_participant_token');
    appView.innerHTML = `<section class="route-state">${emptyState('شكرًا لمشاركتك','إجاباتك مرسلة ومقفلة، ولا يلزم إجراء إضافي.','<a class="primary-button" href="#participant">إنهاء</a>')}</section>`;
    return;
  }
  state.assessment = {...data, participantToken}; state.pendingAnswers.clear();
  const byConstruct = data.items.reduce((acc,item) => ((acc[item.construct] ||= []).push(item),acc),{});
  const sections = Object.entries(byConstruct).map(([construct,items]) => `<section class="assessment-section"><header><div><h2>${e(construct)}</h2><p>${construct === 'MCM' ? 'النضج الاتصالي' : construct === 'SMCE' ? 'كفاءة التواصل المستقلة' : 'سياق أو نتائج اختيارية'}</p></div></header><div class="panel">${items.map(item => questionCard(item,data.responses[item.id])).join('')}</div></section>`).join('');
  appView.innerHTML = `<div class="page assessment-page">${pageHeading(`بوابة المشارك · تقييم #${data.assessment.id}`,'التقييم المؤسسي','تُحفظ الإجابات تلقائيًا، ويمكن العودة قبل انتهاء صلاحية الدعوة.')} ${researchNotice()}<section class="assessment-header"><div class="progress-row"><strong>التقدم <span id="progress-value">${number(data.review.progress)}%</span></strong><span class="save-state" id="save-state">محفوظ</span></div><div class="progress-track"><span id="progress-bar" style="--progress:${data.review.progress}%"></span></div></section><form id="assessment-form">${sections}</form><section class="panel"><button class="primary-button" data-action="submit-participant" type="button">إرسال التقييم</button></section></div>`;
}

async function renderNotifications() {
  loading(); const data = await api('/api/notifications');
  const cards = data.notifications.map(item => `<article class="card"><div class="card-title"><div>${badge(item.read_at ? 'مقروء' : 'جديد',item.read_at ? 'neutral':'')}<h3>${e(item.title)}</h3></div><small>${dateText(item.created_at)}</small></div><p>${e(item.body)}</p><div class="button-row">${item.target_url ? `<a class="secondary-button" href="${e(item.target_url)}">فتح</a>` : ''}${!item.read_at ? `<button class="secondary-button" data-action="read-notification" data-id="${item.id}">تحديد كمقروء</button>` : ''}</div></article>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · التنبيهات','الإشعارات','أحداث التقييمات والدعوات وإصدارات الأداة.', '<button class="secondary-button" data-action="read-all-notifications">تحديد الكل كمقروء</button>')}<div class="card-grid">${cards || emptyState('لا توجد إشعارات','ستظهر الأحداث المرتبطة بمساحة العمل هنا.')}</div></div>`;
}

async function renderSettings() {
  loading(); const [settings, profile, team, consents] = await Promise.all([api('/api/settings'),api('/api/company/profile'),api('/api/company/team'),api('/api/consents')]);
  const researchConsent = Boolean(profile.profile?.research_consent);
  const personalResearch = consents.consents.find(item => item.consent_type === 'RESEARCH_USE');
  const companyContent = canManageCompany() ? `<form id="company-profile-form" class="form-grid"><label class="field full"><span>اسم المؤسسة</span><input name="name" value="${e(profile.organization.name)}" required></label><label class="field"><span>القطاع</span><input name="sector" value="${e(profile.organization.sector)}"></label><label class="field"><span>الحجم</span><select name="size"><option value="">غير محدد</option>${['MICRO','SMALL','MEDIUM','LARGE'].map(value => `<option value="${value}" ${profile.organization.size === value ? 'selected':''}>${value}</option>`).join('')}</select></label><label class="field"><span>الموقع</span><input name="website" type="url" value="${e(profile.profile?.website)}"></label><label class="field"><span>نموذج الأعمال</span><input name="business_model" value="${e(profile.profile?.business_model)}"></label><label class="field"><span>عدد الموظفين</span><input name="employee_count" value="${e(profile.profile?.employee_count)}"></label><label class="field"><span>حجم فريق الاتصال</span><input name="communication_team_size" value="${e(profile.profile?.communication_team_size)}"></label><label class="field"><span>CRM</span><input name="crm_system" value="${e(profile.profile?.crm_system)}"></label><label class="field"><span>نظام التحليلات</span><input name="analytics_system" value="${e(profile.profile?.analytics_system)}"></label><label class="checkbox-field full"><input name="research_consent" type="checkbox" ${researchConsent ? 'checked':''}><span>موافقة المؤسسة على إدراج الحالات الواقعية المؤهلة بصورة مجهولة.</span></label><button class="primary-button full">حفظ ملف المؤسسة</button></form>` : `<div class="pill-list"><span>${e(profile.organization.name)}</span><span>${e(profile.organization.sector || 'قطاع غير محدد')}</span><span>${e(profile.organization.size || 'حجم غير محدد')}</span><span>موافقة المؤسسة البحثية: ${researchConsent ? 'مفعلة' : 'غير مفعلة'}</span></div><p>تعديل ملف المؤسسة وموافقتها مخصص لمدير الشركة.</p>`;
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · الإعدادات','الإعدادات والخصوصية','إدارة الحساب والمؤسسة والموافقات من مكان واحد.')}<div class="card-grid"><section class="card span-6"><div class="card-title"><div><h2>الملف الشخصي</h2><p>بيانات الحساب والواجهة العربية.</p></div></div><form id="settings-form" class="form-grid"><input type="hidden" name="locale" value="ar"><label class="field full"><span>الاسم</span><input name="name" value="${e(settings.user.name)}" required></label><label class="field"><span>المسمى</span><input name="job_title" value="${e(settings.user.job_title)}"></label><label class="field"><span>الجوال</span><input name="phone" value="${e(settings.user.phone)}"></label><label class="checkbox-field"><input name="email_notifications" type="checkbox" ${settings.settings?.email_notifications ? 'checked':''}><span>إشعارات البريد</span></label><button class="primary-button full">حفظ الحساب</button></form></section><section class="card span-6"><div class="card-title"><div><h2>ملف المؤسسة</h2><p>الاكتمال الحالي ${number(profile.profile?.completion)}%.</p></div></div>${companyContent}</section><section class="card span-12"><div class="card-title"><div><h2>الفريق والصلاحيات</h2><p>أعضاء المؤسسة الحاليون.</p></div></div><div class="pill-list">${team.members.map(item => `<span>${e(item.name)} · ${e(roleLabels[item.role] || item.role)} · ${e(item.status)}</span>`).join('')}</div></section><section class="card span-12"><h2>الموافقات المنفصلة</h2><p>موافقتك الشخصية على البحث مستقلة عن موافقة المؤسسة. لا تدخل الحالة الواقعية في البحث إلا باجتماع الموافقات المطلوبة.</p><form id="personal-consent-form" class="form-grid"><label class="checkbox-field full"><input name="accepted" type="checkbox" ${personalResearch?.accepted ? 'checked':''}><span>أوافق اختياريًا على استخدام إجاباتي المجهولة لأغراض البحث والمقارنة.</span></label><button class="secondary-button full">حفظ موافقتي البحثية</button></form><div class="pill-list">${consents.consents.map(item => `<span>${e(item.consent_type)} · ${item.accepted ? 'مقبولة':'مرفوضة'} · v${e(item.consent_version)}</span>`).join('')}</div></section></div></div>`;
}

function renderMethodology() {
  const mcm = ['MCM01 الحوكمة والتوجيه الاستراتيجي','MCM02 ذكاء أصحاب المصلحة والسياق','MCM03 حوكمة المعلومات والنزاهة','MCM04 التنسيق التنظيمي ورحلة العميل','MCM05 مواءمة الوعد والتجربة','MCM06 الأدلة والتعلم التكيفي','MCM07 المأسسة وقابلية التوسع'];
  const smce = ['SMCE01 كفاءة الاستجابة والحل','SMCE02 جودة المعنى والتفاعل','SMCE03 كفاءة الانتقال إلى الفعل','SMCE04 انخفاض الاحتكاك الاتصالي','SMCE05 كفاءة الموارد وتحقيق الأهداف'];
  appView.innerHTML = `<div class="page">${pageHeading('المعرفة · المنهجية','كيف يعمل نموذج نضج MCM','فصل واضح بين السياق، النضج المؤسسي، وكفاءة التواصل الاجتماعي.')}${researchNotice()}<div class="card-grid"><article class="card span-4"><span class="status-badge">1</span><h2>السياق والعوامل التمكينية</h2><p>تفسر الظروف المحيطة ولا تدخل تلقائيًا في درجة MCM.</p></article><article class="card span-4"><span class="status-badge">2</span><h2>MCM</h2><p>سبعة أبعاد تُطبع بنودها إلى 0–100 ثم تجمع بأوزان إصدار الأداة.</p></article><article class="card span-4"><span class="status-badge">3</span><h2>SMCE</h2><p>خمسة أبعاد تُحتسب بصورة مستقلة ولا تدخل في MCM.</p></article><article class="card span-6"><h2>أبعاد MCM</h2><div class="pill-list">${mcm.map(item => `<span>${e(item)}</span>`).join('')}</div></article><article class="card span-6"><h2>أبعاد SMCE</h2><div class="pill-list">${smce.map(item => `<span>${e(item)}</span>`).join('')}</div></article><article class="card span-12"><h2>عقد علمي واضح</h2><ul><li>الإجابة المفقودة لا تتحول إلى صفر.</li><li>الاحتساب والتصنيف والتشخيص تجري على الخادم.</li><li>كل نتيجة ترتبط بإصدار أداة وإصدار احتساب.</li><li>لا يحدد الذكاء الاصطناعي درجة أو مستوى أو صلاحية علمية.</li><li>المستويات والحدود الحالية مؤقتة وموسومة Provisional حتى اعتمادها بحثيًا.</li></ul></article></div></div>`;
}

async function renderResearch() {
  loading(); const data = await api('/api/research/summary');
  const sectorRows = data.cases_by_sector.map(item => `<div class="data-table__row"><strong>${e(item.label)}</strong><span>${number(item.count)}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading('البحث والتحليل','لوحة الباحث','إحصاءات فعلية فقط، ولا تُعرض أرقام مصطنعة عند غياب الملاحظات.',`<a class="secondary-button" href="#dataset">مجموعة البيانات</a><a class="primary-button" href="#exports">مركز التصدير</a>`)}${researchNotice(data.current_instrument?.status)}<div class="card-grid"><article class="card metric-card span-3"><small>إجمالي الحالات</small><strong>${number(data.total_cases)}</strong></article><article class="card metric-card span-3"><small>مكتملة</small><strong>${number(data.completed)}</strong></article><article class="card metric-card span-3"><small>غير مكتملة</small><strong>${number(data.incomplete)}</strong></article><article class="card metric-card span-3"><small>موافقة بحثية</small><strong>${number(data.research_consent_organizations)}</strong></article><article class="card span-6"><h2>مصدر البيانات</h2><div class="pill-list">${Object.entries(data.origins).map(([key,value]) => `<span>${e(key)}: ${number(value)}</span>`).join('') || '<span>لا توجد بيانات</span>'}</div></article><article class="card span-6"><h2>إصدار الأداة الحالي</h2><p>${data.current_instrument ? `${e(data.current_instrument.version)} · ${e(data.current_instrument.status)}` : 'لا يوجد إصدار.'}</p><a href="#instruments">إدارة الإصدارات</a></article></div><section class="panel"><div class="card-title"><div><h2>الحالات حسب القطاع</h2><p>عد فعلي من قاعدة البيانات.</p></div></div>${sectorRows.length ? table(['القطاع','الحالات'],sectorRows,2,420) : emptyState('لا توجد بيانات كافية حتى الآن.','تظهر التوزيعات بعد وصول حالات فعلية أو تجريبية وفق الفلتر.')}</section></div>`;
}

async function renderDataset(route) {
  loading(); const origin = route.query.get('origin') || 'REAL'; const data = await api(`/api/research/dataset?data_origin=${encodeURIComponent(origin)}&limit=100`);
  const columns = data.columns.slice(0, 10);
  const rows = data.rows.map(record => `<div class="data-table__row">${columns.map(column => `<span>${e(record[column] ?? '--')}</span>`).join('')}</div>`);
  const filters = `<div class="button-row"><a class="secondary-button" href="#dataset?origin=REAL">واقعية فقط</a><a class="secondary-button" href="#dataset?origin=SYNTHETIC">اصطناعية</a><a class="secondary-button" href="#dataset?origin=DEMO_TEST">Demo/Test</a></div>`;
  appView.innerHTML = `<div class="page">${pageHeading('البحث · البيانات','مستكشف مجموعة البيانات',`المعرّفات مجهولة وPII غير مدرج افتراضيًا. عدد الصفوف: ${number(data.row_count)}.`,filters)}<section class="panel">${rows.length ? table(columns,rows,columns.length,Math.max(900,columns.length*150)) : emptyState('لا توجد بيانات بحثية متاحة حتى الآن.','الفلتر الافتراضي REAL ONLY ويتطلب موافقة بحثية صريحة.')}</section></div>`;
}

async function renderInstruments() {
  loading(); const data = await api('/api/instruments');
  const rows = data.versions.map(item => `<div class="data-table__row"><strong>${e(item.version)}<small>${e(item.name)}</small></strong><span>${badge(item.status,item.status === 'PILOT' ? 'warning':'')}</span><span>${number(item.item_count)}</span><span>${number(item.assessment_count)}</span><span>${dateText(item.created_at)}</span><span class="button-row"><a class="secondary-button" href="#instrument/${item.id}">فتح</a>${item.status === 'DRAFT' ? `<button class="primary-button" data-action="publish-instrument" data-id="${item.id}">نشر Pilot</button>` : `<button class="secondary-button" data-action="duplicate-instrument" data-id="${item.id}">نسخ لمسودة</button>`}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading('البحث · الأداة','إصدارات الأداة','النسخ المستخدمة غير قابلة للتعديل؛ أي تغيير يبدأ مسودة جديدة.')}<section class="panel"><div class="card-title"><div><h2>استيراد DOCX منظم</h2><p>الرفع والتحقق يجريان على الخادم بحد حجم ونوع ملف.</p></div><span class="status-badge warning">لا نشر تلقائي</span></div><form id="instrument-upload-form" class="form-grid"><label class="field full"><span>ملف DOCX</span><input id="instrument-file" name="instrument" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required><small>يجب أن يحتوي TABLE:DIMENSIONS وTABLE:ITEMS والجداول العلمية المرتبطة.</small></label><button class="primary-button full">رفع والتحقق</button></form><div id="instrument-preview"></div></section><section class="panel">${rows.length ? table(['الإصدار','الحالة','البنود','التقييمات','الإنشاء',''],rows,6,860) : emptyState('لا توجد إصدارات','ارفع ملف الأداة المنظم لإنشاء مسودة.')}</section></div>`;
}

async function renderInstrument(route) {
  const id = Number(route.parts[1]); if (!id) return navigate('instruments');
  loading(); const [detail,items] = await Promise.all([api(`/api/instruments/${id}`),api(`/api/instruments/${id}/items`)]);
  const dimRows = detail.dimensions.map(item => `<div class="data-table__row"><strong>${e(item.code)}</strong><span>${e(item.construct)}</span><span>${e(item.name)}</span><span>${number(item.weight,2)}</span></div>`);
  const itemRows = items.items.slice(0,100).map(item => `<div class="data-table__row"><strong>${e(item.code)}<small>${e(item.dimension_code)}</small></strong><span>${e(item.construct)}</span><span>${e(item.prompt_ar)}</span><span>${item.required ? 'نعم':'لا'}</span><span>${item.reverse_coded ? 'نعم':'لا'}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading(`إصدار ${e(detail.version.version)}`,e(detail.version.name),`الحالة: ${e(detail.version.status)} · ${number(items.items.length)} بندًا.`,`<a class="secondary-button" href="#instruments">كل الإصدارات</a>`)}${researchNotice(detail.version.status)}<section class="panel"><h2>الأبعاد</h2>${table(['الرمز','البناء','الاسم','الوزن'],dimRows,4,650)}</section><section class="panel"><h2>بنك البنود</h2>${table(['البند','البناء','الصياغة','مطلوب','عكسي'],itemRows,5,900)}</section></div>`;
}

async function renderDataQuality() {
  loading(); const data = await api('/api/research/data-quality');
  const rows = data.flags.map(item => `<div class="data-table__row"><strong>#${item.assessment_id}</strong><span>${e(item.flag_type)}</span><span>${badge(item.severity,item.severity === 'HIGH' ? 'danger':'warning')}</span><span>${e(item.details)}</span><span>${e(item.status)}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading('البحث · الجودة','جودة البيانات','لا تُحذف الحالات آليًا؛ تظهر الإشارات للباحث للمراجعة.','<a class="secondary-button" href="#statistics">الإحصاءات الوصفية</a>')}<div class="card-grid"><article class="card metric-card span-4"><small>إشارات الجودة</small><strong>${number(data.flags.length)}</strong></article><article class="card metric-card span-4"><small>حالات غير مكتملة</small><strong>${number(data.incomplete_cases.length)}</strong></article><article class="card metric-card span-4"><small>حذف تلقائي</small><strong>${number(data.auto_deleted)}</strong></article></div><section class="panel">${rows.length ? table(['التقييم','الإشارة','الخطورة','التفاصيل','الحالة'],rows,5,820) : emptyState('لا توجد إشارات جودة','لم يكتشف المحرك حالات تستدعي المراجعة.')}</section></div>`;
}

async function renderStatistics(route) {
  loading(); const origin = route.query.get('origin') || 'REAL'; const data = await api(`/api/research/statistics?data_origin=${encodeURIComponent(origin)}`);
  const metric = (title,value) => `<article class="card metric-card span-6"><small>${e(title)}</small><strong>${value === null || value === undefined ? '--' : number(value,2)}</strong></article>`;
  const section = (title,item) => item ? `<section class="card span-6"><h2>${e(title)}</h2><div class="card-grid">${metric('N',item.n)}${metric('المتوسط',item.mean)}${metric('الوسيط',item.median)}${metric('الانحراف المعياري',item.sd)}${metric('الأدنى',item.min)}${metric('الأعلى',item.max)}</div></section>` : `<section class="card span-6">${emptyState(`لا توجد بيانات ${title}`,'لا توجد ملاحظات كافية للفلتر المختار.')}</section>`;
  appView.innerHTML = `<div class="page">${pageHeading('البحث · الإحصاءات','الإحصاءات الوصفية',`مصدر البيانات: ${e(data.data_origin)}. لا تُعرض موثوقية أو صلاحية مصطنعة.`)}<div class="card-grid">${section('MCM',data.MCM)}${section('SMCE',data.SMCE)}<article class="card span-6"><h2>الموثوقية</h2>${badge('غير متاح','neutral')}<p>${e(data.reliability.reason)}</p></article><article class="card span-6"><h2>الصلاحية</h2>${badge('غير متاح','neutral')}<p>${e(data.validity.reason)}</p></article></div></div>`;
}

function renderExports() {
  appView.innerHTML = `<div class="page">${pageHeading('البحث · التصدير','مركز التصدير','الافتراضي REAL ONLY، ولا تُدرج البيانات الشخصية في ملفات البحث.')}<section class="panel"><form id="export-form" class="form-grid"><label class="field"><span>مصدر البيانات</span><select name="data_origin"><option value="REAL">واقعية فقط</option><option value="SYNTHETIC">اصطناعية فقط</option><option value="DEMO_TEST">Demo / Test</option><option value="ALL">كل المصادر - مراجعة خاصة</option></select></label><label class="field"><span>نوع التصدير</span><select name="format"><option value="XLSX">Excel Workbook</option><option value="CSV">CSV UTF-8</option><option value="SPSS">SPSS-ready Package</option><option value="CODEBOOK">Codebook Excel</option><option value="INSTRUMENT">Instrument JSON</option></select></label><label class="checkbox-field full"><input type="checkbox" required><span>أفهم أن التصدير مسجّل في سجل التدقيق وأن البيانات الواقعية تتطلب موافقة بحثية.</span></label><button class="primary-button full">إنشاء وتنزيل</button></form></section><section class="card"><h2>محتويات Excel</h2><div class="pill-list">${['01_RESPONSES_WIDE','02_RESPONSES_LONG','03_MCM_SCORES','04_SMCE_SCORES','05_COMPANY_PROFILE','06_CODEBOOK','07_VARIABLE_LABELS','08_VALUE_LABELS','09_INSTRUMENT','10_METADATA'].map(item => `<span>${item}</span>`).join('')}</div></section></div>`;
}

async function renderAdmin() {
  loading(); const [overview,users,organizations] = await Promise.all([api('/api/admin'),api('/api/admin/users'),api('/api/admin/organizations')]);
  const userRows = users.users.map(item => `<div class="data-table__row"><strong>${e(item.name)}<small>${e(item.email)}</small></strong><span>${e(roleLabels[item.role] || item.role || '--')}</span><span>${e(item.organization_name || '--')}</span><span>${badge(item.is_active ? 'نشط':'معطل',item.is_active ? '':'danger')}</span><button class="secondary-button" data-action="toggle-user" data-id="${item.id}" data-active="${item.is_active ? '1':'0'}">${item.is_active ? 'تعطيل':'تفعيل'}</button></div>`);
  const options = organizations.organizations.map(item => `<option value="${item.id}">${e(item.name)}</option>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading('إدارة المنصة','لوحة المدير العام','إدارة المستخدمين والمنظمات والإعدادات التشغيلية.')}<div class="card-grid"><article class="card metric-card span-3"><small>المؤسسات</small><strong>${number(overview.organizations)}</strong></article><article class="card metric-card span-3"><small>المستخدمون</small><strong>${number(overview.users)}</strong></article><article class="card metric-card span-3"><small>التقييمات</small><strong>${number(overview.assessments)}</strong></article><article class="card metric-card span-3"><small>الجلسات النشطة</small><strong>${number(overview.active_sessions)}</strong></article><section class="card span-12"><div class="card-title"><div><h2>إنشاء مستخدم</h2><p>تعيين مؤسسة ودور واضحين.</p></div></div><form id="admin-user-form" class="form-grid"><label class="field"><span>الاسم</span><input name="name" required></label><label class="field"><span>البريد</span><input name="email" type="email" required></label><label class="field"><span>كلمة المرور</span><input name="password" type="password" minlength="10" required></label><label class="field"><span>المؤسسة</span><select name="organization_id">${options}</select></label><label class="field full"><span>الدور</span><select name="role"><option value="COMPANY_RESPONDENT">مشارك شركة</option><option value="COMPANY_ADMIN">مدير شركة</option><option value="CONSULTANT">استشاري</option><option value="RESEARCHER">باحث</option><option value="SUPER_ADMIN">مدير المنصة</option></select></label><button class="primary-button full">إنشاء المستخدم</button></form></section></div><section class="panel">${table(['المستخدم','الدور','المؤسسة','الحالة',''],userRows,5,820)}</section><section class="card"><h2>إعدادات النظام</h2><div class="pill-list">${Object.entries(overview.configuration).map(([key,value]) => `<span>${e(key)}: ${e(typeof value === 'object' ? JSON.stringify(value) : value)}</span>`).join('')}</div></section></div>`;
}

function queueAnswer(itemId, value, missingType = null) {
  state.pendingAnswers.set(Number(itemId), {item_id:Number(itemId), value, missing_type:missingType});
  const indicator = document.querySelector('#save-state'); if (indicator) indicator.textContent = 'تغييرات غير محفوظة...';
  clearTimeout(state.saveTimer); state.saveTimer = setTimeout(() => flushAnswers().catch(error => showToast(apiMessage(error),'error')), 650);
}

async function flushAnswers() {
  clearTimeout(state.saveTimer);
  if (state.saveInFlight) {
    await state.saveInFlight;
    return state.pendingAnswers.size ? flushAnswers() : undefined;
  }
  if (!state.pendingAnswers.size || !state.assessment) return;
  const assessment = state.assessment;
  const answers = [...state.pendingAnswers.values()];
  answers.forEach(item => {
    if (state.pendingAnswers.get(item.item_id) === item) state.pendingAnswers.delete(item.item_id);
  });
  const indicator = document.querySelector('#save-state'); if (indicator) indicator.textContent = 'جارٍ الحفظ...';
  let path;
  if (assessment.participantToken) path = `/api/participant/session/${encodeURIComponent(assessment.participantToken)}/answers`;
  else path = `/api/assessments/${assessment.assessment.id}/answers`;
  try {
    state.saveInFlight = api(path,{method:'POST',body:JSON.stringify({answers}),routeScoped:false});
    const result = await state.saveInFlight;
    if (state.assessment === assessment && result.review) state.assessment.review = result.review;
    if (indicator) indicator.textContent = `محفوظ · ${new Date().toLocaleTimeString('ar-SA',{hour:'2-digit',minute:'2-digit'})}`;
    const progress = result.review?.progress ?? 0;
    const progressValue = document.querySelector('#progress-value'); if (progressValue) progressValue.textContent = `${number(progress)}%`;
    const progressBar = document.querySelector('#progress-bar'); if (progressBar) progressBar.style.setProperty('--progress',`${progress}%`);
  } catch (error) {
    answers.forEach(item => { if (!state.pendingAnswers.has(item.item_id)) state.pendingAnswers.set(item.item_id,item); });
    if (indicator) indicator.textContent = 'فشل الحفظ · أعد المحاولة';
    throw error;
  } finally {
    state.saveInFlight = null;
  }
  if (state.pendingAnswers.size) return flushAnswers();
}

async function createAssessment(sourceId = null) {
  const body = sourceId ? null : {assessment_type:'FULL'};
  const result = sourceId ? await api(`/api/assessments/${sourceId}/repeat`,{method:'POST',body:'{}'}) : await api('/api/assessments',{method:'POST',body:JSON.stringify(body)});
  navigate(`assessment/${result.id}`);
}

async function confirmSubmission(id, participant = false) {
  await flushAnswers();
  let review;
  if (participant) review = state.assessment.review;
  else review = await api(`/api/assessments/${id}/review`);
  if (!review?.complete) {
    showToast(`تبقى ${review.missing_required.length} بندًا مطلوبًا.`,'error');
    const first = document.querySelector(`[data-question="${review.missing_required[0]?.item_id}"]`); first?.scrollIntoView({behavior:'smooth',block:'center'});
    return;
  }
  openDialog(`<h2 id="dialog-title">تأكيد إرسال التقييم</h2><p>بعد الإرسال تُقفل الإجابات وتُحسب النتائج على الخادم. لا يمكن التراجع عن هذه الخطوة.</p><div class="button-row"><button class="primary-button" data-action="confirm-submit" data-id="${id}" data-participant="${participant ? '1':'0'}">تأكيد الإرسال</button><button class="secondary-button" data-action="close-dialog">العودة للمراجعة</button></div>`);
}

async function fileAsBase64(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer); let binary = '';
  const chunk = 0x8000;
  for (let index=0; index<bytes.length; index+=chunk) binary += String.fromCharCode(...bytes.subarray(index,index+chunk));
  return btoa(binary);
}

document.addEventListener('change', event => {
  if (event.target.matches('#assessment-form input[type="radio"][data-answer-input]')) queueAnswer(event.target.dataset.itemId,Number(event.target.value));
  if (event.target.matches('#assessment-form input[type="number"][data-answer-input]')) queueAnswer(event.target.dataset.itemId,event.target.value === '' ? null : Number(event.target.value),event.target.value === '' ? 'NOT_ANSWERED' : null);
});
document.addEventListener('input', event => {
  if (event.target.matches('#assessment-form textarea[data-answer-input]')) queueAnswer(event.target.dataset.itemId,event.target.value || null,event.target.value ? null : 'NOT_ANSWERED');
});

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const action = button.dataset.action;
  try {
    if (action === 'auth-mode') { state.authMode = button.dataset.mode; renderAuth(); }
    else if (action === 'forgot-password') navigate('forgot');
    else if (action === 'close-dialog') closeDialog();
    else if (action === 'retry-route') router();
    else if (action === 'create-assessment') await createAssessment();
    else if (action === 'repeat-assessment') await createAssessment(Number(button.dataset.id));
    else if (action === 'missing-answer') {
      const itemId = Number(button.dataset.itemId); document.querySelectorAll(`[name="q_${itemId}"]`).forEach(input => { if (input.type === 'radio') input.checked=false; else input.value=''; });
      queueAnswer(itemId,null,button.dataset.missing); showToast('تم تسجيل حالة الغياب وستُراجع عند الإرسال.');
    }
    else if (action === 'clear-answer') {
      const itemId = Number(button.dataset.itemId); document.querySelectorAll(`[name="q_${itemId}"]`).forEach(input => { if (input.type === 'radio') input.checked=false; else input.value=''; });
      queueAnswer(itemId,null,'NOT_ANSWERED');
    }
    else if (action === 'submit-assessment') await confirmSubmission(Number(button.dataset.id),false);
    else if (action === 'submit-participant') await confirmSubmission(state.assessment.assessment.id,true);
    else if (action === 'confirm-submit') {
      button.disabled = true; button.textContent = 'جارٍ الاحتساب...';
      if (button.dataset.participant === '1') {
        await api(`/api/participant/session/${encodeURIComponent(state.assessment.participantToken)}/submit`,{method:'POST',body:'{}'});
        sessionStorage.removeItem('mcm_participant_token'); closeDialog();
        appView.innerHTML = `<section class="route-state">${emptyState('شكرًا لمشاركتك','تم إرسال التقييم وقفل إجاباتك بنجاح.','<a class="primary-button" href="#participant">إنهاء</a>')}</section>`;
      } else {
        const id = Number(button.dataset.id); const result = await api(`/api/assessments/${id}/submit`,{method:'POST',body:'{}'}); closeDialog();
        if (result.assessment_complete) navigate(`results/${id}`); else { showToast(result.message || 'تم إرسال إجاباتك، وبانتظار بقية المشاركين.'); navigate('assessments'); }
      }
    }
    else if (action === 'generate-report') {
      button.disabled = true; const report = await api('/api/reports',{method:'POST',body:JSON.stringify({assessment_id:Number(button.dataset.id),report_type:button.dataset.type || 'EXECUTIVE'})});
      await downloadApi(report.download_url); button.disabled = false; showToast('تم إنشاء التقرير وتنزيله.');
    }
    else if (action === 'download-report') await downloadApi(`/api/reports/${button.dataset.id}/download`);
    else if (action === 'edit-roadmap') {
      openDialog(`<h2 id="dialog-title">تحديث إجراء الخارطة</h2><form id="roadmap-form" class="form-grid"><input type="hidden" name="assessment_id" value="${e(button.dataset.assessmentId)}"><input type="hidden" name="item_id" value="${e(button.dataset.id)}"><label class="field full"><span>المالك</span><input name="owner" value="${e(button.dataset.owner)}"></label><label class="field"><span>التاريخ المستهدف</span><input name="target_date" type="date" value="${e(button.dataset.date)}"></label><label class="field"><span>الحالة</span><select name="status">${['NOT_STARTED','IN_PROGRESS','COMPLETED','DEFERRED'].map(value => `<option value="${value}" ${button.dataset.status === value ? 'selected':''}>${statusLabels[value] || value}</option>`).join('')}</select></label><button class="primary-button full">حفظ</button></form>`);
    }
    else if (action === 'read-notification') { await api('/api/notifications/read',{method:'PATCH',body:JSON.stringify({notification_id:Number(button.dataset.id)})}); router(); }
    else if (action === 'read-all-notifications') { await api('/api/notifications/read',{method:'PATCH',body:'{}'}); state.me = await api('/api/me'); applyShell(); router(); }
    else if (action === 'publish-instrument') { await api(`/api/instrument-versions/${button.dataset.id}/approve`,{method:'POST',body:'{}'}); showToast('نُشر الإصدار بصفة PILOT.'); router(); }
    else if (action === 'duplicate-instrument') { const result = await api(`/api/instrument-versions/${button.dataset.id}/duplicate`,{method:'POST',body:'{}'}); showToast(`أُنشئت المسودة ${result.version}.`); router(); }
    else if (action === 'import-instrument') {
      button.disabled = true; const result = await api('/api/instrument-versions/import',{method:'POST',body:JSON.stringify(state.importPayload)}); showToast(`أُنشئت المسودة ${result.version}.`); navigate(`instrument/${result.id}`);
    }
    else if (action === 'toggle-user') { await api(`/api/admin/users/${button.dataset.id}`,{method:'PATCH',body:JSON.stringify({is_active:button.dataset.active !== '1'})}); router(); }
    else if (action === 'logout') { await flushAnswers(); await api('/api/auth/logout',{method:'POST',body:'{}'}).catch(()=>{}); state.token='';state.me=null;localStorage.removeItem('mcm_token');closeDialog();navigate('login'); }
    else if (action === 'switch-org') { await api('/api/session/organization',{method:'POST',body:JSON.stringify({organization_id:Number(button.dataset.id)})}); state.me=await api('/api/me');applyShell();closeDialog();navigate('overview'); }
    else if (action === 'copy-invite') { await navigator.clipboard.writeText(document.querySelector('#invite-url').value); showToast('تم نسخ رابط الدعوة.'); }
    else if (action === 'open-settings') { closeDialog(); navigate('settings'); }
  } catch (error) { button.disabled = false; showToast(apiMessage(error),'error'); }
});

document.addEventListener('submit', async event => {
  event.preventDefault(); const form = event.target; const data = Object.fromEntries(new FormData(form));
  try {
    if (form.id === 'auth-form') {
      const register = state.authMode === 'register'; if (register) data.service_consent = true;
      const result = await api(register ? '/api/auth/register':'/api/auth/login',{method:'POST',body:JSON.stringify(data)});
      state.token=result.token;localStorage.setItem('mcm_token',result.token);state.me=await api('/api/me');applyShell();navigate('overview');
    }
    else if (form.id === 'forgot-form') {
      const result=await api('/api/auth/forgot-password',{method:'POST',body:JSON.stringify(data)});
      const dev=result.development_reset_token ? `<p class="form-success">بيئة التطوير: <a href="#reset?token=${e(result.development_reset_token)}">فتح رابط الاستعادة</a></p>`:'';
      form.insertAdjacentHTML('afterend',`<p class="form-success">تم قبول الطلب. ${dev}</p>`);
    }
    else if (form.id === 'reset-form') { await api('/api/auth/reset-password',{method:'POST',body:JSON.stringify(data)});showToast('تم تحديث كلمة المرور.');navigate('login'); }
    else if (form.id === 'report-form') { const report=await api('/api/reports',{method:'POST',body:JSON.stringify({assessment_id:Number(data.assessment_id),report_type:data.report_type})});await downloadApi(report.download_url);router(); }
    else if (form.id === 'invite-form') {
      const result=await api('/api/invitations',{method:'POST',body:JSON.stringify({...data,assessment_id:Number(data.assessment_id)})});
      openDialog(`<h2 id="dialog-title">تم إنشاء الدعوة</h2><p>انسخ الرابط وأرسله للمشارك عبر قناة آمنة.</p><label class="field"><span>رابط الدعوة</span><input id="invite-url" dir="ltr" value="${e(new URL(result.invitation_url,location.href).href)}" readonly></label><button class="primary-button" type="button" data-action="copy-invite">نسخ الرابط</button>`);
    }
    else if (form.id === 'invitation-token-form') navigate(`participant?token=${encodeURIComponent(data.token.trim())}`);
    else if (form.id === 'accept-invitation-form') {
      const result=await api(`/api/invitations/${encodeURIComponent(data.token)}/accept`,{method:'POST',body:JSON.stringify({full_name:data.full_name,service_consent:true,research_consent:new FormData(form).has('research_consent')})});
      sessionStorage.setItem('mcm_participant_token',result.token);navigate(`participant-assessment/${result.assessment_id}`);
    }
    else if (form.id === 'settings-form') { const fd=new FormData(form);await api('/api/settings',{method:'PATCH',body:JSON.stringify({...data,email_notifications:fd.has('email_notifications'),security_notifications:true})});state.me=await api('/api/me');applyShell();showToast('تم حفظ إعدادات الحساب.'); }
    else if (form.id === 'company-profile-form') { const fd=new FormData(form);await api('/api/company/profile',{method:'PATCH',body:JSON.stringify({...data,research_consent:fd.has('research_consent')})});showToast('تم حفظ ملف المؤسسة والموافقة.');router(); }
    else if (form.id === 'personal-consent-form') { const accepted=new FormData(form).has('accepted');await api('/api/consents',{method:'PATCH',body:JSON.stringify({consent_type:'RESEARCH_USE',consent_version:'1.0',accepted})});showToast('تم حفظ موافقتك البحثية.');router(); }
    else if (form.id === 'roadmap-form') { await api(`/api/roadmap/${Number(data.assessment_id)}`,{method:'PATCH',body:JSON.stringify({item_id:Number(data.item_id),owner:data.owner,target_date:data.target_date,status:data.status})});closeDialog();router(); }
    else if (form.id === 'instrument-upload-form') {
      const file=form.querySelector('input[type="file"]').files[0]; if(!file) return;
      const preview=document.querySelector('#instrument-preview');preview.innerHTML='<p>جارٍ الرفع والتحقق على الخادم...</p>';
      const payload={filename:file.name,mime_type:file.type,docx_base64:await fileAsBase64(file)};state.importPayload=payload;
      const result=await api('/api/instrument-versions/preview',{method:'POST',body:JSON.stringify(payload)});state.importPreview=result;
      preview.innerHTML=`<div class="card ${result.valid?'':'diagnosis-card high'}"><h3>${result.valid?'اجتاز الملف التحقق':'الملف يحتاج تصحيحًا'}</h3><div class="pill-list"><span>${number(result.stats.items)} بندًا</span><span>${number(result.stats.dimensions)} أبعاد</span><span>${number(result.stats.mcm_items)} MCM</span><span>${number(result.stats.smce_items)} SMCE</span></div>${result.errors.length?`<ul>${result.errors.map(item=>`<li>${e(item.code)} ${e(item.table||item.item||'')}</li>`).join('')}</ul>`:''}${result.warnings.length?`<p>تحذيرات: ${result.warnings.map(item=>e(item.table||item.code)).join('، ')}</p>`:''}${result.valid?'<button class="primary-button" data-action="import-instrument" type="button">إنشاء مسودة غير منشورة</button>':''}</div>`;
    }
    else if (form.id === 'export-form') { const result=await api('/api/research/exports',{method:'POST',body:JSON.stringify(data)});await downloadApi(result.download_url);showToast('تم إنشاء التصدير وتسجيله.'); }
    else if (form.id === 'admin-user-form') { await api('/api/admin/users',{method:'POST',body:JSON.stringify({...data,organization_id:Number(data.organization_id)})});showToast('تم إنشاء المستخدم.');router(); }
  } catch (error) {
    const target=form.querySelector('.form-error')||document.querySelector('#auth-error');
    if(target){target.textContent=apiMessage(error);target.hidden=false;} else showToast(apiMessage(error),'error');
  }
});

document.querySelector('#menu-button').addEventListener('click', event => {
  const sidebar=document.querySelector('#sidebar');const open=sidebar.classList.toggle('open');event.currentTarget.setAttribute('aria-expanded',String(open));
});
document.querySelector('#mobile-more').addEventListener('click',()=>{document.querySelector('#sidebar').classList.add('open');document.querySelector('#menu-button').setAttribute('aria-expanded','true');});
document.querySelector('#org-switcher').addEventListener('click',()=>{
  if(!state.me) return; openDialog(`<h2 id="dialog-title">تبديل المؤسسة</h2><div class="button-row">${state.me.organizations.map(item=>`<button class="secondary-button" data-action="switch-org" data-id="${item.id}">${e(item.name)} · ${e(roleLabels[item.role]||item.role)}</button>`).join('')}</div>`);
});
document.querySelector('#user-menu').addEventListener('click',()=>openDialog(`<h2 id="dialog-title">${e(state.me?.user?.name||'الحساب')}</h2><p>${e(state.me?.user?.email||'')}</p><div class="button-row"><button class="secondary-button" data-action="open-settings">الإعدادات</button><button class="danger-button" data-action="logout">تسجيل الخروج</button></div>`));
window.addEventListener('hashchange',router);
window.addEventListener('beforeunload',()=>{
  if (!state.pendingAnswers.size || !state.assessment) return;
  const answers=[...state.pendingAnswers.values()];
  const path=state.assessment.participantToken ? `/api/participant/session/${encodeURIComponent(state.assessment.participantToken)}/answers` : `/api/assessments/${state.assessment.assessment.id}/answers`;
  const headers={'Content-Type':'application/json'}; if(state.token) headers.Authorization=`Bearer ${state.token}`;
  fetch(path,{method:'POST',headers,body:JSON.stringify({answers}),keepalive:true}).catch(()=>{});
});

async function bootstrap() {
  try { state.publicConfig=await api('/api/public-config',{routeScoped:false}); } catch {}
  try { if(state.token) state.me=await api('/api/me'); }
  catch { state.token='';localStorage.removeItem('mcm_token');state.me=null; }
  applyShell();
  if(!location.hash) navigate(state.token?'overview':'login'); else router();
}
bootstrap();
