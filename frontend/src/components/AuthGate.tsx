import { KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";

interface AuthGateProps {
  onConnect: (token: string, remember: boolean) => Promise<void>;
}

export function AuthGate({ onConnect }: AuthGateProps) {
  const [token, setToken] = useState("");
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = token.trim();
    if (!value) return;
    setError("");
    setIsSubmitting(true);
    try {
      await onConnect(value, remember);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法验证 API Key，请稍后重试");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-shell" id="main-content">
      <section className="auth-card" aria-labelledby="auth-title">
        <div className="auth-mark" aria-hidden="true">
          <KeyRound size={24} />
        </div>
        <p className="eyebrow">Z · PERSONAL DATA</p>
        <h1 id="auth-title">连接你的数据</h1>
        <p className="auth-copy">可粘贴 API Key、Bearer Token 或完整 Authorization 值。默认只保存在当前浏览器会话中。</p>
        <form onSubmit={submit}>
          <label htmlFor="api-key">API Key</label>
          <input
            id="api-key"
            name="api-key"
            type="password"
            autoComplete="current-password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="例如 Bearer xxxxx，或仅粘贴 xxxxx"
            required
            autoFocus
          />
          {error && <p className="form-error" role="alert">{error}</p>}
          <label className="check-row">
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
            />
            <span>在这台设备上记住</span>
          </label>
          <button className="primary-button" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "正在验证…" : "查看睡眠状态"}
          </button>
        </form>
      </section>
    </main>
  );
}
