import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const PARENT_PALETTE: Record<string, string> = {
  ANTHROPIC: "#d97757",
  OPENAI: "#10a37f",
  GOOGLE: "#4285f4",
  AI_INFRA: "#76b900",
  OPEN_SOURCE: "#a78bfa",
  ML_RESEARCH: "#f59e0b",
  OTHER: "#94a3b8",
};

export function parentColor(parentId: string | null | undefined): string {
  if (!parentId) return PARENT_PALETTE.OTHER;
  return PARENT_PALETTE[parentId] ?? PARENT_PALETTE.OTHER;
}
