document.addEventListener("click", (event) => {
  const toggle = event.target.closest(".enrol-password-toggle");
  if (!toggle) return;

  const password = document.getElementById(toggle.getAttribute("aria-controls"));
  if (!password) return;

  const visible = password.type === "password";
  password.type = visible ? "text" : "password";
  toggle.classList.toggle("is-visible", visible);
  toggle.setAttribute("aria-pressed", String(visible));
  toggle.setAttribute("aria-label", visible ? "Hide password" : "Show password");
  toggle.title = visible ? "Hide password" : "Show password";
  password.focus({ preventScroll: true });
});
