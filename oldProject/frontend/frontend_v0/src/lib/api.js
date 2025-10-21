// src/lib/api.js
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const api = axios.create({ baseURL: API_BASE });

const TOKENS_KEY = "auth_tokens";
export const getTokens = () => JSON.parse(localStorage.getItem(TOKENS_KEY) || "{}");
export const setTokens = (t) => localStorage.setItem(TOKENS_KEY, JSON.stringify(t));
export const clearTokens = () => localStorage.removeItem(TOKENS_KEY);

// Attach bearer
api.interceptors.request.use((cfg) => {
  const { access_token } = getTokens();
  if (access_token) cfg.headers.Authorization = `Bearer ${access_token}`;
  return cfg;
});

// Silent refresh on 401
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const { response, config } = err || {};
    const original = config || {};
    if (response?.status === 401 && !original._retried) {
      const { refresh_token } = getTokens();
      if (refresh_token) {
        try {
          const { data } = await axios.post(
            `${API_BASE}/auth/refresh?refresh_token=${encodeURIComponent(refresh_token)}`
          );
          setTokens(data);
          original._retried = true;
          original.headers = original.headers || {};
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return api.request(original);
        } catch (e) {
          clearTokens();
        }
      }
    }
    throw err;
  }
);

// === Real backend APIs ===
export const auth = {
  signup: (email, password) =>
    api.post("/auth/signup", { email, password }).then(({ data }) => (setTokens(data), data)),
  signin: (email, password) =>
    api.post("/auth/signin", { email, password }).then(({ data }) => (setTokens(data), data)),
  refresh: (refresh_token) =>
    api.post(`/auth/refresh?refresh_token=${encodeURIComponent(refresh_token)}`).then(({ data }) => (setTokens(data), data)),
  logout: () => api.post("/auth/logout").finally(clearTokens),
};

export const chats = {
  list: () => api.get("/chats").then((r) => r.data),
  create: (title) => api.post("/chats", { title }).then((r) => r.data),
  patch: (id, body) => api.patch(`/chats/${id}`, body).then((r) => r.data),
};

export const messages = {
  list: (chatId) => api.get(`/messages/${chatId}`).then((r) => r.data),
  send: (chatId, prompt) => api.post(`/messages/${chatId}`, { prompt }).then((r) => r.data),
};

// === Legacy test endpoint (kept for reference; not used now) ===
// export async function sendMessage(chatId, text) {
//   const { data } = await api.post("/chat/send", { chat_id: chatId, message: text });
//   return { reply: data.message, raw: data };
// }