import { createContext, useContext, ReactNode } from "react";
import { lightThemeColors, darkThemeColors, ThemeColors } from "./colors";

interface ThemeContextType {
  isDarkMode: boolean;
  colors: ThemeColors;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

interface ThemeProviderProps {
  children: ReactNode;
  isDarkMode: boolean;
}

export function ThemeProvider({ children, isDarkMode }: ThemeProviderProps) {
  const colors = isDarkMode ? darkThemeColors : lightThemeColors;

  return (
    <ThemeContext.Provider value={{ isDarkMode, colors }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
