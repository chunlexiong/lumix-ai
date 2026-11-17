(() => {
  const toggle = document.querySelector(".menu-toggle");
  const nav = document.querySelector(".main-nav");
  if (!toggle || !nav) return;

  toggle.addEventListener("click", () => {
    const isOpen = nav.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", String(isOpen));
    toggle.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
  });

  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      nav.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Open navigation");
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && nav.classList.contains("is-open")) {
      nav.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Open navigation");
      toggle.focus();
    }
  });
})();

(() => {
  const form = document.querySelector('#contact-demo-form');
  const button = document.querySelector('#preview-enquiry');
  const status = document.querySelector('#enquiry-status');
  if (!form || !button || !status) return;
  form.addEventListener('submit', event => event.preventDefault());
  button.addEventListener('click', () => {
    if (!form.reportValidity()) return;
    status.hidden = false;
  });
  form.addEventListener('input', () => { status.hidden = true; });
})();

(() => {
  if (location.pathname !== '/') return;
  const destinations = {courses:'/courses/', 'term-four':'/courses/#term-four', 'january-home':'/courses/#january-home', 'term-one':'/courses/#term-one', skills:'/our-approach/#skills', approach:'/our-approach/', 'how-it-works':'/our-approach/#how-it-works', parents:'/for-parents/', contact:'/contact/'};
  const destination = destinations[location.hash.slice(1)];
  if (destination) location.replace(destination);
})();
