import { AlertCircle, LoaderCircle } from "lucide-react";

export function LoadingState() {
  return (
    <div className="page-state" role="status">
      <LoaderCircle className="spin" size={24} aria-hidden="true" />
      <span>正在读取数据…</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="page-state error-state" role="alert">
      <AlertCircle size={24} aria-hidden="true" />
      <div>
        <strong>数据没有加载成功</strong>
        <p>{message}</p>
      </div>
      <button type="button" onClick={onRetry}>重新加载</button>
    </div>
  );
}
