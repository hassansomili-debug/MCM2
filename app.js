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
  service_consent_required: 'يلزم قبول موافقة الخدمة للبدء.', organization_name_required: 'أدخل اسم منشأة صحيحًا.',
  sector_required: 'اختر قطاع المنشأة.', sme_size_required: 'اختر حجم منشأة صغيرة أو متوسطة.',
  region_required: 'اختر المنطقة.', respondent_role_required: 'اختر دور المجيب.',
  invalid_demographics: 'تحقق من عدد الموظفين وعمر المنشأة وحجم فريق التواصل.',
  business_model_required: 'اختر نموذج أعمال المنشأة.', regulated_sector_required: 'حدد ما إذا كان القطاع منظمًا رقابيًا.',
  platform_not_ready: 'المنصة قيد التهيئة؛ حاول بعد قليل.',
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
  const isGuest = !state.me || state.publicPage;
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

const publicRoutes = new Set(['landing', 'participant-start', 'login', 'participant', 'participant-assessment', 'forgot', 'reset']);
const researchRoutes = new Set(['research', 'dataset', 'instruments', 'instrument', 'data-quality', 'statistics', 'exports']);
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
  if (route.parts[0] === 'participants' && !canManageAssessments()) return navigate('overview');
  const labels = {landing:'الرئيسية','participant-start':'ابدأ المقياس',overview:'نظرة عامة',assessments:'التقييمات',assessment:'التقييم',results:'النتائج',dimension:'تفاصيل البعد',diagnosis:'التشخيص',gaps:'تحليل الفجوات',priorities:'الأولويات',roadmap:'خارطة التحسين',history:'مسار النضج',benchmark:'المقارنة المرجعية',reports:'التقارير',participants:'المشاركون',participant:'دخول المشارك','participant-assessment':'تقييم المشارك',notifications:'الإشعارات',settings:'الإعدادات',methodology:'المنهجية',research:'لوحة الباحث',dataset:'مجموعة البيانات',instruments:'إصدارات الأداة',instrument:'تفاصيل الأداة','data-quality':'جودة البيانات',statistics:'الإحصاءات',exports:'التصدير',admin:'إدارة المنصة'};
  document.querySelector('#page-label').textContent = labels[route.parts[0]] || 'مقياس النضج الاتصالي التسويقي';
  const handlers = {landing:renderLanding,'participant-start':renderParticipantStart,login:renderAuth,forgot:renderForgot,reset:renderReset,overview:renderOverview,assessments:renderAssessments,assessment:renderAssessment,results:renderResults,dimension:renderDimension,diagnosis:renderDiagnosis,gaps:renderGaps,priorities:renderPriorities,roadmap:renderRoadmap,history:renderHistory,benchmark:renderBenchmark,reports:renderReports,participants:renderParticipants,participant:renderParticipant,'participant-assessment':renderParticipantAssessment,notifications:renderNotifications,settings:renderSettings,methodology:renderMethodology,research:renderResearch,dataset:renderDataset,instruments:renderInstruments,instrument:renderInstrument,'data-quality':renderDataQuality,statistics:renderStatistics,exports:renderExports,admin:renderAdmin};
  const handler = handlers[route.parts[0]];
  if (!handler) { appView.innerHTML = emptyState('الصفحة غير موجودة', 'تحقق من الرابط أو عد إلى لوحة البيانات.', '<a class="primary-button" href="#overview">العودة للرئيسية</a>'); return; }
  try { await handler(route); if (request === state.routeRequest) appView.focus({preventScroll:true}); }
  catch (error) { if (error.name !== 'AbortError' && request === state.routeRequest) appView.innerHTML = errorState(error); }
}

function publicNav() {
  return `<nav class="public-nav" aria-label="التنقل الرئيسي"><a class="public-brand" href="#landing"><span>ن</span><b>مقياس النضج الاتصالي التسويقي</b></a><div><a href="#landing">الرئيسية</a><a href="#participant">لدي دعوة</a><a class="secondary-button" href="#login">تسجيل الدخول</a><a class="primary-button" href="#participant-start">ابدأ المقياس</a></div></nav>`;
}

function renderLanding() {
  state.publicPage = true; applyShell();
  const storageNotice = state.publicConfig.storage === 'ephemeral-demo' ? `<div class="landing-alert"><strong>نسخة عرض مؤقتة</strong><span>${e(state.publicConfig.notice || 'قد تُعاد تهيئة البيانات؛ لا تدخل بيانات حساسة.')}</span></div>` : '';
  const mcmDimensions = ['الحوكمة والتوجيه','ذكاء أصحاب المصلحة','نزاهة المعلومات','تنسيق رحلة العميل','مواءمة الوعد والتجربة','الأدلة والتعلّم','المأسسة والتوسع'];
  const smceDimensions = ['الاستجابة والحل','المعنى والتفاعل','كفاءة الفعل','انخفاض الاحتكاك','كفاءة الموارد والأهداف'];
  const stages = [['١','تفاعلي'],['٢','مستجيب'],['٣','مُدار ومتكامل'],['٤','استباقي ومتكيّف'],['٥','مؤسسي وذكي']];
  appView.innerHTML = `<div class="landing-page">${publicNav()}${storageNotice}<main><section class="landing-hero"><div class="hero-copy"><div class="eyebrow">للمنشآت الصغيرة والمتوسطة في السعودية</div><h1>حوّل الاتصال التسويقي من نشاط متفرق إلى <i>قدرة مؤسسية تصنع الأثر.</i></h1><p>شخّص نضج منظومتك الاتصالية، واكتشف مدى ترجمة هذا النضج إلى كفاءة في التواصل الاجتماعي، ثم احصل على تصنيف واضح وخارطة تطوير عملية.</p><div class="hero-actions"><a class="primary-button large" href="#participant-start">ابدأ المقياس مباشرة</a><button class="secondary-button large" data-action="scroll-model" type="button">استكشف النموذج</button></div><div class="hero-proof"><span><b>٧</b> أبعاد للنضج</span><span><b>٥</b> أبعاد للكفاءة</span><span><b>٥</b> مراحل تطور</span></div></div><div class="hero-model" aria-label="ملخص النموذج المفاهيمي"><div class="model-column enablers"><small>السياق والممكنات</small><b>قيادة · كفاءات · تقنية · بيانات</b></div><span class="model-arrow">←</span><div class="model-column mcm"><small>قدرة مؤسسية</small><b>MCM</b><strong>النضج الاتصالي التسويقي</strong></div><span class="model-arrow teal">←</span><div class="model-column smce"><small>نتيجة اتصالية</small><b>SMCE</b><strong>كفاءة التواصل الاجتماعي</strong></div><p>أثر إيجابي مقترح · نموذج بحثي أولي</p></div></section><section class="landing-section value-section"><div class="section-intro"><span>قراءة أعمق من مؤشرات التفاعل</span><h2>ماذا سيكشف المقياس لمنشأتك؟</h2></div><div class="value-grid"><article><b>01</b><h3>أين تقف الآن؟</h3><p>تصنيف منشأتك ضمن خمس مراحل نضج متدرجة بلغة إدارية واضحة.</p></article><article><b>02</b><h3>ما الذي يعطّل الكفاءة؟</h3><p>فهم الفجوة بين قدرات المؤسسة وبين سرعة وجودة وكلفة الاتصال عبر المنصات.</p></article><article><b>03</b><h3>ما الخطوة التالية؟</h3><p>أولويات مرتبة وخارطة عمل مرحلية مبنية على أضعف أبعاد القدرة.</p></article></div></section><section class="landing-section model-section" id="methodology-public"><div class="section-intro"><span>النموذج التشخيصي</span><h2>النضج قدرة أعلى رتبة، والكفاءة نتيجة لاحقة مقترحة</h2><p>تُحفظ خصائص المنشأة والممكنات كسياق تفسيري منفصل، ولا تُخلط بدرجة النضج الأساسية.</p></div><div class="construct-grid"><article class="construct-card navy"><header><span>MCM</span><h3>النضج الاتصالي التسويقي</h3></header><ol>${mcmDimensions.map((item,index)=>`<li><i>${index+1}</i>${e(item)}</li>`).join('')}</ol></article><div class="effect-card"><b>أثر إيجابي<br>مقترح</b><span>←</span><small>يُختبر كميًا ولا يُعرض كعلاقة سببية مثبتة</small></div><article class="construct-card teal"><header><span>SMCE</span><h3>الكفاءة الاتصالية</h3></header><ol>${smceDimensions.map((item,index)=>`<li><i>${index+1}</i>${e(item)}</li>`).join('')}</ol></article></div></section><section class="landing-section stages-section"><div class="section-intro"><span>مسار التطور</span><h2>خمس مراحل تصف موقع المنشأة واتجاه انتقالها</h2></div><div class="maturity-stages">${stages.map(([n,label])=>`<div><b>${n}</b><span>${e(label)}</span></div>`).join('')}</div></section><section class="landing-section report-preview"><div><span>نتيجة قابلة للاستخدام</span><h2>تقرير تنفيذي برسوم واضحة، وليس مجرد درجة.</h2><p>يقارن بين MCM وSMCE، يعرض الأبعاد الاثني عشر، يحدد المرحلة الحالية، ويرتب أولويات التطوير. وتتوفر للمدير ملفات Excel وSPSS مع قاموس متغيرات وترميزات جاهزة للتحليل.</p><a class="primary-button large" href="#participant-start">ابدأ تشخيص منشأتك</a></div><div class="preview-card"><header><span>نتيجة افتراضية للتوضيح</span><b>مُدار ومتكامل</b></header><div class="preview-score"><strong>64</strong><small>/100</small></div><div class="preview-bars">${[82,71,64,58,46].map((score,index)=>`<div><span>البعد ${index+1}</span><i><b style="--score:${score}%"></b></i><em>${score}</em></div>`).join('')}</div></div></section><section class="landing-cta"><span>البدء لا يحتاج حسابًا</span><h2>أدخل معلومات منشأتك وابدأ الإجابة مباشرة.</h2><p>تعرض العبارات خيارات لفظية حسب نوعها: مدى انطباق الممارسة أو موقع النتيجة مقارنة بالمنافسين، مع «لا ينطبق» و«لا أعرف» عند الحاجة.</p><a class="primary-button light large" href="#participant-start">ابدأ المقياس الآن</a></section></main><footer class="public-footer"><b>مقياس النضج الاتصالي التسويقي</b><span>نموذج بحثي تشخيصي أولي للمنشآت الصغيرة والمتوسطة · 2026</span><a href="#login">تسجيل الدخول</a></footer></div>`;
}

function renderParticipantStart() {
  state.publicPage = true; applyShell();
  const regions = ['الرياض','مكة المكرمة','المنطقة الشرقية','المدينة المنورة','القصيم','عسير','تبوك','حائل','الحدود الشمالية','جازان','نجران','الباحة','الجوف'];
  const storageNotice = state.publicConfig.storage === 'ephemeral-demo' ? `<div class="research-notice"><strong>تنبيه بيئة العرض</strong><span>${e(state.publicConfig.notice || 'البيانات مؤقتة؛ استخدم معلومات غير حساسة فقط.')}</span></div>` : '';
  appView.innerHTML = `<div class="participant-start-page">${publicNav()}<main><section class="start-heading"><div><span>دخول مباشر للمشارك</span><h1>عرّفنا بمنشأتك قبل بدء المقياس</h1><p>تساعد هذه المتغيرات على تفسير النتيجة في سياق المنشأة، ولا تدخل في درجة النضج الأساسية. ستقيّم الممكنات التنظيمية داخل الأداة نفسها.</p></div><div class="start-meta"><b>حوالي 15–20 دقيقة</b><span>لا يلزم إنشاء حساب</span><span>الحفظ تلقائي</span></div></section>${storageNotice}<form id="direct-assessment-form" class="direct-form"><section class="panel"><div class="form-section-title"><b>01</b><div><h2>الخصائص الديموغرافية للمنشأة</h2><p>تُحفظ مع حالة القياس لأغراض التشخيص والتحليل المجهول وفق الموافقات.</p></div></div><div class="form-grid"><label class="field full"><span>اسم المنشأة</span><input name="organization_name" minlength="2" maxlength="120" required></label><label class="field"><span>القطاع</span><select name="sector" required><option value="">اختر القطاع</option><option>التجزئة والتجارة</option><option>الخدمات المهنية</option><option>التقنية والاتصالات</option><option>الصناعة</option><option>السياحة والضيافة</option><option>الصحة</option><option>التعليم</option><option>النقل والخدمات اللوجستية</option><option>قطاع آخر</option></select></label><label class="field"><span>حجم المنشأة</span><select name="firm_size" required><option value="">اختر الحجم</option><option value="MICRO">متناهية الصغر</option><option value="SMALL">صغيرة</option><option value="MEDIUM">متوسطة</option></select></label><label class="field"><span>عدد الموظفين</span><input name="employee_count" type="number" min="1" max="250000" required></label><label class="field"><span>عمر المنشأة بالسنوات</span><input name="firm_age_years" type="number" min="0" max="200" required></label><label class="field"><span>نموذج الأعمال</span><select name="business_model" required><option value="">اختر النموذج</option><option value="B2C">منشأة إلى مستهلك B2C</option><option value="B2B">منشأة إلى منشأة B2B</option><option value="B2B2C">مختلط B2B2C</option><option value="GOVERNMENT">جهة حكومية / تعامل حكومي</option><option value="NONPROFIT">غير ربحي</option><option value="OTHER">آخر</option></select></label><label class="field"><span>المنطقة الرئيسية للنشاط</span><select name="region" required><option value="">اختر المنطقة</option>${regions.map(region=>`<option>${e(region)}</option>`).join('')}</select></label><label class="field"><span>عدد منصات التواصل المستخدمة بانتظام</span><input name="social_platform_count" type="number" min="0" max="50" required></label><label class="field"><span>عدد العاملين المسؤولين مباشرة عن التواصل الاجتماعي</span><input name="social_team_size" type="number" min="0" max="250000" required></label><label class="field"><span>هل تعمل المنشأة في قطاع منظم رقابيًا؟</span><select name="regulated_sector" required><option value="">اختر الإجابة</option><option value="YES">نعم</option><option value="NO">لا</option></select></label><label class="field full"><span>دور المجيب</span><select name="respondent_role" required><option value="">اختر الدور</option><option>مالك / مؤسس</option><option>إدارة عليا</option><option>مدير تسويق أو اتصال</option><option>أخصائي تسويق أو اتصال</option><option>خدمة عملاء / تجربة عميل</option><option>دور آخر</option></select></label></div></section><section class="panel consent-panel"><div class="form-section-title"><b>02</b><div><h2>الموافقة والبدء</h2><p>يمكنك الانسحاب قبل إرسال الإجابات، والموافقة البحثية مستقلة واختيارية.</p></div></div><label class="checkbox-field"><input name="service_consent" type="checkbox" required><span><b>موافقة الخدمة مطلوبة:</b> أوافق على معالجة الإجابات لإصدار التشخيص والتقرير للمنشأة.</span></label><label class="checkbox-field"><input name="research_consent" type="checkbox"><span><b>موافقة بحثية اختيارية:</b> أوافق على استخدام البيانات بعد إزالة المعرّفات المباشرة لأغراض البحث والمقارنة.</span></label><div class="form-error" hidden></div><button class="primary-button large" type="submit">حفظ البيانات وبدء المقياس</button></section></form></main></div>`;
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
  appView.innerHTML = `<div class="public-result-page dashboard-result">${publicNav()}<main><section class="result-hero dashboard-hero"><div><span>اكتمل مقياس النضج الاتصالي التسويقي</span><h1>تصنيف منشأتك: <i>${e(currentStage.label_ar || 'غير متاح')}</i></h1><p>${e(summary)}</p></div><div class="result-score-cards"><article><small>النضج MCM</small><strong>${number(mcmTotal,1)}</strong><span>/100</span></article><article><small>الكفاءة SMCE</small><strong>${number(smceTotal,1)}</strong><span>/100</span></article><article><small>الفارق بين الكفاءة والنضج</small><strong>${Number(efficiencyGap || 0) > 0 ? '+' : ''}${number(efficiencyGap,1)}</strong><span>نقطة</span></article></div></section><section class="panel maturity-dashboard"><div class="card-title"><div><h2>رحلة النضج والخطوة التالية</h2><p>المرحلة الحالية مميزة، والحدود تشخيصية أولية قيد التحقق.</p></div><div class="next-stage-callout"><small>الفجوة إلى ${e(nextLabel)}</small><strong>${nextGap > 0 ? `${number(nextGap,1)} نقطة` : 'أنت في المرحلة الأعلى'}</strong></div></div><div class="maturity-stages compact">${stages.map(stage=>`<div class="${Number(stage.level_order) === currentOrder ? 'active':''}"><b>${number(stage.level_order)}</b><span>${e(stage.label_ar)}</span></div>`).join('')}</div></section><section class="dashboard-grid"><article class="card dashboard-panel radar-panel"><div class="card-title"><div><span class="dashboard-kicker">بصمة القدرة المؤسسية</span><h2>أبعاد النضج السبعة MCM</h2><p>كل محور يمثل درجة بُعد مستقلة من 100.</p></div></div>${radarChart(mcmDimensions)}</article><article class="card dashboard-panel smce-panel"><div class="card-title"><div><span class="dashboard-kicker teal">النتيجة الاتصالية</span><h2>كفاءة التواصل SMCE</h2><p>قراءة مستقلة للأداء الاتصالي المرصود.</p></div></div>${scoreProfile(smceDimensions,'لا تتوفر درجات SMCE لهذه الحالة.','teal')}<div class="relationship-compact"><b>MCM</b><span>أثر إيجابي مقترح ←</span><b>SMCE</b><p>${e(relation.interpretation_ar || '')}</p></div></article></section><section class="dashboard-grid context-outcomes"><article class="card dashboard-panel"><div class="card-title"><div><span class="dashboard-kicker">جاهزية التنفيذ</span><h2>الممكنات التنظيمية</h2><p>تفسر قدرة المنشأة على التنفيذ ولا تدخل في مقام درجة MCM.</p></div></div>${scoreProfile(enablers,'تظهر الممكنات هنا عند احتساب بنود القيادة والكفاءات والتقنية والبيانات.','navy')}</article><article class="card dashboard-panel"><div class="card-title"><div><span class="dashboard-kicker teal">نتائج اختيارية</span><h2>الثقة والرضا والعلامة والأعمال</h2><p>مؤشرات سياقية اختيارية لا تدخل في التصنيف الأساسي.</p></div></div>${scoreProfile(outcomes,'لم تُجب هذه الحالة عن بنود النتائج الاختيارية، لذلك لم تُعرض درجة.','sand')}</article></section><section class="insights-grid"><article class="card"><div class="card-title"><div><span class="dashboard-kicker success">ما يعمل جيدًا</span><h2>نقاط القوة</h2></div></div><div class="insight-list">${insightCards(strengthItems,'strength','لا تتوفر نقاط قوة محسوبة.')}</div></article><article class="card"><div class="card-title"><div><span class="dashboard-kicker warning">بداية التحسين</span><h2>الفرص ذات الأولوية</h2></div></div><div class="insight-list">${insightCards(opportunityItems,'opportunity','لا تتوفر فرص محسوبة.')}</div></article></section><section class="dashboard-grid improvement-section"><article class="card dashboard-panel"><div class="card-title"><div><span class="dashboard-kicker">قرار تنفيذي</span><h2>مصفوفة الأثر والجهد</h2><p>الأرقام تربط النقاط بأولوية التحسين المقابلة.</p></div></div>${impactEffortMatrix(priorities.length ? priorities : opportunityItems)}</article><article class="card dashboard-panel priority-panel"><div class="card-title"><div><span class="dashboard-kicker teal">الترتيب المقترح</span><h2>أولويات العمل</h2><p>ابدأ بالأثر الأعلى والجهد الأقل، ثم راجع الملاءمة مع فريقك.</p></div></div><ol>${(priorities.length ? priorities : opportunityItems).slice(0,5).map((item,index)=>`<li><b>${number(item.rank || index+1)}</b><div><h3>${e(item.problem || item.title || dashboardName(item))}</h3>${item.action || item.description ? `<p>${e(item.action || item.description)}</p>` : ''}<span>${e(item.dimension_code || item.code || '')}${item.kpi ? ` · KPI: ${e(item.kpi)}` : ''}</span></div></li>`).join('') || '<li class="dashboard-empty">لا توجد أولويات مادية لهذه النتيجة.</li>'}</ol></article></section><section class="panel roadmap-dashboard"><div class="card-title"><div><span class="dashboard-kicker">من التشخيص إلى التنفيذ</span><h2>خارطة التحسين 30 / 90 / 180 يومًا</h2><p>خطوات مرحلية قابلة للمراجعة؛ حدّث المسؤول والمؤشر والتاريخ عند اعتماد الخطة داخليًا.</p></div></div><div class="roadmap-timeline">${timeline}</div></section><section class="card result-boundary"><div><h2>كيف تقرأ النتيجة؟</h2><p>${e(result.classification_notice || 'هذه نتيجة تشخيصية أولية، وليست إثباتًا سببيًا أو اعتمادًا علميًا نهائيًا.')}</p></div><div class="button-row public-result-actions"><button class="secondary-button" data-action="print-result">طباعة الداشبورد</button><a class="primary-button" href="#landing">العودة للرئيسية</a></div></section></main></div>`;
}

function renderAuth() {
  state.me = null; applyShell();
  if (!state.publicConfig.registration_enabled && state.authMode === 'register') state.authMode = 'login';
  const register = state.authMode === 'register';
  const ephemeralNotice = state.publicConfig.storage === 'ephemeral-demo' ? `<div class="research-notice"><strong>بيئة عرض مؤقتة</strong><span>${e(state.publicConfig.notice || 'لا تستخدم بيانات حقيقية؛ قد يعاد ضبط البيانات.')}</span></div>` : '';
  const registerTab = state.publicConfig.registration_enabled ? `<button class="${register ? 'active' : ''}" data-action="auth-mode" data-mode="register" type="button">إنشاء حساب</button>` : '';
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>مقياس النضج الاتصالي التسويقي</div><div class="auth-copy"><div class="eyebrow">PLATFORM MANAGEMENT</div><h1>قرارات أوضح.<br><i>أثر أقوى.</i></h1><p>مساحة مدير المنصة لمتابعة الحالات والتقارير وخارطة التطوير وتصدير ملفات التحليل.</p><div class="auth-features"><span>تقارير ورسوم تنفيذية</span><span>ربط MCM وSMCE</span><span>Excel وSPSS</span></div></div><small>Provisional diagnostic model · Quantitative validation required</small></div><div class="auth-panel"><div class="auth-box">${ephemeralNotice}<div class="auth-tabs"><button class="${register ? '' : 'active'}" data-action="auth-mode" data-mode="login" type="button">تسجيل الدخول</button>${registerTab}</div><h2>${register ? 'أنشئ مساحة مؤسستك' : 'تسجيل الدخول'}</h2><p>${register ? 'ابدأ بملف المؤسسة ثم نفّذ التقييم الأول.' : 'أدخل بيانات الحساب الإداري للوصول إلى لوحة التحكم.'}</p><form id="auth-form" class="form-grid">${register ? `<label class="field"><span>الاسم الكامل</span><input name="name" required autocomplete="name"></label><label class="field"><span>اسم المؤسسة</span><input name="organization_name" required></label>` : ''}<label class="field ${register ? '' : 'full'}"><span>البريد الإلكتروني</span><input name="email" type="email" required autocomplete="email"></label><label class="field ${register ? '' : 'full'}"><span>كلمة المرور</span><input name="password" type="password" required autocomplete="${register ? 'new-password' : 'current-password'}"></label>${register ? `<label class="checkbox-field full"><input name="service_consent" type="checkbox" required><span>أوافق على معالجة البيانات لأغراض التشخيص وتقديم الخدمة.</span></label>` : ''}<div id="auth-error" class="form-error full" hidden></div><button class="primary-button full" type="submit">${register ? 'إنشاء الحساب' : 'تسجيل الدخول'}</button></form>${register ? '' : `<div class="button-row"><button class="secondary-button" data-action="forgot-password" type="button">نسيت كلمة المرور</button><a class="secondary-button" href="#participant-start">دخول المشارك مباشرة</a><a class="secondary-button" href="#landing">الرئيسية</a></div>`}</div></div></section>`;
}

function renderForgot() {
  state.me = null; applyShell();
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>مقياس النضج الاتصالي التسويقي</div><div class="auth-copy"><h1>استعادة<br><i>آمنة للحساب.</i></h1><p>لن نكشف ما إذا كان البريد مسجلًا أم لا.</p></div></div><div class="auth-panel"><div class="auth-box"><h2>نسيت كلمة المرور</h2><p>أدخل بريدك لاستلام تعليمات الاستعادة عبر القناة المضبوطة.</p><form id="forgot-form" class="form-grid"><label class="field full"><span>البريد</span><input name="email" type="email" required></label><button class="primary-button full">إرسال الطلب</button></form><p><a href="#login">العودة لتسجيل الدخول</a></p></div></div></section>`;
}
function renderReset(route) {
  state.me = null; applyShell();
  const token = route.query.get('token') || '';
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>مقياس النضج الاتصالي التسويقي</div><div class="auth-copy"><h1>كلمة مرور<br><i>جديدة.</i></h1></div></div><div class="auth-panel"><div class="auth-box"><h2>إعادة ضبط كلمة المرور</h2><form id="reset-form" class="form-grid"><input type="hidden" name="token" value="${e(token)}"><label class="field full"><span>كلمة المرور الجديدة</span><input name="password" type="password" minlength="10" required></label><button class="primary-button full">حفظ كلمة المرور</button></form></div></div></section>`;
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
    const choices = values.map((choice,index) => `<label><input type="radio" name="q_${item.id}" value="${choice}" data-answer-input data-item-id="${item.id}" ${Number(value) === choice && !response?.missing_type ? 'checked' : ''}${lock}><span>${type === 'BOOLEAN' ? (index ? 'نعم' : 'لا') : e(labels[choice] || String(choice))}</span></label>`).join('');
    const hint = extent ? 'إلى أي مدى تنطبق العبارة على منشأتك خلال الاثني عشر شهرًا الماضية؟' : relative ? 'كيف تقارن النتيجة بالمنافسين الرئيسيين؟' : '';
    control = `${hint ? `<p class="scale-hint">${e(hint)}</p>` : ''}<div class="choice-scale labelled ${relative ? 'relative':''}" style="--choice-count:${values.length}">${choices}</div>`;
  }
  const disabledButton = disabled ? ' disabled' : '';
  const supportsScientificMissing = ['LIKERT_EXTENT','LIKERT_5_EXTENT','LIKERT_RELATIVE','RELATIVE_5_COMPETITOR'].includes(type);
  const missingLabel = {NOT_APPLICABLE:'لا ينطبق',DONT_KNOW:'لا أعرف',NOT_ANSWERED:'غير مجاب'}[response?.missing_type] || response?.missing_type;
  const missingButtons = supportsScientificMissing
    ? `<button type="button" data-action="missing-answer" data-item-id="${item.id}" data-missing="NOT_APPLICABLE"${disabledButton}>لا ينطبق</button><button type="button" data-action="missing-answer" data-item-id="${item.id}" data-missing="DONT_KNOW"${disabledButton}>لا أعرف</button>`
    : `<button type="button" data-action="missing-answer" data-item-id="${item.id}" data-missing="NOT_APPLICABLE"${disabledButton}>لا ينطبق</button><button type="button" data-action="missing-answer" data-item-id="${item.id}" data-missing="DONT_KNOW"${disabledButton}>لا أعرف</button>`;
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
  appView.innerHTML = `<div class="page assessment-page">${pageHeading(`التقييم #${id} · ${e(data.instrument.version)}`,'التقييم المؤسسي','اختر الإجابة التي تصف الممارسة الحالية، لا الحالة المرغوبة.', '<a class="secondary-button" href="#assessments">حفظ وخروج</a>')} ${researchNotice(data.instrument.status)}<section class="assessment-header"><div class="progress-row"><strong>التقدم <span id="progress-value">${number(data.review.progress,0)}%</span></strong><span class="save-state" id="save-state">محفوظ على الخادم</span></div><div class="progress-track"><span id="progress-bar" style="--progress:${data.review.progress}%"></span></div></section><form id="assessment-form">${sections}</form><section class="panel">${footer}</section></div>`;
}

async function renderResults(route) {
  const id = Number(route.parts[1]); if (!id) return navigate('assessments');
  loading('جارٍ تحميل النتائج...'); const data = await api(`/api/results/${id}`);
  const mcm = data.scores.MCM; const smce = data.scores.SMCE;
  const dimLines = mcm.dimensions.map(item => `<div class="dimension-line"><a href="#dimension/${id}/${e(item.code)}">${e(item.code)} · ${e(item.name)}</a><div class="dimension-track"><i style="--score:${Number(item.score)}%"></i></div><b>${number(item.score,1)}</b></div>`).join('');
  const smceLines = smce.dimensions.map(item => `<div class="dimension-line"><span>${e(item.code)} · ${e(item.name)}</span><div class="dimension-track"><i style="--score:${Number(item.score)}%"></i></div><b>${number(item.score,1)}</b></div>`).join('');
  const relation = data.relationship || {};
  const stages = (data.maturity_progression || []).map(stage => `<div class="${stage.level_order === mcm.maturity_level?.order ? 'active':''}"><b>${number(stage.level_order)}</b><span>${e(stage.label_ar)}</span></div>`).join('');
  const context = data.context ? `<section class="panel"><div class="card-title"><div><h2>السياق الديموغرافي للحالة</h2><p>عوامل تفسيرية لا تدخل في مقام درجة MCM.</p></div></div><div class="pill-list"><span>القطاع: ${e(data.context.sector)}</span><span>الحجم: ${e(data.context.firm_size)}</span><span>العمر: ${number(data.context.firm_age_years)} سنة</span><span>المنطقة: ${e(data.context.region)}</span><span>منصات التواصل: ${number(data.context.social_platform_count)}</span><span>دور المجيب: ${e(data.context.respondent_role)}</span></div></section>` : '';
  const actions = `<a class="secondary-button" href="#diagnosis/${id}">التشخيص</a><a class="secondary-button" href="#gaps/${id}">الفجوات</a><a class="secondary-button" href="#priorities/${id}">الأولويات</a><a class="primary-button" href="#roadmap/${id}">خارطة التحسين</a>`;
  const reportAction = canManageAssessments() ? `<button class="primary-button" data-action="generate-report" data-id="${id}" data-type="EXECUTIVE">5. إنشاء التقرير</button>` : '';
  const aiPlanAction = canManageAssessments() ? `<button class="secondary-button" data-action="generate-ai-plan" data-id="${id}">6. تحليل خطة التحسين</button>` : '';
  appView.innerHTML = `<div class="page">${pageHeading(`نتائج التقييم #${id}`,`نتيجة ${e(data.organization_name)}`,`اكتمل القياس بتاريخ ${e(dateText(data.completed_at))}.`, actions)}${researchNotice(data.instrument_status)}<section class="panel maturity-panel"><div class="card-title"><div><h2>تصنيف المنشأة: ${e(mcm.maturity_level?.label_ar || 'غير مصنف')}</h2><p>مرحلة تشخيصية أولية ضمن مسار من خمس مراحل.</p></div><strong class="level-score">${number(mcm.total,1)} / 100</strong></div><div class="maturity-stages compact">${stages}</div></section><div class="card-grid"><article class="card span-6"><div class="card-title"><div><h2>النضج الاتصالي MCM</h2><p>متوسط موزون للأبعاد السبعة فقط.</p></div>${badge(mcm.maturity_level?.label_ar || 'غير مصنف')}</div><div class="score-layout"><div class="score-ring" style="--score:${Number(mcm.total || 0)}"><div><strong>${number(mcm.total,1)}</strong><small>/100</small></div></div><div class="dimension-list">${dimLines}</div></div></article><article class="card span-6"><div class="card-title"><div><h2>كفاءة التواصل SMCE</h2><p>نتيجة اتصالية لاحقة مقترحة، وتُحتسب بصورة مستقلة.</p></div></div><div class="score-layout"><div class="score-ring" style="--score:${Number(smce.total || 0)}"><div><strong>${number(smce.total,1)}</strong><small>/100</small></div></div><div class="dimension-list">${smceLines}</div></div></article><article class="card span-12 relationship-card"><div><small>النموذج المقترح</small><h2>MCM <span>←</span> SMCE</h2><p>${e(relation.interpretation_ar || '')}</p></div><div class="relationship-gap"><small>الكفاءة ناقص النضج</small><strong>${Number(relation.efficiency_minus_maturity || 0) > 0 ? '+' : ''}${number(relation.efficiency_minus_maturity,1)}</strong><span>${e(relation.narrative_ar || '')}</span></div></article></div>${context}<section class="panel"><div class="card-title"><div><h2>من النتيجة إلى التنفيذ</h2><p>انتقل بالتسلسل من الأدلة إلى الفجوة والأولوية ثم خارطة العمل.</p></div></div><div class="button-row"><a class="secondary-button" href="#diagnosis/${id}">1. التشخيص العميق</a><a class="secondary-button" href="#gaps/${id}">2. تحليل الفجوات</a><a class="secondary-button" href="#priorities/${id}">3. ترتيب الأولويات</a><a class="secondary-button" href="#benchmark/${id}">4. المقارنة المرجعية</a>${reportAction}${aiPlanAction}</div><p class="classification-boundary">${e(data.classification_notice)}</p></section></div>`;
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
  appView.innerHTML = `<section class="auth-layout"><div class="auth-brand"><div class="auth-logo"><span>ن</span>مقياس النضج الاتصالي التسويقي</div><div class="auth-copy"><div class="eyebrow">SECURE PARTICIPANT PORTAL</div><h1>شارك خبرتك.<br><i>بخصوصية واضحة.</i></h1><p>تُحفظ إجابتك في التقييم المحدد، ولا تظهر بياناتك الشخصية في مجموعة البحث الافتراضية.</p></div><small>Research consent is optional and separate</small></div><div class="auth-panel"><div class="auth-box"><h2>${invitation ? `دعوة من ${e(invitation.organization_name)}` : 'لديك دعوة؟'}</h2>${invitation ? `<p>التقييم #${invitation.assessment_id} · ${e(invitation.email)}</p><form id="accept-invitation-form" class="form-grid"><input type="hidden" name="token" value="${e(token)}"><label class="field full"><span>الاسم الكامل</span><input name="full_name" value="${e(invitation.full_name || '')}" required></label><label class="checkbox-field full"><input name="service_consent" type="checkbox" required><span>أوافق على معالجة إجاباتي لتقديم التشخيص للمؤسسة.</span></label><label class="checkbox-field full"><input name="research_consent" type="checkbox"><span>أوافق اختياريًا على استخدام بيانات مجهولة لأغراض البحث.</span></label><button class="primary-button full">قبول وبدء التقييم</button></form>` : `<p>ألصق رمز الدعوة الذي استلمته من مسؤول التقييم، أو ابدأ المقياس مباشرة دون حساب.</p><form id="invitation-token-form" class="form-grid"><label class="field full"><span>رمز الدعوة</span><input name="token" required autocomplete="off"></label><button class="primary-button full">التحقق من الدعوة</button></form><a class="primary-button full" href="#participant-start">بدء المقياس مباشرة</a>`}${state.token ? '<p><a href="#overview">العودة لمساحة العمل</a></p>' : '<p><a href="#landing">العودة للرئيسية</a> · <a href="#login">تسجيل الدخول</a></p>'}</div></div></section>`;
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
  appView.innerHTML = `<div class="page assessment-page participant-measure">${pageHeading(`تقييم #${data.assessment.id}`,'مقياس النضج الاتصالي التسويقي',`أجب عن ${number(visibleItems.length)} عبارة وفق واقع المنشأة خلال الاثني عشر شهرًا الماضية. استخدم «لا ينطبق» أو «لا أعرف» فقط عند الحاجة.`)} ${researchNotice()}<section class="assessment-header"><div class="progress-row"><strong>التقدم <span id="progress-value">${number(data.review.progress)}%</span></strong><span class="save-state" id="save-state">محفوظ تلقائيًا</span></div><div class="progress-track"><span id="progress-bar" style="--progress:${data.review.progress}%"></span></div></section><form id="assessment-form">${sections}</form><section class="panel submit-panel"><p>راجع البنود المطلوبة قبل الإرسال. بعد الإرسال ستُقفل الإجابات وتظهر لوحة النتيجة وخارطة التحسين.</p><button class="primary-button large" data-action="submit-participant" type="button">إرسال التقييم وعرض الداشبورد</button></section></div>`;
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
  appView.innerHTML = `<div class="page">${pageHeading('المعرفة · المنهجية','كيف يعمل مقياس النضج الاتصالي التسويقي','فصل واضح بين السياق، القدرة المؤسسية، والكفاءة الاتصالية الناتجة.')}${researchNotice()}<div class="card-grid"><article class="card span-4"><span class="status-badge">1</span><h2>السياق والعوامل التمكينية</h2><p>دعم القيادة والكفاءات البشرية والبنية التقنية وجاهزية البيانات، إضافة إلى حجم المنشأة وعمرها وقطاعها وعدد المنصات. تفسر الظروف ولا تدخل في درجة MCM.</p></article><article class="card span-4"><span class="status-badge">2</span><h2>MCM · القدرة المؤسسية</h2><p>سبعة أبعاد تُطبّع بنودها إلى 0–100 ثم تجمع بأوزان إصدار الأداة.</p></article><article class="card span-4"><span class="status-badge">3</span><h2>SMCE · النتيجة الاتصالية</h2><p>خمسة أبعاد تُحتسب بصورة مستقلة لاختبار الأثر الإيجابي المقترح للنضج على الكفاءة.</p></article><article class="card span-6"><h2>أبعاد MCM</h2><div class="pill-list">${mcm.map(item => `<span>${e(item)}</span>`).join('')}</div></article><article class="card span-6"><h2>أبعاد SMCE</h2><div class="pill-list">${smce.map(item => `<span>${e(item)}</span>`).join('')}</div></article><article class="card span-12"><h2>المراحل الخمس</h2><div class="maturity-stages compact">${['تفاعلي','مستجيب','مُدار ومتكامل','استباقي ومتكيّف','مؤسسي وذكي'].map((label,index)=>`<div><b>${index+1}</b><span>${e(label)}</span></div>`).join('')}</div></article><article class="card span-12"><h2>عقد علمي واضح</h2><ul><li>الإجابة المفقودة لا تتحول إلى صفر.</li><li>الاحتساب والتصنيف والتشخيص تجري على الخادم.</li><li>كل نتيجة ترتبط بإصدار أداة وإصدار احتساب.</li><li>العلاقة MCM ← SMCE مقترحة وليست ادعاءً سببيًا مثبتًا.</li><li>المستويات والحدود الحالية مؤقتة وموسومة Provisional حتى التحقق الكمي.</li></ul></article></div></div>`;
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
  appView.innerHTML = `<div class="page">${pageHeading('البحث · التصدير','Excel وSPSS جاهزان للتحليل','صف واحد لكل ملاحظة، أسماء متغيرات ASCII، قيم رقمية صحيحة، وترميزات وقاموس متغيرات منفصل—دون معرّفات شخصية مباشرة.')}<div class="card-grid"><section class="panel span-7"><form id="export-form" class="form-grid"><label class="field"><span>مصدر البيانات</span><select name="data_origin"><option value="REAL">واقعية بموافقة بحثية</option><option value="SYNTHETIC">اصطناعية فقط</option><option value="DEMO_TEST">Demo / Test</option><option value="ALL">كل المصادر - مراجعة خاصة</option></select></label><label class="field"><span>نوع التصدير</span><select name="format"><option value="XLSX">Excel متوافق مع SPSS</option><option value="SPSS">حزمة SPSS: XLSX + CSV + Syntax</option><option value="CSV">CSV UTF-8</option><option value="CODEBOOK">قاموس المتغيرات Excel</option><option value="INSTRUMENT">Instrument JSON</option></select></label><label class="checkbox-field full"><input type="checkbox" required><span>أفهم أن التصدير مسجّل في سجل التدقيق وأن البيانات الواقعية تتطلب موافقة بحثية.</span></label><button class="primary-button full">إنشاء وتنزيل الملف</button></form></section><aside class="card span-5 export-summary"><h2>تشمل المتغيرات</h2><ul><li>خصائص المنشأة: القطاع والحجم والعمر والمنطقة.</li><li>عدد المنصات ودور المجيب والممكنات الأربعة.</li><li>بنود ليكرت ودرجات الأبعاد MCM وSMCE.</li><li>المرحلة الخماسية وفارق الكفاءة عن النضج.</li></ul></aside></div><section class="card"><h2>محتويات مصنف Excel</h2><div class="pill-list">${['01_RESPONSES_WIDE','02_RESPONSES_LONG','03_MCM_SCORES','04_SMCE_SCORES','05_COMPANY_PROFILE','06_CODEBOOK','07_VARIABLE_LABELS','08_VALUE_LABELS','09_INSTRUMENT','10_METADATA'].map(item => `<span>${item}</span>`).join('')}</div></section></div>`;
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
    else if (action === 'scroll-model') document.querySelector('#methodology-public')?.scrollIntoView({behavior:'smooth',block:'start'});
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
      openDialog(`<div class="ai-plan-dialog"><span class="status-badge">${e(modeLabel)}</span><h2 id="dialog-title">خطة التحسين المقترحة</h2><p>${e(plan.summary_ar)}</p><div class="ai-plan-priorities">${(plan.priorities || []).map(item=>`<span><b>${e(item.dimension_code)}</b>${e(item.name_ar)} · ${number(item.score,1)}/100</span>`).join('')}</div>${roadmap}<p class="classification-boundary">${e(plan.safeguards?.notice_ar || 'تحتاج الخطة مراجعة واعتمادًا بشريًا قبل التنفيذ.')}</p><button class="secondary-button" data-action="close-dialog">إغلاق</button></div>`);
      button.disabled = false; button.textContent = '6. تحليل خطة التحسين';
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
  if(!location.hash) navigate(state.token?'overview':'landing'); else router();
}
bootstrap();
