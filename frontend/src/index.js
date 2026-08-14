import React from "react";
import ReactDOM from "react-dom/client";
import axios from "axios";
import "@/index.css";
import App from "@/App";

axios.defaults.withCredentials = true;
axios.interceptors.request.use((config) => {
  if (["post", "put", "patch", "delete"].includes((config.method || "get").toLowerCase())) {
    const csrf = sessionStorage.getItem("accounts_csrf");
    if (csrf) config.headers["X-CSRF-Token"] = csrf;
  }
  return config;
});

axios.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestUrl = error.config?.url || "";
    if (error.response?.status === 401 && !requestUrl.includes("/auth/login") && !requestUrl.includes("/auth/me")) {
      sessionStorage.removeItem("accounts_csrf");
      window.dispatchEvent(new Event("accounts-session-expired"));
    }
    return Promise.reject(error);
  }
);

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
