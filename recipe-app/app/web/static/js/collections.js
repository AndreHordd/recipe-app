import { api } from "./api.js";
import { sessionReady } from "./auth.js";
import { element, message, renderPagination } from "./ui.js";

const form = document.getElementById("collection-create");
let page = 1;
let requestNumber = 0;

async function load() {
  const currentRequest = ++requestNumber;
  const buttons = [document.getElementById("previous-page"), document.getElementById("next-page")];
  buttons.forEach(button => { button.disabled = true; });
  message("page-error", "");
  try {
    const data = await api(`/collections?page=${page}&page_size=12`, { protectedAction: true });
    if (currentRequest !== requestNumber) return;
    const list = document.getElementById("collection-list");
    list.replaceChildren();
    for (const collection of data.items) {
      const card = element("article", "", "panel recipe-card");
      const heading = element("h2");
      const link = element("a", collection.name);
      link.href = `/collections/${collection.id}`;
      heading.append(link);
      card.append(heading, element("p", `Створено ${new Date(collection.created_at).toLocaleDateString("uk-UA")}`, "muted"));
      list.append(card);
    }
    renderPagination(data);
    message("list-status", data.items.length ? "" : "Колекцій поки немає. Створіть першу добірку.");
  } catch (error) {
    if (currentRequest === requestNumber) { message("list-status", ""); message("page-error", error.message); }
  } finally {
    if (currentRequest === requestNumber) buttons.forEach(button => { button.disabled = false; });
  }
}

if (form) form.addEventListener("submit", async event => {
  event.preventDefault();
  message("form-error", "");
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    const collection = await api("/collections", {
      method: "POST", body: { name: form.elements.namedItem("name").value }, protectedAction: true,
    });
    window.location.assign(`/collections/${collection.id}`);
  } catch (error) { message("form-error", error.message); }
  finally { button.disabled = false; }
});
document.getElementById("previous-page").addEventListener("click", () => { page--; load(); });
document.getElementById("next-page").addEventListener("click", () => { page++; load(); });

const session = await sessionReady;
if (session === null) window.location.assign("/login");
else if (session) { if (form) form.hidden = false; load(); }
