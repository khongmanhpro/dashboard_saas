import { usePublicConfig } from "../auth/useAuth";
import { t } from "../i18n";

/** Tiêu đề màn hình, kèm nhãn "Dữ liệu mẫu" khi chạy MOCK_MODE (theo thiết kế). */
export function PageHeader({ title }: { title: string }) {
  const config = usePublicConfig();
  return (
    <div className="page-header">
      <h1>{title}</h1>
      {config.data?.mock_mode ? <span className="badge-sample">{t.app.sampleData}</span> : null}
    </div>
  );
}
