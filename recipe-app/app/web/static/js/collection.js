import { api } from "./api.js";
import { sessionReady } from "./auth.js";
import { element, message, recipeCard, renderPagination } from "./ui.js";

const content = document.getElementById("collection-content");
const id = content.dataset.collectionId;
const form = document.getElementById("collection-rename");
let page = 1;
let requestNumber = 0;

function renderCollection(collection) {
  document.title = `${collection.name} · Кулінарні рецепти`;
  document.getElementById("collection-title").textContent = collection.name;
  form.elements.namedItem("name").value = collection.name;
  content.hidden = false;
}

async function loadEntries() {
  const currentRequest = ++requestNumber;
  const buttons = [document.getElementById("previous-page"), document.getElementById("next-page")];
  buttons.forEach(button => { button.disabled = true; });
  message("page-error", "");
  try {
    const data = await api(`/collections/${id}/recipes?page=${page}&page_size=12`, { protectedAction: true });
    if (currentRequest !== requestNumber) return;
    if (data.items.length === 0 && page > 1) { page--; await loadEntries(); return; }
    const list = document.getElementById("recipe-list");
    list.replaceChildren();
    for (const entry of data.items) {
      const card = entry.available ? recipeCard(entry.recipe) : element("article", "", "panel recipe-card");
      if (!entry.available) card.append(element("h2", "Рецепт недоступний"));
      card.append(element("p", `Збережено ${new Date(entry.saved_at).toLocaleDateString("uk-UA")}`, "muted"));
      const remove = element("button", "Вилучити з колекції", "secondary");
      remove.type = "button";
      remove.addEventListener("click", async () => {
        remove.disabled = true;
        try {
          await api(`/collections/${id}/recipes/${entry.recipe_id}`, { method: "DELETE", protectedAction: true });
          await loadEntries();
        } catch (error) { message("page-error", error.message); remove.disabled = false; }
      });
      card.append(remove);
      list.append(card);
    }
    renderPagination(data);
    message("list-status", data.items.length ? "" : "Колекція порожня. Знайдіть рецепт у каталозі та збережіть його сюди.");
  } catch (error) {
    if (currentRequest === requestNumber) {
      message("list-status", ""); message("page-error", error.message);
      if (error.status === 404) content.hidden = true;
    }
  } finally {
    if (currentRequest === requestNumber) buttons.forEach(button => { button.disabled = false; });
  }
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  message("form-error", ""); message("form-success", "");
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    const collection = await api(`/collections/${id}`, {
      method: "PUT", body: { name: form.elements.namedItem("name").value }, protectedAction: true,
    });
    renderCollection(collection); message("form-success", "Назву збережено.");
  } catch (error) { message("form-error", error.message); }
  finally { button.disabled = false; }
});
document.getElementById("delete-collection").addEventListener("click", async event => {
  if (!window.confirm("Видалити колекцію? Збережені рецепти залишаться в каталозі, але добірку відновити не можна.")) return;
  event.currentTarget.disabled = true;
  try {
    await api(`/collections/${id}`, { method: "DELETE", protectedAction: true });
    window.location.assign("/collections");
  } catch (error) { message("page-error", error.message); document.getElementById("delete-collection").disabled = false; }
});
document.getElementById("previous-page").addEventListener("click", () => { page--; loadEntries(); });
document.getElementById("next-page").addEventListener("click", () => { page++; loadEntries(); });

const session = await sessionReady;
if (session === null) window.location.assign("/login");
else if (session) {
  try { renderCollection(await api(`/collections/${id}`, { protectedAction: true })); await loadEntries(); }
  catch (error) { message("page-error", error.message); }
}
message("collection-loading", "");
