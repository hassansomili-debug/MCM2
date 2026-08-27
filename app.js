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
  if (link.dataset.view !== 'overview') showToast(`تم فتح قسم ${labels[link.dataset.view]}`);
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
