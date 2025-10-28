// src/lib/api.js
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const api = axios.create({ baseURL: API_BASE });

const TOKENS_KEY = "auth_tokens";
export const getTokens = () => JSON.parse(localStorage.getItem(TOKENS_KEY) || "{}");
export const setTokens = (t) => localStorage.setItem(TOKENS_KEY, JSON.stringify(t));
export const clearTokens = () => localStorage.removeItem(TOKENS_KEY);

// Attach bearer for every request
api.interceptors.request.use((cfg) => {
  const { access_token } = getTokens();
  if (access_token) cfg.headers.Authorization = `Bearer ${access_token}`;
  return cfg;
});

// Auto-refresh access token on a single 401
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const { response, config } = err || {};
    const original = config || {};

    if (response?.status === 401 && !original._retried) {
      const { refresh_token } = getTokens() || {};
      if (!refresh_token) {
        clearTokens();
        throw err;
      }
      try {
        const { data } = await axios.post(
          `${API_BASE}/auth/refresh`,
          { refresh_token },
          { headers: { "Content-Type": "application/json" } }
        );
        setTokens(data);
        original._retried = true;
        original.headers = original.headers || {};
        original.headers.Authorization = `Bearer ${data.access_token}`;
        api.defaults.headers.common.Authorization = `Bearer ${data.access_token}`;
        return api.request(original);
      } catch (e) {
        clearTokens();
        throw err;
      }
    }
    throw err;
  }
);

export const auth = {
  signin: async (email, password) => {
    const { data } = await api.post("/auth/signin", { email, password });
    setTokens(data);
    return data;
  },
  signup: async (email, password) => {
    const { data } = await api.post("/auth/signup", { email, password });
    setTokens(data);
    return data;
  },
  refresh: async () => {
    const { refresh_token } = getTokens();
    const { data } = await api.post("/auth/refresh", { refresh_token });
    setTokens(data);
    return data;
  },
  logout: async () => {
    // Backend expects body with refresh_token
    const { refresh_token } = getTokens();
    try {
      if (refresh_token) {
        await api.post("/auth/logout", { refresh_token });
      } else {
        await api.post("/auth/logout"); // ok if BE tolerates empty body
      }
    } finally {
      clearTokens();
    }
  },
};

export const chats = {
  list: () => api.get("/chats").then((r) => r.data),
  create: (title) => api.post("/chats", { title }).then((r) => r.data),
  patch: (id, body) => api.patch(`/chats/${id}`, body).then((r) => r.data),
  remove: (id) => api.delete(`/chats/${id}`).then((r) => r.data),
};

export const messages = {
  // list: (chatId) => api.get(`/messages/${chatId}`).then((r) => r.data),
  // send: (chatId, prompt) =>
  //   api.post(`/messages/${chatId}`, { prompt }).then((r) => r.data),

  list: (chatId) => api.get(`/messages/${chatId}`).then((r) => r.data),
  send: (chatId, prompt, requestId) =>
    api.post(`/messages/${chatId}`, { prompt, request_id: requestId }).then((r) => r.data),
};

// UIA survey submissions (Phase C)
export const uia = {
  submitEmployment: ({ chat_id, employment_category_id, vault_version }) =>
    api.post("/uia/submit/employment", {
      chat_id,
      employment_category_id,
      vault_version,
    }).then((r) => r.data),

  submitSkills: ({ chat_id, employment_category_id, vault_version, let_system_decide, skills_selected }) =>
    api.post("/uia/submit/skills", {
      chat_id,
      employment_category_id,
      vault_version,
      let_system_decide: !!let_system_decide,
      skills_selected: let_system_decide ? undefined : skills_selected,
    }).then((r) => r.data),
};

// (Optional) Read current UIA state badge
export const uiaState = {
  get: (chatId) => api.get(`/chats/${chatId}/uia-state`).then((r) => r.data),
};

export const insights = {
  submit: (payload) => api.post("/insights/submit", payload).then((r) => r.data),
};
