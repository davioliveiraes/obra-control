import { SessionStatus } from "../auth/SessionStatus";
import type { AuthSession } from "../auth/useAuthSession";
import { OrganizationSection } from "./OrganizationSection";
import { useOrganizationContext } from "./useOrganizationContext";

export function AuthenticatedSession({
  session,
  notify,
}: {
  session: AuthSession;
  notify: () => void;
}) {
  const context = useOrganizationContext(session, notify);
  return (
    <>
      <SessionStatus
        state={session.state}
        onVerify={session.verify}
        onLogin={session.login}
        onLogout={session.logout}
        logoutDisabled={context.mutationBlocked}
      />
      <OrganizationSection
        key={context.revision}
        state={context.state}
        onSelect={context.select}
        onClear={context.clear}
        onVerify={context.recover}
      />
    </>
  );
}
