import { useEffect, useMemo, useState } from "react";
import { Layout, Typography, Space, Segmented, Switch, Button } from "antd";
import { Routes, Route, useLocation, useNavigate } from "react-router-dom";
import { ConfigProvider, theme } from "antd";
import { MoonOutlined, SunOutlined } from "@ant-design/icons";
import { HomePage } from "./pages/Home";
import { JobDetailPage } from "./pages/JobDetail";
import { ObservePage } from "./pages/Observe";
import { WorkersPage } from "./pages/Workers";
import { AdminPage } from "./pages/Admin";
import { HydraLogo } from "./components/HydraLogo";
import { HeaderSettings } from "./components/HeaderSettings";
import { AuthPrompt } from "./components/AuthPrompt";
import { AUTH_REQUIRED_EVENT, hasAnyToken } from "./api/client";
import { WorkerDetailPage } from "./pages/WorkerDetail";
import { ActiveDomainProvider, useActiveDomain } from "./context/ActiveDomainContext";
import { ThemeProvider, useTheme } from "./theme";

const THEME_PREF_KEY = "hydra_theme_preference";
type ThemePreference = "system" | "light" | "dark";

function getSystemDarkMode(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function getInitialThemePreference(): ThemePreference {
  try {
    const pref = localStorage.getItem(THEME_PREF_KEY);
    if (pref === "light" || pref === "dark" || pref === "system") {
      return pref;
    }
    // Backward compatibility with older binary setting.
    const legacy = localStorage.getItem("hydra_theme");
    if (legacy === "light" || legacy === "dark") {
      return legacy;
    }
  } catch {
    // ignore storage errors
  }
  return "system";
}

function AppShell({ darkMode, setDarkMode }: { darkMode: boolean; setDarkMode: (dark: boolean) => void }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { domain: activeDomain } = useActiveDomain();
  const [authOpen, setAuthOpen] = useState(!hasAnyToken());
  const { colors } = useTheme();
  const { Header, Content } = Layout;

  useEffect(() => {
    setAuthOpen(!hasAnyToken());
  }, [activeDomain]);

  useEffect(() => {
    const onAuthRequired = () => setAuthOpen(true);
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
  }, []);
  const navItems = useMemo(
    () => {
      const items = [
        { value: "operate", label: "Operate", path: "/" },
        { value: "observe", label: "Observe", path: "/observe" },
        { value: "workers", label: "Workers", path: "/workers" },
      ];
      return items;
    },
    [],
  );
  const currentNav = useMemo(() => {
    if (location.pathname.startsWith("/observe")) return "observe";
    if (location.pathname.startsWith("/workers")) return "workers";
    if (location.pathname.startsWith("/admin")) return undefined;
    return "operate";
  }, [location.pathname]);

  if (authOpen) {
    return (
      <Layout style={{ minHeight: "100vh", background: colors.bgSecondary }}>
        <Content style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <AuthPrompt
            open
            onClose={() => {}}
            onSuccess={() => {
              setAuthOpen(!hasAnyToken());
            }}
          />
        </Content>
      </Layout>
    );
  }

  return (
    <ConfigProvider
      theme={{
        algorithm: darkMode ? theme.darkAlgorithm : theme.defaultAlgorithm,
      }}
    >
      <Layout>
        <Header
          style={{
            padding: "12px 18px",
            minHeight: 82,
            lineHeight: "normal",
            position: "sticky",
            top: 0,
            zIndex: 1000,
            width: "100%",
            background: darkMode
              ? "linear-gradient(115deg, #020617 0%, #0f172a 55%, #1e293b 100%)"
              : "linear-gradient(115deg, #ffffff 0%, #f8fbff 60%, #e7efff 100%)",
            borderBottom: `1px solid ${colors.border}`,
            boxShadow: darkMode
              ? "0 6px 24px rgba(2, 6, 23, 0.45)"
              : "0 6px 24px rgba(15, 23, 42, 0.08)",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: "14px",
            }}
          >
            <Space align="center" wrap>
              <HydraLogo size={40} color={colors.primary} />
              <Space size={12} align="baseline" style={{ flexWrap: "wrap" }}>
                <Typography.Title
                  level={3}
                  style={{
                    color: darkMode ? "#e2e8f0" : "#0f172a",
                    margin: 0,
                    fontSize: "clamp(16px, 4vw, 24px)",
                    letterSpacing: "0.2px",
                  }}
                >
                  Hydra Scheduler
                </Typography.Title>
                <Typography.Text
                  style={{
                    color: darkMode ? "#94a3b8" : "#334155",
                    fontSize: "clamp(12px, 2vw, 14px)",
                  }}
                  className="hide-on-mobile"
                >
                  Jobs, tasks, and insights at a glance
                </Typography.Text>
              </Space>
            </Space>
            <Space align="center" size={12} style={{ flexWrap: "wrap", justifyContent: "flex-end" }}>
              <Segmented
                className="header-nav-tabs"
                value={currentNav}
                options={navItems.map((item) => ({ label: item.label, value: item.value }))}
                onChange={(value) => {
                  const next = navItems.find((item) => item.value === value);
                  if (next) {
                    navigate(next.path);
                  }
                }}
              />
              <Switch
                checked={darkMode}
                onChange={(checked) => setDarkMode(checked)}
                checkedChildren={<MoonOutlined />}
                unCheckedChildren={<SunOutlined />}
                aria-label="Theme mode"
              />
              <Button
                type={location.pathname.startsWith("/admin") ? "primary" : "default"}
                onClick={() => navigate("/admin")}
              >
                Admin
              </Button>
              <HeaderSettings />
            </Space>
          </div>
        </Header>
        <Content
          style={{ 
            background: colors.bgSecondary,
            minHeight: "calc(100vh - 72px)"
          }}
          className="main-content"
        >
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/observe" element={<ObservePage />} />
            <Route path="/workers" element={<WorkersPage />} />
            <Route path="/workers/:workerId" element={<WorkerDetailPage />} />
            <Route
              path="/admin"
              element={<AdminPage />}
            />
            <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          </Routes>
        </Content>
      </Layout>
    </ConfigProvider>
  );
}

export default function App() {
  const [themePreference, setThemePreference] = useState<ThemePreference>(() => getInitialThemePreference());
  const [darkMode, setDarkMode] = useState<boolean>(() => {
    const pref = getInitialThemePreference();
    return pref === "system" ? getSystemDarkMode() : pref === "dark";
  });

  useEffect(() => {
    if (themePreference !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => setDarkMode(media.matches);
    apply();
    media.addEventListener?.("change", apply);
    return () => media.removeEventListener?.("change", apply);
  }, [themePreference]);

  useEffect(() => {
    if (themePreference === "system") {
      setDarkMode(getSystemDarkMode());
    } else {
      setDarkMode(themePreference === "dark");
    }
  }, [themePreference]);

  useEffect(() => {
    localStorage.setItem(THEME_PREF_KEY, themePreference);
    // Keep legacy key synchronized for older code paths.
    localStorage.setItem("hydra_theme", darkMode ? "dark" : "light");
  }, [darkMode, themePreference]);

  useEffect(() => {
    document.documentElement.setAttribute("data-hydra-theme", darkMode ? "dark" : "light");
  }, [darkMode]);
  
  return (
    <ActiveDomainProvider>
      <ThemeProvider isDarkMode={darkMode}>
        <AppShellWrapper
          darkMode={darkMode}
          setDarkMode={(dark) => {
            setThemePreference(dark ? "dark" : "light");
            setDarkMode(dark);
          }}
        />
      </ThemeProvider>
    </ActiveDomainProvider>
  );
}

function AppShellWrapper({ darkMode, setDarkMode }: { darkMode: boolean; setDarkMode: (dark: boolean) => void }) {
  return <AppShell darkMode={darkMode} setDarkMode={setDarkMode} />;
}
