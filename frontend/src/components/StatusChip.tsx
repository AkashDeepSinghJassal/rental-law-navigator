import { STATUS_ICON } from "../lib/domain";
import { STATUS_LABEL } from "../lib/i18n";
import { usePrefs } from "../lib/prefs";
import type { ResultStatus } from "../lib/types";

/** Status is always written in words with an icon, never colour alone. */
export function StatusChip({ status }: { status: ResultStatus }) {
  const { lang } = usePrefs();
  return (
    <span className={`chip s-${status}`}>
      <span aria-hidden="true">{STATUS_ICON[status]}</span> {STATUS_LABEL[lang][status]}
    </span>
  );
}
