import React from "react";
import { isTauri } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";

interface ExternalLinkProps {
  href: string;
  className?: string;
  children: React.ReactNode;
}

const getSafeUrl = (value: string): string | null => {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
};

const ExternalLink: React.FC<ExternalLinkProps> = ({ href, className, children }) => {
  const [error, setError] = React.useState<string | null>(null);
  const safeUrl = getSafeUrl(href);

  if (!safeUrl) {
    return <>{children}</>;
  }

  const handleClick = async (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (!isTauri()) {
      return;
    }

    event.preventDefault();
    setError(null);
    try {
      await openUrl(safeUrl);
    } catch (openError) {
      setError(
        `Could not open link: ${openError instanceof Error ? openError.message : String(openError)}`,
      );
    }
  };

  return (
    <>
      <a href={safeUrl} target="_blank" rel="noreferrer" className={className} onClick={(event) => void handleClick(event)}>
        {children}
      </a>
      {error && <span role="alert" className="ml-2 text-xs text-red-600">{error}</span>}
    </>
  );
};

export default ExternalLink;
