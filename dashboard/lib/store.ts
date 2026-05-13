import { create } from "zustand";

export interface FilterState {
  subreddits: string[];
  parents: string[];
  dateRange: [string, string];
  setSubreddits: (next: string[]) => void;
  setParents: (next: string[]) => void;
  setDateRange: (next: [string, string]) => void;
}

export const useFilterStore = create<FilterState>((set) => ({
  subreddits: [],
  parents: [],
  dateRange: ["", ""],
  setSubreddits: (subreddits) => set({ subreddits }),
  setParents: (parents) => set({ parents }),
  setDateRange: (dateRange) => set({ dateRange }),
}));
