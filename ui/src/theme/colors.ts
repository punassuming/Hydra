/**
 * Theme colors for Hydra Scheduler UI
 * Provides consistent colors that work in both light and dark modes
 */

export interface ThemeColors {
  // Primary brand colors
  primary: string;
  primaryHover: string;
  
  // Status colors
  success: string;
  error: string;
  warning: string;
  info: string;
  
  // Text colors
  textPrimary: string;
  textSecondary: string;
  textDisabled: string;
  
  // Background colors
  bgPrimary: string;
  bgSecondary: string;
  bgTertiary: string;
  
  // Border colors
  border: string;
  borderLight: string;
  
  // Special purpose colors
  headerBg: string;
  cardHover: string;
  logBg: string;
  logText: string;
  logErrorBg: string;
}

export const lightThemeColors: ThemeColors = {
  // Primary brand colors
  primary: "#2563eb",
  primaryHover: "#1d4ed8",
  
  // Status colors
  success: "#52c41a",
  error: "#f5222d",
  warning: "#fa8c16",
  info: "#1890ff",
  
  // Text colors
  textPrimary: "#0f172a",
  textSecondary: "#64748b",
  textDisabled: "#94a3b8",
  
  // Background colors
  bgPrimary: "#ffffff",
  bgSecondary: "#f5f7fb",
  bgTertiary: "#f5f5f5",
  
  // Border colors
  border: "#e2e8f0",
  borderLight: "#cbd5e1",
  
  // Special purpose colors
  headerBg: "#0f172a",
  cardHover: "#f0f5ff",
  logBg: "#1e1e1e",
  logText: "#d4d4d4",
  logErrorBg: "#2e1e1e",
};

export const darkThemeColors: ThemeColors = {
  // Primary brand colors
  primary: "#38bdf8",
  primaryHover: "#0ea5e9",
  
  // Status colors
  success: "#52c41a",
  error: "#ff4d4f",
  warning: "#fa8c16",
  info: "#1890ff",
  
  // Text colors
  textPrimary: "#f1f5f9",
  textSecondary: "#cbd5f5",
  textDisabled: "#64748b",
  
  // Background colors
  bgPrimary: "#0f172a",
  bgSecondary: "#1e293b",
  bgTertiary: "#334155",
  
  // Border colors
  border: "#334155",
  borderLight: "#475569",
  
  // Special purpose colors
  headerBg: "#050b18",
  cardHover: "#1e293b",
  logBg: "#0a0f1e",
  logText: "#e2e8f0",
  logErrorBg: "#1e0a0a",
};
