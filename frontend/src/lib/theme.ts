import { useSyncExternalStore } from "react";

const query = window.matchMedia("(prefers-color-scheme: dark)");

function apply(): void {
  document.documentElement.classList.toggle("dark", query.matches);
}

/** Follows the OS colour scheme by toggling shadcn's `.dark` class. */
export function initTheme(): void {
  apply();
  query.addEventListener("change", apply);
}

export function useIsDark(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    },
    () => query.matches,
  );
}
