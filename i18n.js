// Arabic-keyed English catalogue.
//
// The Arabic wording stays the source in the markup, and `t()` swaps it when
// the reader chooses English. A key with no entry returns the Arabic
// unchanged, which is deliberate: an untranslated string stays legible and is
// counted by `translationCoverage()` rather than disappearing or turning into
// a placeholder. The previous release refused a half-translated interface, so
// what remains untranslated has to stay measurable.
const EN = {
  // Shell and navigation
  'مقياس النضج الاتصالي التسويقي': 'Marketing Communication Maturity',
  'مساحة العمل': 'Workspace',
  'نظرة عامة': 'Overview',
  'التقييمات': 'Assessments',
  'النتائج': 'Results',
  'مسار النضج': 'Maturity journey',
  'خارطة التحسين': 'Improvement roadmap',
  'التقارير': 'Reports',
  'المشاركون': 'Participants',
  'بدء تقييم مباشر': 'Start a direct assessment',
  'البحث والتحليل': 'Research & analysis',
  'لوحة الباحث': 'Researcher console',
  'البيانات': 'Dataset',
  'إصدارات الأداة': 'Instrument versions',
  'جودة البيانات': 'Data quality',
  'مركز التصدير': 'Export centre',
  'مركز تحليل البيانات': 'Analysis centre',
  'المعرفة والإدارة': 'Knowledge & administration',
  'المنهجية': 'Methodology',
  'المعرفة الاتصالية': 'Communication knowledge',
  'محرر المحتوى المعرفي': 'Knowledge editor',
  'طلبات الاستشارة': 'Consultation requests',
  'إدارة المنصة': 'Platform administration',
  'الإعدادات': 'Settings',
  'الإشعارات': 'Notifications',
  'نموذج تطبيقي قائم على الأدلة': 'Evidence-informed applied model',
  'الرئيسية': 'Home',
  'التقييم': 'Assessment',
  'الخطة': 'Plan',
  'المزيد': 'More',
  'تجاوز إلى المحتوى': 'Skip to content',
  'فتح قائمة التنقل': 'Open navigation',
  'المستخدم': 'User',
  'المؤسسة': 'Organization',
  'الحساب المؤسسي': 'Organization account',
  'تبديل المؤسسة': 'Switch organization',
  'جارٍ تجهيز مساحة العمل...': 'Preparing your workspace…',
  'نموذج تطبيقي قائم على الأدلة العلمية للمنشآت الصغيرة والمتوسطة': 'Evidence-informed applied model for small and medium enterprises',

  // Public navigation and landing
  'مراحل النضج': 'Maturity stages',
  'المعرفة': 'Knowledge',
  'لدي كود مشاركة': 'I have a join code',
  'الخصوصية': 'Privacy',
  'تسجيل الدخول': 'Sign in',
  'ابدأ المقياس': 'Start the assessment',
  'ابدأ المقياس مباشرة': 'Start the assessment now',
  'تعرّف على المراحل': 'See the stages',
  'مقياس تشخيصي للمنشآت الصغيرة والمتوسطة في السعودية': 'A diagnostic instrument for Saudi small and medium enterprises',
  'عبارة علمية': 'scientific items',
  'بُعدًا وسياقًا': 'dimensions and context factors',
  'مراحل نضج': 'maturity stages',
  'لماذا يهمّ النضج الاتصالي التسويقي؟': 'Why does marketing communication maturity matter?',
  'مسار التطور': 'Development path',
  'اكتشف مستوى منشأتك': 'Discover your organization’s stage',
  'تعرف على هذه المرحلة': 'Learn about this stage',
  'المرحلة': 'Stage',
  'الخصائص': 'Characteristics',
  'المخاطر الشائعة': 'Common risks',
  'محور التطوير': 'Development focus',
  'مؤشرات الانتقال إلى المرحلة التالية': 'Indicators of moving to the next stage',
  'أبعد من مؤشرات التفاعل': 'Beyond engagement metrics',
  'ماذا سيكشف المقياس لمنشأتك؟': 'What will the instrument reveal?',
  'أين تقف الآن؟': 'Where do you stand?',
  'ما الذي يعطّل الكفاءة؟': 'What is holding efficiency back?',
  'ما الخطوة التالية؟': 'What comes next?',
  'النموذج التشخيصي': 'The diagnostic model',
  'أبعاد MCM': 'MCM dimensions',
  'أبعاد SMCE': 'SMCE dimensions',
  'النضج الاتصالي التسويقي': 'Marketing communication maturity',
  'الكفاءة الاتصالية': 'Communication efficiency',
  'نتيجة قابلة للاستخدام': 'A result you can act on',
  'نتائج تنفيذية، وليست مجرد درجة.': 'Executive results, not just a score.',
  'ابدأ تشخيص منشأتك': 'Assess your organization',
  'نتيجة افتراضية للتوضيح': 'Illustrative result',
  'البدء لا يحتاج حسابًا': 'No account required',
  'ابدأ المقياس الآن': 'Start now',
  'اتساق الرسالة': 'Message consistency',
  'سرعة القرار': 'Decision speed',
  'كفاءة الإنفاق': 'Spend efficiency',
  'قدرة لا تعتمد على الأفراد': 'Capability that does not depend on individuals',

  // Direct participant entry
  'دخول مباشر للمشارك': 'Direct participant entry',
  'عرّفنا بمنشأتك قبل بدء المقياس': 'Tell us about your organization before you begin',
  'الخصائص الديموغرافية للمنشأة': 'Organization profile',
  'الموافقة والبدء': 'Consent and start',
  'اسم المنشأة': 'Organization name',
  'القطاع': 'Sector',
  'حجم المنشأة': 'Organization size',
  'عدد الموظفين': 'Number of employees',
  'عمر المنشأة بالسنوات': 'Organization age in years',
  'نموذج الأعمال': 'Business model',
  'المنطقة الرئيسية للنشاط': 'Primary region',
  'عدد منصات التواصل المستخدمة بانتظام': 'Social platforms used regularly',
  'عدد العاملين المسؤولين مباشرة عن التواصل الاجتماعي': 'Staff directly responsible for social communication',
  'هل تعمل المنشأة في قطاع منظم رقابيًا؟': 'Does the organization operate in a regulated sector?',
  'دور المجيب': 'Respondent role',
  'اختر القطاع': 'Select a sector',
  'اختر الحجم': 'Select a size',
  'اختر النموذج': 'Select a model',
  'اختر المنطقة': 'Select a region',
  'اختر الإجابة': 'Select an answer',
  'اختر الدور': 'Select a role',
  'نعم': 'Yes',
  'لا': 'No',
  'حفظ البيانات وبدء المقياس': 'Save and start the assessment',
  'لا يلزم إنشاء حساب': 'No account needed',
  'الحفظ تلقائي': 'Saved automatically',

  // Assessment
  'التقدم': 'Progress',
  'محفوظ تلقائيًا': 'Saved automatically',
  'محفوظ على الخادم': 'Saved on the server',
  'تغييرات غير محفوظة...': 'Unsaved changes…',
  'إرسال التقييم وعرض النتائج': 'Submit and view results',
  'تأكيد إرسال التقييم': 'Confirm submission',
  'تأكيد الإرسال': 'Confirm',
  'العودة للمراجعة': 'Back to review',
  'لا ينطبق': 'Not applicable',
  'لا أعرف': 'Don’t know',

  // Results
  'اكتمل مقياس النضج الاتصالي التسويقي': 'Assessment complete',
  'تصنيف منشأتك': 'Your organization’s stage',
  'النضج MCM': 'MCM maturity',
  'الكفاءة SMCE': 'SMCE efficiency',
  'الفارق بين الكفاءة والنضج': 'Efficiency minus maturity',
  'نقطة': 'points',
  'رحلة النضج والخطوة التالية': 'Your maturity journey and next step',
  'الفجوة إلى': 'Gap to',
  'أنت في المرحلة الأعلى': 'You are at the highest stage',
  'أبعاد النضج السبعة MCM': 'The seven MCM dimensions',
  'كفاءة التواصل SMCE': 'SMCE communication efficiency',
  'الممكنات التنظيمية': 'Organizational enablers',
  'نقاط القوة': 'Strengths',
  'الفرص ذات الأولوية': 'Priority opportunities',
  'مصفوفة الأثر والجهد': 'Impact and effort matrix',
  'أولويات العمل': 'Action priorities',
  'خارطة التحسين 30 / 90 / 180 يومًا': '30 / 90 / 180-day improvement roadmap',
  'كيف تقرأ النتيجة؟': 'How to read this result',
  'طباعة النتائج': 'Print results',
  'العودة للرئيسية': 'Back to home',
  'درجة الأولوية': 'Priority score',
  'الحالي': 'Current',
  'الفجوة': 'Gap',
  'المالك': 'Owner',
  'الجهد': 'Effort',

  // Optional account and consultation
  'اختياري': 'Optional',
  'تحليل أعمق بحساب مشارك': 'Deeper analysis with a participant account',
  'إنشاء حساب': 'Create an account',
  'لدي حساب': 'I have an account',
  'إنشاء حساب مشارك': 'Create a participant account',
  'الاسم الكامل': 'Full name',
  'البريد الإلكتروني': 'Email',
  'كلمة المرور': 'Password',
  'المسمى الوظيفي': 'Job title',
  'الانضمام بكود مشاركة': 'Join with a code',
  'كود المشاركة': 'Join code',
  'انضم إلى التقييم': 'Join the assessment',
  'اطلب استشارة': 'Request a consultation',
  'ليس الآن': 'Not now',
  'طلب استشارة': 'Consultation request',
  'إرسال الطلب': 'Send request',
  'ملاحظات': 'Notes',
  'وسيلة التواصل المفضلة': 'Preferred contact method',
  'الوقت المفضل للتواصل': 'Preferred contact time',
  'محاور الاستشارة': 'Consultation topics',
  'بلا تفضيل': 'No preference',
  'رقم الجوال': 'Mobile number',
  'سياسة الخصوصية': 'Privacy notice',
  'سحب موافقة التواصل': 'Withdraw contact consent',
  'رقم الطلب': 'Request number',
  'سحب الموافقة': 'Withdraw consent',
  'تم الاستلام': 'Received',

  // Shared states and actions
  'إغلاق': 'Close',
  'إلغاء': 'Cancel',
  'حفظ': 'Save',
  'فتح': 'Open',
  'إعادة المحاولة': 'Try again',
  'تعذر تحميل الصفحة': 'This page could not be loaded',
  'تعذر إكمال الطلب.': 'The request could not be completed.',
  'جارٍ تحميل البيانات...': 'Loading…',
  'جارٍ تحميل النتائج...': 'Loading results…',
  'الصفحة غير موجودة': 'Page not found',
  'العدد': 'Count',
  'النسبة': 'Share',
  'التاريخ': 'Date',
  'الحالة': 'Status',
  'الدور': 'Role',
};

let LOCALE = localStorage.getItem('mcm_locale') === 'en' ? 'en' : 'ar';
const MISSING = new Set();

function locale() { return LOCALE; }

function setLocale(next) {
  LOCALE = next === 'en' ? 'en' : 'ar';
  localStorage.setItem('mcm_locale', LOCALE);
  document.documentElement.lang = LOCALE;
  document.documentElement.dir = LOCALE === 'en' ? 'ltr' : 'rtl';
}

function t(arabic) {
  if (LOCALE !== 'en') return arabic;
  const value = EN[arabic];
  if (value === undefined) { MISSING.add(arabic); return arabic; }
  return value;
}

// Reports what the English catalogue does not yet cover, so the gap stays a
// measured number rather than an impression.
function translationCoverage() {
  return {locale: LOCALE, translated: Object.keys(EN).length, missing: [...MISSING].sort()};
}
