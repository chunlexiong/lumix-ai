/* Progressive enhancement: navigation, program/age finder, enquiry prefill. */
(() => {
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('.main-nav');
  if (!toggle || !nav) return;
  const close = () => {
    nav.classList.remove('is-open');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Open navigation');
  };
  toggle.addEventListener('click', () => {
    const open = nav.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
  });
  nav.querySelectorAll('a').forEach(link => link.addEventListener('click', close));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && nav.classList.contains('is-open')) { close(); toggle.focus(); }
  });
  document.addEventListener('click', event => {
    if (!event.target.closest('.site-header')) close();
  });
  matchMedia('(min-width:741px)').addEventListener('change', event => { if (event.matches) close(); });
})();

(() => {
  const blocks = [...document.querySelectorAll('[data-catalogue-program]')];
  const ageFilter = document.querySelector('#age-filter');
  if (!blocks.length || !ageFilter) return;
  const links = [...document.querySelectorAll('[data-program]')];
  const params = new URLSearchParams(location.search);
  const valid = new Set(blocks.map(block => block.id));
  const incomingAge = params.get('age');
  if ([...ageFilter.options].some(option => option.value === incomingAge)) ageFilter.value = incomingAge;
  let selected = valid.has(location.hash.slice(1)) ? location.hash.slice(1) : valid.has(params.get('program')) ? params.get('program') : '';
  const motion = () => matchMedia('(prefers-reduced-motion:reduce)').matches ? 'auto' : 'smooth';
  function render(updateUrl = false, scroll = false) {
    const age = Number(ageFilter.value);
    let count = 0;
    blocks.forEach(block => {
      block.hidden = false;
      block.querySelectorAll('[data-age-min]').forEach(card => {
        const matches = !age || (age >= Number(card.dataset.ageMin) && age <= Number(card.dataset.ageMax));
        card.hidden = !matches;
        if (matches) count++;
      });
    });
    links.forEach(link => {
      if (link.dataset.program === selected) link.setAttribute('aria-current', 'true');
      else link.removeAttribute('aria-current');
    });
    document.querySelector('#catalogue-status').textContent = `${age ? `Age ${age} · ` : ''}${count} class ${count === 1 ? 'option' : 'options'} · Choose a term or workshop to jump to it.`;
    if (updateUrl) {
      const url = new URL(location.href);
      url.searchParams.delete('program');
      if (age) url.searchParams.set('age', String(age)); else url.searchParams.delete('age');
      url.hash = selected;
      history.replaceState(null, '', url);
    }
    if (scroll) (document.getElementById(selected) || document.querySelector('.catalogue-controls')).scrollIntoView({behavior:motion(), block:'start'});
  }
  links.forEach(link => link.addEventListener('click', event => {
    event.preventDefault(); selected = link.dataset.program; render(true, true);
  }));
  ageFilter.addEventListener('change', () => render(true, Boolean(selected)));
  addEventListener('hashchange', () => { selected = valid.has(location.hash.slice(1)) ? location.hash.slice(1) : ''; render(false, Boolean(selected)); });
  addEventListener('popstate', () => {
    const url = new URL(location.href);
    selected = valid.has(url.hash.slice(1)) ? url.hash.slice(1) : '';
    ageFilter.value = [...ageFilter.options].some(option => option.value === url.searchParams.get('age')) ? url.searchParams.get('age') : '';
    render(false, Boolean(selected));
  });
  render(false, Boolean(selected));
})();

(() => {
  const form = document.querySelector('#contact-form');
  if (!form) return;

  const program = form.elements.namedItem('program');
  const age = form.elements.namedItem('age');
  const ageGroup = document.querySelector('#enquiry-age-group');
  const placeholder = age.options[0];
  const groups = [...age.querySelectorAll('[data-age-program]')];

  function showAgeOptions(selectedAge = '') {
    const group = groups.find(optionGroup => optionGroup.dataset.ageProgram === program.value);
    age.replaceChildren(placeholder);
    if (group) age.append(group);
    age.value = [...age.options].some(option => option.value === selectedAge) ? selectedAge : '';
    age.disabled = !group;
    ageGroup.hidden = !group && !ageGroup.hasAttribute('data-has-errors');
  }

  showAgeOptions(age.value);
  program.addEventListener('change', () => showAgeOptions());
})();

(() => {
  if (location.pathname !== '/') return;
  const paths = {courses:'/courses/', 'term-four':'/courses/#term-four', 'january-home':'/courses/#january-home', 'term-one':'/courses/#term-one', skills:'/our-approach/#skills', approach:'/our-approach/', parents:'/parent-guide/', contact:'/contact/'};
  if (paths[location.hash.slice(1)]) location.replace(paths[location.hash.slice(1)]);
})();


(() => {
  const filters = [...document.querySelectorAll('[data-gallery-filter]')];
  if (!filters.length) return;
  const cards = [...document.querySelectorAll('[data-gallery-kind]')];
  const empty = document.querySelector('#gallery-empty');
  const status = document.querySelector('#gallery-status');
  filters.forEach(button => button.addEventListener('click', () => {
    const type = button.dataset.galleryFilter;
    let count = 0;
    cards.forEach(card => { card.hidden = type !== 'all' && type !== card.dataset.galleryKind; if (!card.hidden) count++; });
    filters.forEach(filter => filter.setAttribute('aria-pressed', String(filter === button)));
    if (empty) empty.hidden = count > 0;
    if (status) status.textContent = `${count} ${count === 1 ? 'item' : 'items'} · ${button.textContent}`;
  }));
  const dialog = document.querySelector('#gallery-lightbox');
  const image = document.querySelector('#lightbox-image');
  let trigger;
  document.querySelectorAll('[data-gallery-image]').forEach(button => button.addEventListener('click', () => {
    trigger = button;
    image.src = button.dataset.galleryImage;
    image.alt = button.dataset.galleryAlt;
    document.querySelector('#lightbox-title').textContent = button.dataset.galleryTitle;
    dialog.showModal();
  }));
  document.querySelector('#lightbox-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close(); } });
  dialog.addEventListener('close', () => { image.removeAttribute('src'); trigger?.focus(); });
})();
