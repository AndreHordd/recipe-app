import { api } from "/static/js/api.js";
import { sessionReady } from "/static/js/auth.js";

const form = document.getElementById("collection-create");
const error = document.getElementById("form-error");
const session = await sessionReady;
if (session === null) window.location.assign("/login");

form.addEventListener("submit", async event => {
  event.preventDefault();
  error.hidden = true;
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    const collection = await api("/collections", { method: "POST", body: { name: form.elements.namedItem("name").value }, protectedAction: true });
    window.location.assign(`/collections/${collection.id}`);
  } catch (requestError) {
    error.textContent = requestError.message;
    error.hidden = false;
  } finally { button.disabled = false; }
});
