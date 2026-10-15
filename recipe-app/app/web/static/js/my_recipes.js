import { api } from "./api.js";
import { sessionReady } from "./auth.js";
import { message, renderRecipes, renderPagination } from "./ui.js";

let page = 1;
let requestNumber = 0;
async function load() {
  const currentRequest = ++requestNumber;
  document.getElementById("previous-page").disabled = true;
  document.getElementById("next-page").disabled = true;
  message("page-error", "");
  try {
    const status = document.getElementById("status-filter").value;
    const data = await api(`/recipes/mine?page=${page}&page_size=12&${status ? `status=${status}` : ""}`, { protectedAction: true });
    if (currentRequest !== requestNumber) return;
    renderRecipes(data.items);
    renderPagination(data);
    message("list-status", data.items.length ? "" : "Рецептів із таким станом ще немає.");
  } catch (error) {
    if (currentRequest === requestNumber) { message("list-status", ""); message("page-error", error.message); }
  } finally {
    if (currentRequest === requestNumber) {
      document.getElementById("previous-page").disabled = false;
      document.getElementById("next-page").disabled = false;
    }
  }
}
document.getElementById("status-filter").addEventListener("change", () => { page = 1; load(); });
document.getElementById("previous-page").addEventListener("click", () => { page--; load(); });
document.getElementById("next-page").addEventListener("click", () => { page++; load(); });
const session = await sessionReady;
if (session === null) window.location.assign("/login");
else if (session) load();
