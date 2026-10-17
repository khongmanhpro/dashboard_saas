import { useStaffDetail } from "../api/staff";
import type { Me } from "../api/types";
import { format, t } from "../i18n";
import { Funnel, Parts } from "../pages/staff/StaffDetailPage";
import { TierBadge } from "../pages/staff/StaffPage";
import { formatScore } from "../staff/format";

export function MyScoreScreen({ me }: { me: Me }) {
  const detail = useStaffDetail(me.member.id, "week");
  const data = detail.data;
  return (
    <div className="m-pad m-stack">
      <h1 className="m-title">{t.mobile.score.title}</h1>
      {data ? (
        <>
          <div className="staff-score">
            <TierBadge tier={data.tier} />
            <span>
              <b>{data.total === null ? t.staff.insufficient : format(t.staffDetail.points, { n: formatScore(data.total) })}</b>
              {data.rank !== null ? (
                <span className="muted">{format(t.staffDetail.rankOf, { rank: data.rank, total: data.ranked_count })}</span>
              ) : null}
            </span>
          </div>
          <Parts data={data} canFormula={false} />
          <Funnel data={data} />
        </>
      ) : (
        <div className="muted">{t.app.loading}</div>
      )}
    </div>
  );
}
