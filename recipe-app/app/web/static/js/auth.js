import { api, loadSession, setSession } from "./api.js";

function showMessage(id, message) {
  const element = document.getElementById(id);
  if (!element) return;
  element.textContent = message;
  element.hidden = !message;
}

function renderSession(session) {
  document.getElementById("guest-navigation").hidden = !!session;
  document.getElementById("user-navigation").hidden = !session;
  document.getElementById("navigation-name").textContent = session?.user.display_name || "";
  document.getElementById("admin-navigation").hidden = session?.user.role !== "ADMIN";
  const guest = document.getElementById("guest-account");
  const user = document.getElementById("user-account");
  if (guest) guest.hidden = !!session;
  if (user) {
    user.hidden = !session;
    document.getElementById("account-name").textContent = session?.user.display_name || "";
    document.getElementById("account-email").textContent = session?.user.email || "";
  }
}

export const sessionReady = loadSession().then(session => {
  renderSession(session);
  return session;
}).catch(error => {
  showMessage("page-error", error.message);
  document.getElementById("guest-navigation").hidden = false;
});

const form = document.getElementById("auth-form");
if (form) {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    showMessage("form-error", "");
    showMessage("form-success", "");
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const body = Object.fromEntries(new FormData(form));
      if (form.dataset.mode === "register") {
        await api("/auth/register", { method: "POST", body });
        form.reset();
        showMessage("form-success", "Обліковий запис створено. Тепер увійдіть за своєю адресою та паролем.");
      } else {
        const session = await api("/auth/login", { method: "POST", body });
        setSession(session);
        window.location.assign("/");
      }
    } catch (error) {
      showMessage("form-error", error.message);
      for (const field of error.fields || []) {
        const input = form.elements.namedItem(field.field);
        if (input) { input.focus(); break; }
      }
    } finally {
      button.disabled = false;
    }
  });
}

document.getElementById("logout-button").addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await sessionReady;
    await api("/auth/logout", { method: "POST", protectedAction: true });
    setSession(null);
    window.location.assign("/");
  } catch (error) {
    showMessage("page-error", error.message);
  } finally {
    button.disabled = false;
  }
});
