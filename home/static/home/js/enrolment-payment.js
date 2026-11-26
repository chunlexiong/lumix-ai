const transferStatus = document.querySelector("[data-transfer-copy-status]");

for (const button of document.querySelectorAll("[data-transfer-copy]")) {
  const value = button.parentElement.querySelector("[data-transfer-value]");
  let resetTimer;
  button.hidden = false;

  button.addEventListener("click", async () => {
    let feedback;
    try {
      await navigator.clipboard.writeText(value.textContent.trim());
      feedback = "Copied";
    } catch {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(value);
      selection.removeAllRanges();
      selection.addRange(range);
      feedback = "Selected";
    }

    button.textContent = feedback;
    transferStatus.textContent = button.dataset.transferCopy + " " + feedback.toLowerCase() + ".";
    clearTimeout(resetTimer);
    resetTimer = setTimeout(() => {
      button.textContent = "Copy";
    }, 2200);
  });
}

const cardForm = document.getElementById("embedded-card-form");

if (cardForm) {
  setupCardCheckout(cardForm);
}

function setupCardCheckout(container) {
  const cardChoice = document.getElementById("payment-card");
  const fallback = document.querySelector("[data-hosted-card]");
  const status = document.querySelector("[data-card-status]");
  let checkout;
  let loading = false;
  let mounted = false;

  async function fetchClientSecret() {
    const payload = new FormData(fallback);
    payload.set("method", "embedded_card");
    const response = await fetch(fallback.action, {method: "POST", body: payload});
    if (!response.ok || response.redirected) {
      throw new Error("Card form unavailable");
    }
    const data = await response.json();
    if (data.redirect) {
      window.location.assign(data.redirect);
      throw new Error("Returning to enrolment");
    }
    if (!data.clientSecret) {
      throw new Error("Card form unavailable");
    }
    return data.clientSecret;
  }

  async function updateCardForm() {
    if (!cardChoice.checked) {
      if (mounted) {
        checkout.unmount();
        mounted = false;
      }
      return;
    }
    if (loading || mounted) {
      return;
    }

    fallback.hidden = true;
    loading = true;
    status.textContent = "Loading card form…";
    try {
      if (!checkout) {
        await loadStripeCheckout();
        const stripe = window.Stripe(container.dataset.embeddedKey);
        checkout = await stripe.createEmbeddedCheckoutPage({fetchClientSecret});
      }
      if (cardChoice.checked) {
        checkout.mount(container);
        mounted = true;
      }
      status.textContent = "";
    } catch {
      if (checkout) {
        checkout.destroy();
        checkout = undefined;
      }
      status.textContent = "The inline card form is unavailable. Continue to card payment to try again.";
      fallback.hidden = false;
    } finally {
      loading = false;
    }
  }

  cardChoice.closest("fieldset").addEventListener("change", updateCardForm);
  updateCardForm();
}

function loadStripeCheckout() {
  if (window.Stripe) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://js.stripe.com/endive/stripe.js";
    script.onload = resolve;
    script.onerror = () => {
      script.remove();
      reject(new Error("Card form unavailable"));
    };
    document.head.append(script);
  });
}
