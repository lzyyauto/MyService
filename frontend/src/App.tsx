import { useState } from "react";
import { ApiError, getSleepDashboard, normalizeApiKey } from "./api";
import { AuthGate } from "./components/AuthGate";
import { SleepPage } from "./pages/SleepPage";
import { SportPage } from "./pages/SportPage";
import { currentMonth } from "./utils";

const STORAGE_KEY = "z-dashboard-api-key";

function initialToken() {
  const stored = sessionStorage.getItem(STORAGE_KEY) ?? localStorage.getItem(STORAGE_KEY) ?? "";
  return normalizeApiKey(stored);
}

export default function App() {
  const [token, setToken] = useState(initialToken);
  const isSportPage = window.location.pathname.replace(/\/$/, "") === "/sport";
  document.title = isSportPage ? "运动记录" : "睡眠状态";

  async function connect(value: string, remember: boolean) {
    const apiKey = normalizeApiKey(value);
    if (!apiKey) throw new Error("请输入 API Key");
    try {
      await getSleepDashboard(apiKey, "month", currentMonth(), 1);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        throw new Error("API Key 无效，或粘贴内容不完整。请确认使用的是系统用户的 api_key。");
      }
      throw cause;
    }
    sessionStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_KEY);
    (remember ? localStorage : sessionStorage).setItem(STORAGE_KEY, apiKey);
    setToken(apiKey);
  }

  function disconnect() {
    sessionStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STORAGE_KEY);
    setToken("");
  }

  if (!token) return <AuthGate onConnect={connect} />;
  return isSportPage ? <SportPage token={token} onDisconnect={disconnect} /> : <SleepPage token={token} onDisconnect={disconnect} />;
}
