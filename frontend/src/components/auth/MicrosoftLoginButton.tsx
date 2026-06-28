import { Button } from "@/components/ui/button";

interface MicrosoftLoginButtonProps {
  onClick?: () => void;
  disabled?: boolean;
}

/**
 * Single "Sign in with SSO" button (Epic 23). Navigates the browser to the
 * backend SSO login endpoint; carries the Microsoft brand mark since the
 * corporate IdP is Azure Entra ID.
 */
export function MicrosoftLoginButton({
  onClick,
  disabled,
}: MicrosoftLoginButtonProps) {
  return (
    <Button
      onClick={onClick}
      disabled={disabled}
      data-testid="sso-login-button"
      className="w-full h-12 bg-[#2F2F2F] hover:bg-[#1F1F1F] text-white font-semibold rounded-lg flex items-center justify-center gap-3 transition-colors"
    >
      <MicrosoftLogo />
      <span>Sign in with SSO</span>
    </Button>
  );
}

function MicrosoftLogo() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 21 21"
      className="w-5 h-5"
      aria-hidden="true"
    >
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  );
}
