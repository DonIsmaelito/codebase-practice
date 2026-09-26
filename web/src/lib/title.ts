import { useEffect } from "react";

/** The browser tab shows where you are (a page, or the client you're working for). */
export function usePageTitle(title: string | undefined | null): void {
  useEffect(() => {
    if (title) document.title = title;
  }, [title]);
}
