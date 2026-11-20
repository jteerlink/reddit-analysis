import { create } from "zustand";

export interface FilterState {
  subreddits: string[];
  parents: string[];
  dateRange: [string, string];
  setSubreddits: (next: string[]) => void;
  setParents: (next: string[]) => void;
  setDateRange: (next: [string, string]) => void;
}

/** Build the shared query string used by every scoped dashboard view. */
export function buildFilterQuery(
  subreddits: string[],
  parents: string[],
  dateRange: [string, string],
): string {
  const params = new URLSearchParams();
  subreddits.forEach((subreddit) => params.append("subreddits", subreddit));
  parents.forEach((parent) => params.append("parents", parent));
  if (dateRange[0]) params.set("start", dateRange[0]);
  if (dateRange[1]) params.set("end", dateRange[1]);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export const useFilterStore = create<FilterState>((set) => ({
  subreddits: [],
  parents: [],
  dateRange: ["", ""],
  setSubreddits: (subreddits) => set({ subreddits }),
  setParents: (parents) => set({ parents }),
  setDateRange: (dateRange) => set({ dateRange }),
}));
