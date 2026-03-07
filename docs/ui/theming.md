# Hydra UI Theming System

## Overview

The Hydra Scheduler UI now uses a centralized theming system to ensure consistent colors across light and dark modes. All hard-coded color values have been replaced with theme references.

## Architecture

### Theme Structure

The theming system consists of three main files:

1. **`theme/colors.ts`** - Defines color palettes for light and dark themes
2. **`theme/ThemeContext.tsx`** - Provides ThemeProvider and useTheme hook
3. **`theme/index.ts`** - Public exports

### Color Categories

Colors are organized into semantic categories:

- **Primary Brand Colors**: `primary`, `primaryHover`
- **Status Colors**: `success`, `error`, `warning`, `info`
- **Text Colors**: `textPrimary`, `textSecondary`, `textDisabled`
- **Background Colors**: `bgPrimary`, `bgSecondary`, `bgTertiary`
- **Border Colors**: `border`, `borderLight`
- **Special Purpose**: `headerBg`, `cardHover`, `logBg`, `logText`, `logErrorBg`

## Usage

### Accessing Theme Colors

Use the `useTheme` hook in any component:

```typescript
import { useTheme } from "../theme";

function MyComponent() {
  const { colors, isDarkMode } = useTheme();
  
  return (
    <div style={{ 
      background: colors.bgPrimary,
      color: colors.textPrimary,
      borderColor: colors.border
    }}>
      <span style={{ color: colors.success }}>Success!</span>
      <span style={{ color: colors.error }}>Error!</span>
    </div>
  );
}
```

### Setting Up ThemeProvider

The ThemeProvider is already set up in `App.tsx`:

```typescript
function App() {
  const [darkMode, setDarkMode] = useState(false);
  
  return (
    <ThemeProvider isDarkMode={darkMode}>
      <AppContent darkMode={darkMode} setDarkMode={setDarkMode} />
    </ThemeProvider>
  );
}
```

## Color Palettes

### Light Theme

```typescript
{
  primary: "#2563eb",
  success: "#52c41a",
  error: "#f5222d",
  warning: "#fa8c16",
  info: "#1890ff",
  textPrimary: "#0f172a",
  textSecondary: "#64748b",
  bgPrimary: "#ffffff",
  bgSecondary: "#f5f7fb",
  // ... more colors
}
```

### Dark Theme

```typescript
{
  primary: "#38bdf8",
  success: "#52c41a",
  error: "#ff4d4f",
  warning: "#fa8c16",
  info: "#1890ff",
  textPrimary: "#f1f5f9",
  textSecondary: "#cbd5f5",
  bgPrimary: "#0f172a",
  bgSecondary: "#1e293b",
  // ... more colors
}
```

## Examples

### Status Indicators

```typescript
function StatusIndicator({ status }: { status: string }) {
  const { colors } = useTheme();
  
  const statusColor = status === "success" 
    ? colors.success 
    : status === "error" 
    ? colors.error 
    : colors.warning;
  
  return <div style={{ color: statusColor }}>{status}</div>;
}
```

### Themed Cards

```typescript
function ThemedCard({ children }: { children: ReactNode }) {
  const { colors } = useTheme();
  
  return (
    <Card 
      style={{ 
        background: colors.bgPrimary,
        borderColor: colors.border
      }}
      hoverable
      styles={{
        body: { color: colors.textPrimary }
      }}
    >
      {children}
    </Card>
  );
}
```

### Log Viewer with Theme

```typescript
function LogViewer({ stdout, stderr }: LogViewerProps) {
  const { colors } = useTheme();
  
  const logStyle = {
    background: colors.logBg,
    color: colors.logText,
    padding: 16,
  };
  
  const errorLogStyle = {
    ...logStyle,
    background: colors.logErrorBg,
  };
  
  return (
    <div>
      <pre style={logStyle}>{stdout}</pre>
      <pre style={errorLogStyle}>{stderr}</pre>
    </div>
  );
}
```

## Adding New Colors

To add a new color to the theme:

1. Update the `ThemeColors` interface in `theme/colors.ts`:

```typescript
export interface ThemeColors {
  // ... existing colors
  myNewColor: string;
}
```

2. Add the color to both theme palettes:

```typescript
export const lightThemeColors: ThemeColors = {
  // ... existing colors
  myNewColor: "#abc123",
};

export const darkThemeColors: ThemeColors = {
  // ... existing colors
  myNewColor: "#def456",
};
```

3. Use the new color in components:

```typescript
const { colors } = useTheme();
<div style={{ color: colors.myNewColor }} />
```

## Best Practices

1. **Always use theme colors** - Never hard-code hex values
2. **Choose semantic colors** - Use `success`/`error`/`warning` for status, not specific shades
3. **Test in both modes** - Verify components look good in light and dark themes
4. **Be consistent** - Use the same color for the same purpose across components
5. **Consider accessibility** - Ensure sufficient contrast in both themes

## Migration Guide

To migrate a component from hard-coded colors to the theme:

1. Import the useTheme hook:
```typescript
import { useTheme } from "../theme";
```

2. Get the colors object:
```typescript
const { colors } = useTheme();
```

3. Replace hard-coded colors:
```typescript
// Before
<div style={{ color: "#52c41a" }} />

// After
<div style={{ color: colors.success }} />
```

## Testing

When writing tests, ensure components are wrapped in ThemeProvider:

```typescript
import { ThemeProvider } from "../theme";

test("component renders correctly", () => {
  render(
    <ThemeProvider isDarkMode={false}>
      <MyComponent />
    </ThemeProvider>
  );
});
```

The test utilities in `test/utils.tsx` already include ThemeProvider.

## Future Enhancements

Potential improvements to the theming system:

- User-customizable color schemes
- Theme persistence in localStorage
- Additional theme variants (high contrast, colorblind-friendly)
- CSS variables for theme colors
- Runtime theme switching animation
