let currentSession = null;

export class ApiError extends Error {
  constructor(status, data) {
    super(data?.error?.message || "Не вдалося виконати запит.");
    this.status = status;
    this.code = data?.error?.code;
    this.fields = data?.error?.fields || [];
  }
}

export function setSession(session) { currentSession = session; }
export function getSession() { return currentSession; }

export async function api(path, { method = "GET", body, binary = false, protectedAction = false } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = binary ? body.type || "application/octet-stream" : "application/json";
  if (method !== "GET" && currentSession) headers["X-CSRF-Token"] = currentSession.csrf_token;
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method, headers, credentials: "same-origin", cache: "no-store",
      body: body === undefined ? undefined : binary ? body : JSON.stringify(body),
    });
  } catch {
    throw new Error("Немає зв’язку із сервером. Спробуйте ще раз.");
  }
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok) {
    if (response.status === 401 && protectedAction) {
      setSession(null);
      window.location.assign("/login");
    }
    throw new ApiError(response.status, data);
  }
  return data;
}

export async function loadSession() {
  try {
    const session = await api("/auth/me");
    setSession(session);
    return session;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      setSession(null);
      return null;
    }
    throw error;
  }
}
