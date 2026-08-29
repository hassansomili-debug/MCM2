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
  publicConfig: {registration_enabled:false,direct_participant_enabled:true,storage:'unknown'},
  publicPage: false,
  importPreview: null,
  importPayload: null,
  maturity: null,
  privacyNotice: null,
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
  DRAFT: 'مسودة', IN_PROGRESS: 'قيد التنفيذ', COMPLETED: 'مكتمل', PILOT: 'قيد التجربة الداخلية',
  VALIDATED: 'مُعتمد', ARCHIVED: 'مؤرشف', PENDING: 'بانتظار القبول', ACCEPTED: 'مقبولة',
  ACTIVE: 'نشط', INACTIVE: 'موقوف',
  EVIDENCE_INFORMED: 'قائم على الأدلة', EXPERT_REVIEWED: 'مراجَع من خبراء', EMPIRICALLY_VALIDATED: 'محقق تجريبيًا',
  NOT_STARTED: 'لم يبدأ', IN_PROGRESS_ROADMAP: 'قيد التنفيذ', DEFERRED: 'مؤجل',
};
const errorLabels = {
  invalid_credentials: 'بيانات الدخول غير صحيحة.', session_expired: 'انتهت الجلسة. سجّل الدخول مرة أخرى.',
  authentication_required: 'يلزم تسجيل الدخول.', permission_denied: 'ليست لديك صلاحية لهذا الإجراء.',
  required_answers_missing: 'لا يزال هناك بنود مطلوبة بلا إجابة.', assessment_locked: 'هذا التقييم مكتمل ومقفل.',
  password_policy_failed: 'استخدم 10 أحرف على الأقل تتضمن حرفًا كبيرًا وصغيرًا ورقمًا.',
  email_already_exists: 'البريد مستخدم بالفعل.',
  instrument_validation_failed: 'ملف الأداة لم يجتز التحقق.', rate_limit_exceeded: 'محاولات كثيرة. حاول لاحقًا.',
  internal_error: 'حدث خطأ غير متوقع. حاول مرة أخرى.', route_not_found: 'المسار المطلوب غير موجود.',
  registration_disabled: 'إنشاء الحسابات معطل في بيئة العرض المؤقتة.',
  service_consent_required: 'يلزم قبول موافقة الخدمة للبدء.', organization_name_required: 'أدخل اسم منشأة صحيحًا.',
  sector_required: 'اختر قطاع المنشأة.', sme_size_required: 'اختر حجم منشأة صغيرة أو متوسطة.',
  region_required: 'اختر المنطقة.', respondent_role_required: 'اختر دور المجيب.',
  invalid_demographics: 'تحقق من عدد الموظفين وعمر المنشأة وحجم فريق التواصل.',
  business_model_required: 'اختر نموذج أعمال المنشأة.', regulated_sector_required: 'حدد ما إذا كان القطاع منظمًا رقابيًا.',
  platform_not_ready: 'المنصة قيد التهيئة؛ حاول بعد قليل.', durable_storage_required: 'التقييم المباشر متوقف مؤقتًا حتى يتم ربط قاعدة بيانات دائمة. تواصل مع مسؤول المنصة.',
  contact_consent_required: 'يلزم إقرار موافقة التواصل لإرسال الطلب.',
  contact_consent_withdrawn: 'سُحبت موافقة التواصل؛ لا يمكن إلا الإغلاق أو الإيقاف.',
  consultant_not_eligible: 'المستشار غير مؤهل أو غير نشط.',
  unsupported_consultation_status: 'حالة غير مدعومة.',
  note_required: 'أدخل نص الملاحظة.',
  invalid_filter: 'قيمة فلتر غير صالحة.',
  invalid_phone_number: 'تحقق من رقم الجوال؛ استخدم صيغة مثل 05xxxxxxxx أو +9665xxxxxxxx.',
  full_name_required: 'أدخل الاسم الكامل.',
  unsupported_contact_method: 'وسيلة التواصل المختارة غير مدعومة.',
  unsupported_consultation_topic: 'أحد محاور الاستشارة غير مدعوم.',
  invalid_consultation_topics: 'تعذر قراءة محاور الاستشارة.',
  consultation_lead_not_found: 'الطلب غير متاح لهذا الحساب.',
  assessment_id_required: 'تعذر ربط الطلب بالتقييم.',
  participant_session_invalid: 'انتهت جلسة المشارك؛ افتح النتيجة من جديد.',
  cannot_delete_own_account: 'لا يمكنك حذف حسابك أنت.',
  last_platform_administrator: 'لا يمكن حذف آخر مدير منصة نشط.',
  user_not_found: 'المستخدم غير موجود.',
  join_code_required: 'أدخل كود المشاركة.',
  join_code_invalid_or_expired: 'كود المشاركة غير صالح أو منتهي أو استُنفد.',
  service_consent_required: 'يلزم إقرار موافقة الخدمة.',
  organization_name_required: 'أدخل اسم المنشأة.',
  assessment_cooldown_active: 'لا يمكن بدء تقييم جديد قبل انقضاء دورة القياس.',
  join_code_unavailable: 'تعذر توليد كود؛ حاول مرة أخرى.',
};

function e(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}
function number(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
  // Western digits throughout. The `ar-SA` locale renders Arabic-Indic
  // numerals, which read poorly next to the Latin dimension codes and score
  // scales used everywhere in this interface.
  return new Intl.NumberFormat('en-US', {maximumFractionDigits: digits, minimumFractionDigits: digits}).format(Number(value));
}
function dateText(timestamp) {
  if (!timestamp) return '--';
  const date = typeof timestamp === 'number' ? new Date(timestamp * 1000) : new Date(timestamp);
  // Arabic month names with Western digits.
  // Month names follow the reader's language; digits stay Western in both.
  const calendar = locale() === 'en' ? 'en-GB' : 'ar-SA-u-nu-latn-ca-gregory';
  return new Intl.DateTimeFormat(calendar, {year:'numeric',month:'short',day:'numeric'}).format(date);
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
  const raw = (location.hash.slice(1) || (state.token ? 'overview' : 'landing'));
  const [path, queryString = ''] = raw.split('?');
  return {path: path.replace(/^\/+|\/+$/g, '') || 'overview', parts: path.split('/').filter(Boolean), query: new URLSearchParams(queryString)};
}
function navigate(route) {
  const target = `#${String(route).replace(/^#/, '')}`;
  if (location.hash === target) router(); else location.hash = target;
}
function loading(label = 'جارٍ تحميل البيانات...') { appView.innerHTML = `<section class="loading-page"><span class="spinner" aria-hidden="true"></span><p>${e(label)}</p></section>`; }
function emptyState(title, copy, action = '') { return `<section class="empty-state"><b>${e(title)}</b><p>${e(copy)}</p>${action}</section>`; }
function errorState(error) { return `<section class="route-state"><div>${emptyState(t('تعذر تحميل الصفحة'), apiMessage(error), '<button class="primary-button" data-action="retry-route" type="button">إعادة المحاولة</button>')}</div></section>`; }
function pageHeading(kicker, title, copy, actions = '') { return `<section class="page-heading"><div><div class="eyebrow">${e(kicker)}</div><h1>${e(title)}</h1><p>${copy}</p></div>${actions ? `<div class="page-heading-actions">${actions}</div>` : ''}</section>`; }
// Participant-facing notice. It names the evidentiary basis of the model and
// the limit of the result, without pilot wording and without any claim of
// completed validation. Internal instrument lifecycle status is shown only in
// the researcher and super-admin screens, never here.
function modelNotice() {
  const model = modelInfo();
  return `<div class="research-notice"><strong>${e(model.label_ar || 'نموذج تطبيقي قائم على الأدلة العلمية')}</strong><span>${e(pick(model, 'result_disclaimer_ar').replace(/^$/, model.result_disclaimer_ar || ''))}</span></div>`;
}
function badge(value, tone = '') { return `<span class="status-badge ${tone}">${e(statusLabels[value] || value || '--')}</span>`; }
function table(headers, rows, columns = headers.length, min = 720) {
  return `<div class="table-scroll"><div class="data-table" style="--table-columns:repeat(${columns},minmax(130px,1fr));--table-min:${min}px"><div class="data-table__row header">${headers.map(item => `<span>${e(item)}</span>`).join('')}</div>${rows.join('')}</div></div>`;
}

function hasRole(...roles) { return roles.includes(state.me?.user?.role); }
function canManageAssessments() { return hasRole('COMPANY_ADMIN','CONSULTANT','SUPER_ADMIN'); }
function canManageCompany() { return hasRole('COMPANY_ADMIN','SUPER_ADMIN'); }
function canManageRoadmap() { return hasRole('COMPANY_ADMIN','SUPER_ADMIN'); }

function applyShell() {
  const isGuest = !state.me || state.publicPage;
  appShell.classList.toggle('is-guest', isGuest);
  document.documentElement.lang = locale();
  document.documentElement.dir = locale() === 'en' ? 'ltr' : 'rtl';
  const langToggle = document.querySelector('#lang-toggle');
  if (langToggle) langToggle.textContent = locale() === 'en' ? 'ع' : 'EN';
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

const publicRoutes = new Set(['landing', 'participant-start', 'login', 'participant-assessment', 'forgot', 'reset', 'privacy', 'join', 'signup', 'knowledge']);
const researchRoutes = new Set(['research', 'dataset', 'instruments', 'instrument', 'data-quality', 'statistics', 'exports', 'knowledge-editor']);
async function router() {
  const request = ++state.routeRequest;
  state.routeController?.abort();
  state.routeController = new AbortController();
  const route = parseRoute();
  state.publicPage = publicRoutes.has(route.parts[0]);
  applyShell();
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
  if (route.parts[0] === 'consultations' && !['SUPER_ADMIN','CONSULTANT'].includes(state.me?.user?.role)) return navigate('overview');
  if (route.parts[0] === 'analytics' && !['SUPER_ADMIN','RESEARCHER'].includes(state.me?.user?.role)) return navigate('overview');
  if (route.parts[0] === 'participants' && !canManageAssessments()) return navigate('overview');
  const labels = {landing:'الرئيسية','participant-start':'ابدأ المقياس',overview:'نظرة عامة',assessments:'التقييمات',assessment:'التقييم',results:'النتائج',dashboard:'النتائج',privacy:'سياسة الخصوصية',join:'الانضمام بكود',signup:'إنشاء حساب مشارك',knowledge:'المعرفة الاتصالية','knowledge-editor':'محرر المحتوى المعرفي',dimension:'تفاصيل البعد',diagnosis:'التشخيص',gaps:'تحليل الفجوات',priorities:'الأولويات',roadmap:'خارطة التحسين',history:'مسار النضج',benchmark:'المقارنة المرجعية',reports:'التقارير',participants:'المشاركون','participant-assessment':'تقييم المشارك',notifications:'الإشعارات',settings:'الإعدادات',methodology:'المنهجية',research:'لوحة الباحث',dataset:'مجموعة البيانات',instruments:'إصدارات الأداة',instrument:'تفاصيل الأداة','data-quality':'جودة البيانات',statistics:'الإحصاءات',exports:'التصدير',admin:'إدارة المنصة',consultations:'طلبات الاستشارة',analytics:'مركز تحليل البيانات'};
  document.querySelector('#page-label').textContent = labels[route.parts[0]] || 'مقياس النضج الاتصالي التسويقي';
  if (route.parts[0] === 'dashboard') return navigate('results/latest');
  const handlers = {landing:renderLanding,privacy:renderPrivacy,join:renderJoin,signup:renderSignup,knowledge:renderKnowledge,'knowledge-editor':renderKnowledgeAdmin,'participant-start':renderParticipantStart,login:renderAuth,forgot:renderForgot,reset:renderReset,overview:renderOverview,assessments:renderAssessments,assessment:renderAssessment,results:renderResults,dimension:renderDimension,diagnosis:renderDiagnosis,gaps:renderGaps,priorities:renderPriorities,roadmap:renderRoadmap,history:renderHistory,benchmark:renderBenchmark,reports:renderReports,participants:renderParticipants,'participant-assessment':renderParticipantAssessment,notifications:renderNotifications,settings:renderSettings,methodology:renderMethodology,research:renderResearch,dataset:renderDataset,instruments:renderInstruments,instrument:renderInstrument,'data-quality':renderDataQuality,statistics:renderStatistics,exports:renderExports,admin:renderAdmin,consultations:renderConsultations,analytics:renderAnalytics};
  const handler = handlers[route.parts[0]];
  if (!handler) { appView.innerHTML = emptyState('الصفحة غير موجودة', 'تحقق من الرابط أو عد إلى مساحة العمل.', '<a class="primary-button" href="#overview">العودة للرئيسية</a>'); return; }
  try { await handler(route); if (request === state.routeRequest) appView.focus({preventScroll:true}); }
  catch (error) { if (error.name !== 'AbortError' && request === state.routeRequest) appView.innerHTML = errorState(error); }
}

function publicNav() {
  return `<nav class="public-nav" aria-label="التنقل الرئيسي"><a class="public-brand" href="#landing"><span>ن</span><b>${t('مقياس النضج الاتصالي التسويقي')}</b></a><div><a href="#landing">${t('الرئيسية')}</a><button class="landing-nav-link" data-action="scroll-maturity" type="button">${t('مراحل النضج')}</button><a href="#knowledge">${t('المعرفة')}</a><a href="#join">${t('لدي كود مشاركة')}</a><a href="#privacy">${t('الخصوصية')}</a><a class="secondary-button" href="#login">${t('تسجيل الدخول')}</a><a class="primary-button" href="#participant-start">${t('ابدأ المقياس')}</a></div></nav>`;
}

function scrollElementIntoView(element, block = 'start') {
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  element?.scrollIntoView({behavior: reducedMotion ? 'auto' : 'smooth', block});
}

// The five stages are served from the instrument configuration so the homepage,
// the methodology page and the stage drawer all read one source. Loaded once
// per session; a failure degrades to an empty list rather than a broken page.
async function loadMaturity() {
  if (state.maturity) return state.maturity;
  try { state.maturity = await api('/api/public/maturity-levels'); }
  catch { state.maturity = {levels: [], model: state.publicConfig.model || {}}; }
  return state.maturity;
}

// Server payloads carry Arabic fields with English counterparts beside them.
// `pick` chooses by locale and falls back to Arabic, so a payload that predates
// a translation still renders rather than showing an empty panel.
function pick(source, base) {
  if (!source) return '';
  const english = source[`${base}_en`];
  return (locale() === 'en' && english) ? english : (source[base] || '');
}

function modelInfo() { return state.maturity?.model || state.publicConfig.model || {}; }

function stageCards(levels) {
  return levels.map(level => `<li class="stage-card">
    <span class="stage-index">المرحلة ${e(String(level.level_order))}</span>
    <h3>${e(level.label_ar)}</h3>
    <small class="stage-en">${e(level.label_en)}</small>
    <p>${e(level.summary_ar || '')}</p>
    <button class="stage-more" type="button" data-action="stage-detail" data-code="${e(level.code)}" aria-label="تعرف على مرحلة ${e(level.label_ar)}">${t('تعرف على هذه المرحلة')}</button>
  </li>`).join('');
}

function stageDetailDialog(code) {
  const level = (state.maturity?.levels || []).find(item => item.code === code);
  if (!level) return;
  const list = (title, values) => values && values.length
    ? `<section class="stage-detail-block"><h3>${e(title)}</h3><ul>${values.map(value=>`<li>${e(value)}</li>`).join('')}</ul></section>` : '';
  openDialog(`<div class="stage-detail">
    <span class="status-badge">المرحلة ${e(String(level.level_order))}</span>
    <h2 id="dialog-title">${e(level.label_ar)}</h2>
    <small class="stage-en">${e(level.label_en)}</small>
    <p>${e(level.description_ar || level.summary_ar || '')}</p>
    ${list('الخصائص', level.characteristics_ar)}
    ${list('المخاطر الشائعة', level.risks_ar)}
    ${list('محور التطوير', level.focus_ar)}
    ${list('مؤشرات الانتقال إلى المرحلة التالية', level.transition_ar)}
    <button class="secondary-button" data-action="close-dialog">${t('إغلاق')}</button>
  </div>`);
}

async function renderLanding() {
  const maturity = await loadMaturity();
  const model = modelInfo();
  const storageNotice = state.publicConfig.storage === 'ephemeral-demo' ? `<div class="landing-alert"><strong>نسخة عرض مؤقتة</strong><span>${e(state.publicConfig.notice || 'قد تُعاد تهيئة البيانات؛ لا تدخل بيانات حساسة.')}</span></div>` : '';
  // Names come from the instrument, so a rename never has to be repeated here.
  const mcmDimensions = (maturity.dimensions?.MCM || []).map(item => locale() === 'en' ? (item.name_en || item.name_ar) : item.name_ar);
  const smceDimensions = (maturity.dimensions?.SMCE || []).map(item => locale() === 'en' ? (item.name_en || item.name_ar) : item.name_ar);
  const levels = maturity.levels || [];
  const maturityCards = stageCards(levels);
  appView.innerHTML = `<div class="landing-page">${publicNav()}${storageNotice}<main>
    <section class="landing-hero">
      <div class="hero-copy">
        <div class="eyebrow">${t('مقياس تشخيصي للمنشآت الصغيرة والمتوسطة في السعودية')}</div>
        <h1>اعرف أين تقف منشأتك، وحوّل الاتصال إلى <i>قدرة مؤسسية تصنع الأثر.</i></h1>
        <p>شخّص نضج الاتصال التسويقي، واكتشف مدى تحوّله إلى كفاءة في التواصل الاجتماعي، ثم انتقل من النتيجة إلى أولويات وخارطة تحسين قابلة للتنفيذ.</p>
        <div class="hero-actions"><a class="primary-button large" href="#participant-start">${t('ابدأ المقياس مباشرة')}</a><button class="secondary-button large" data-action="scroll-maturity" type="button">${t('تعرّف على المراحل')}</button></div>
        <div class="hero-proof"><span><b>67</b> ${t('عبارة علمية')}</span><span><b>20</b> ${t('بُعدًا وسياقًا')}</span><span><b>5</b> ${t('مراحل نضج')}</span></div>
      </div>
      <aside class="hero-rationale" aria-label="أهمية النضج الاتصالي التسويقي">
        <span class="eyebrow">${t('لماذا يهمّ النضج الاتصالي التسويقي؟')}</span>
        <p><strong>النضج الاتصالي ليس نشاطًا تسويقيًا، بل قدرة مؤسسية.</strong> هو أن تكون الرسالة محكومة بمالك واضح، والمعلومة من مصدر واحد معتمد، ورحلة العميل متسقة بين الإدارات، والقرار مبنيًا على أدلة تُراجع دوريًا.</p>
        <p>حين ترسخ هذه القدرة تقلّ التناقضات أمام العميل، ويقصر زمن القرار، ويتراجع الهدر في الجهد والإنفاق التسويقي، لأن المبادرات تصبح مرتبطة بهدف ومؤشر بدل أن تتفرق باجتهادات فردية.</p>
        <p class="hero-rationale-model">ويقترح النموذج أن ارتفاع هذه القدرة ينعكس على كفاءة الاتصال عبر وسائل التواصل الاجتماعي. المقياس يقيس الاثنين بصورة مستقلة ويعرض الفجوة بينهما، دون ادعاء علاقة سببية مثبتة.</p>
        <small>${e(model.label_ar || 'نموذج تطبيقي قائم على الأدلة العلمية')}</small>
      </aside>
    </section>
    <section class="landing-confidence" aria-label="ما الذي يتغير عند تحسين النضج الاتصالي">
      <article><b>${t('اتساق الرسالة')}</b><span>رسالة واحدة عبر كل قناة ونقطة تماس، بدل إجابات تختلف باختلاف الموظف.</span></article>
      <article><b>${t('سرعة القرار')}</b><span>معلومة موثقة ومالك معروف، فيقصر زمن الاستجابة والتصعيد.</span></article>
      <article><b>${t('كفاءة الإنفاق')}</b><span>مبادرات مرتبطة بهدف ومؤشر ومراجعة، بدل جهد متفرق يصعب قياس أثره.</span></article>
      <article><b>${t('قدرة لا تعتمد على الأفراد')}</b><span>ممارسات راسخة في النظام تصمد مع النمو وتغيّر الفريق.</span></article>
    </section>
    <section class="landing-section value-section">
      <div class="section-intro"><span>${t('أبعد من مؤشرات التفاعل')}</span><h2>${t('ماذا سيكشف المقياس لمنشأتك؟')}</h2><p>قراءة إدارية تساعدك على تحديد موضع القدرة الاتصالية، وفهم الفجوات، وترتيب الاستثمار التالي.</p></div>
      <div class="value-grid">
        <article><b>01</b><h3>${t('أين تقف الآن؟')}</h3><p>تصنيف المنشأة ضمن خمس مراحل واضحة، من العمل العشوائي إلى القدرة المؤسسية الذكية.</p></article>
        <article><b>02</b><h3>${t('ما الذي يعطّل الكفاءة؟')}</h3><p>فهم الفجوة بين قدرات المؤسسة وبين سرعة وجودة وكلفة الاتصال عبر المنصات.</p></article>
        <article><b>03</b><h3>${t('ما الخطوة التالية؟')}</h3><p>أولويات مرتبة وخارطة عمل مرحلية مرتبطة بالمسؤول والمؤشر والأفق الزمني.</p></article>
      </div>
    </section>
    <section class="landing-section model-section" id="methodology-public">
      <div class="section-intro"><span>${t('النموذج التشخيصي')}</span><h2>النضج قدرة مؤسسية، والكفاءة نتيجة اتصالية مقترحة</h2><p>تُحفظ خصائص المنشأة والممكنات كسياق تفسيري منفصل، ولا تُخلط بدرجة النضج الأساسية.</p></div>
      <div class="construct-grid">
        <article class="construct-card navy"><header><span>MCM</span><h3>${t('النضج الاتصالي التسويقي')}</h3></header><ol>${mcmDimensions.map((item,index)=>`<li><i>${index+1}</i>${e(item)}</li>`).join('')}</ol></article>
        <div class="effect-card"><b>أثر إيجابي<br>مقترح</b><span aria-hidden="true">←</span><small>يُختبر كميًا ولا يُعرض كعلاقة سببية مثبتة</small></div>
        <article class="construct-card teal"><header><span>SMCE</span><h3>${t('الكفاءة الاتصالية')}</h3></header><ol>${smceDimensions.map((item,index)=>`<li><i>${index+1}</i>${e(item)}</li>`).join('')}</ol></article>
      </div>
    </section>
    <section class="landing-section stages-section" id="maturity-public">
      <div class="section-intro"><span>${t('مسار التطور')}</span><h2>${e(maturity.title_ar || 'مراحل النضج الاتصالي التسويقي')}</h2><p>${e((locale() === 'en' && maturity.subtitle_en) ? maturity.subtitle_en : (maturity.subtitle_ar || ''))}</p></div>
      ${levels.length ? `<ol class="landing-maturity" aria-label="مراحل النضج الخمس">${maturityCards}</ol>` : emptyState('تعذر تحميل المراحل','حدّث الصفحة للمحاولة مرة أخرى.')}
      <div class="stages-cta"><a class="primary-button large" href="#participant-start">${t('اكتشف مستوى منشأتك')}</a></div>
    </section>
    <section class="landing-section report-preview">
      <div><span>${t('نتيجة قابلة للاستخدام')}</span><h2>${t('نتائج تنفيذية، وليست مجرد درجة.')}</h2><p>يقارن بين MCM وSMCE، يعرض الأبعاد والممكنات والنتائج، يحدد المرحلة الحالية، ثم يرتب فرص التطوير. وتتوفر للمدير ملفات Excel وSPSS مع قاموس متغيرات وترميزات جاهزة.</p><a class="primary-button large" href="#participant-start">${t('ابدأ تشخيص منشأتك')}</a></div>
      <div class="preview-card"><header><span>${t('نتيجة افتراضية للتوضيح')}</span><b>${e(levels[2]?.label_ar || 'مدار / متكامل')}</b></header><div class="preview-score"><strong>64</strong><small>/100</small></div><div class="preview-bars">${[82,71,64,58,46].map((score,index)=>`<div><span>البعد ${index+1}</span><i><b style="--score:${score}%"></b></i><em>${score}</em></div>`).join('')}</div><footer><span>الأولوية التالية</span><b>تعزيز التعلّم والتكيّف</b></footer></div>
    </section>
    <section class="landing-cta"><span>${t('البدء لا يحتاج حسابًا')}</span><h2>أدخل معلومات منشأتك وابدأ الإجابة مباشرة.</h2><p>خيارات لفظية واضحة بمقياس ليكرت، مع «لا ينطبق» و«لا أعرف» عند الحاجة.</p><a class="primary-button light large" href="#participant-start">${t('ابدأ المقياس الآن')}</a></section>
  </main><footer class="public-footer"><b>${t('مقياس النضج الاتصالي التسويقي')}</b><span>${e(model.label_ar || 'نموذج تطبيقي قائم على الأدلة العلمية')} للمنشآت الصغيرة والمتوسطة · 2026</span><a href="#login">${t('تسجيل الدخول')}</a></footer></div>`;
}

function renderParticipantStart() {
  state.publicPage = true; applyShell();
  if (!state.publicConfig.direct_participant_enabled) {
    appView.innerHTML = `<div class="participant-start-page">${publicNav()}<main><section class="route-state">${emptyState('التقييم المباشر غير متاح حاليًا', state.publicConfig.notice || 'يجب ربط قاعدة بيانات دائمة قبل استقبال التقييمات.', '<a class="primary-button" href="#landing">العودة للرئيسية</a>')}</section></main></div>`;
    return;
  }
  const regions = ['الرياض','مكة المكرمة','المنطقة الشرقية','المدينة المنورة','القصيم','عسير','تبوك','حائل','الحدود الشمالية','جازان','نجران','الباحة','الجوف'];
  const storageNotice = state.publicConfig.storage === 'ephemeral-demo' ? `<div class="research-notice"><strong>تنبيه بيئة العرض</strong><span>${e(state.publicConfig.notice || 'البيانات مؤقتة؛ استخدم معلومات غير حساسة فقط.')}</span></div>` : '';
  appView.innerHTML = `<div class="participant-start-page">${publicNav()}<main><section class="start-heading"><div><span>${t('دخول مباشر للمشارك')}</span><h1>${t('عرّفنا بمنشأتك قبل بدء المقياس')}</h1><p>تساعد هذه المتغيرات على تفسير النتيجة في سياق المنشأة، ولا تدخل في درجة النضج الأساسية. ستقيّم الممكنات التنظيمية داخل الأداة نفسها.</p></div><div class="start-meta"><b>حوالي 15–20 دقيقة</b><span>${t('لا يلزم إنشاء حساب')}</span><span>${t('الحفظ تلقائي')}</span></div></section>${storageNotice}<form id="direct-assessment-form" class="direct-form"><section class="panel"><div class="form-section-title"><b>01</b><div><h2>${t('الخصائص الديموغرافية للمنشأة')}</h2><p>تُحفظ مع حالة القياس لأغراض التشخيص والتحليل المجهول وفق الموافقات.</p></div></div><div class="form-grid"><label class="field full"><span>${t('اسم المنشأة')}</span><input name="organization_name" minlength="2" maxlength="120" required></label><label class="field"><span>${t('القطاع')}</span><select name="sector" required><option value="">${t('اختر القطاع')}</option><option>التجزئة والتجارة</option><option>الخدمات المهنية</option><option>التقنية والاتصالات</option><option>الصناعة</option><option>السياحة والضيافة</option><option>الصحة</option><option>التعليم</option><option>النقل والخدمات اللوجستية</option><option>قطاع آخر</option></select></label><label class="field"><span>${t('حجم المنشأة')}</span><select name="firm_size" required><option value="">${t('اختر الحجم')}</option><option value="MICRO">متناهية الصغر</option><option value="SMALL">صغيرة</option><option value="MEDIUM">متوسطة</option></select></label><label class="field"><span>${t('عدد الموظفين')}</span><input name="employee_count" type="number" min="1" max="250000" required></label><label class="field"><span>${t('عمر المنشأة بالسنوات')}</span><input name="firm_age_years" type="number" min="0" max="200" required></label><label class="field"><span>${t('نموذج الأعمال')}</span><select name="business_model" required><option value="">${t('اختر النموذج')}</option><option value="B2C">منشأة إلى مستهلك B2C</option><option value="B2B">منشأة إلى منشأة B2B</option><option value="B2B2C">مختلط B2B2C</option><option value="GOVERNMENT">جهة حكومية / تعامل حكومي</option><option value="NONPROFIT">غير ربحي</option><option value="OTHER">آخر</option></select></label><label class="field"><span>${t('المنطقة الرئيسية للنشاط')}</span><select name="region" required><option value="">${t('اختر المنطقة')}</option>${regions.map(region=>`<option>${e(region)}</option>`).join('')}</select></label><label class="field"><span>${t('عدد منصات التواصل المستخدمة بانتظام')}</span><input name="social_platform_count" type="number" min="0" max="50" required></label><label class="field"><span>${t('عدد العاملين المسؤولين مباشرة عن التواصل الاجتماعي')}</span><input name="social_team_size" type="number" min="0" max="250000" required></label><label class="field"><span>${t('هل تعمل المنشأة في قطاع منظم رقابيًا؟')}</span><select name="regulated_sector" required><option value="">${t('اختر الإجابة')}</option><option value="YES">${t('نعم')}</option><option value="NO">${t('لا')}</option></select></label><label class="field full"><span>${t('دور المجيب')}</span><select name="respondent_role" required><option value="">${t('اختر الدور')}</option><option>مالك / مؤسس</option><option>إدارة عليا</option><option>مدير تسويق أو اتصال</option><option>أخصائي تسويق أو اتصال</option><option>خدمة عملاء / تجربة عميل</option><option>دور آخر</option></select></label></div></section><section class="panel consent-panel"><div class="form-section-title"><b>02</b><div><h2>${t('الموافقة والبدء')}</h2><p>يمكنك الانسحاب قبل إرسال الإجابات، والموافقة البحثية مستقلة واختيارية.</p></div></div><label class="checkbox-field"><input name="service_consent" type="checkbox" required><span><b>موافقة الخدمة مطلوبة:</b> أوافق على معالجة الإجابات لإصدار التشخيص والتقرير للمنشأة.</span></label><label class="checkbox-field"><input name="research_consent" type="checkbox"><span><b>موافقة بحثية اختيارية:</b> أوافق على استخدام البيانات بعد إزالة المعرّفات المباشرة لأغراض البحث والمقارنة.</span></label><div class="form-error" hidden></div><button class="primary-button large" type="submit">${t('حفظ البيانات وبدء المقياس')}</button></section></form></main></div>`;
}

function dashboardArray(value) {
  if (Array.isArray(value)) return value;
  if (value && typeof value === 'object') {
    for (const key of ['dimensions','items','values']) if (Array.isArray(value[key])) return value[key];
    return Object.values(value).filter(item => item && typeof item === 'object' && !Array.isArray(item));
  }
  return [];
}

function dashboardScore(item) {
  const value = Number(item?.score ?? item?.current_score ?? item?.value ?? 0);
  return Number.isFinite(value) ? Math.max(0,Math.min(100,value)) : 0;
}

function dashboardName(item) {
  return item?.name_ar || item?.name || item?.label_ar || item?.title || item?.dimension_code || item?.code || 'بُعد تشخيصي';
}

function radarChart(items) {
  if (items.length < 3) return emptyState('لا تتوفر بيانات كافية للرسم','يظهر المخطط عند اكتمال درجات ثلاثة أبعاد على الأقل.');
  const size = 320; const center = size / 2; const radius = 105;
  const point = (index, percent) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index / items.length);
    const distance = radius * Math.max(0,Math.min(100,percent)) / 100;
    return [center + Math.cos(angle) * distance, center + Math.sin(angle) * distance];
  };
  const polygon = percent => items.map((_,index) => point(index,percent).map(value=>value.toFixed(1)).join(',')).join(' ');
  const axes = items.map((_,index) => { const [x,y]=point(index,100); return `<line x1="${center}" y1="${center}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}"></line>`; }).join('');
  const labels = items.map((item,index) => { const [x,y]=point(index,118); return `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="middle" dominant-baseline="middle">${e(item.code || `D${index+1}`)}</text>`; }).join('');
  const scores = items.map((item,index) => point(index,dashboardScore(item)).map(value=>value.toFixed(1)).join(',')).join(' ');
  const accessible = items.map(item=>`${item.code || dashboardName(item)} ${number(dashboardScore(item),1)} من 100`).join('، ');
  return `<div class="radar-wrap"><svg class="radar-chart" viewBox="0 0 ${size} ${size}" role="img" aria-label="${e(accessible)}"><g class="radar-grid">${[25,50,75,100].map(p=>`<polygon points="${polygon(p)}"></polygon>`).join('')}${axes}</g><polygon class="radar-area" points="${scores}"></polygon><g class="radar-labels">${labels}</g></svg><div class="radar-legend">${items.map(item=>`<div><span><i></i>${e(item.code || '')} · ${e(dashboardName(item))}</span><b>${number(dashboardScore(item),1)}</b></div>`).join('')}</div></div>`;
}

function scoreProfile(items, emptyCopy, tone = 'teal') {
  if (!items.length) return `<p class="dashboard-empty">${e(emptyCopy)}</p>`;
  return `<div class="dashboard-bars ${e(tone)}">${items.map(item=>`<div><header><span>${e(item.code || item.dimension_code || '')} · ${e(dashboardName(item))}</span><b>${number(dashboardScore(item),1)}</b></header><i><span style="--score:${dashboardScore(item)}%"></span></i></div>`).join('')}</div>`;
}

function normalizeRoadmap(dashboard, priorities) {
  const buckets = {'0-30':[],'31-90':[],'3-6':[]};
  const raw = dashboard.roadmap || dashboard.improvement_plan?.roadmap || dashboard.timeline || [];
  const add = (horizon,item) => {
    const key = String(horizon || '').toLowerCase().replace(/_/g,'-');
    if (key.includes('0-30') || key === '30' || key.includes('first')) buckets['0-30'].push(item);
    else if (key.includes('31-90') || key === '90' || key.includes('second')) buckets['31-90'].push(item);
    else buckets['3-6'].push(item);
  };
  if (Array.isArray(raw)) raw.forEach(item=>add(item.horizon || item.period,item));
  else if (raw && typeof raw === 'object') Object.entries(raw).forEach(([key,items])=>dashboardArray(items).forEach(item=>add(key,item)));
  if (!Object.values(buckets).some(items=>items.length)) {
    priorities.forEach((item,index)=>add(index < 1 ? '0-30' : index < 3 ? '31-90' : '3-6',item));
  }
  return buckets;
}

function impactEffortMatrix(priorities) {
  const impactMap = {LOW:25,MEDIUM:58,HIGH:86}; const effortMap = {LOW:20,MEDIUM:52,HIGH:84};
  const points = priorities.slice(0,6).map((item,index) => {
    const impact = Math.max(8,Math.min(92,Number(item.impact_score ?? impactMap[String(item.expected_impact || item.impact || 'MEDIUM').toUpperCase()] ?? 58)));
    const effort = Math.max(8,Math.min(92,Number(item.effort_score ?? effortMap[String(item.effort || 'MEDIUM').toUpperCase()] ?? 52)));
    return `<span class="matrix-point" style="--impact:${impact};--effort:${effort}" title="${e(dashboardName(item))}"><b>${number(item.rank || index+1)}</b><small>${e(item.dimension_code || item.code || '')}</small></span>`;
  }).join('');
  if (!points) return `<p class="dashboard-empty">تظهر المصفوفة عند توفر أولويات مرتبطة بالأثر والجهد.</p>`;
  return `<div class="impact-matrix" role="img" aria-label="مصفوفة أثر وجهد لأولويات التحسين"><span class="matrix-y high">أثر أعلى</span><span class="matrix-y low">أثر أقل</span><div class="matrix-plot">${points}</div><div class="matrix-x"><span>جهد أقل</span><span>جهد أعلى</span></div></div>`;
}

function roadmapMeta(item) {
  return [
    item.owner ? `المسؤول: ${item.owner}` : '',
    item.kpi ? `المؤشر: ${item.kpi}` : '',
    item.target_date ? `الموعد: ${item.target_date}` : '',
  ].filter(Boolean).join(' · ');
}

// The consultation invitation is rendered after the complete result, never
// before it and never in place of it. Declining changes nothing: the result,
// its detail, its report and the methodology stay open either way.
function consultationCta(assessmentId) {
  if (!assessmentId) return '';
  return `<section class="card consultation-cta" id="consultation-cta">
    <div>
      <span class="dashboard-kicker teal">الخطوة الاختيارية التالية</span>
      <h2>هل ترغب في تطوير مستوى النضج الاتصالي في منشأتك؟</h2>
      <p>يمكنك طلب جلسة استشارية لمناقشة نتائج منشأتك، وتحديد الأولويات، وبناء خطة عملية لتطوير النضج الاتصالي التسويقي.</p>
      <small class="consultation-note">نتيجتك وتقريرها متاحان كاملين سواء طلبت الاستشارة أو لم تطلبها.</small>
    </div>
    <div class="button-row">
      <button class="primary-button" data-action="consultation-open" data-assessment="${e(String(assessmentId))}" type="button">${t('اطلب استشارة')}</button>
      <button class="secondary-button" data-action="consultation-dismiss" type="button">${t('ليس الآن')}</button>
    </div>
  </section>`;
}

async function consultationForm(assessmentId) {
  const notice = await loadPrivacyNotice();
  const topics = [
    ['STRATEGY_AND_GOVERNANCE','الاستراتيجية والحوكمة'],
    ['STAKEHOLDER_COMMUNICATION','التواصل مع أصحاب المصلحة'],
    ['INFORMATION_GOVERNANCE','حوكمة المعلومات'],
    ['CUSTOMER_JOURNEY','رحلة العميل'],
    ['PROMISE_EXPERIENCE_ALIGNMENT','مواءمة الوعد والتجربة'],
    ['MEASUREMENT_AND_LEARNING','القياس والتعلم'],
    ['CAPABILITY_SUSTAINABILITY','استدامة القدرات'],
    ['FULL_90_DAY_PLAN','خطة 90 يومًا كاملة'],
    ['OTHER','موضوع آخر'],
  ];
  const methods = [['PHONE','اتصال هاتفي'],['EMAIL','بريد إلكتروني'],['WHATSAPP','واتساب'],['VIDEO_MEETING','اجتماع مرئي']];
  const contactText = notice?.consent_texts?.contact?.text_ar || '';
  const marketingText = notice?.consent_texts?.marketing?.text_ar || '';
  openDialog(`<div class="consultation-form-wrap">
    <h2 id="dialog-title">${t('طلب استشارة')}</h2>
    <p>الحقول المعلّمة مطلوبة. لن تُستخدم بيانات التواصل في احتساب أي درجة أو في المقارنات البحثية.</p>
    <form id="consultation-form" class="form-grid">
      <input type="hidden" name="assessment_id" value="${e(String(assessmentId))}">
      <label class="field"><span>الاسم الكامل *</span><input name="full_name" required minlength="2" maxlength="160" autocomplete="name"></label>
      <label class="field"><span>البريد الإلكتروني *</span><input name="email" type="email" required autocomplete="email"></label>
      <label class="field"><span>رقم الجوال *</span><input name="phone_number" required inputmode="tel" autocomplete="tel" placeholder="05xxxxxxxx"></label>
      <label class="field"><span>${t('اسم المنشأة')}</span><input name="organization_name" maxlength="160"></label>
      <label class="field"><span>${t('المسمى الوظيفي')}</span><input name="job_title" maxlength="120"></label>
      <label class="field"><span>${t('وسيلة التواصل المفضلة')}</span><select name="preferred_contact_method"><option value="">${t('بلا تفضيل')}</option>${methods.map(([value,label])=>`<option value="${value}">${e(label)}</option>`).join('')}</select></label>
      <label class="field"><span>${t('الوقت المفضل للتواصل')}</span><input name="preferred_contact_time" maxlength="120" placeholder="مثال: صباحًا بين 9 و11"></label>
      <fieldset class="field full consultation-topics"><legend>${t('محاور الاستشارة')}</legend><div class="topic-grid">${topics.map(([value,label])=>`<label class="checkbox-field"><input type="checkbox" name="consultation_topics" value="${value}"><span>${e(label)}</span></label>`).join('')}</div></fieldset>
      <label class="field full"><span>${t('ملاحظات')}</span><textarea name="notes" rows="3" maxlength="2000"></textarea></label>
      <label class="checkbox-field full"><input name="consent_to_contact" type="checkbox" required><span>${e(contactText)} <a href="#privacy" target="_blank" rel="noopener">${t('سياسة الخصوصية')}</a></span></label>
      <label class="checkbox-field full"><input name="marketing_consent" type="checkbox"><span>${e(marketingText)}</span></label>
      <div class="form-error full" hidden></div>
      <button class="primary-button full" type="submit">${t('إرسال الطلب')}</button>
    </form>
  </div>`);
}

async function loadPrivacyNotice() {
  if (state.privacyNotice) return state.privacyNotice;
  try { state.privacyNotice = await api('/api/public/privacy'); }
  catch { state.privacyNotice = null; }
  return state.privacyNotice;
}

const constructLabels = {
  MCM:'النضج الاتصالي التسويقي', SMCE:'كفاءة التواصل الاجتماعي',
  ENABLER:'الممكنات التنظيمية', OUTCOME:'النتائج الاختيارية',
};

async function renderKnowledge() {
  state.publicPage = !state.token; applyShell();
  loading('جارٍ تحميل المحتوى المعرفي...');
  const data = await api('/api/public/knowledge');
  const sections = Object.entries(data.constructs)
    .filter(([, items]) => items.length)
    .map(([construct, items]) => `<section class="panel"><div class="card-title"><div><h2>${e(constructLabels[construct] || construct)}</h2></div></div><div class="knowledge-list">${items.map(item => `<article class="knowledge-entry"><header><b>${e(item.code)}</b><h3>${e(item.name_ar)}</h3><small>${e(item.name_en || '')}</small></header>${data.fields.map(field => item.content[field] ? `<div class="knowledge-field"><h4>${e(data.field_labels_ar[field])}</h4><p>${e(item.content[field])}</p></div>` : '').join('')}</article>`).join('')}</div></section>`).join('');
  const shell = body => state.token
    ? `<div class="page">${body}</div>`
    : `<div class="landing-page">${publicNav()}<main><div class="page">${body}</div></main></div>`;
  const heading = pageHeading('المعرفة','المعرفة الاتصالية','تعريف كل بُعد من أبعاد النموذج، ولماذا يهم، وكيف يبدو تحسينه عمليًا.');
  appView.innerHTML = shell(sections
    ? `${heading}${sections}`
    : `${heading}${emptyState('المحتوى المعرفي قيد الإعداد','يكتب الباحث المسؤول عن الأداة هذا المحتوى، ولا يُولَّد آليًا. سيظهر هنا فور اعتماده.', '<a class="primary-button" href="#methodology">اطلع على المنهجية</a>')}`);
}

async function renderKnowledgeAdmin() {
  loading('جارٍ تحميل محرر المحتوى...');
  const data = await api('/api/research/knowledge');
  const sections = Object.entries(data.constructs)
    .filter(([, items]) => items.length)
    .map(([construct, items]) => `<section class="panel"><div class="card-title"><div><h2>${e(constructLabels[construct] || construct)}</h2><p>${number(items.filter(i=>i.written).length)} من ${number(items.length)} مكتوب.</p></div></div>${items.map(item => `<form class="knowledge-form form-grid" data-knowledge-code="${e(item.code)}"><div class="field full knowledge-head"><b>${e(item.code)}</b><span>${e(item.name_ar)}</span>${item.written ? badge('مكتوب') : badge('غير مكتوب','warning')}</div>${data.fields.map(field => `<label class="field full"><span>${e(data.field_labels_ar[field])}</span><textarea name="${field}" rows="3" maxlength="4000" placeholder="اكتب هنا…">${e(item.content[field] || '')}</textarea></label>`).join('')}<div class="field full"><button class="primary-button" type="submit">حفظ ${e(item.code)}</button></div></form>`).join('')}</section>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading('البحث · المعرفة',t('محرر المحتوى المعرفي'),`المحتوى الذي يظهر في صفحة المعرفة العامة. لا يُولَّد آليًا ولا يُملأ بنص افتراضي. المكتوب ${number(data.written_count)} من ${number(data.dimension_count)}.`)}<div class="research-notice"><strong>ملاحظة</strong><span>${e(data.authoring_notice_ar)}</span></div>${sections || emptyState('لا توجد أبعاد','لم يُبذر إصدار أداة بعد.')}</div>`;
}

function renderJoin(route) {
  state.publicPage = true; applyShell();
  const prefilled = route?.query?.get('code') || '';
  appView.innerHTML = `<div class="landing-page">${publicNav()}<main><div class="page narrow-page">
    ${pageHeading('مشاركة زملاء العمل',t('الانضمام بكود مشاركة'),'زميلك في المنشأة أنشأ كود مشاركة ليجيب أكثر من موظف على نفس التقييم. الإجابات تُجمع في تقييم واحد، ولا يلزمك حساب.')}
    <section class="panel"><form id="join-code-form" class="form-grid">
      <label class="field full"><span>${t('كود المشاركة')}</span><input name="code" dir="ltr" required autocomplete="off" placeholder="XXXX-XXXX" value="${e(prefilled)}"></label>
      <label class="field"><span>${t('الاسم الكامل')}</span><input name="full_name" required minlength="2" autocomplete="name"></label>
      <label class="field"><span>${t('المسمى الوظيفي')}</span><input name="job_title" maxlength="120"></label>
      <label class="checkbox-field full"><input name="service_consent" type="checkbox" required><span>أوافق على معالجة إجاباتي لإصدار تشخيص المنشأة.</span></label>
      <div class="form-error full" hidden></div>
      <button class="primary-button full" type="submit">${t('انضم إلى التقييم')}</button>
    </form></section>
    <section class="panel"><p>لا تملك كودًا؟ <a href="#participant-start">ابدأ تقييمًا جديدًا لمنشأتك</a>.</p></section>
  </div></main></div>`;
}

function renderSignup(route) {
  state.publicPage = true; applyShell();
  // A token means the participant just finished anonymously and is claiming
  // that result, so the organisation name is already known.
  const claiming = Boolean(sessionStorage.getItem('mcm_participant_token'));
  appView.innerHTML = `<div class="landing-page">${publicNav()}<main><div class="page narrow-page">
    ${pageHeading('حساب اختياري',t('إنشاء حساب مشارك'), claiming
      ? 'احفظ نتيجتك بحساب لتعود إليها لاحقًا، وتتابع خارطة التحسين، وتدعو زملاءك، وتطلب استشارة. نتيجتك متاحة الآن سواء أنشأت حسابًا أو لم تفعل.'
      : 'حساب المشارك اختياري. يتيح لك العودة إلى تقييماتك ونتائجك وخارطة التحسين، ودعوة زملائك بكود مشاركة، وطلب استشارة.')}
    <section class="panel"><form id="participant-signup-form" class="form-grid">
      <label class="field"><span>${t('الاسم الكامل')}</span><input name="full_name" required minlength="2" autocomplete="name"></label>
      <label class="field"><span>${t('البريد الإلكتروني')}</span><input name="email" type="email" required autocomplete="email"></label>
      ${claiming ? '' : '<label class="field full"><span>اسم المنشأة</span><input name="organization_name" required minlength="2"></label>'}
      <label class="field full"><span>${t('كلمة المرور')}</span><input name="password" type="password" minlength="10" required autocomplete="new-password"><small>عشرة محارف على الأقل، وتشمل حرفًا كبيرًا وصغيرًا ورقمًا.</small></label>
      <div class="form-error full" hidden></div>
      <button class="primary-button full" type="submit">إنشاء الحساب</button>
    </form></section>
    <section class="panel"><p>لديك حساب؟ <a href="#login">${t('تسجيل الدخول')}</a> · <a href="#landing">${t('العودة للرئيسية')}</a></p></section>
  </div></main></div>`;
}

async function renderPrivacy() {
  state.publicPage = true; applyShell();
  const notice = await loadPrivacyNotice();
  if (!notice) { appView.innerHTML = `<div class="page">${errorState({code:'unavailable'})}</div>`; return; }
  const pending = value => value && value.startsWith('[[')
    ? `<em class="privacy-pending">${e(value)}</em>` : e(value || '—');
  appView.innerHTML = `<div class="landing-page">${publicNav()}<main><div class="page privacy-page">
    ${pageHeading('الشفافية', notice.title_ar, `الإصدار ${e(notice.version)}`)}
    <section class="panel"><div class="pill-list">
      <span>الجهة المتحكمة: ${pending(notice.controller_ar)}</span>
      <span>جهة طلبات الخصوصية: ${pending(notice.privacy_contact_ar)}</span>
    </div></section>
    ${notice.sections.map(section=>`<section class="panel"><h2>${e(section.title_ar)}</h2><p>${section.body_ar.includes('[[') ? pending(section.body_ar) : e(section.body_ar)}</p></section>`).join('')}
    <section class="panel"><div class="card-title"><div><h2>${t('سحب موافقة التواصل')}</h2><p>أدخل رقم الطلب الذي ظهر لك عند الإرسال. يوقف السحب التواصل بشأن الطلب، ولا يؤثر على نتيجة التقييم ولا على إتاحتها.</p></div></div><form id="withdraw-consent-form" class="form-grid"><label class="field"><span>${t('رقم الطلب')}</span><input name="lead_id" type="number" min="1" required inputmode="numeric"></label><div class="field full"><button class="danger-button" type="submit">${t('سحب الموافقة')}</button></div><div class="form-error full" hidden></div></form></section>
  </div></main></div>`;
}

function renderPublicResult(result) {
  state.publicPage = true; applyShell();
  const scores = result.scores || {}; const mcm = scores.MCM || {dimensions:[]}; const smce = scores.SMCE || {dimensions:[]};
  const relation = result.relationship || {}; const dashboard = result.dashboard || {};
  const charts = dashboard.charts || {};
  const dashboardSummary = dashboard.summary && typeof dashboard.summary === 'object' ? dashboard.summary : {};
  const mcmTotalRaw = Number(dashboardSummary.mcm_total ?? mcm.total); const smceTotalRaw = Number(dashboardSummary.smce_total ?? smce.total);
  const mcmTotal = Number.isFinite(mcmTotalRaw) ? mcmTotalRaw : null; const smceTotal = Number.isFinite(smceTotalRaw) ? smceTotalRaw : null;
  const efficiencyGap = Number.isFinite(Number(relation.efficiency_minus_maturity)) ? Number(relation.efficiency_minus_maturity) : (mcmTotal !== null && smceTotal !== null ? smceTotal-mcmTotal : null);
  const stages = result.maturity_progression || dashboard.maturity_progression || [];
  const mcmDimensions = dashboardArray(charts.mcm_radar || dashboard.mcm_dimensions || dashboard.dimensions?.MCM || mcm.dimensions);
  const smceDimensions = dashboardArray(charts.smce_bars || dashboard.smce_dimensions || dashboard.dimensions?.SMCE || smce.dimensions);
  const enablers = dashboardArray(charts.enabler_bars || dashboard.enablers || dashboard.dimensions?.ENABLER || scores.ENABLER?.dimensions || result.enablers);
  const outcomes = dashboardArray(charts.outcome_bars || dashboard.outcomes || dashboard.dimensions?.OUTCOME || scores.OUTCOME?.dimensions || result.outcomes);
  const rankedMcm = [...mcmDimensions].sort((a,b)=>dashboardScore(a)-dashboardScore(b));
  const strengths = dashboardArray(dashboard.strengths || dashboard.insights?.strengths);
  const opportunities = dashboardArray(dashboard.opportunities || dashboard.development_areas || dashboard.insights?.opportunities || dashboard.insights?.development_areas);
  const strengthItems = strengths.length ? strengths : rankedMcm.slice(-2).reverse();
  const opportunityItems = opportunities.length ? opportunities : rankedMcm.slice(0,3);
  const priorities = dashboardArray(dashboard.priorities || dashboard.improvement_plan?.priorities || result.priorities);
  const roadmap = normalizeRoadmap(dashboard,priorities.length ? priorities : opportunityItems);
  const currentStage = dashboardSummary.current_stage || mcm.maturity_level || {};
  const currentOrder = Number(currentStage.order || currentStage.level_order || 0);
  const suppliedNext = dashboardSummary.next_stage || dashboard.next_stage || dashboard.progression?.next_stage || {};
  const derivedNext = stages.find(stage=>Number(stage.level_order) === currentOrder + 1) || null;
  const nextLabel = suppliedNext.label_ar || suppliedNext.name || derivedNext?.label_ar || 'المحافظة على المرحلة الأعلى';
  const nextTarget = Number(suppliedNext.min_score ?? suppliedNext.target_score ?? derivedNext?.min_score);
  const suppliedGap = Number(dashboardSummary.gap_to_next_stage ?? dashboard.next_stage_gap ?? suppliedNext.gap_points ?? suppliedNext.gap);
  const nextGap = Number.isFinite(suppliedGap) ? Math.max(0,suppliedGap) : Number.isFinite(nextTarget) ? Math.max(0,nextTarget-Number(mcmTotal || 0)) : 0;
  const summary = (typeof dashboard.summary === 'string' ? dashboard.summary : '') || dashboard.executive_summary || dashboard.summary_ar || relation.narrative_ar || 'تعرض هذه القراءة موقع المنشأة الحالي وأولويات الانتقال إلى ممارسة أكثر نضجًا.';
  const timelineLabels = {'0-30':['الآن','أول 30 يومًا'],'31-90':['بعدها','من 31 إلى 90 يومًا'],'3-6':['ترسيخ','من 3 إلى 6 أشهر']};
  const timeline = Object.entries(timelineLabels).map(([key,[kicker,label]])=>`<section><header><small>${kicker}</small><h3>${label}</h3></header><div>${roadmap[key].slice(0,4).map(item=>`<article><b>${e(item.title || item.problem || dashboardName(item))}</b>${item.description || item.action ? `<p>${e(item.description || item.action)}</p>` : ''}${roadmapMeta(item) ? `<span>${e(roadmapMeta(item))}</span>` : ''}</article>`).join('') || '<p class="dashboard-empty">لا توجد إجراءات مقررة في هذا الأفق.</p>'}</div></section>`).join('');
  const insightCards = (items,tone,empty) => items.length ? items.map(item=>`<article class="insight-item ${tone}"><span>${e(item.code || item.dimension_code || '')}</span><h3>${e(dashboardName(item))}</h3><strong>${number(dashboardScore(item),1)}<small>/100</small></strong>${item.interpretation || item.reason ? `<p>${e(item.interpretation || item.reason)}</p>` : ''}</article>`).join('') : `<p class="dashboard-empty">${e(empty)}</p>`;
  appView.innerHTML = `<div class="public-result-page dashboard-result">${publicNav()}<main><section class="result-hero dashboard-hero"><div><span>${t('اكتمل مقياس النضج الاتصالي التسويقي')}</span><h1>تصنيف منشأتك: <i>${e(currentStage.label_ar || 'غير متاح')}</i></h1><p>${e(summary)}</p></div><div class="result-score-cards"><article><small>${t('النضج MCM')}</small><strong>${number(mcmTotal,1)}</strong><span>/100</span></article><article><small>${t('الكفاءة SMCE')}</small><strong>${number(smceTotal,1)}</strong><span>/100</span></article><article><small>${t('الفارق بين الكفاءة والنضج')}</small><strong>${Number(efficiencyGap || 0) > 0 ? '+' : ''}${number(efficiencyGap,1)}</strong><span>${t('نقطة')}</span></article></div></section><section class="panel maturity-dashboard"><div class="card-title"><div><h2>${t('رحلة النضج والخطوة التالية')}</h2><p>المرحلة الحالية مميزة، والحدود تشخيصية أولية قيد التحقق.</p></div><div class="next-stage-callout"><small>الفجوة إلى ${e(nextLabel)}</small><strong>${nextGap > 0 ? `${number(nextGap,1)} نقطة` : t('أنت في المرحلة الأعلى')}</strong></div></div><div class="maturity-stages compact">${stages.map(stage=>`<div class="${Number(stage.level_order) === currentOrder ? 'active':''}"><b>${number(stage.level_order)}</b><span>${e(stage.label_ar)}</span></div>`).join('')}</div></section><section class="dashboard-grid"><article class="card dashboard-panel radar-panel"><div class="card-title"><div><span class="dashboard-kicker">بصمة القدرة المؤسسية</span><h2>${t('أبعاد النضج السبعة MCM')}</h2><p>كل محور يمثل درجة بُعد مستقلة من 100.</p></div></div>${radarChart(mcmDimensions)}</article><article class="card dashboard-panel smce-panel"><div class="card-title"><div><span class="dashboard-kicker teal">النتيجة الاتصالية</span><h2>${t('كفاءة التواصل SMCE')}</h2><p>قراءة مستقلة للأداء الاتصالي المرصود.</p></div></div>${scoreProfile(smceDimensions,'لا تتوفر درجات SMCE لهذه الحالة.','teal')}<div class="relationship-compact"><b>MCM</b><span>أثر إيجابي مقترح ←</span><b>SMCE</b><p>${e(relation.interpretation_ar || '')}</p></div></article></section><section class="dashboard-grid context-outcomes"><article class="card dashboard-panel"><div class="card-title"><div><span class="dashboard-kicker">جاهزية التنفيذ</span><h2>${t('الممكنات التنظيمية')}</h2><p>تفسر قدرة المنشأة على التنفيذ ولا تدخل في مقام درجة MCM.</p></div></div>${scoreProfile(enablers,'تظهر الممكنات هنا عند احتساب بنود القيادة والكفاءات والتقنية والبيانات.','navy')}</article><article class="card dashboard-panel"><div class="card-title"><div><span class="dashboard-kicker teal">نتائج اختيارية</span><h2>الثقة والرضا والعلامة والأعمال</h2><p>مؤشرات سياقية اختيارية لا تدخل في التصنيف الأساسي.</p></div></div>${scoreProfile(outcomes,'لم تُجب هذه الحالة عن بنود النتائج الاختيارية، لذلك لم تُعرض درجة.','sand')}</article></section><section class="insights-grid"><article class="card"><div class="card-title"><div><span class="dashboard-kicker success">ما يعمل جيدًا</span><h2>${t('نقاط القوة')}</h2></div></div><div class="insight-list">${insightCards(strengthItems,'strength','لا تتوفر نقاط قوة محسوبة.')}</div></article><article class="card"><div class="card-title"><div><span class="dashboard-kicker warning">بداية التحسين</span><h2>${t('الفرص ذات الأولوية')}</h2></div></div><div class="insight-list">${insightCards(opportunityItems,'opportunity','لا تتوفر فرص محسوبة.')}</div></article></section><section class="dashboard-grid improvement-section"><article class="card dashboard-panel"><div class="card-title"><div><span class="dashboard-kicker">قرار تنفيذي</span><h2>${t('مصفوفة الأثر والجهد')}</h2><p>الأرقام تربط النقاط بأولوية التحسين المقابلة.</p></div></div>${impactEffortMatrix(priorities.length ? priorities : opportunityItems)}</article><article class="card dashboard-panel priority-panel"><div class="card-title"><div><span class="dashboard-kicker teal">الترتيب المقترح</span><h2>${t('أولويات العمل')}</h2><p>ابدأ بالأثر الأعلى والجهد الأقل، ثم راجع الملاءمة مع فريقك.</p></div></div><ol>${(priorities.length ? priorities : opportunityItems).slice(0,5).map((item,index)=>`<li><b>${number(item.rank || index+1)}</b><div><h3>${e(item.problem || item.title || dashboardName(item))}</h3>${item.action || item.description ? `<p>${e(item.action || item.description)}</p>` : ''}<span>${e(item.dimension_code || item.code || '')}${item.kpi ? ` · KPI: ${e(item.kpi)}` : ''}</span></div></li>`).join('') || '<li class="dashboard-empty">لا توجد أولويات مادية لهذه النتيجة.</li>'}</ol></article></section><section class="panel roadmap-dashboard"><div class="card-title"><div><span class="dashboard-kicker">من التشخيص إلى التنفيذ</span><h2>${t('خارطة التحسين 30 / 90 / 180 يومًا')}</h2><p>خطوات مرحلية قابلة للمراجعة؛ حدّث المسؤول والمؤشر والتاريخ عند اعتماد الخطة داخليًا.</p></div></div><div class="roadmap-timeline">${timeline}</div></section>${state.token ? '' : `<section class="card account-cta"><div><span class="dashboard-kicker">${t('اختياري')}</span><h2>${t('تحليل أعمق بحساب مشارك')}</h2><p><strong>نتيجتك أعلاه كاملة، ولا يُحجب منها شيء.</strong> الحساب يفتح تحليلًا إضافيًا لا يظهر في هذه الصفحة:</p><ul class="account-benefits"><li>تفاصيل كل بُعد على حدة مع توصيته الخاصة</li><li>التشخيص العميق بالأدلة الرقمية ودرجة الثقة</li><li>تحليل الفجوات بين الأبعاد المترابطة</li><li>المقارنة المرجعية مع منشآت مشابهة</li><li>مسار النضج عبر دورات القياس المتتالية</li><li>تقرير PDF لتقييمك، ودعوة زملائك بكود مشاركة</li></ul></div><div class="button-row"><a class="primary-button" href="#signup">${t('إنشاء حساب')}</a><a class="secondary-button" href="#login">${t('لدي حساب')}</a></div></section>`}${consultationCta(result.assessment_id)}<section class="card result-boundary"><div><h2>${t('كيف تقرأ النتيجة؟')}</h2><p>${e((locale() === 'en' && result.classification_notice_en) ? result.classification_notice_en : (result.classification_notice || ''))}</p></div><div class="button-row public-result-actions"><button class="secondary-button" data-action="print-result">${t('طباعة النتائج')}</button><a class="primary-button" href="#landing">${t('العودة للرئيسية')}</a></div></section></main></div>`;
}

function renderAuth() {
  state.me = null; applyShell();
  if (!state.publicConfig.registration_enabled && state.authMode === 'register') state.authMode = 'login';
  const register = state.authMode === 'register';
  const ephemeralNotice = state.publicConfig.storage === 'ephemeral-demo' ? `<div class="research-notice"><strong>بيئة عرض مؤقتة</strong><span>${e(state.publicConfig.notice || 'لا تستخدم بيانات حقيقية؛ قد يعاد ضبط البيانات.')}</span></div>` : '';
  const registerTab = state.publicConfig.registration_enabled ? `<button class="${register ? 'active' : ''}" data-action="auth-mode" data-mode="register" type="button">${t('إنشاء حساب')}</button>` : '';
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>${t('مقياس النضج الاتصالي التسويقي')}</div><div class="auth-copy"><div class="eyebrow">PLATFORM MANAGEMENT</div><h1>قرارات أوضح.<br><i>أثر أقوى.</i></h1><p>مساحة مدير المنصة لمتابعة الحالات والتقارير وخارطة التطوير وتصدير ملفات التحليل.</p><div class="auth-features"><span>تقارير ورسوم تنفيذية</span><span>ربط MCM وSMCE</span><span>Excel وSPSS</span></div></div><small>Evidence-Informed Applied Model</small></div><div class="auth-panel"><div class="auth-box">${ephemeralNotice}<div class="auth-tabs"><button class="${register ? '' : 'active'}" data-action="auth-mode" data-mode="login" type="button">${t('تسجيل الدخول')}</button>${registerTab}</div><h2>${register ? 'أنشئ مساحة مؤسستك' : t('تسجيل الدخول')}</h2><p>${register ? 'ابدأ بملف المؤسسة ثم نفّذ التقييم الأول.' : 'أدخل بيانات الحساب الإداري للوصول إلى مساحة العمل.'}</p><form id="auth-form" class="form-grid">${register ? `<label class="field"><span>${t('الاسم الكامل')}</span><input name="name" required autocomplete="name"></label><label class="field"><span>اسم المؤسسة</span><input name="organization_name" required></label>` : ''}<label class="field ${register ? '' : 'full'}"><span>${t('البريد الإلكتروني')}</span><input name="email" type="email" required autocomplete="email"></label><label class="field ${register ? '' : 'full'}"><span>${t('كلمة المرور')}</span><input name="password" type="password" required autocomplete="${register ? 'new-password' : 'current-password'}"></label>${register ? `<label class="checkbox-field full"><input name="service_consent" type="checkbox" required><span>أوافق على معالجة البيانات لأغراض التشخيص وتقديم الخدمة.</span></label>` : ''}<div id="auth-error" class="form-error full" hidden></div><button class="primary-button full" type="submit">${register ? 'إنشاء الحساب' : t('تسجيل الدخول')}</button></form>${register ? '' : `<div class="button-row"><button class="secondary-button" data-action="forgot-password" type="button">نسيت كلمة المرور</button><a class="secondary-button" href="#participant-start">دخول المشارك مباشرة</a><a class="secondary-button" href="#landing">${t('الرئيسية')}</a></div>`}</div></div></section>`;
}

function renderForgot() {
  state.me = null; applyShell();
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>${t('مقياس النضج الاتصالي التسويقي')}</div><div class="auth-copy"><h1>استعادة<br><i>آمنة للحساب.</i></h1><p>لن نكشف ما إذا كان البريد مسجلًا أم لا.</p></div></div><div class="auth-panel"><div class="auth-box"><h2>نسيت كلمة المرور</h2><p>أدخل بريدك لاستلام تعليمات الاستعادة عبر القناة المضبوطة.</p><form id="forgot-form" class="form-grid"><label class="field full"><span>البريد</span><input name="email" type="email" required></label><button class="primary-button full">${t('إرسال الطلب')}</button></form><p><a href="#login">العودة لتسجيل الدخول</a></p></div></div></section>`;
}
function renderReset(route) {
  state.me = null; applyShell();
  const token = route.query.get('token') || '';
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>${t('مقياس النضج الاتصالي التسويقي')}</div><div class="auth-copy"><h1>كلمة مرور<br><i>جديدة.</i></h1></div></div><div class="auth-panel"><div class="auth-box"><h2>إعادة ضبط كلمة المرور</h2><form id="reset-form" class="form-grid"><input type="hidden" name="token" value="${e(token)}"><label class="field full"><span>كلمة المرور الجديدة</span><input name="password" type="password" minlength="10" required></label><button class="primary-button full">حفظ كلمة المرور</button></form></div></div></section>`;
}

async function renderOverview() {
  loading('جارٍ تحميل لوحة النضج...');
  const data = await api('/api/dashboard');
  const actions = canManageAssessments() ? `<button class="primary-button" data-action="create-assessment" type="button">تقييم جديد</button>` : '';
  if (!data.latest) {
    const emptyAction = canManageAssessments() ? '<button class="primary-button" data-action="create-assessment" type="button">ابدأ أول تقييم</button>' : '<a class="primary-button" href="#assessments">عرض التقييمات المعيّنة</a>';
    appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · نظرة عامة', `مرحبًا، ${state.me.user.name}`, `ابدأ أول قياس لمؤسسة <strong>${e(data.organization.name)}</strong>.`, actions)}${modelNotice()}<div class="card-grid"><article class="card metric-card span-4"><small>اكتمال ملف المؤسسة</small><strong>${number(data.profile_completion)}<em>%</em></strong><a href="#settings">عرض الملف</a></article><article class="card metric-card span-4"><small>تقييمات قيد التنفيذ</small><strong>${number(data.draft_count)}</strong><a href="#assessments">عرض المسودات</a></article><article class="card metric-card span-4"><small>النتائج المتاحة</small><strong>0</strong><span>تظهر بعد إرسال التقييم</span></article></div>${emptyState('لم يتم تنفيذ تقييم بعد.', 'تظهر هنا النتائج بعد اكتمال تقييم يستخدم إصدار الأداة الحالي.', emptyAction)}</div>`;
    return;
  }
  const result = data.latest; const mcm = result.scores.MCM; const smce = result.scores.SMCE;
  const dimensions = mcm.dimensions.map(item => `<div class="dimension-line"><a href="#dimension/${result.assessment_id}/${e(item.code)}">${e(item.code)} · ${e(item.name)}</a><div class="dimension-track"><i style="--score:${Number(item.score)}%"></i></div><b>${number(item.score,1)}</b></div>`).join('');
  const history = data.history.map(item => `<div class="trend-column" title="${e(dateText(item.completed_at))}: ${number(item.mcm,1)}"><i style="--score:${Number(item.mcm || 0)}"></i><span>${e(dateText(item.completed_at))}</span></div>`).join('');
  const diagnoses = data.diagnoses.length ? data.diagnoses.map(item => `<article class="card diagnosis-card ${item.severity === 'HIGH' ? 'high' : ''}">${badge(item.severity, item.severity === 'HIGH' ? 'danger' : 'warning')}<h3>${e(item.name)}</h3><p>${e(item.business_implication)}</p><a href="#diagnosis/${result.assessment_id}">عرض الأدلة</a></article>`).join('') : `<article class="card"><h3>لا توجد قواعد تشخيص مفعلة على النتيجة</h3><p>لا يعني ذلك اعتماد الأداة؛ راجع الأبعاد والأولويات المتاحة.</p></article>`;
  const priorityRows = data.priorities.map(item => `<div class="data-table__row"><span>${number(item.rank)}</span><strong>${e(item.dimension_code)}<small>${e(item.problem)}</small></strong><span>${number(item.current_score,1)}</span><span>${number(item.gap,1)}</span><span>${e(item.suggested_owner || '--')}</span><a href="#priorities/${result.assessment_id}">${t('فتح')}</a></div>`);
  appView.innerHTML = `<div class="page">${pageHeading(`آخر تقييم · ${dateText(result.completed_at)}`, `صباح الخير، ${state.me.user.name}`, `هذه قراءة آخر تقييم مكتمل لمؤسسة <strong>${e(data.organization.name)}</strong> · مصدر البيانات ${e(result.data_origin)}.`, actions)}${modelNotice()}<div class="card-grid"><article class="card metric-card teal span-4"><small>درجة MCM الكلية</small><strong>${number(mcm.total,1)}<em>/100</em></strong><span>${e(mcm.maturity_level?.label_ar || 'تصنيف غير متاح')}</span></article><article class="card metric-card span-4"><small>${t('كفاءة التواصل SMCE')}</small><strong>${number(smce.total,1)}<em>/100</em></strong><span>نتيجة مستقلة عن MCM</span></article><article class="card metric-card span-4"><small>اكتمال ملف المؤسسة</small><strong>${number(data.profile_completion)}<em>%</em></strong><a href="#settings">عرض الملف</a></article><article class="card span-8"><div class="card-title"><div><h2>أبعاد النضج الاتصالي</h2><p>الأبعاد السبعة مستقلة وقابلة للتشخيص.</p></div><a href="#results/${result.assessment_id}">كل النتائج</a></div><div class="dimension-list">${dimensions}</div></article><article class="card span-4"><div class="card-title"><div><h2>قراءة تشخيصية</h2><p>قواعد حتمية لا تعتمد على الذكاء الاصطناعي.</p></div></div>${diagnoses}</article><article class="card span-12"><div class="card-title"><div><h2>${t('مسار النضج')}</h2><p>التقييمات المكتملة فقط.</p></div><a href="#history">التاريخ الكامل</a></div><div class="trend-chart">${history}</div></article></div><section class="panel"><div class="card-title"><div><h2>أولويات التطوير</h2><p>ترتيب قابل للتدقيق من الفجوة والأثر والاعتمادية والجهد.</p></div><a href="#roadmap/${result.assessment_id}">عرض الخارطة</a></div>${data.priorities.length ? table(['الترتيب','البعد',t('الحالي'),t('الفجوة'),t('المالك'),''], priorityRows, 6, 820) : emptyState('لا توجد أولويات بعد', 'لم تُولد أولويات لهذه النتيجة.')}</section></div>`;
}

async function renderAssessments() {
  loading(); const data = await api('/api/assessments');
  const createAction = canManageAssessments() ? '<button class="primary-button" data-action="create-assessment" type="button">تقييم جديد</button>' : '';
  const rows = data.assessments.map(item => `<div class="data-table__row"><strong>#${item.id}<small>${e(item.assessment_type)}</small></strong><span>${badge(item.status, item.status === 'COMPLETED' ? '' : 'warning')}</span><span>${e(item.instrument_version)} · ${e(item.instrument_status)}</span><span>${dateText(item.created_at)}</span><span>${number(item.mcm_total,1)}</span><span class="button-row">${item.status === 'COMPLETED' ? `<a class="secondary-button" href="#results/${item.id}">${t('النتائج')}</a>${canManageAssessments() ? `<button class="secondary-button" data-action="repeat-assessment" data-id="${item.id}">إعادة</button>` : ''}` : `<a class="primary-button" href="#assessment/${item.id}">${t('فتح')}</a>`}${item.status !== 'COMPLETED' ? `<button class="secondary-button" data-action="share-join-code" data-id="${item.id}">دعوة زميل</button>` : ''}${hasRole('SUPER_ADMIN') ? `<button class="danger-button" data-action="delete-assessment" data-id="${item.id}">حذف</button>` : ''}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · التقييمات','التقييمات المؤسسية','الحفظ والاستكمال مرتبطان بالمشارك وصلاحيته داخل المؤسسة.', createAction)}${modelNotice()}<section class="panel">${rows.length ? table([t('التقييم'),t('الحالة'),'إصدار الأداة','تاريخ البدء','MCM','الإجراء'], rows, 6, 850) : emptyState('لا توجد تقييمات', 'لا توجد تقييمات معيّنة لهذا الحساب.', createAction)}</section></div>`;
}

function questionCard(item, response, disabled = false) {
  const value = response?.value;
  const type = String(item.response_type || 'LIKERT').toUpperCase();
  const minimum = Number(item.min_value ?? 1); const maximum = Number(item.max_value ?? 5);
  const lock = disabled ? ' disabled' : '';
  let control;
  if (type === 'TEXT') {
    control = `<label class="field answer-field"><span>الإجابة النصية</span><textarea name="q_${item.id}" data-answer-input data-item-id="${item.id}" rows="4"${lock}>${response?.missing_type ? '' : e(value)}</textarea></label>`;
  } else if (type === 'NUMERIC') {
    control = `<label class="field answer-field"><span>قيمة من ${number(minimum)} إلى ${number(maximum)}</span><input name="q_${item.id}" data-answer-input data-item-id="${item.id}" type="number" min="${minimum}" max="${maximum}" step="any" value="${response?.missing_type || value === null || value === undefined ? '' : e(value)}"${lock}></label>`;
  } else {
    const values = type === 'BOOLEAN' ? [minimum, maximum] : Array.from({length:Math.max(1,Math.min(11,Math.floor(maximum)-Math.ceil(minimum)+1))},(_,index)=>Math.ceil(minimum)+index);
    const extent = type === 'LIKERT_EXTENT' || type === 'LIKERT_5_EXTENT';
    const relative = type === 'LIKERT_RELATIVE' || type === 'RELATIVE_5_COMPETITOR';
    const labels = extent
      ? {1:'لا تنطبق إطلاقًا',2:'تنطبق بدرجة قليلة',3:'تنطبق بدرجة متوسطة',4:'تنطبق بدرجة كبيرة',5:'تنطبق بدرجة كبيرة جدًا'}
      : relative
        ? {1:'أضعف بكثير من المنافسين الرئيسيين',2:'أضعف من المنافسين الرئيسيين',3:'مماثل للمنافسين الرئيسيين',4:'أفضل من المنافسين الرئيسيين',5:'أفضل بكثير من المنافسين الرئيسيين'}
        : {1:'لا أوافق بشدة',2:'لا أوافق',3:'محايد',4:'أوافق',5:'أوافق بشدة'};
    const choices = values.map((choice,index) => `<label><input type="radio" name="q_${item.id}" value="${choice}" data-answer-input data-item-id="${item.id}" ${Number(value) === choice && !response?.missing_type ? 'checked' : ''}${lock}><span>${type === 'BOOLEAN' ? (index ? t('نعم') : t('لا')) : e(labels[choice] || String(choice))}</span></label>`).join('');
    const hint = extent ? 'إلى أي مدى تنطبق العبارة على منشأتك خلال الاثني عشر شهرًا الماضية؟' : relative ? 'كيف تقارن النتيجة بالمنافسين الرئيسيين؟' : '';
    control = `${hint ? `<p class="scale-hint">${e(hint)}</p>` : ''}<div class="choice-scale labelled ${relative ? 'relative':''}" style="--choice-count:${values.length}">${choices}</div>`;
  }
  const disabledButton = disabled ? ' disabled' : '';
  const supportsScientificMissing = ['LIKERT_EXTENT','LIKERT_5_EXTENT','LIKERT_RELATIVE','RELATIVE_5_COMPETITOR'].includes(type);
  const missingLabel = {NOT_APPLICABLE:'لا ينطبق',DONT_KNOW:'لا أعرف',NOT_ANSWERED:'غير مجاب'}[response?.missing_type] || response?.missing_type;
  const missingButtons = supportsScientificMissing
    ? `<button type="button" data-action="missing-answer" data-item-id="${item.id}" data-missing="NOT_APPLICABLE"${disabledButton}>${t('لا ينطبق')}</button><button type="button" data-action="missing-answer" data-item-id="${item.id}" data-missing="DONT_KNOW"${disabledButton}>${t('لا أعرف')}</button>`
    : `<button type="button" data-action="missing-answer" data-item-id="${item.id}" data-missing="NOT_APPLICABLE"${disabledButton}>${t('لا ينطبق')}</button><button type="button" data-action="missing-answer" data-item-id="${item.id}" data-missing="DONT_KNOW"${disabledButton}>${t('لا أعرف')}</button>`;
  return `<fieldset class="question-card" data-question="${item.id}"${disabled ? ' disabled' : ''}><legend class="question-title"><code>${e(item.code)}</code><span>${e(item.prompt_ar)}${item.required ? ' <b class="required-mark">*</b>' : ''}</span></legend>${control}<details class="missing-control" ${response?.missing_type ? 'open':''}><summary>${response?.missing_type ? `الإجابة المسجلة: ${e(missingLabel)}` : 'لا ينطبق أو لا أعرف'}</summary><div class="missing-options">${missingButtons}<button type="button" data-action="clear-answer" data-item-id="${item.id}"${disabledButton}>مسح الإجابة</button></div></details></fieldset>`;
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
  appView.innerHTML = `<div class="page assessment-page">${pageHeading(`التقييم #${id} · ${e(data.instrument.version)}`,'التقييم المؤسسي','اختر الإجابة التي تصف الممارسة الحالية، لا الحالة المرغوبة.', '<a class="secondary-button" href="#assessments">حفظ وخروج</a>')} ${modelNotice()}<section class="assessment-header"><div class="progress-row"><strong>${t('التقدم')} <span id="progress-value">${number(data.review.progress,0)}%</span></strong><span class="save-state" id="save-state">${t('محفوظ على الخادم')}</span></div><div class="progress-track"><span id="progress-bar" style="--progress:${data.review.progress}%"></span></div></section><form id="assessment-form">${sections}</form><section class="panel">${footer}</section></div>`;
}

async function renderResults(route) {
  // #results and #results/latest resolve to the newest completed assessment.
  // With nothing completed the route explains the state instead of bouncing
  // the user to another page with no explanation.
  let id = Number(route.parts[1]);
  if (!id) {
    loading('جارٍ تحميل النتائج...');
    id = await latestCompletedId();
    if (!id) {
      const pending = await firstIncompleteAssessment();
      appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · النتائج',t('النتائج'),'تظهر النتائج بعد إرسال تقييم مكتمل.')}${
        pending
          ? emptyState('لديك تقييم غير مكتمل.', 'أكمل الإجابة على البنود المطلوبة ثم أرسل التقييم لعرض النتائج.', `<a class="primary-button" href="#assessment/${pending}">استكمال التقييم</a>`)
          : emptyState('لم تكمل أي تقييم حتى الآن.', 'ابدأ التقييم لتحصل على تصنيف منشأتك وخارطة التحسين.', '<a class="primary-button" href="#assessments">ابدأ التقييم</a>')
      }</div>`;
      return;
    }
  }
  loading('جارٍ تحميل النتائج...'); const data = await api(`/api/results/${id}`);
  const mcm = data.scores.MCM; const smce = data.scores.SMCE;
  const dimLines = mcm.dimensions.map(item => `<div class="dimension-line"><a href="#dimension/${id}/${e(item.code)}">${e(item.code)} · ${e(item.name)}</a><div class="dimension-track"><i style="--score:${Number(item.score)}%"></i></div><b>${number(item.score,1)}</b></div>`).join('');
  const smceLines = smce.dimensions.map(item => `<div class="dimension-line"><span>${e(item.code)} · ${e(item.name)}</span><div class="dimension-track"><i style="--score:${Number(item.score)}%"></i></div><b>${number(item.score,1)}</b></div>`).join('');
  const relation = data.relationship || {};
  const stages = (data.maturity_progression || []).map(stage => `<div class="${stage.level_order === mcm.maturity_level?.order ? 'active':''}"><b>${number(stage.level_order)}</b><span>${e(stage.label_ar)}</span></div>`).join('');
  const context = data.context ? `<section class="panel"><div class="card-title"><div><h2>السياق الديموغرافي للحالة</h2><p>عوامل تفسيرية لا تدخل في مقام درجة MCM.</p></div></div><div class="pill-list"><span>القطاع: ${e(data.context.sector)}</span><span>الحجم: ${e(data.context.firm_size)}</span><span>العمر: ${number(data.context.firm_age_years)} سنة</span><span>المنطقة: ${e(data.context.region)}</span><span>منصات التواصل: ${number(data.context.social_platform_count)}</span><span>دور المجيب: ${e(data.context.respondent_role)}</span></div></section>` : '';
  const actions = `<a class="secondary-button" href="#diagnosis/${id}">التشخيص</a><a class="secondary-button" href="#gaps/${id}">الفجوات</a><a class="secondary-button" href="#priorities/${id}">الأولويات</a><a class="primary-button" href="#roadmap/${id}">${t('خارطة التحسين')}</a>`;
  const reportAction = canManageAssessments() ? `<button class="primary-button" data-action="generate-report" data-id="${id}" data-type="EXECUTIVE">5. إنشاء التقرير</button>` : '';
  const aiPlanAction = canManageAssessments() ? `<button class="secondary-button" data-action="generate-ai-plan" data-id="${id}">6. تحليل خطة التحسين</button>` : '';
  appView.innerHTML = `<div class="page">${pageHeading(`نتائج التقييم #${id}`,`نتيجة ${e(data.organization_name)}`,`اكتمل القياس بتاريخ ${e(dateText(data.completed_at))}.`, actions)}${modelNotice()}<section class="panel maturity-panel"><div class="card-title"><div><h2>تصنيف المنشأة: ${e(mcm.maturity_level?.label_ar || 'غير مصنف')}</h2><p>مرحلة تشخيصية أولية ضمن مسار من خمس مراحل.</p></div><strong class="level-score">${number(mcm.total,1)} / 100</strong></div><div class="maturity-stages compact">${stages}</div></section><div class="card-grid"><article class="card span-6"><div class="card-title"><div><h2>النضج الاتصالي MCM</h2><p>متوسط موزون للأبعاد السبعة فقط.</p></div>${badge(mcm.maturity_level?.label_ar || 'غير مصنف')}</div><div class="score-layout"><div class="score-ring" style="--score:${Number(mcm.total || 0)}"><div><strong>${number(mcm.total,1)}</strong><small>/100</small></div></div><div class="dimension-list">${dimLines}</div></div></article><article class="card span-6"><div class="card-title"><div><h2>${t('كفاءة التواصل SMCE')}</h2><p>نتيجة اتصالية لاحقة مقترحة، وتُحتسب بصورة مستقلة.</p></div></div><div class="score-layout"><div class="score-ring" style="--score:${Number(smce.total || 0)}"><div><strong>${number(smce.total,1)}</strong><small>/100</small></div></div><div class="dimension-list">${smceLines}</div></div></article><article class="card span-12 relationship-card"><div><small>النموذج المقترح</small><h2>MCM <span>←</span> SMCE</h2><p>${e(relation.interpretation_ar || '')}</p></div><div class="relationship-gap"><small>الكفاءة ناقص النضج</small><strong>${Number(relation.efficiency_minus_maturity || 0) > 0 ? '+' : ''}${number(relation.efficiency_minus_maturity,1)}</strong><span>${e(relation.narrative_ar || '')}</span></div></article></div>${context}<section class="panel"><div class="card-title"><div><h2>من النتيجة إلى التنفيذ</h2><p>انتقل بالتسلسل من الأدلة إلى الفجوة والأولوية ثم خارطة العمل.</p></div></div><div class="button-row"><a class="secondary-button" href="#diagnosis/${id}">1. التشخيص العميق</a><a class="secondary-button" href="#gaps/${id}">2. تحليل الفجوات</a><a class="secondary-button" href="#priorities/${id}">3. ترتيب الأولويات</a><a class="secondary-button" href="#benchmark/${id}">4. المقارنة المرجعية</a>${reportAction}${aiPlanAction}</div><p class="classification-boundary">${e(data.classification_notice)}</p></section>${consultationCta(id)}</div>`;
}

async function renderDimension(route) {
  const id = Number(route.parts[1]); const code = route.parts[2]; if (!id || !code) return navigate(`results/${id || ''}`);
  loading(); const data = await api(`/api/results/${id}/dimensions/${encodeURIComponent(code)}`); const item = data.dimension;
  const diagnoses = data.diagnoses.map(row => `<article class="card diagnosis-card ${row.severity === 'HIGH' ? 'high' : ''}">${badge(row.severity,row.severity === 'HIGH' ? 'danger':'warning')}<h3>${e(row.name)}</h3><p>${e(row.interpretation)}</p></article>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading(`نتائج #${id} · ${e(code)}`,e(item.name || code),e(item.name_en || ''),`<a class="secondary-button" href="#results/${id}">العودة للنتائج</a>`)}${modelNotice()}<div class="card-grid"><article class="card metric-card teal span-4"><small>درجة البعد</small><strong>${number(item.score,1)}<em>/100</em></strong><span>${number(item.answered_count)} من ${number(item.eligible_count)} بندًا</span></article><article class="card span-8"><h2>التفسير والإجراء</h2>${data.recommendation ? `<h3>${e(data.recommendation.problem)}</h3><p>${e(data.recommendation.action)}</p><div class="pill-list"><span>المالك: ${e(data.recommendation.suggested_owner)}</span><span>الأثر: ${e(data.recommendation.expected_impact)}</span><span>الجهد: ${e(data.recommendation.effort)}</span><span>KPI: ${e(data.recommendation.kpi)}</span></div>` : '<p>لا توجد توصية مرتبطة بهذا الإصدار.</p>'}</article></div><section><div class="card-title"><div><h2>التشخيصات المرتبطة</h2><p>${e(data.evidence_notice)}</p></div></div><div class="card-grid">${diagnoses || emptyState('لا توجد قاعدة مطابقة', 'لم تتحقق شروط تشخيص مرتبطة بهذا البعد.')}</div></section></div>`;
}

async function renderDiagnosis(route) {
  const id = Number(route.parts[1]) || await latestCompletedId(); if (!id) return navigate('assessments');
  loading(); const data = await api(`/api/diagnostics/${id}`);
  const cards = data.diagnoses.map(item => `<article class="card diagnosis-card ${item.severity === 'HIGH' ? 'high' : ''}"><div class="card-title"><div>${badge(item.severity,item.severity === 'HIGH' ? 'danger':'warning')}<h3>${e(item.name)}</h3></div><strong>${number(item.confidence * 100)}%</strong></div><div class="evidence-list">${Object.entries(item.evidence).map(([key,value]) => `<span>${e(key)}: ${number(value,1)}</span>`).join('')}</div><p><strong>التفسير:</strong> ${e(item.interpretation)}</p><p><strong>الأثر:</strong> ${e(item.business_implication)}</p></article>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading(`التقييم #${id}`,'التشخيص العميق','قواعد بيانات حتمية مع أدلة ظاهرة وثقة مسجلة.',`<a class="secondary-button" href="#results/${id}">${t('النتائج')}</a><a class="primary-button" href="#priorities/${id}">الأولويات</a>`)}${modelNotice()}<div class="card-grid">${cards || emptyState('لا توجد تشخيصات مطابقة', 'لم تتحقق الشروط الرقمية للقواعد النشطة في هذا الإصدار.')}</div></div>`;
}

async function renderGaps(route) {
  const id = Number(route.parts[1]) || await latestCompletedId(); if (!id) return navigate('assessments');
  loading(); const data = await api(`/api/gaps/${id}`);
  const rows = data.gaps.map(item => `<div class="data-table__row"><strong>${e(item.name)}<small>${e(item.code)}</small></strong><span>${e(item.source)}</span><span>${e(item.target)}</span><span>${number(item.gap,1)}</span><span>${number(item.threshold,1)}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading(`التقييم #${id}`,'تحليل الفجوات',`تظهر الفجوة عندما يتجاوز الفرق الحد المضبوط (${number(data.threshold,1)} نقطة).`,`<a class="secondary-button" href="#diagnosis/${id}">التشخيص</a><a class="primary-button" href="#priorities/${id}">ترتيب الأولويات</a>`)}<section class="panel">${rows.length ? table(['النمط','المصدر','الهدف',t('الفجوة'),'الحد'],rows,5,760) : emptyState('لا توجد فجوات عابرة للأبعاد', 'لم يتجاوز أي نمط حد الفجوة المضبوط.')}</section></div>`;
}

async function renderPriorities(route) {
  const id = Number(route.parts[1]) || await latestCompletedId(); if (!id) return navigate('assessments');
  loading(); const data = await api(`/api/priorities/${id}`);
  const cards = data.priorities.map(item => `<article class="card"><div class="card-title"><div><span class="status-badge">الأولوية ${number(item.rank)}</span><h3>${e(item.problem)}</h3><p>${e(item.dimension_code)}</p></div><span class="priority-score"><small>${t('درجة الأولوية')}</small><b>${number(item.priority_score,1)}</b></span></div><p>${e(item.action)}</p><div class="pill-list"><span>الحالي ${number(item.current_score,1)}</span><span>الفجوة ${number(item.gap,1)}</span><span>المالك ${e(item.suggested_owner)}</span><span>الجهد ${e(item.effort)}</span></div></article>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading(`التقييم #${id}`,'أولويات التطوير','ترتيب حتمي قابل للتدقيق، ولا تدخل الفجوات السالبة في الأولوية.',`<a class="secondary-button" href="#gaps/${id}">الفجوات</a><a class="primary-button" href="#roadmap/${id}">تحويلها إلى خطة</a>`)}<div class="card-grid">${cards || emptyState('لا توجد أولويات', 'لم تُولد توصيات قابلة للترتيب لهذا الإصدار.')}</div></div>`;
}

async function latestCompletedId() {
  const data = await api('/api/assessments');
  return data.assessments.find(item => item.status === 'COMPLETED')?.id || null;
}

async function firstIncompleteAssessment() {
  const data = await api('/api/assessments');
  return data.assessments.find(item => item.status !== 'COMPLETED')?.id || null;
}

async function renderRoadmap(route) {
  const id = Number(route.parts[1]) || await latestCompletedId();
  if (!id) { appView.innerHTML = `<div class="page">${pageHeading(t('مساحة العمل'),t('خارطة التحسين'),'تُنشأ الخارطة بعد اكتمال تقييم.','<a class="primary-button" href="#assessments">اذهب للتقييمات</a>')}${emptyState('لا توجد خارطة بعد','أكمل أول تقييم ليحوّل المحرك الأولويات إلى خطة 30/90/180 يومًا.')}</div>`; return; }
  loading(); const data = await api(`/api/roadmap/${id}`);
  const columns = [['0-30','0–30 يومًا'],['31-90','31–90 يومًا'],['3-6','3–6 أشهر']].map(([key,label]) => `<section class="roadmap-column"><h2>${label}</h2>${(data.roadmap[key] || []).map(item => `<article class="roadmap-item"><h3>${e(item.title)}</h3><p>${e(item.description)}</p><div class="roadmap-meta"><span>${e(item.owner || 'غير معيّن')}</span><span>${e(item.target_date || '--')}</span>${badge(item.status,item.status === 'COMPLETED' ? '' : 'neutral')}</div>${['COMPANY_ADMIN','SUPER_ADMIN'].includes(state.me.user.role) ? `<button class="secondary-button" data-action="edit-roadmap" data-assessment-id="${id}" data-id="${item.id}" data-owner="${e(item.owner || '')}" data-date="${e(item.target_date || '')}" data-status="${e(item.status)}" type="button">تحديث</button>` : ''}</article>`).join('') || '<p>لا توجد إجراءات في هذا الأفق.</p>'}</section>`).join('');
  const reportAction = canManageAssessments() ? `<button class="primary-button" data-action="generate-report" data-id="${id}" data-type="DETAILED">تقرير تفصيلي</button>` : '';
  appView.innerHTML = `<div class="page">${pageHeading(`التقييم #${id}`,t('خارطة التحسين'),'حوّل التشخيص إلى مالك وتاريخ وحالة ومؤشر قياس.',`<a class="secondary-button" href="#priorities/${id}">الأولويات</a>${reportAction}`)}<div class="roadmap-board">${columns}</div></div>`;
}

async function renderHistory() {
  loading(); const data = await api('/api/history?range=all');
  const trend = data.history.map(item => `<div class="trend-column"><i style="--score:${Number(item.mcm_total || 0)}"></i><span>${e(dateText(item.completed_at))}</span></div>`).join('');
  const rows = data.history.map(item => `<div class="data-table__row"><strong>#${item.id}<small>${e(item.assessment_type)}</small></strong><span>${dateText(item.completed_at)}</span><span>${e(item.instrument_version)}</span><span>${number(item.mcm_total,1)}</span><span>${e(item.maturity_level || '--')}</span><span>${number(item.smce_total,1)}</span><a href="#results/${item.id}">${t('فتح')}</a></div>`);
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · التاريخ',t('مسار النضج'),'كل نقطة مرتبطة بتاريخ تقييم فعلي وإصدار أداة محفوظ.')}<section class="card"><div class="trend-chart">${trend || '<p>لا توجد نقاط بعد.</p>'}</div></section><section class="panel">${rows.length ? table([t('التقييم'),t('التاريخ'),'الإصدار','MCM','المستوى','SMCE',''],rows,7,900) : emptyState('لا يوجد تاريخ بعد','أكمل تقييمين على الأقل لمقارنة المسار.')}</section></div>`;
}

async function renderBenchmark(route) {
  const id = Number(route.parts[1]) || await latestCompletedId(); if (!id) return navigate('assessments');
  loading(); const cohort = route.query.get('cohort') || 'overall'; const data = await api(`/api/benchmark/${id}?cohort=${encodeURIComponent(cohort)}`);
  const filters = `<div class="button-row"><a class="secondary-button" href="#benchmark/${id}?cohort=overall">الإجمالي</a><a class="secondary-button" href="#benchmark/${id}?cohort=sector">${t('القطاع')}</a><a class="secondary-button" href="#benchmark/${id}?cohort=size">الحجم</a></div>`;
  const content = data.available ? `<div class="card-grid"><article class="card metric-card span-4"><small>نتيجة المؤسسة</small><strong>${number(data.company_score,1)}</strong></article><article class="card metric-card span-4"><small>متوسط المجموعة</small><strong>${number(data.cohort_average,1)}</strong></article><article class="card metric-card span-4"><small>الربع الأعلى</small><strong>${number(data.top_quartile,1)}</strong></article></div><p>حجم العينة: ${number(data.sample_size)} · وحدة التحليل: آخر تقييم مكتمل لكل مؤسسة.</p>` : emptyState('لا تتوفر عينة كافية حاليًا لإظهار مقارنة موثوقة.', data.reason === 'NON_REAL_ASSESSMENT' ? 'التقييمات التجريبية لا تدخل في المقارنة الواقعية.' : `تُحجب المقارنة عندما تكون العينة أقل من ${number(data.minimum_sample)}، دون كشف حجم الخلية الدقيق.`);
  appView.innerHTML = `<div class="page">${pageHeading(`التقييم #${id}`,'المقارنة المرجعية','تطبيق صارم للموافقة، مصدر البيانات، الإصدار، والحد الأدنى للعينة.',filters)}${content}</div>`;
}

async function renderReports() {
  loading(); const data = await api('/api/reports'); const assessments = await api('/api/assessments');
  const completed = assessments.assessments.filter(item => item.status === 'COMPLETED');
  const form = completed.length && canManageAssessments() ? `<form id="report-form" class="filter-bar"><label class="field"><span>${t('التقييم')}</span><select name="assessment_id">${completed.map(item => `<option value="${item.id}">#${item.id} · ${dateText(item.completed_at)}</option>`).join('')}</select></label><label class="field"><span>نوع التقرير</span><select name="report_type"><option value="EXECUTIVE">تنفيذي</option><option value="DETAILED">تفصيلي</option></select></label><button class="primary-button">إنشاء PDF</button></form>` : '';
  const rows = data.reports.map(item => `<div class="data-table__row"><strong>#${item.id}<small>تقييم ${item.assessment_id}</small></strong><span>${e(item.report_type)}</span><span>${badge(item.status)}</span><span>${dateText(item.created_at)}</span><button class="secondary-button" data-action="download-report" data-id="${item.id}">تنزيل PDF</button></div>`);
  const reportEmpty = canManageAssessments() ? emptyState('لا يوجد تقييم مكتمل','أكمل تقييمًا قبل إنشاء التقرير.') : emptyState('عرض التقارير','يمكنك تنزيل التقارير المتاحة، وإنشاؤها مخصص لمدير الشركة أو الاستشاري.');
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · التقارير','التقارير التنفيذية','تقارير PDF حقيقية مرتبطة بنسخة التقييم والأداة.')}${modelNotice()}<section class="panel"><div class="card-title"><div><h2>تقرير جديد</h2><p>اختر تقييمًا مكتملًا.</p></div></div>${form || reportEmpty}</section><section class="panel">${rows.length ? table(['التقرير','النوع',t('الحالة'),'الإنشاء',''],rows,5,720) : emptyState('لا توجد تقارير','لم تُنشأ تقارير متاحة بعد.')}</section></div>`;
}

async function renderParticipants() {
  loading(); const [participants, assessments] = await Promise.all([api('/api/participants'), api('/api/assessments')]);
  const active = assessments.assessments.filter(item => ['DRAFT','IN_PROGRESS'].includes(item.status));
  const rows = participants.participants.map(item => `<div class="data-table__row"><strong>${e(item.full_name || 'مشارك مباشر')}<small dir="ltr">${e(item.research_id || '')}</small></strong><span>${item.assessment_id ? `#${number(item.assessment_id)}` : '--'}</span><span>${e(item.job_title || '--')}</span><span>${e(item.department || '--')}</span><span>${badge(item.assessment_status || item.participation_status, item.assessment_status === 'COMPLETED' ? '' : 'warning')}</span><span>${dateText(item.completed_at || item.created_at)}</span><span class="button-row">${item.assessment_status === 'COMPLETED' && item.assessment_id ? `<a class="secondary-button" href="#results/${item.assessment_id}">النتيجة</a>` : ''}</span></div>`);
  const startAction = `<a class="primary-button" href="#participant-start">ابدأ تقييمًا مباشرًا</a>`;
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · المشاركون',t('المشاركون'),'الدخول مباشر بلا دعوات وبلا حسابات؛ تظهر هنا الحالات التي بدأت فعلًا وحالة كل منها.', startAction)}<section class="panel"><div class="card-title"><div><h2>تقييمات نشطة</h2><p>${active.length ? `${number(active.length)} تقييم قيد التنفيذ في هذه المؤسسة.` : 'لا توجد تقييمات قيد التنفيذ حاليًا.'}</p></div></div>${rows.length ? table(['المشارك',t('التقييم'),'المسمى','القسم',t('الحالة'),t('التاريخ'),''],rows,7,940) : emptyState('لا يوجد مشاركون بعد','يبدأ المشارك المقياس مباشرة من الصفحة العامة دون دعوة أو حساب.',startAction)}</section></div>`;
}


async function renderParticipantAssessment(route) {
  state.me = state.token ? state.me : null; applyShell();
  const participantToken = sessionStorage.getItem('mcm_participant_token');
  if (!participantToken) return navigate('participant');
  await flushAnswers();
  loading(); const data = await api(`/api/participant/session/${encodeURIComponent(participantToken)}`);
  if (data.assessment.status === 'COMPLETED' || data.assessment.participant_status === 'COMPLETED') {
    if (data.result) renderPublicResult(data.result);
    else { sessionStorage.removeItem('mcm_participant_token'); appView.innerHTML = `<section class="route-state">${emptyState('شكرًا لمشاركتك','إجاباتك مرسلة ومقفلة، ولا يلزم إجراء إضافي.','<a class="primary-button" href="#landing">إنهاء</a>')}</section>`; }
    return;
  }
  state.assessment = {...data, participantToken}; state.pendingAnswers.clear();
  const visibleItems = data.items;
  const byConstruct = visibleItems.reduce((acc,item) => ((acc[item.construct] ||= []).push(item),acc),{});
  const constructTitles = {MCM:['النضج الاتصالي التسويقي MCM','قيّم مدى انطباق الممارسات المؤسسية خلال الاثني عشر شهرًا الماضية.'],SMCE:['كفاءة التواصل الاجتماعي SMCE','قيّم مدى انطباق نتائج الاتصال اليومية عبر الأبعاد الخمسة.'],ENABLER:['الممكنات التنظيمية','بنود تفصيلية للقيادة والكفاءات والتقنية والبيانات؛ تُحلل منفصلة عن درجة MCM.'],OUTCOME:['النتائج البعيدة الاختيارية','الثقة والرضا والعلامة وأثر الأعمال؛ وبعض البنود تقارن الأداء بالمنافسين.']};
  const sections = Object.entries(byConstruct).map(([construct,items]) => `<section class="assessment-section"><header><div><h2>${e(constructTitles[construct]?.[0] || construct)}</h2><p>${e(constructTitles[construct]?.[1] || '')}</p></div><span>${number(items.length)} عبارة</span></header><div class="panel">${items.map(item => questionCard(item,data.responses[item.id])).join('')}</div></section>`).join('');
  appView.innerHTML = `<div class="page assessment-page participant-measure">${pageHeading(`تقييم #${data.assessment.id}`,t('مقياس النضج الاتصالي التسويقي'),`أجب عن ${number(visibleItems.length)} عبارة وفق واقع المنشأة خلال الاثني عشر شهرًا الماضية. استخدم «لا ينطبق» أو «لا أعرف» فقط عند الحاجة.`)} ${modelNotice()}<section class="assessment-header"><div class="progress-row"><strong>${t('التقدم')} <span id="progress-value">${number(data.review.progress)}%</span></strong><span class="save-state" id="save-state">${t('محفوظ تلقائيًا')}</span></div><div class="progress-track"><span id="progress-bar" style="--progress:${data.review.progress}%"></span></div></section><form id="assessment-form">${sections}</form><section class="panel submit-panel"><p>راجع البنود المطلوبة قبل الإرسال. بعد الإرسال ستُقفل الإجابات وتظهر النتائج وخارطة التحسين.</p><button class="primary-button large" data-action="submit-participant" type="button">${t('إرسال التقييم وعرض النتائج')}</button></section></div>`;
}

async function renderNotifications() {
  loading(); const data = await api('/api/notifications');
  const cards = data.notifications.map(item => `<article class="card"><div class="card-title"><div>${badge(item.read_at ? 'مقروء' : 'جديد',item.read_at ? 'neutral':'')}<h3>${e(item.title)}</h3></div><small>${dateText(item.created_at)}</small></div><p>${e(item.body)}</p><div class="button-row">${item.target_url ? `<a class="secondary-button" href="${e(item.target_url)}">${t('فتح')}</a>` : ''}${!item.read_at ? `<button class="secondary-button" data-action="read-notification" data-id="${item.id}">تحديد كمقروء</button>` : ''}</div></article>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · التنبيهات',t('الإشعارات'),'أحداث التقييمات والدعوات وإصدارات الأداة.', '<button class="secondary-button" data-action="read-all-notifications">تحديد الكل كمقروء</button>')}<div class="card-grid">${cards || emptyState('لا توجد إشعارات','ستظهر الأحداث المرتبطة بمساحة العمل هنا.')}</div></div>`;
}

async function renderSettings() {
  loading(); const [settings, profile, team, consents] = await Promise.all([api('/api/settings'),api('/api/company/profile'),api('/api/company/team'),api('/api/consents')]);
  const researchConsent = Boolean(profile.profile?.research_consent);
  const personalResearch = consents.consents.find(item => item.consent_type === 'RESEARCH_USE');
  const companyContent = canManageCompany() ? `<form id="company-profile-form" class="form-grid"><label class="field full"><span>اسم المؤسسة</span><input name="name" value="${e(profile.organization.name)}" required></label><label class="field"><span>${t('القطاع')}</span><input name="sector" value="${e(profile.organization.sector)}"></label><label class="field"><span>الحجم</span><select name="size"><option value="">غير محدد</option>${['MICRO','SMALL','MEDIUM','LARGE'].map(value => `<option value="${value}" ${profile.organization.size === value ? 'selected':''}>${value}</option>`).join('')}</select></label><label class="field"><span>الموقع</span><input name="website" type="url" value="${e(profile.profile?.website)}"></label><label class="field"><span>${t('نموذج الأعمال')}</span><input name="business_model" value="${e(profile.profile?.business_model)}"></label><label class="field"><span>${t('عدد الموظفين')}</span><input name="employee_count" value="${e(profile.profile?.employee_count)}"></label><label class="field"><span>حجم فريق الاتصال</span><input name="communication_team_size" value="${e(profile.profile?.communication_team_size)}"></label><label class="field"><span>CRM</span><input name="crm_system" value="${e(profile.profile?.crm_system)}"></label><label class="field"><span>نظام التحليلات</span><input name="analytics_system" value="${e(profile.profile?.analytics_system)}"></label><label class="checkbox-field full"><input name="research_consent" type="checkbox" ${researchConsent ? 'checked':''}><span>موافقة المؤسسة على إدراج الحالات الواقعية المؤهلة بصورة مجهولة.</span></label><button class="primary-button full">حفظ ملف المؤسسة</button></form>` : `<div class="pill-list"><span>${e(profile.organization.name)}</span><span>${e(profile.organization.sector || 'قطاع غير محدد')}</span><span>${e(profile.organization.size || 'حجم غير محدد')}</span><span>موافقة المؤسسة البحثية: ${researchConsent ? 'مفعلة' : 'غير مفعلة'}</span></div><p>تعديل ملف المؤسسة وموافقتها مخصص لمدير الشركة.</p>`;
  appView.innerHTML = `<div class="page">${pageHeading('مساحة العمل · الإعدادات','الإعدادات والخصوصية','إدارة الحساب والمؤسسة والموافقات من مكان واحد.')}<div class="card-grid"><section class="card span-6"><div class="card-title"><div><h2>الملف الشخصي</h2><p>بيانات الحساب والواجهة العربية.</p></div></div><form id="settings-form" class="form-grid"><input type="hidden" name="locale" value="ar"><label class="field full"><span>الاسم</span><input name="name" value="${e(settings.user.name)}" required></label><label class="field"><span>المسمى</span><input name="job_title" value="${e(settings.user.job_title)}"></label><label class="field"><span>الجوال</span><input name="phone" value="${e(settings.user.phone)}"></label><label class="checkbox-field"><input name="email_notifications" type="checkbox" ${settings.settings?.email_notifications ? 'checked':''}><span>إشعارات البريد</span></label><button class="primary-button full">حفظ الحساب</button></form></section><section class="card span-6"><div class="card-title"><div><h2>ملف المؤسسة</h2><p>الاكتمال الحالي ${number(profile.profile?.completion)}%.</p></div></div>${companyContent}</section><section class="card span-12"><div class="card-title"><div><h2>الفريق والصلاحيات</h2><p>أعضاء المؤسسة الحاليون.</p></div></div><div class="pill-list">${team.members.map(item => `<span>${e(item.name)} · ${e(roleLabels[item.role] || item.role)} · ${e(item.status)}</span>`).join('')}</div></section><section class="card span-12"><h2>الموافقات المنفصلة</h2><p>موافقتك الشخصية على البحث مستقلة عن موافقة المؤسسة. لا تدخل الحالة الواقعية في البحث إلا باجتماع الموافقات المطلوبة.</p><form id="personal-consent-form" class="form-grid"><label class="checkbox-field full"><input name="accepted" type="checkbox" ${personalResearch?.accepted ? 'checked':''}><span>أوافق اختياريًا على استخدام إجاباتي المجهولة لأغراض البحث والمقارنة.</span></label><button class="secondary-button full">حفظ موافقتي البحثية</button></form><div class="pill-list">${consents.consents.map(item => `<span>${e(item.consent_type)} · ${item.accepted ? 'مقبولة':'مرفوضة'} · v${e(item.consent_version)}</span>`).join('')}</div></section></div></div>`;
}

async function renderMethodology() {
  const maturity = await loadMaturity();
  const model = modelInfo();
  const label = item => `${item.code} ${locale() === 'en' ? (item.name_en || item.name_ar) : item.name_ar}`;
  const mcm = (maturity.dimensions?.MCM || []).map(label);
  const smce = (maturity.dimensions?.SMCE || []).map(label);
  appView.innerHTML = `<div class="page">${pageHeading('المعرفة · المنهجية','كيف يعمل مقياس النضج الاتصالي التسويقي','فصل واضح بين السياق، القدرة المؤسسية، والكفاءة الاتصالية الناتجة.')}${modelNotice()}<div class="card-grid"><article class="card span-4"><span class="status-badge">1</span><h2>السياق والعوامل التمكينية</h2><p>دعم القيادة والكفاءات البشرية والبنية التقنية وجاهزية البيانات، إضافة إلى حجم المنشأة وعمرها وقطاعها وعدد المنصات. تفسر الظروف ولا تدخل في درجة MCM.</p></article><article class="card span-4"><span class="status-badge">2</span><h2>MCM · القدرة المؤسسية</h2><p>سبعة أبعاد تُطبّع بنودها إلى 0–100 ثم تجمع بأوزان إصدار الأداة.</p></article><article class="card span-4"><span class="status-badge">3</span><h2>SMCE · النتيجة الاتصالية</h2><p>خمسة أبعاد تُحتسب بصورة مستقلة لاختبار الأثر الإيجابي المقترح للنضج على الكفاءة.</p></article><article class="card span-6"><h2>${t('أبعاد MCM')}</h2><div class="pill-list">${mcm.map(item => `<span>${e(item)}</span>`).join('')}</div></article><article class="card span-6"><h2>${t('أبعاد SMCE')}</h2><div class="pill-list">${smce.map(item => `<span>${e(item)}</span>`).join('')}</div></article><article class="card span-12"><h2>${e(model.label_ar || '')}</h2>${((locale() === 'en' && model.methodology_en) ? model.methodology_en : (model.methodology_ar || [])).map(paragraph=>`<p>${e(paragraph)}</p>`).join('')}<p class="classification-boundary">${e(model.result_disclaimer_ar || '')}</p></article><article class="card span-12"><h2>المراحل الخمس</h2><ol class="landing-maturity methodology-stages">${stageCards(maturity.levels || [])}</ol></article><article class="card span-12"><h2>عقد علمي واضح</h2><ul><li>الإجابة المفقودة لا تتحول إلى صفر.</li><li>الاحتساب والتصنيف والتشخيص تجري على الخادم.</li><li>كل نتيجة ترتبط بإصدار أداة وإصدار احتساب.</li><li>العلاقة MCM ← SMCE مقترحة وليست ادعاءً سببيًا مثبتًا.</li><li>تخضع الأوزان وحدود المستويات ومكتبة التوصيات للمراجعة والتحسين المستمر مع تراكم البيانات.</li></ul></article></div></div>`;
}

async function renderResearch() {
  loading(); const data = await api('/api/research/summary');
  const sectorRows = data.cases_by_sector.map(item => `<div class="data-table__row"><strong>${e(item.label)}</strong><span>${number(item.count)}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading(t('البحث والتحليل'),t('لوحة الباحث'),'إحصاءات فعلية فقط، ولا تُعرض أرقام مصطنعة عند غياب الملاحظات.',`<a class="secondary-button" href="#dataset">مجموعة البيانات</a><a class="primary-button" href="#exports">${t('مركز التصدير')}</a>`)}${modelNotice()}<div class="card-grid"><article class="card metric-card span-3"><small>إجمالي الحالات</small><strong>${number(data.total_cases)}</strong></article><article class="card metric-card span-3"><small>مكتملة</small><strong>${number(data.completed)}</strong></article><article class="card metric-card span-3"><small>غير مكتملة</small><strong>${number(data.incomplete)}</strong></article><article class="card metric-card span-3"><small>موافقة بحثية</small><strong>${number(data.research_consent_organizations)}</strong></article><article class="card span-6"><h2>مصدر البيانات</h2><div class="pill-list">${Object.entries(data.origins).map(([key,value]) => `<span>${e(key)}: ${number(value)}</span>`).join('') || '<span>لا توجد بيانات</span>'}</div></article><article class="card span-6"><h2>إصدار الأداة الحالي</h2><p>${data.current_instrument ? `${e(data.current_instrument.version)} · ${e(data.current_instrument.status)}` : 'لا يوجد إصدار.'}</p><a href="#instruments">إدارة الإصدارات</a></article></div><section class="panel"><div class="card-title"><div><h2>الحالات حسب القطاع</h2><p>عد فعلي من قاعدة البيانات.</p></div></div>${sectorRows.length ? table([t('القطاع'),'الحالات'],sectorRows,2,420) : emptyState('لا توجد بيانات كافية حتى الآن.','تظهر التوزيعات بعد وصول حالات فعلية أو تجريبية وفق الفلتر.')}</section></div>`;
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
  const rows = data.versions.map(item => `<div class="data-table__row"><strong>${e(item.version)}<small>${e(item.name)}</small></strong><span>${badge(item.product_status, item.product_status === 'ACTIVE' ? '' : 'warning')}</span><span>${badge(item.scientific_status, item.scientific_status === 'EMPIRICALLY_VALIDATED' ? '' : 'warning')}</span><span>${number(item.item_count)}</span><span>${number(item.assessment_count)}</span><span class="button-row"><a class="secondary-button" href="#instrument/${item.id}">${t('فتح')}</a>${item.product_status === 'DRAFT' ? `<button class="primary-button" data-action="publish-instrument" data-id="${item.id}">تفعيل الإصدار</button>` : `<button class="secondary-button" data-action="duplicate-instrument" data-id="${item.id}">نسخ لمسودة</button>`}<button class="secondary-button" data-action="scientific-status" data-id="${item.id}" data-current="${e(item.scientific_status)}">الحالة العلمية</button></span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading('البحث · الأداة',t('إصدارات الأداة'),'النسخ المستخدمة غير قابلة للتعديل؛ أي تغيير يبدأ مسودة جديدة.')}<section class="panel"><div class="card-title"><div><h2>استيراد DOCX منظم</h2><p>الرفع والتحقق يجريان على الخادم بحد حجم ونوع ملف.</p></div><span class="status-badge warning">لا نشر تلقائي</span></div><form id="instrument-upload-form" class="form-grid"><label class="field full"><span>ملف DOCX</span><input id="instrument-file" name="instrument" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required><small>يجب أن يحتوي TABLE:DIMENSIONS وTABLE:ITEMS والجداول العلمية المرتبطة.</small></label><button class="primary-button full">رفع والتحقق</button></form><div id="instrument-preview"></div></section><section class="panel"><div class="card-title"><div><h2>حالتان منفصلتان</h2><p>حالة المنتج قرار تشغيلي. الحالة العلمية ادعاء استدلالي لا يتغير تلقائيًا، ويحتاج مبررًا مكتوبًا ويُسجَّل في التدقيق.</p></div></div>${rows.length ? table(['الإصدار','حالة المنتج','الحالة العلمية','البنود',t('التقييمات'),''],rows,6,940) : emptyState('لا توجد إصدارات','ارفع ملف الأداة المنظم لإنشاء مسودة.')}</section></div>`;
}

async function renderInstrument(route) {
  const id = Number(route.parts[1]); if (!id) return navigate('instruments');
  loading(); const [detail,items] = await Promise.all([api(`/api/instruments/${id}`),api(`/api/instruments/${id}/items`)]);
  const dimRows = detail.dimensions.map(item => `<div class="data-table__row"><strong>${e(item.code)}</strong><span>${e(item.construct)}</span><span>${e(item.name)}</span><span>${number(item.weight,2)}</span></div>`);
  const itemRows = items.items.slice(0,100).map(item => `<div class="data-table__row"><strong>${e(item.code)}<small>${e(item.dimension_code)}</small></strong><span>${e(item.construct)}</span><span>${e(item.prompt_ar)}</span><span>${item.required ? t('نعم'):t('لا')}</span><span>${item.reverse_coded ? t('نعم'):t('لا')}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading(`إصدار ${e(detail.version.version)}`,e(detail.version.name),`الحالة: ${e(detail.version.status)} · ${number(items.items.length)} بندًا.`,`<a class="secondary-button" href="#instruments">كل الإصدارات</a>`)}${modelNotice()}<section class="panel"><h2>الأبعاد</h2>${table(['الرمز','البناء','الاسم','الوزن'],dimRows,4,650)}</section><section class="panel"><h2>بنك البنود</h2>${table(['البند','البناء','الصياغة','مطلوب','عكسي'],itemRows,5,900)}</section></div>`;
}

async function renderDataQuality() {
  loading(); const data = await api('/api/research/data-quality');
  const rows = data.flags.map(item => `<div class="data-table__row"><strong>#${item.assessment_id}</strong><span>${e(item.flag_type)}</span><span>${badge(item.severity,item.severity === 'HIGH' ? 'danger':'warning')}</span><span>${e(item.details)}</span><span>${e(item.status)}</span></div>`);
  appView.innerHTML = `<div class="page">${pageHeading('البحث · الجودة',t('جودة البيانات'),'لا تُحذف الحالات آليًا؛ تظهر الإشارات للباحث للمراجعة.','<a class="secondary-button" href="#statistics">الإحصاءات الوصفية</a>')}<div class="card-grid"><article class="card metric-card span-4"><small>إشارات الجودة</small><strong>${number(data.flags.length)}</strong></article><article class="card metric-card span-4"><small>حالات غير مكتملة</small><strong>${number(data.incomplete_cases.length)}</strong></article><article class="card metric-card span-4"><small>حذف تلقائي</small><strong>${number(data.auto_deleted)}</strong></article></div><section class="panel">${rows.length ? table([t('التقييم'),'الإشارة','الخطورة','التفاصيل',t('الحالة')],rows,5,820) : emptyState('لا توجد إشارات جودة','لم يكتشف المحرك حالات تستدعي المراجعة.')}</section></div>`;
}

async function renderStatistics(route) {
  loading(); const origin = route.query.get('origin') || 'REAL'; const data = await api(`/api/research/statistics?data_origin=${encodeURIComponent(origin)}`);
  const metric = (title,value) => `<article class="card metric-card span-6"><small>${e(title)}</small><strong>${value === null || value === undefined ? '--' : number(value,2)}</strong></article>`;
  const section = (title,item) => item ? `<section class="card span-6"><h2>${e(title)}</h2><div class="card-grid">${metric('N',item.n)}${metric('المتوسط',item.mean)}${metric('الوسيط',item.median)}${metric('الانحراف المعياري',item.sd)}${metric('الأدنى',item.min)}${metric('الأعلى',item.max)}</div></section>` : `<section class="card span-6">${emptyState(`لا توجد بيانات ${title}`,'لا توجد ملاحظات كافية للفلتر المختار.')}</section>`;
  appView.innerHTML = `<div class="page">${pageHeading('البحث · الإحصاءات','الإحصاءات الوصفية',`مصدر البيانات: ${e(data.data_origin)}. لا تُعرض موثوقية أو صلاحية مصطنعة.`)}<div class="card-grid">${section('MCM',data.MCM)}${section('SMCE',data.SMCE)}<article class="card span-6"><h2>الموثوقية</h2>${badge('غير متاح','neutral')}<p>${e(data.reliability.reason)}</p></article><article class="card span-6"><h2>الصلاحية</h2>${badge('غير متاح','neutral')}<p>${e(data.validity.reason)}</p></article></div></div>`;
}

function renderExports() {
  appView.innerHTML = `<div class="page">${pageHeading('البحث · التصدير','Excel وSPSS جاهزان للتحليل','صف واحد لكل ملاحظة، أسماء متغيرات ASCII، قيم رقمية صحيحة، وترميزات وقاموس متغيرات منفصل—دون معرّفات شخصية مباشرة.')}<div class="card-grid"><section class="panel span-7"><form id="export-form" class="form-grid"><label class="field"><span>مصدر البيانات</span><select name="data_origin"><option value="REAL">واقعية بموافقة بحثية</option><option value="SYNTHETIC">اصطناعية فقط</option><option value="DEMO_TEST">Demo / Test</option><option value="ALL">كل المصادر - مراجعة خاصة</option></select></label><label class="field"><span>نوع التصدير</span><select name="format"><option value="XLSX">Excel متوافق مع SPSS</option><option value="SPSS">حزمة SPSS: XLSX + CSV + Syntax</option><option value="CSV">CSV UTF-8</option><option value="CODEBOOK">قاموس المتغيرات Excel</option><option value="INSTRUMENT">Instrument JSON</option></select></label><label class="checkbox-field full"><input type="checkbox" required><span>أفهم أن التصدير مسجّل في سجل التدقيق وأن البيانات الواقعية تتطلب موافقة بحثية.</span></label><button class="primary-button full">إنشاء وتنزيل الملف</button></form></section><aside class="card span-5 export-summary"><h2>تشمل المتغيرات</h2><ul><li>خصائص المنشأة: القطاع والحجم والعمر والمنطقة.</li><li>عدد المنصات ودور المجيب والممكنات الأربعة.</li><li>بنود ليكرت ودرجات الأبعاد MCM وSMCE.</li><li>المرحلة الخماسية وفارق الكفاءة عن النضج.</li></ul></aside></div><section class="card"><h2>محتويات مصنف Excel</h2><div class="pill-list">${['01_RESPONSES_WIDE','02_RESPONSES_LONG','03_MCM_SCORES','04_SMCE_SCORES','05_COMPANY_PROFILE','06_CODEBOOK','07_VARIABLE_LABELS','08_VALUE_LABELS','09_INSTRUMENT','10_METADATA'].map(item => `<span>${item}</span>`).join('')}</div></section></div>`;
}

const consultationTopicLabels = {
  STRATEGY_AND_GOVERNANCE:'الاستراتيجية والحوكمة', STAKEHOLDER_COMMUNICATION:'أصحاب المصلحة',
  INFORMATION_GOVERNANCE:'حوكمة المعلومات', CUSTOMER_JOURNEY:'رحلة العميل',
  PROMISE_EXPERIENCE_ALIGNMENT:'الوعد والتجربة', MEASUREMENT_AND_LEARNING:'القياس والتعلم',
  CAPABILITY_SUSTAINABILITY:'استدامة القدرات', FULL_90_DAY_PLAN:'خطة 90 يومًا', OTHER:'آخر',
};

function statCell(stats) {
  if (!stats || !stats.n) return '<span class="dashboard-empty">لا توجد بيانات</span>';
  return `<span class="stat-block"><b>${number(stats.mean,1)}</b><small>الوسيط ${number(stats.median,1)} · الانحراف ${stats.sd === null ? '—' : number(stats.sd,2)} · N=${number(stats.n)}</small></span>`;
}

function correlationCell(result) {
  if (!result || !result.available) {
    return `<span class="corr-cell muted">${e(result?.notice_ar || 'غير متاح')} (N=${number(result?.n || 0)})</span>`;
  }
  const r = Number(result.pearson_r);
  const strength = Math.abs(r) >= 0.5 ? 'strong' : Math.abs(r) >= 0.3 ? 'moderate' : 'weak';
  const ci = result.ci95 ? ` · 95% [${number(result.ci95[0],2)}, ${number(result.ci95[1],2)}]` : '';
  return `<span class="corr-cell ${strength}"><b dir="ltr">r = ${number(r,3)}</b><small dir="ltr">ρ = ${number(result.spearman_rho,3)}${ci} · N=${number(result.n)}</small></span>`;
}

// Scatter drawn as inline SVG: the content security policy allows no external
// script, so no chart library can be loaded here.
function scatterPlot(points, boundaries) {
  if (!points.length) return emptyState('لا توجد حالات مكتملة','تظهر الخريطة بعد اكتمال تقييمات تحمل درجتي MCM وSMCE.');
  const size = 460, pad = 46, span = size - pad * 2;
  const px = value => pad + (Number(value) / 100) * span;
  const py = value => size - pad - (Number(value) / 100) * span;
  const ticks = [0,25,50,75,100];
  const grid = ticks.map(t => `<line x1="${px(t)}" y1="${pad}" x2="${px(t)}" y2="${size-pad}"></line><line x1="${pad}" y1="${py(t)}" x2="${size-pad}" y2="${py(t)}"></line>`).join('');
  const labels = ticks.map(t => `<text class="axis" x="${px(t)}" y="${size-pad+16}" text-anchor="middle">${t}</text><text class="axis" x="${pad-8}" y="${py(t)+4}" text-anchor="end">${t}</text>`).join('');
  const median = (boundaries.mcm_boundary !== null && boundaries.smce_boundary !== null)
    ? `<line class="median" x1="${px(boundaries.mcm_boundary)}" y1="${pad}" x2="${px(boundaries.mcm_boundary)}" y2="${size-pad}"></line><line class="median" x1="${pad}" y1="${py(boundaries.smce_boundary)}" x2="${size-pad}" y2="${py(boundaries.smce_boundary)}"></line>` : '';
  const dots = points.map(point => `<circle cx="${px(point.mcm_total)}" cy="${py(point.smce_total)}" r="6"><title>${e(point.organization_name || `منشأة #${point.organization_id}`)} · MCM ${number(point.mcm_total,1)} · SMCE ${number(point.smce_total,1)}</title></circle>`).join('');
  const described = points.map(point => `${point.organization_name || `منشأة ${point.organization_id}`}: نضج ${number(point.mcm_total,1)}، كفاءة ${number(point.smce_total,1)}`).join('؛ ');
  return `<div class="scatter-wrap"><svg class="scatter" viewBox="0 0 ${size} ${size}" role="img" aria-label="${e(`خريطة النضج مقابل الكفاءة. ${described}`)}"><g class="scatter-grid">${grid}</g>${median}<g class="scatter-points">${dots}</g><g>${labels}</g><text class="axis-title" x="${size/2}" y="${size-6}" text-anchor="middle">MCM · النضج</text><text class="axis-title" transform="rotate(-90 14 ${size/2})" x="14" y="${size/2}" text-anchor="middle">SMCE · الكفاءة</text></svg></div>`;
}

async function renderAnalytics(route) {
  loading('جارٍ تحليل البيانات...');
  const params = new URLSearchParams();
  ['mode','data_origin','sector','firm_size','business_model','region'].forEach(key => {
    const value = route?.query?.get(key); if (value) params.set(key, value);
  });
  const data = await api(`/api/analytics${params.toString() ? `?${params}` : ''}`);
  const current = key => route?.query?.get(key) || '';

  const cards = [
    ['الحالات المحللة', number(data.n)],
    ['متوسط النضج MCM', data.summary.mcm.n ? number(data.summary.mcm.mean,1) : '--'],
    ['متوسط الكفاءة SMCE', data.summary.smce.n ? number(data.summary.smce.mean,1) : '--'],
    ['الحد الأدنى للمجموعة', number(data.minimum_group_size)],
  ].map(([label,value]) => `<article class="card metric-card span-3"><small>${e(label)}</small><strong>${value}</strong></article>`).join('');

  const stageRows = data.summary.stage_distribution.map(item =>
    `<div class="data-table__row"><strong>${e(item.label_ar)}</strong><span>${number(item.n)}</span><span>${data.n ? number(item.n / data.n * 100, 1) : '0'}%</span></div>`);

  const dimensionRows = data.dimensions.map(item =>
    `<div class="data-table__row"><strong>${e(item.code)}</strong><span>${number(item.mean,1)}</span><span>${number(item.median,1)}</span><span>${item.sd === null ? '—' : number(item.sd,2)}</span><span>${number(item.min,1)} – ${number(item.max,1)}</span><span>${number(item.n)}</span></div>`);

  const associationRows = data.associations.map(item =>
    `<div class="data-table__row"><strong>${e(item.label_ar)}<small>${e(item.variable)}</small></strong><span>${statCell(item.descriptives)}</span><span>${correlationCell(item.with_mcm)}</span><span>${correlationCell(item.with_smce)}</span></div>`);

  const groupSections = Object.entries(data.groups).map(([variable, block]) => {
    const rows = block.groups.map(group => group.suppressed
      ? `<div class="data-table__row"><strong>${e(group.value)}</strong><span>${number(group.n)}</span><span class="suppressed" colspan="2">محجوبة — العينة أقل من ${number(data.minimum_group_size)}</span><span></span></div>`
      : `<div class="data-table__row"><strong>${e(group.value)}</strong><span>${number(group.n)}</span><span>${statCell(group.mcm)}</span><span>${statCell(group.smce)}</span></div>`);
    return `<section class="panel"><div class="card-title"><div><h2>${e(block.label_ar)}</h2><p>وصف منفصل لكل من النضج والكفاءة داخل كل فئة.</p></div></div>${rows.length ? table(['الفئة',t('العدد'),'MCM','SMCE'],rows,4,760) : emptyState('لا توجد فئات','لم تصل بيانات كافية بعد.')}</section>`;
  }).join('');

  const q = data.quadrants;
  const quadrantCards = Object.entries(q.labels_ar).map(([key,label]) =>
    `<article class="card quadrant-card span-3"><small>${e(label)}</small><strong>${number(q.counts[key] || 0)}</strong><span>منشأة</span></article>`).join('');

  const versionWarning = data.version_warning_ar ? `<div class="research-notice"><strong>تنبيه إصدارات</strong><span>${e(data.version_warning_ar)}</span></div>` : '';

  appView.innerHTML = `<div class="page">${pageHeading('التحليل · مركز البيانات',t('مركز تحليل البيانات'),'إحصاءات وصفية وعلاقات بين المتغيرات، محسوبة على الخادم من الدرجات المخزّنة.')}
    ${versionWarning}
    <div class="research-notice"><strong>حدود القراءة</strong><span>${e(data.notice_ar)}</span></div>
    <section class="panel"><div class="card-title"><div><h2>نطاق التحليل</h2></div></div><form id="analytics-filters" class="form-grid">
      <label class="field"><span>وحدة التحليل</span><select name="mode"><option value="LATEST_PER_ORGANIZATION" ${current('mode') !== 'ALL_COMPLETED' ? 'selected':''}>آخر تقييم لكل منشأة</option><option value="ALL_COMPLETED" ${current('mode') === 'ALL_COMPLETED' ? 'selected':''}>كل التقييمات المكتملة</option></select></label>
      <label class="field"><span>مصدر البيانات</span><select name="data_origin">${['REAL','TEST','DEMO','ALL'].map(v=>`<option value="${v}" ${(current('data_origin') || 'REAL') === v ? 'selected':''}>${e(v === 'REAL' ? 'واقعي' : v === 'ALL' ? 'الكل' : v)}</option>`).join('')}</select></label>
      <label class="field"><span>${t('القطاع')}</span><input name="sector" value="${e(current('sector'))}" placeholder="كل القطاعات"></label>
      <label class="field"><span>${t('حجم المنشأة')}</span><select name="firm_size"><option value="">الكل</option>${['MICRO','SMALL','MEDIUM'].map(v=>`<option value="${v}" ${current('firm_size') === v ? 'selected':''}>${e({MICRO:'متناهية الصغر',SMALL:'صغيرة',MEDIUM:'متوسطة'}[v])}</option>`).join('')}</select></label>
      <div class="field full button-row"><button class="primary-button" type="submit">تطبيق</button><a class="secondary-button" href="#analytics">إعادة الضبط</a></div>
    </form></section>
    <div class="card-grid">${cards}</div>
    <section class="panel"><div class="card-title"><div><h2>خريطة النضج والكفاءة</h2><p>كل نقطة منشأة واحدة. الخطان المتقطعان وسيط العينة، وهما حدّ الأرباع لا عتبة معيارية.</p></div></div>${scatterPlot(data.scatter, q)}<div class="card-grid">${quadrantCards}</div></section>
    <section class="panel"><div class="card-title"><div><h2>العلاقة بين النضج والكفاءة</h2><p>${e(data.relationship.interpretation_ar)}</p></div></div><div class="correlation-headline">${correlationCell(data.relationship)}</div></section>
    <section class="panel"><div class="card-title"><div><h2>توزيع المراحل</h2></div></div>${stageRows.length ? table([t('المرحلة'),t('العدد'),t('النسبة')],stageRows,3,520) : emptyState('لا توجد حالات مصنفة','')}</section>
    <section class="panel"><div class="card-title"><div><h2>وصف الأبعاد</h2><p>الأبعاد السبعة للنضج والخمسة للكفاءة والممكنات والنتائج.</p></div></div>${dimensionRows.length ? table(['البعد','المتوسط','الوسيط','الانحراف','المدى','N'],dimensionRows,6,760) : emptyState('لا توجد درجات أبعاد','')}</section>
    <section class="panel"><div class="card-title"><div><h2>الارتباط بين المتغيرات</h2><p>يُعرض المعامل فقط عند بلوغ ${number(data.minimum_relationship_sample)} حالة. الارتباط وصفي ولا يثبت سببية.</p></div></div>${associationRows.length ? table(['المتغير','وصفه','مع MCM','مع SMCE'],associationRows,4,900) : emptyState('لا توجد متغيرات','')}</section>
    ${groupSections}
  </div>`;
}

async function renderConsultations(route) {
  loading('جارٍ تحميل طلبات الاستشارة...');
  const filters = new URLSearchParams();
  ['status','assigned_consultant_id','topic','created_from','created_to'].forEach(key => {
    const value = route?.query?.get(key); if (value) filters.set(key, value);
  });
  const suffix = filters.toString() ? `?${filters.toString()}` : '';
  const data = await api(`/api/admin/consultations${suffix}`);
  const cards = [
    ['طلبات جديدة', data.counts.NEW || 0],
    ['غير مسندة', data.unassigned || 0],
    ['تم التواصل', data.counts.CONTACTED || 0],
    ['جلسات مجدولة', data.counts.CONSULTATION_SCHEDULED || 0],
  ].map(([label, value]) => `<article class="card metric-card span-3"><small>${e(label)}</small><strong>${number(value)}</strong></article>`).join('');
  const isAdmin = data.scope === 'ALL';
  const rows = data.leads.map(lead => {
    const withheld = lead.contact_withheld_reason === 'CONTACT_CONSENT_WITHDRAWN';
    const contact = withheld
      ? '<span class="contact-withheld">سُحبت موافقة التواصل — البيانات محجوبة</span>'
      : `<a href="mailto:${e(lead.email || '')}">${e(lead.email || '--')}</a><small dir="ltr">${e(lead.phone_e164 || '')}</small>`;
    const actions = withheld ? '' : `<button class="secondary-button" data-action="consultation-status" data-id="${lead.id}" data-current="${e(lead.status)}">${t('الحالة')}</button><button class="secondary-button" data-action="consultation-note" data-id="${lead.id}">ملاحظة</button>${isAdmin ? `<button class="secondary-button" data-action="consultation-assign" data-id="${lead.id}" data-current="${lead.assigned_consultant_id || ''}">إسناد</button>` : ''}`;
    return `<div class="data-table__row">
      <strong>#${number(lead.id)}<small>${e(withheld ? '—' : (lead.full_name || ''))}</small></strong>
      <span>${e(lead.organization_display || '--')}</span>
      <span class="lead-contact">${contact}</span>
      <span>${lead.mcm_total === null || lead.mcm_total === undefined ? '--' : `${number(lead.mcm_total,1)}<small>${e(lead.maturity_label || '')}</small>`}</span>
      <span>${lead.smce_total === null || lead.smce_total === undefined ? '--' : number(lead.smce_total,1)}</span>
      <span>${(lead.consultation_topics || []).map(topic=>e(consultationTopicLabels[topic] || topic)).join('، ') || '--'}</span>
      <span>${badge(lead.status, lead.status === 'DO_NOT_CONTACT' ? 'danger' : lead.status === 'NEW' ? 'warning' : '')}</span>
      <span>${e(lead.consultant_name || 'غير مسند')}</span>
      <span>${dateText(lead.created_at)}</span>
      <span class="button-row"><a class="secondary-button" href="#results/${lead.assessment_id}">النتيجة</a>${actions}${isAdmin ? `<button class="danger-button" data-action="consultation-erase" data-id="${lead.id}">حذف البيانات</button>` : ''}</span>
    </div>`;
  });
  const current = key => route?.query?.get(key) || '';
  const filterBar = `<form id="consultation-filters" class="form-grid">
    <label class="field"><span>${t('الحالة')}</span><select name="status"><option value="">الكل</option>${data.statuses.map(value=>`<option value="${value}" ${current('status') === value ? 'selected':''}>${e(statusLabels[value] || value)}</option>`).join('')}</select></label>
    <label class="field"><span>المحور</span><select name="topic"><option value="">الكل</option>${(data.topics || []).map(value=>`<option value="${value}" ${current('topic') === value ? 'selected':''}>${e(consultationTopicLabels[value] || value)}</option>`).join('')}</select></label>
    ${isAdmin ? `<label class="field"><span>المستشار</span><select name="assigned_consultant_id"><option value="">الكل</option>${(data.consultants || []).map(item=>`<option value="${item.id}" ${current('assigned_consultant_id') === String(item.id) ? 'selected':''}>${e(item.name)}</option>`).join('')}</select></label>` : ''}
    <label class="field"><span>من تاريخ</span><input name="created_from" type="date" value="${e(current('created_from_date'))}"></label>
    <div class="field full button-row"><button class="primary-button" type="submit">تطبيق الفلاتر</button><a class="secondary-button" href="#consultations">مسح</a></div>
  </form>`;
  const scopeNotice = isAdmin ? '' : '<div class="research-notice"><strong>نطاقك</strong><span>تُعرض الطلبات المسندة إليك فقط.</span></div>';
  appView.innerHTML = `<div class="page">${pageHeading(isAdmin ? 'إدارة المنصة · الاستشارات' : 'مساحة العمل · الاستشارات',t('طلبات الاستشارة'),'بيانات التواصل تُعرض لمن يملك صلاحية معلنة فقط، وتُحجب فور سحب الموافقة، ولا تدخل في أي تصدير بحثي.')}${scopeNotice}<div class="card-grid">${cards}</div><section class="panel"><div class="card-title"><div><h2>تصفية</h2></div></div>${filterBar}</section><section class="panel">${rows.length ? table(['الطلب','المنشأة','التواصل','MCM','SMCE','المحاور',t('الحالة'),'المستشار',t('التاريخ'),''],rows,10,1520) : emptyState('لا توجد طلبات مطابقة','عدّل الفلاتر أو انتظر وصول طلب جديد من صفحة النتائج.')}</section></div>`;
}

async function renderAdmin() {
  loading(); const [overview,users,organizations] = await Promise.all([api('/api/admin'),api('/api/admin/users'),api('/api/admin/organizations')]);
  const roleOptions = ['COMPANY_RESPONDENT','COMPANY_ADMIN','CONSULTANT','RESEARCHER','SUPER_ADMIN'];
  // One row per account. The flat join used to render a row per membership,
  // which looked like several duplicate accounts sharing one email.
  const userRows = users.users.map(item => {
    const memberships = (item.memberships || []).map(membership => `<li>
      <b>${e(membership.organization_name || `#${membership.organization_id}`)}</b>
      <select data-action="membership-role" data-user="${item.id}" data-org="${membership.organization_id}" data-previous-role="${e(membership.role || '')}" aria-label="دور ${e(item.name)} في ${e(membership.organization_name || '')}">
        ${roleOptions.map(value=>`<option value="${value}" ${membership.role === value ? 'selected':''}>${e(roleLabels[value] || value)}</option>`).join('')}
      </select>
      <button class="danger-button" data-action="remove-membership" data-user="${item.id}" data-org="${membership.organization_id}" data-name="${e(item.name || '')}" data-org-name="${e(membership.organization_name || '')}" type="button">إزالة من المؤسسة</button>
    </li>`).join('') || '<li class="dashboard-empty">لا توجد عضويات.</li>';
    return `<div class="data-table__row user-row">
      <strong>${e(item.name)}<small>${e(item.email)}</small></strong>
      <span>${badge(item.is_active ? 'نشط':'معطل', item.is_active ? '':'danger')}</span>
      <span>${number((item.memberships || []).length)} عضوية</span>
      <span class="membership-list"><ul>${memberships}</ul></span>
      <span class="button-row">
        <button class="secondary-button" data-action="toggle-user" data-id="${item.id}" data-active="${item.is_active ? '1':'0'}">${item.is_active ? 'تعطيل':'تفعيل'}</button>
        <button class="danger-button" data-action="delete-user" data-id="${item.id}" data-name="${e(item.name || '')}" data-email="${e(item.email || '')}">حذف الحساب</button>
      </span>
    </div>`;
  });
  const options = organizations.organizations.map(item => `<option value="${item.id}">${e(item.name)}</option>`).join('');
  appView.innerHTML = `<div class="page">${pageHeading(t('إدارة المنصة'),'لوحة المدير العام','إدارة المستخدمين والمنظمات والإعدادات التشغيلية.')}<div class="card-grid"><article class="card metric-card span-3"><small>المؤسسات</small><strong>${number(overview.organizations)}</strong></article><article class="card metric-card span-3"><small>المستخدمون</small><strong>${number(overview.users)}</strong></article><article class="card metric-card span-3"><small>${t('التقييمات')}</small><strong>${number(overview.assessments)}</strong></article><article class="card metric-card span-3"><small>الجلسات النشطة</small><strong>${number(overview.active_sessions)}</strong></article><section class="card span-12"><div class="card-title"><div><h2>إنشاء مستخدم</h2><p>تعيين مؤسسة ودور واضحين.</p></div></div><form id="admin-user-form" class="form-grid"><label class="field"><span>الاسم</span><input name="name" required></label><label class="field"><span>البريد</span><input name="email" type="email" required></label><label class="field"><span>${t('كلمة المرور')}</span><input name="password" type="password" minlength="10" required></label><label class="field"><span>${t('المؤسسة')}</span><select name="organization_id">${options}</select></label><label class="field full"><span>${t('الدور')}</span><select name="role"><option value="COMPANY_RESPONDENT">مشارك شركة</option><option value="COMPANY_ADMIN">مدير شركة</option><option value="CONSULTANT">استشاري</option><option value="RESEARCHER">باحث</option><option value="SUPER_ADMIN">مدير المنصة</option></select></label><button class="primary-button full">إنشاء المستخدم</button></form></section></div><section class="panel"><div class="card-title"><div><h2>الحسابات والعضويات</h2><p>الحساب واحد وقد ينتمي لعدة مؤسسات. إزالة العضوية تُلغي وصوله لتلك المؤسسة وحدها؛ حذف الحساب يُلغيه بالكامل ولا يمس تقييمات المؤسسات.</p></div></div>${table([t('المستخدم'),t('الحالة'),'العضويات','المؤسسات والأدوار',''],userRows,5,1080)}</section><section class="card"><h2>إعدادات النظام</h2><div class="pill-list">${Object.entries(overview.configuration).map(([key,value]) => `<span>${e(key)}: ${e(typeof value === 'object' ? JSON.stringify(value) : value)}</span>`).join('')}</div></section></div>`;
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
    const first = document.querySelector(`[data-question="${review.missing_required[0]?.item_id}"]`); scrollElementIntoView(first, 'center');
    return;
  }
  openDialog(`<h2 id="dialog-title">${t('تأكيد إرسال التقييم')}</h2><p>بعد الإرسال تُقفل الإجابات وتُحسب النتائج على الخادم. لا يمكن التراجع عن هذه الخطوة.</p><div class="button-row"><button class="primary-button" data-action="confirm-submit" data-id="${id}" data-participant="${participant ? '1':'0'}">${t('تأكيد الإرسال')}</button><button class="secondary-button" data-action="close-dialog">${t('العودة للمراجعة')}</button></div>`);
}

async function fileAsBase64(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer); let binary = '';
  const chunk = 0x8000;
  for (let index=0; index<bytes.length; index+=chunk) binary += String.fromCharCode(...bytes.subarray(index,index+chunk));
  return btoa(binary);
}

document.addEventListener('change', async event => {
  if (event.target.matches('#assessment-form input[type="radio"][data-answer-input]')) queueAnswer(event.target.dataset.itemId,Number(event.target.value));
  if (event.target.matches('#assessment-form input[type="number"][data-answer-input]')) queueAnswer(event.target.dataset.itemId,event.target.value === '' ? null : Number(event.target.value),event.target.value === '' ? 'NOT_ANSWERED' : null);
  if (event.target.matches('select[data-action="membership-role"]')) {
    const select = event.target;
    const previous = select.dataset.previousRole || '';
    select.disabled = true;
    try {
      await api(`/api/admin/users/${select.dataset.user}/memberships/${select.dataset.org}`,{method:'PATCH',body:JSON.stringify({role:select.value})});
      select.dataset.previousRole = select.value;
      showToast('حُدّث الدور في هذه المؤسسة.');
    } catch (error) {
      // Put the control back where it was, so the screen never shows a role
      // the server refused to store.
      if (previous) select.value = previous;
      showToast(apiMessage(error),'error');
    }
    select.disabled = false;
  }
});
document.addEventListener('input', event => {
  if (event.target.matches('#assessment-form textarea[data-answer-input]')) queueAnswer(event.target.dataset.itemId,event.target.value || null,event.target.value ? null : 'NOT_ANSWERED');
});

document.querySelector('#lang-toggle')?.addEventListener('click', () => {
  // Cached payloads carry server-side wording, so drop them on a switch.
  setLocale(locale() === 'en' ? 'ar' : 'en');
  state.maturity = null; state.privacyNotice = null;
  applyShell(); router();
});

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const action = button.dataset.action;
  try {
    if (action === 'auth-mode') { state.authMode = button.dataset.mode; renderAuth(); }
    else if (action === 'scroll-model') scrollElementIntoView(document.querySelector('#methodology-public'));
    else if (action === 'scroll-maturity') scrollElementIntoView(document.querySelector('#maturity-public'));
    else if (action === 'stage-detail') stageDetailDialog(button.dataset.code);
    else if (action === 'consultation-open') await consultationForm(button.dataset.assessment);
    else if (action === 'consultation-dismiss') {
      // Declining is a UI-only choice. Nothing is sent, nothing is stored, and
      // the result stays exactly as it was.
      const section = document.querySelector('#consultation-cta');
      if (section) section.innerHTML = '<p class="consultation-note">يمكنك طلب الاستشارة لاحقًا من هذه الصفحة.</p>';
    }
    else if (action === 'scientific-status') {
      const options = ['EVIDENCE_INFORMED','EXPERT_REVIEWED','EMPIRICALLY_VALIDATED','ARCHIVED'];
      openDialog(`<h2 id="dialog-title">تغيير الحالة العلمية</h2><p class="classification-boundary">هذا ادعاء استدلالي عن الإصدار، ومستقل عن حالة المنتج. لا يُرفع تلقائيًا، ويُسجَّل كل تغيير في سجل التدقيق باسمك.</p><form id="scientific-status-form" class="form-grid"><input type="hidden" name="version_id" value="${e(button.dataset.id)}"><label class="field full"><span>الحالة العلمية</span><select name="scientific_status" required>${options.map(value=>`<option value="${value}" ${button.dataset.current === value ? 'selected':''}>${e(statusLabels[value] || value)}</option>`).join('')}</select></label><label class="field full"><span>المبرر (إلزامي)</span><textarea name="rationale" rows="3" required minlength="10" placeholder="ما الدليل الذي يسند هذه الحالة؟"></textarea></label><button class="primary-button full" type="submit">حفظ الحالة العلمية</button></form>`);
    }
    else if (action === 'print-result') window.print();
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
        const result = await api(`/api/participant/session/${encodeURIComponent(state.assessment.participantToken)}/submit`,{method:'POST',body:'{}'});
        const directEntry = Boolean(state.assessment.context); closeDialog();
        if (directEntry && result.assessment_complete) renderPublicResult(result);
        else { sessionStorage.removeItem('mcm_participant_token'); appView.innerHTML = `<section class="route-state">${emptyState('شكرًا لمشاركتك','تم إرسال التقييم وقفل إجاباتك بنجاح.','<a class="primary-button" href="#landing">إنهاء</a>')}</section>`; }
      } else {
        const id = Number(button.dataset.id); const result = await api(`/api/assessments/${id}/submit`,{method:'POST',body:'{}'}); closeDialog();
        if (result.assessment_complete) navigate(`results/${id}`); else { showToast(result.message || 'تم إرسال إجاباتك، وبانتظار بقية المشاركين.'); navigate('assessments'); }
      }
    }
    else if (action === 'generate-ai-plan') {
      button.disabled = true; button.textContent = 'جارٍ تحليل الخطة...';
      const result = await api(`/api/assessments/${Number(button.dataset.id)}/ai-plan`,{method:'POST',body:'{}'});
      const plan = result.plan || {}; const generation = plan.generation || {};
      const modeLabel = generation.mode === 'ai_enhanced' ? `خطة مدعومة بالذكاء الاصطناعي · ${generation.provider}` : 'خطة تحليلية محلية آمنة';
      const phaseLabels = {days_30:'أول 30 يومًا',days_90:'من 31 إلى 90 يومًا',days_180:'من 3 إلى 6 أشهر'};
      const roadmap = Object.entries(phaseLabels).map(([key,label])=>`<section class="ai-plan-phase"><h3>${e(label)}</h3>${(plan.roadmap?.[key] || []).map(item=>`<article><b>${e(item.title_ar)}</b><p>${e(item.action_ar)}</p><small>${e(item.owner_ar)} · KPI: ${e(item.kpi_ar)}</small></article>`).join('')}</section>`).join('');
      openDialog(`<div class="ai-plan-dialog"><span class="status-badge">${e(modeLabel)}</span><h2 id="dialog-title">خطة التحسين المقترحة</h2><p>${e(plan.summary_ar)}</p><div class="ai-plan-priorities">${(plan.priorities || []).map(item=>`<span><b>${e(item.dimension_code)}</b>${e(item.name_ar)} · ${number(item.score,1)}/100</span>`).join('')}</div>${roadmap}<p class="classification-boundary">${e(plan.safeguards?.notice_ar || 'تحتاج الخطة مراجعة واعتمادًا بشريًا قبل التنفيذ.')}</p><button class="secondary-button" data-action="close-dialog">${t('إغلاق')}</button></div>`);
      button.disabled = false; button.textContent = '6. تحليل خطة التحسين';
    }
    else if (action === 'generate-report') {
      button.disabled = true; const report = await api('/api/reports',{method:'POST',body:JSON.stringify({assessment_id:Number(button.dataset.id),report_type:button.dataset.type || 'EXECUTIVE'})});
      await downloadApi(report.download_url); button.disabled = false; showToast('تم إنشاء التقرير وتنزيله.');
    }
    else if (action === 'download-report') await downloadApi(`/api/reports/${button.dataset.id}/download`);
    else if (action === 'edit-roadmap') {
      openDialog(`<h2 id="dialog-title">تحديث إجراء الخارطة</h2><form id="roadmap-form" class="form-grid"><input type="hidden" name="assessment_id" value="${e(button.dataset.assessmentId)}"><input type="hidden" name="item_id" value="${e(button.dataset.id)}"><label class="field full"><span>${t('المالك')}</span><input name="owner" value="${e(button.dataset.owner)}"></label><label class="field"><span>التاريخ المستهدف</span><input name="target_date" type="date" value="${e(button.dataset.date)}"></label><label class="field"><span>${t('الحالة')}</span><select name="status">${['NOT_STARTED','IN_PROGRESS','COMPLETED','DEFERRED'].map(value => `<option value="${value}" ${button.dataset.status === value ? 'selected':''}>${statusLabels[value] || value}</option>`).join('')}</select></label><button class="primary-button full">${t('حفظ')}</button></form>`);
    }
    else if (action === 'read-notification') { await api('/api/notifications/read',{method:'PATCH',body:JSON.stringify({notification_id:Number(button.dataset.id)})}); router(); }
    else if (action === 'read-all-notifications') { await api('/api/notifications/read',{method:'PATCH',body:'{}'}); state.me = await api('/api/me'); applyShell(); router(); }
    else if (action === 'publish-instrument') { await api(`/api/instrument-versions/${button.dataset.id}/approve`,{method:'POST',body:'{}'}); showToast('نُشر الإصدار بصفة PILOT.'); router(); }
    else if (action === 'duplicate-instrument') { const result = await api(`/api/instrument-versions/${button.dataset.id}/duplicate`,{method:'POST',body:'{}'}); showToast(`أُنشئت المسودة ${result.version}.`); router(); }
    else if (action === 'import-instrument') {
      button.disabled = true; const result = await api('/api/instrument-versions/import',{method:'POST',body:JSON.stringify(state.importPayload)}); showToast(`أُنشئت المسودة ${result.version}.`); navigate(`instrument/${result.id}`);
    }
    else if (action === 'toggle-user') { await api(`/api/admin/users/${button.dataset.id}`,{method:'PATCH',body:JSON.stringify({is_active:button.dataset.active !== '1'})}); router(); }
    else if (action === 'delete-assessment') {
      // Irreversible and destroys scientific data, so it is confirmed by name
      // rather than by a single click.
      openDialog(`<h2 id="dialog-title">حذف التقييم #${e(button.dataset.id)}</h2><p class="classification-boundary">سيُحذف التقييم وكل إجاباته ودرجاته وتشخيصاته وخارطته وتقاريره نهائيًا. لا يمكن التراجع، وسيتأثر أي تحليل بحثي يعتمد على هذه الحالة.</p><div class="button-row"><button class="danger-button" data-action="confirm-delete-assessment" data-id="${e(button.dataset.id)}" type="button">تأكيد الحذف النهائي</button><button class="secondary-button" data-action="close-dialog">${t('إلغاء')}</button></div>`);
    }
    else if (action === 'confirm-delete-assessment') {
      button.disabled = true;
      const result = await api(`/api/assessments/${button.dataset.id}`,{method:'DELETE'});
      closeDialog(); showToast(`حُذف التقييم #${result.assessment_id} وسُجّل في التدقيق.`); router();
    }
    else if (action === 'share-join-code') {
      const result = await api(`/api/assessments/${button.dataset.id}/join-code`,{method:'POST',body:'{}'});
      const code = result.join_code.code;
      const url = new URL(`#join?code=${encodeURIComponent(code)}`, location.href).href;
      openDialog(`<h2 id="dialog-title">كود مشاركة الزملاء</h2><p>شارك هذا الكود مع زملائك في المنشأة ليجيبوا على نفس التقييم. تُجمع إجاباتهم في تقييم واحد ولا يلزمهم حساب.</p><div class="join-code-display" dir="ltr">${e(code)}</div><label class="field full"><span>أو شارك الرابط</span><input id="join-url" dir="ltr" value="${e(url)}" readonly></label><p class="consultation-note">صالح حتى ${e(dateText(result.join_code.expires_at))} · حد الاستخدام ${number(result.join_code.max_uses)} · استُخدم ${number(result.join_code.use_count)}</p><div class="button-row"><button class="primary-button" type="button" data-action="copy-join-url">نسخ الرابط</button><button class="secondary-button" data-action="close-dialog">${t('إغلاق')}</button></div>`);
    }
    else if (action === 'copy-join-url') { await navigator.clipboard.writeText(document.querySelector('#join-url').value); showToast('تم نسخ الرابط.'); }
    else if (action === 'consultation-status') {
      const statuses = ['NEW','ASSIGNED','CONTACTED','QUALIFIED','CONSULTATION_SCHEDULED','CONVERTED','CLOSED','DO_NOT_CONTACT'];
      openDialog(`<h2 id="dialog-title">تحديث حالة الطلب #${e(button.dataset.id)}</h2><form id="consultation-status-form" class="form-grid"><input type="hidden" name="lead_id" value="${e(button.dataset.id)}"><label class="field full"><span>${t('الحالة')}</span><select name="status" required>${statuses.map(value=>`<option value="${value}" ${button.dataset.current === value ? 'selected':''}>${e(statusLabels[value] || value)}</option>`).join('')}</select></label><label class="field full"><span>ملاحظة داخلية</span><textarea name="note" rows="2" maxlength="2000"></textarea></label><label class="field full"><span>سبب الإغلاق (عند الإغلاق أو الإيقاف)</span><input name="closure_reason" maxlength="400"></label><div class="form-error full" hidden></div><button class="primary-button full" type="submit">حفظ الحالة</button></form>`);
    }
    else if (action === 'consultation-note') {
      openDialog(`<h2 id="dialog-title">ملاحظة داخلية على الطلب #${e(button.dataset.id)}</h2><p>تُسجَّل الملاحظة في سجل الطلب باسمك ولا تظهر للمشارك.</p><form id="consultation-note-form" class="form-grid"><input type="hidden" name="lead_id" value="${e(button.dataset.id)}"><label class="field full"><span>الملاحظة</span><textarea name="note" rows="3" required maxlength="2000"></textarea></label><div class="form-error full" hidden></div><button class="primary-button full" type="submit">إضافة</button></form>`);
    }
    else if (action === 'consultation-assign') {
      const board = await api('/api/admin/consultations');
      openDialog(`<h2 id="dialog-title">إسناد الطلب #${e(button.dataset.id)}</h2><form id="consultation-assign-form" class="form-grid"><input type="hidden" name="lead_id" value="${e(button.dataset.id)}"><label class="field full"><span>المستشار</span><select name="consultant_id" required>${(board.consultants || []).map(item=>`<option value="${item.id}" ${String(button.dataset.current) === String(item.id) ? 'selected':''}>${e(item.name)}</option>`).join('')}</select></label><label class="field full"><span>ملاحظة</span><input name="note" maxlength="400"></label><div class="form-error full" hidden></div><button class="primary-button full" type="submit">إسناد</button></form>`);
    }
    else if (action === 'consultation-erase') {
      openDialog(`<h2 id="dialog-title">حذف بيانات التواصل</h2><p class="classification-boundary">يُنفَّذ طلب الحذف: تُمحى بيانات التواصل نهائيًا ويبقى سجل الطلب لأغراض التدقيق دون البيانات الشخصية. لا يمكن التراجع.</p><div class="button-row"><button class="danger-button" data-action="confirm-consultation-erase" data-id="${e(button.dataset.id)}" type="button">تأكيد الحذف</button><button class="secondary-button" data-action="close-dialog">${t('إلغاء')}</button></div>`);
    }
    else if (action === 'confirm-consultation-erase') {
      button.disabled = true;
      await api(`/api/admin/consultations/${button.dataset.id}`,{method:'DELETE'});
      closeDialog(); showToast('مُحيت بيانات التواصل وسُجّل الإجراء.'); router();
    }
    else if (action === 'remove-membership') {
      openDialog(`<h2 id="dialog-title">إزالة عضوية</h2><p>${e(button.dataset.name || '')} من <b>${e(button.dataset.orgName || '')}</b></p><p class="classification-boundary">يفقد الحساب وصوله إلى هذه المؤسسة فقط. الحساب وعضوياته الأخرى وتقييمات المؤسسة تبقى كما هي.</p><div class="button-row"><button class="danger-button" data-action="confirm-remove-membership" data-user="${e(button.dataset.user)}" data-org="${e(button.dataset.org)}" type="button">تأكيد الإزالة</button><button class="secondary-button" data-action="close-dialog">${t('إلغاء')}</button></div>`);
    }
    else if (action === 'confirm-remove-membership') {
      button.disabled = true;
      await api(`/api/admin/users/${button.dataset.user}/memberships/${button.dataset.org}`,{method:'DELETE'});
      closeDialog(); showToast('أُزيلت العضوية وسُجّلت في التدقيق.'); router();
    }
    else if (action === 'delete-user') {
      openDialog(`<h2 id="dialog-title">حذف المستخدم</h2><p>${e(button.dataset.name || '')} · ${e(button.dataset.email || '')}</p><p class="classification-boundary">سيُحذف الحساب وعضوياته وجلساته وإشعاراته. لن تُحذف تقييمات المؤسسة ولا إجاباتها، لأنها بيانات المنشأة لا بيانات الشخص.</p><div class="button-row"><button class="danger-button" data-action="confirm-delete-user" data-id="${e(button.dataset.id)}" type="button">تأكيد الحذف</button><button class="secondary-button" data-action="close-dialog">${t('إلغاء')}</button></div>`);
    }
    else if (action === 'confirm-delete-user') {
      button.disabled = true;
      await api(`/api/admin/users/${button.dataset.id}`,{method:'DELETE'});
      closeDialog(); showToast('حُذف المستخدم وسُجّل في التدقيق.'); router();
    }
    else if (action === 'logout') { await flushAnswers(); await api('/api/auth/logout',{method:'POST',body:'{}'}).catch(()=>{}); state.token='';state.me=null;localStorage.removeItem('mcm_token');closeDialog();navigate('login'); }
    else if (action === 'switch-org') { await api('/api/session/organization',{method:'POST',body:JSON.stringify({organization_id:Number(button.dataset.id)})}); state.me=await api('/api/me');applyShell();closeDialog();navigate('overview'); }
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
    else if (form.classList.contains('knowledge-form')) {
      const code = form.dataset.knowledgeCode;
      await api(`/api/research/knowledge/${encodeURIComponent(code)}`,{method:'PATCH',body:JSON.stringify(data)});
      showToast(`حُفظ محتوى ${code}.`); router();
    }
    else if (form.id === 'join-code-form') {
      const errorBox = form.querySelector('.form-error'); errorBox.hidden = true;
      try {
        const result = await api('/api/participant/join',{method:'POST',body:JSON.stringify({
          code:data.code, full_name:data.full_name, job_title:data.job_title || undefined,
          service_consent:Boolean(data.service_consent),
        })});
        sessionStorage.setItem('mcm_participant_token', result.token);
        showToast('انضممت إلى التقييم. ابدأ الإجابة.');
        navigate('participant-assessment');
      } catch (error) { errorBox.textContent = apiMessage(error); errorBox.hidden = false; }
    }
    else if (form.id === 'participant-signup-form') {
      const errorBox = form.querySelector('.form-error'); errorBox.hidden = true;
      try {
        const result = await api('/api/participant/account',{method:'POST',body:JSON.stringify({
          full_name:data.full_name, email:data.email, password:data.password,
          organization_name:data.organization_name || undefined,
          participant_token:sessionStorage.getItem('mcm_participant_token') || undefined,
        })});
        state.token = result.token; localStorage.setItem('mcm_token', result.token);
        state.me = null; state.publicPage = false;
        showToast('أُنشئ حسابك. نتيجتك محفوظة الآن.');
        navigate(result.claimed_assessment_id ? `results/${result.claimed_assessment_id}` : 'overview');
      } catch (error) { errorBox.textContent = apiMessage(error); errorBox.hidden = false; }
    }
    else if (form.id === 'withdraw-consent-form') {
      const errorBox = form.querySelector('.form-error');
      const participantToken = sessionStorage.getItem('mcm_participant_token') || '';
      errorBox.hidden = true;
      try {
        const result = await api(`/api/consultations/${Number(data.lead_id)}/consent`,{method:'POST',body:JSON.stringify({participant_token:participantToken || undefined})});
        showToast(result.message_ar || 'سُحبت موافقة التواصل.');
        form.reset();
      } catch (error) {
        errorBox.textContent = apiMessage(error); errorBox.hidden = false;
      }
    }
    else if (form.id === 'analytics-filters') {
      const params = new URLSearchParams();
      Object.entries(data).forEach(([key, value]) => { if (value) params.set(key, value); });
      navigate(`analytics?${params.toString()}`);
    }
    else if (form.id === 'consultation-filters') {
      const params = new URLSearchParams();
      Object.entries(data).forEach(([key, value]) => {
        if (!value) return;
        // Date inputs arrive as YYYY-MM-DD; the API filters on epoch seconds.
        if (key === 'created_from') params.set(key, String(Math.floor(new Date(`${value}T00:00:00`).getTime() / 1000)));
        else params.set(key, value);
      });
      navigate(`consultations?${params.toString()}`);
    }
    else if (form.id === 'consultation-status-form') {
      await api(`/api/admin/consultations/${Number(data.lead_id)}/status`,{method:'POST',body:JSON.stringify({status:data.status,note:data.note || undefined,closure_reason:data.closure_reason || undefined})});
      closeDialog(); showToast('حُدّثت حالة الطلب.'); router();
    }
    else if (form.id === 'consultation-note-form') {
      await api(`/api/admin/consultations/${Number(data.lead_id)}/notes`,{method:'POST',body:JSON.stringify({note:data.note})});
      closeDialog(); showToast('أُضيفت الملاحظة إلى سجل الطلب.'); router();
    }
    else if (form.id === 'consultation-assign-form') {
      await api(`/api/admin/consultations/${Number(data.lead_id)}/assign`,{method:'POST',body:JSON.stringify({consultant_id:Number(data.consultant_id),note:data.note || undefined})});
      closeDialog(); showToast('أُسند الطلب وأُشعر المستشار.'); router();
    }
    else if (form.id === 'consultation-form') {
      const submit = form.querySelector('button[type="submit"]');
      const errorBox = form.querySelector('.form-error');
      const topics = [...form.querySelectorAll('input[name="consultation_topics"]:checked')].map(input=>input.value);
      const participantToken = sessionStorage.getItem('mcm_participant_token') || '';
      // One key per form instance, so a double click or a retried request
      // cannot create a second lead for the same person.
      form.dataset.idempotencyKey = form.dataset.idempotencyKey || `${data.assessment_id}-${Date.now()}-${Math.random().toString(36).slice(2,10)}`;
      submit.disabled = true; errorBox.hidden = true;
      try {
        const response = await api('/api/consultations',{method:'POST',body:JSON.stringify({
          assessment_id:Number(data.assessment_id),
          participant_token:participantToken || undefined,
          full_name:data.full_name, email:data.email, phone_number:data.phone_number,
          organization_name:data.organization_name || undefined,
          job_title:data.job_title || undefined,
          preferred_contact_method:data.preferred_contact_method || undefined,
          preferred_contact_time:data.preferred_contact_time || undefined,
          consultation_topics:topics,
          notes:data.notes || undefined,
          consent_to_contact:Boolean(data.consent_to_contact),
          marketing_consent:Boolean(data.marketing_consent),
          idempotency_key:form.dataset.idempotencyKey,
        })});
        const lead = response.lead;
        openDialog(`<div class="consultation-success"><span class="status-badge">${t('تم الاستلام')}</span><h2 id="dialog-title">${response.duplicate ? 'طلبك مسجّل بالفعل' : 'تم استلام طلب الاستشارة'}</h2><p>${e(response.confirmation_ar || 'تم استلام طلب الاستشارة، وسيتواصل معك الفريق وفق وسيلة التواصل التي اخترتها.')}</p><div class="pill-list"><span>رقم الطلب: ${number(lead.id)}</span><span>الحالة: ${e(statusLabels[lead.status] || lead.status)}</span></div><p class="consultation-note">احتفظ برقم الطلب. يمكنك سحب موافقة التواصل لاحقًا عبر <a href="#privacy">${t('سياسة الخصوصية')}</a> دون أن يؤثر ذلك على نتيجتك.</p><div class="button-row"><button class="primary-button" data-action="close-dialog">${t('إغلاق')}</button></div></div>`);
      } catch (error) {
        errorBox.textContent = apiMessage(error); errorBox.hidden = false; submit.disabled = false;
      }
    }
    else if (form.id === 'scientific-status-form') {
      await api(`/api/instrument-versions/${Number(data.version_id)}/scientific-status`,{method:'PATCH',body:JSON.stringify({scientific_status:data.scientific_status,rationale:data.rationale})});
      closeDialog(); showToast('سُجّلت الحالة العلمية في سجل التدقيق.'); router();
    }
    else if (form.id === 'report-form') { const report=await api('/api/reports',{method:'POST',body:JSON.stringify({assessment_id:Number(data.assessment_id),report_type:data.report_type})});await downloadApi(report.download_url);router(); }
    else if (form.id === 'direct-assessment-form') {
      const fd = new FormData(form); const submit = form.querySelector('button[type="submit"]');
      submit.disabled = true; submit.textContent = 'جارٍ تجهيز المقياس...';
      const payload = {
        organization_name:data.organization_name,sector:data.sector,firm_size:data.firm_size,
        employee_count:Number(data.employee_count),firm_age_years:Number(data.firm_age_years),business_model:data.business_model,
        region:data.region,social_platform_count:Number(data.social_platform_count),social_team_size:Number(data.social_team_size),
        regulated_sector:data.regulated_sector,
        respondent_role:data.respondent_role,service_consent:fd.has('service_consent'),research_consent:fd.has('research_consent'),
      };
      const result = await api('/api/public/assessments',{method:'POST',body:JSON.stringify(payload)});
      sessionStorage.setItem('mcm_participant_token',result.token); navigate(`participant-assessment/${result.assessment_id}`);
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
    const submit = form.querySelector('button[type="submit"]'); if (submit) submit.disabled = false;
    const target=form.querySelector('.form-error')||document.querySelector('#auth-error');
    if(target){target.textContent=apiMessage(error);target.hidden=false;} else showToast(apiMessage(error),'error');
  }
});

document.querySelector('#menu-button').addEventListener('click', event => {
  const sidebar=document.querySelector('#sidebar');const open=sidebar.classList.toggle('open');event.currentTarget.setAttribute('aria-expanded',String(open));
});
document.querySelector('#mobile-more').addEventListener('click',()=>{document.querySelector('#sidebar').classList.add('open');document.querySelector('#menu-button').setAttribute('aria-expanded','true');});
document.querySelector('#org-switcher').addEventListener('click',()=>{
  if(!state.me) return; openDialog(`<h2 id="dialog-title">${t('تبديل المؤسسة')}</h2><div class="button-row">${state.me.organizations.map(item=>`<button class="secondary-button" data-action="switch-org" data-id="${item.id}">${e(item.name)} · ${e(roleLabels[item.role]||item.role)}</button>`).join('')}</div>`);
});
document.querySelector('#user-menu').addEventListener('click',()=>openDialog(`<h2 id="dialog-title">${e(state.me?.user?.name||'الحساب')}</h2><p>${e(state.me?.user?.email||'')}</p><div class="button-row"><button class="secondary-button" data-action="open-settings">${t('الإعدادات')}</button><button class="danger-button" data-action="logout">تسجيل الخروج</button></div>`));
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
  if(!location.hash) navigate(state.token?'overview':'landing'); else router();
}
bootstrap();
